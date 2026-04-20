# Predictive LLM Kubernetes Scaler

Проєкт реалізує гібридний підхід до предиктивного масштабування (predictive autoscaling) у фізичних гетерогенних Kubernetes кластерах з обмеженими ресурсами
та використанням методів машинного навчання (ML) та великих мовних моделей (LLM) 
на основі підходів Nawaz Dhandala[1] та Shafin Hasnat[2].
 
1. https://oneuptime.com/blog/post/2026-02-09-predictive-autoscaling-ml-models/view 
2. https://shafinhasnat97.medium.com/ipa-building-ai-driven-kubernetes-autoscaler-54bfb17ac61e

## Основні компоненти

- WireMock - HTTP-сервіс, що використовується як цільовий застосунок для оцінки роботи механізму масштабування
- Prometheus - система збору та зберігання метрик
- Predictive LLM Scaler - агент прогнозного масштабування Kubernetes, що поєднує ML-прогнозування та LLM-аналіз з можливістю корегування при зміні LLM моделі на більш потужну
- Ollama + llama2:7b - зовнішній LLM-компонент

## Структура репозиторію

- `app/` - Dockerfile та Python-код scaler
- `k8s/` - Kubernetes YAML-маніфести

## Особливості

- Для прогнозування CPU-навантаження використовується `Prophet`
- LLM виконує проміжний аналітичний етап та архітектура передбачає заміну моделі на більш потужну для виконання корегування рішення на основі більшого контексту для корекції прогнозу ML
- Локальний стенд працює у Kubernetes-кластері
- Ollama виконується поза кластером і доступна через HTTP API
- Конфігурація scaler винесена у `ConfigMap`

## Конфігурація

Налаштування scaler зберігаються у файлі:

- `k8s/scaler-configmap.yaml`

Перед запуском потрібно замінити значення на актуальні адреси сервісів Prometheus та Ollama:

- `CHANGE_ME_PROMETHEUS`
- `CHANGE_ME_OLLAMA`

## Розгортання (локальний стенд)

```bash
kubectl apply -f k8s/scaler-configmap.yaml
kubectl apply -f k8s/wiremock.yaml
kubectl apply -f k8s/predictive-llm-scaler.yaml

## Примітка

У репозиторії не зберігаються реальні IP-адреси лабораторного стенду. Для цього використовуються шаблонні значення у `ConfigMap`.
