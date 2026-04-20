FROM python:3.11-slim

WORKDIR /app

# Системні залежності для prophet + стабільність
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libstdc++6 \
    gcc \
    g++ \
    make \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Оновлюємо pip
RUN pip install --no-cache-dir --upgrade pip

# Python залежності
RUN pip install --no-cache-dir \
    kubernetes \
    requests \
    prometheus-api-client \
    prophet \
    pandas \
    numpy \
    pytz \
    python-dateutil \
    prometheus_client \
    plotly

# Копіюємо код
COPY predictive_scaler.py /app/

# Опціонально: non-root user (краще для Kubernetes)
RUN useradd -m appuser
USER appuser

# Запуск
CMD ["python", "predictive_scaler.py"]
