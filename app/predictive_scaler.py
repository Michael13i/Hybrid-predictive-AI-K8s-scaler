# predictive_scaler.py
import datetime
import json
import logging
import math
import os
import time

import pandas as pd
import pytz
import requests
from kubernetes import client, config
from prometheus_api_client import PrometheusConnect
from prometheus_client import Gauge, start_http_server
from prophet import Prophet


KYIV_TZ = pytz.timezone("Europe/Kyiv")


class KyivFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.datetime.fromtimestamp(record.created, KYIV_TZ)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%d %H:%M:%S")


handler = logging.StreamHandler()
handler.setFormatter(
    KyivFormatter("%(asctime)s - %(levelname)s - %(message)s")
)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.handlers.clear()
root_logger.addHandler(handler)


def now():
    return datetime.datetime.now(KYIV_TZ)


config.load_incluster_config()
apps_v1 = client.AppsV1Api()

PROM_URL = os.getenv("PROMETHEUS_URL", "http://CHANGE_ME_PROMETHEUS:80")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://CHANGE_ME_OLLAMA:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama2:7b")

TARGET_DEPLOYMENT = os.getenv("TARGET_DEPLOYMENT", "wiremock")
TARGET_NAMESPACE = os.getenv("TARGET_NAMESPACE", "default")

MIN_REPLICAS = int(os.getenv("MIN_REPLICAS", "1"))
MAX_REPLICAS = int(os.getenv("MAX_REPLICAS", "6"))
COOLDOWN_SEC = int(os.getenv("COOLDOWN_SEC", "300"))
TARGET_CPU_PER_POD = float(os.getenv("TARGET_CPU_PER_POD", "0.1"))
SAFETY_MARGIN = float(os.getenv("SAFETY_MARGIN", "1.2"))
SLEEP_SEC = int(os.getenv("SLEEP_SEC", "300"))
FORECAST_DAYS = int(os.getenv("FORECAST_DAYS", "2"))

last_scale_time = now() - datetime.timedelta(seconds=COOLDOWN_SEC)

prom = PrometheusConnect(url=PROM_URL, disable_ssl=True)

prediction_error_gauge = Gauge(
    "predictive_scaler_error_percent",
    "MAPE прогнозу CPU (%)"
)
current_replicas_gauge = Gauge(
    "predictive_scaler_current_replicas",
    "Поточна кількість реплік"
)
predicted_replicas_gauge = Gauge(
    "predictive_scaler_predicted_replicas",
    "Прогнозована кількість реплік"
)
predicted_peak_cpu_gauge = Gauge(
    "predictive_scaler_predicted_peak_cpu",
    "Прогнозований peak CPU на наступну годину"
)
current_cpu_gauge = Gauge(
    "predictive_scaler_current_cpu_cores",
    "Поточне середнє CPU навантаження deployment в cores"
)

predictions_log = []


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def query_scalar(query: str, default=0.0):
    try:
        result = prom.custom_query(query=query)
        if not result:
            return default

        value = result[0].get("value")
        if not value or len(value) < 2:
            return default

        return float(value[1])
    except Exception as e:
        logging.error("Prometheus query failed: %s | query=%s", e, query)
        return default


def deployment_avg_cpu_query():
    return (
        f'avg(rate(container_cpu_usage_seconds_total{{'
        f'namespace="{TARGET_NAMESPACE}", pod=~"{TARGET_DEPLOYMENT}-.*"'
        f'}}[5m]))'
    )


class PredictiveScaler:
    def __init__(self):
        self.prom = prom

    def fetch_historical_data(self, days=2):
        end_time = now().replace(tzinfo=None)
        start_time = end_time - datetime.timedelta(days=days)

        query = deployment_avg_cpu_query()

        result = self.prom.custom_query_range(
            query=query,
            start_time=start_time,
            end_time=end_time,
            step="5m"
        )

        if not result:
            raise ValueError("Prometheus returned no historical data")

        values_block = result[0].get("values", [])
        if not values_block:
            raise ValueError("Prometheus returned empty values list")

        timestamps = []
        values = []

        for item in values_block:
            timestamps.append(datetime.datetime.fromtimestamp(float(item[0])))
            values.append(max(0.0, safe_float(item[1], 0.0)))

        df = pd.DataFrame({
            "ds": timestamps,
            "y": values
        }).dropna()

        if df.empty:
            raise ValueError("Historical dataframe is empty after cleanup")

        return df

    def train_forecast_model(self, df):
        model = Prophet(
            daily_seasonality=True,
            weekly_seasonality=True,
            yearly_seasonality=False,
            changepoint_prior_scale=0.05
        )
        model.fit(df)
        return model

    def predict_next_hour(self, model):
        future = model.make_future_dataframe(periods=12, freq="5min")
        forecast = model.predict(future)
        next_hour = forecast.tail(12)
        return next_hour[["ds", "yhat", "yhat_lower", "yhat_upper"]]

    def calculate_required_replicas(self, predicted_cpu):
        predicted_cpu = max(0.0, safe_float(predicted_cpu, 0.0))

        required_replicas = math.ceil(
            (predicted_cpu / TARGET_CPU_PER_POD) * SAFETY_MARGIN
        )

        return max(MIN_REPLICAS, min(required_replicas, MAX_REPLICAS))

    def scale_deployment(self, replicas):
        try:
            apps_v1.read_namespaced_deployment(
                name=TARGET_DEPLOYMENT,
                namespace=TARGET_NAMESPACE
            )

            body = {
                "spec": {
                    "replicas": replicas
                }
            }

            apps_v1.patch_namespaced_deployment(
                name=TARGET_DEPLOYMENT,
                namespace=TARGET_NAMESPACE,
                body=body
            )

            logging.info(
                "Scaled deployment %s/%s to %s replicas",
                TARGET_NAMESPACE,
                TARGET_DEPLOYMENT,
                replicas
            )
            return True
        except Exception as e:
            logging.error(
                "Failed to scale deployment %s/%s: %s",
                TARGET_NAMESPACE,
                TARGET_DEPLOYMENT,
                e
            )
            return False


def get_current_replicas():
    try:
        dep = apps_v1.read_namespaced_deployment(
            TARGET_DEPLOYMENT,
            TARGET_NAMESPACE
        )
        return dep.spec.replicas or 1
    except Exception as e:
        logging.error(
            "Failed to get replicas for %s/%s: %s",
            TARGET_NAMESPACE,
            TARGET_DEPLOYMENT,
            e
        )
        return 1


def get_current_metrics():
    cpu_query = deployment_avg_cpu_query()
    pods_query = (
        f'count(kube_pod_info{{'
        f'namespace="{TARGET_NAMESPACE}", pod=~"{TARGET_DEPLOYMENT}-.*"'
        f'}})'
    )

    cpu = max(0.0, query_scalar(cpu_query, 0.0))
    pods = int(query_scalar(pods_query, 0.0))

    return {
        "cpu_cores": round(cpu, 4),
        "active_pods": pods
    }


def get_forecast():
    scaler = PredictiveScaler()
    df = scaler.fetch_historical_data(days=FORECAST_DAYS)
    model = scaler.train_forecast_model(df)
    predictions = scaler.predict_next_hour(model)

    peak_cpu = max(0.0, safe_float(predictions["yhat_upper"].max(), 0.0))
    avg_cpu = max(0.0, safe_float(predictions["yhat"].mean(), 0.0))
    current_cpu = max(0.0, safe_float(df["y"].iloc[-1], 0.0))

    if avg_cpu > current_cpu + 0.05:
        trend = "up"
    elif avg_cpu < current_cpu - 0.05:
        trend = "down"
    else:
        trend = "steady"

    return {
        "peak_cpu_next_hour": round(peak_cpu, 4),
        "avg_cpu_next_hour": round(avg_cpu, 4),
        "current_cpu_baseline": round(current_cpu, 4),
        "trend": trend
    }


def calculate_replicas(predicted_cpu):
    scaler = PredictiveScaler()
    return scaler.calculate_required_replicas(predicted_cpu)


def apply_scale(target_replicas):
    global last_scale_time

    target = max(MIN_REPLICAS, min(MAX_REPLICAS, int(target_replicas)))
    seconds_since_last_scale = (
        now() - last_scale_time
    ).total_seconds()

    if seconds_since_last_scale < COOLDOWN_SEC:
        logging.info(
            "Cooldown active. %.0f sec left",
            COOLDOWN_SEC - seconds_since_last_scale
        )
        return False

    scaler = PredictiveScaler()
    ok = scaler.scale_deployment(target)
    if ok:
        last_scale_time = now()
    return ok


def calculate_prediction_error(predicted, actual):
    predicted = safe_float(predicted, 0.0)
    actual = safe_float(actual, 0.0)

    if actual == 0:
        return 0.0

    return abs((predicted - actual) / actual) * 100.0


def compute_relation_and_decision(recommended, current_replicas):
    if recommended > current_replicas:
        relation = "greater"
        decision = "scale_up"
    elif recommended < current_replicas:
        relation = "less"
        decision = "scale_down"
    else:
        relation = "equal"
        decision = "no_action"
    return relation, decision


def make_llm_decision(metrics, forecast, recommended, current_replicas):
    relation, decision = compute_relation_and_decision(
        recommended,
        current_replicas
    )

    prompt = f"""
You are an analytical AI agent for proactive Kubernetes autoscaling.

Important rules:
- Do NOT change recommended_replicas.
- Do NOT change relation.
- Do NOT change decision.
- target_replicas must always equal recommended_replicas.
- Your task is to classify the situation and provide a grounded explanation.

Fixed values:
recommended_replicas = {recommended}
current_replicas = {current_replicas}
relation = {relation}
decision = {decision}
target_replicas = {recommended}

Current metrics:
{json.dumps(metrics, ensure_ascii=False)}

Forecast:
{json.dumps(forecast, ensure_ascii=False)}

Classify the situation into exactly one of:
- stable_growth
- short_spike_risk
- low_steady_load
- forecast_uncertainty

Guidance:
- stable_growth: use when load is consistently increasing
- short_spike_risk: use when predicted peak is much higher than average load
- low_steady_load: use when baseline and forecast are both low/stable
- forecast_uncertainty: use when signals are contradictory or unstable

Return ONLY valid JSON:
{{
  "relation": "{relation}",
  "decision": "{decision}",
  "target_replicas": {recommended},
  "situation_type": "stable_growth|short_spike_risk|low_steady_load|forecast_uncertainty",
  "reason": "recommended={recommended} is justified by <main signal> and <secondary signal>"
}}
""".strip()

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.0,
                    "num_predict": 120,
                    "repeat_penalty": 1.1
                }
            },
            timeout=600
        )
        resp.raise_for_status()

        response_json = resp.json()
        full_text = response_json.get("response", "").strip()
        logging.info("Ollama raw response: %s", full_text)

        start = full_text.find("{")
        end = full_text.rfind("}") + 1
        if start == -1 or end <= start:
            raise ValueError("No valid JSON object found in Ollama response")

        json_str = full_text[start:end]
        llm_data = json.loads(json_str)

        situation_type = str(llm_data.get("situation_type", "forecast_uncertainty"))
        reason = str(llm_data.get("reason", "")).strip()

        if situation_type not in {
            "stable_growth",
            "short_spike_risk",
            "low_steady_load",
            "forecast_uncertainty"
        }:
            situation_type = "forecast_uncertainty"

        if not reason:
            reason = (
                f"recommended={recommended} is justified by "
                f"trend={forecast.get('trend', 'steady')} and "
                f"peak_cpu_next_hour={forecast.get('peak_cpu_next_hour', 0.0)}"
            )

        parsed = {
            "decision": decision,
            "target_replicas": recommended,
            "reason": reason,
            "relation": relation,
            "situation_type": situation_type
        }

        logging.info("Parsed decision: %s", parsed)
        return parsed

    except Exception as e:
        logging.error("LLM decision error: %s", e)
        return {
            "decision": decision,
            "target_replicas": recommended,
            "reason": (
                f"recommended={recommended} is justified by "
                f"trend={forecast.get('trend', 'steady')} and "
                f"peak_cpu_next_hour={forecast.get('peak_cpu_next_hour', 0.0)}; "
                f"fallback={e}"
            ),
            "relation": relation,
            "situation_type": "forecast_uncertainty"
        }


def update_prediction_log_with_actual():
    if not predictions_log:
        return

    latest = predictions_log[-1]
    if latest["actual"] is not None:
        return

    age_sec = (now() - latest["timestamp"]).total_seconds()
    if age_sec < 1800:
        return

    actual_cpu = get_current_metrics()["cpu_cores"]
    latest["actual"] = actual_cpu

    error = calculate_prediction_error(latest["predicted"], actual_cpu)
    prediction_error_gauge.set(error)
    logging.info("Prediction error (MAPE): %.2f%%", error)


def check_target_deployment_exists():
    try:
        apps_v1.read_namespaced_deployment(
            name=TARGET_DEPLOYMENT,
            namespace=TARGET_NAMESPACE
        )
        logging.info(
            "Target deployment found: %s/%s",
            TARGET_NAMESPACE,
            TARGET_DEPLOYMENT
        )
        return True
    except Exception as e:
        logging.error(
            "Target deployment %s/%s not found: %s",
            TARGET_NAMESPACE,
            TARGET_DEPLOYMENT,
            e
        )
        return False


def run_scaling_loop():
    if not check_target_deployment_exists():
        logging.error("Scaling loop stopped because target deployment does not exist")
        return

    while True:
        try:
            logging.info("Starting scaling cycle...")

            metrics = get_current_metrics()
            current_replicas = get_current_replicas()

            forecast = get_forecast()
            peak_cpu = forecast["peak_cpu_next_hour"]

            recommended = calculate_replicas(peak_cpu)

            predictions_log.append({
                "timestamp": now(),
                "predicted": peak_cpu,
                "actual": None
            })

            logging.info("Current metrics: %s", metrics)
            logging.info("Forecast: %s", forecast)
            logging.info("Recommended replicas: %s", recommended)
            logging.info("Current replicas: %s", current_replicas)

            decision_data = make_llm_decision(
                metrics=metrics,
                forecast=forecast,
                recommended=recommended,
                current_replicas=current_replicas
            )

            decision = decision_data.get("decision", "no_action")
            target = int(decision_data.get("target_replicas", current_replicas))
            reason = decision_data.get("reason", "No reason")
            relation = decision_data.get("relation", "")
            situation_type = decision_data.get(
                "situation_type",
                "forecast_uncertainty"
            )

            logging.info(
                "Decision=%s, target=%s, current=%s, relation=%s, situation_type=%s, reason=%s",
                decision,
                target,
                current_replicas,
                relation,
                situation_type,
                reason
            )

            if decision in ("scale_up", "scale_down") and target != current_replicas:
                apply_scale(target)
            else:
                logging.info("No scaling action applied")

            current_replicas_gauge.set(current_replicas)
            predicted_replicas_gauge.set(target)
            predicted_peak_cpu_gauge.set(peak_cpu)
            current_cpu_gauge.set(metrics["cpu_cores"])

            update_prediction_log_with_actual()

        except Exception as e:
            logging.error("Cycle error: %s", e)

        time.sleep(SLEEP_SEC)


if __name__ == "__main__":
    start_http_server(8000)
    logging.info("Prometheus metrics server started on port 8000")
    run_scaling_loop()
