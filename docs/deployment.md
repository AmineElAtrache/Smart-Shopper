# Smart Shopper Deployment Guide

## Deployment Targets

The production target is AWS EKS with managed backing services:

- EKS for Python services and scraper workers.
- MSK or Strimzi Kafka for the event bus.
- ElastiCache Redis for cache, rate limits, robots cache, and hot memory.
- MongoDB Atlas or a validated DocumentDB-compatible deployment for user history, watches, and price history.
- ECR for `smart-shopper/service` and `smart-shopper/ner` images.
- AWS Secrets Manager plus External Secrets Operator for Telegram and LLM credentials.

## Build Images

```powershell
docker build -f docker/Dockerfile.service -t smart-shopper/service:dev .
docker build -f docker/Dockerfile.ner -t smart-shopper/ner:dev .
```

For AWS, tag and push both images to ECR.

## Local Production-Like Smoke

```powershell
copy .env.example .env
docker compose -f docker-compose.full.yml up --build
```

Then publish a synthetic request:

```powershell
python -m scripts.smoke_kafka_flow
```

## Kubernetes Apply

Create the real secret first. Do not apply `secrets.example.yaml` unchanged.

```powershell
kubectl apply -k deploy/k8s/base
```

Use overlays for environment-specific image tags:

```powershell
kubectl apply -k deploy/k8s/overlays/dev
kubectl apply -k deploy/k8s/overlays/staging
kubectl apply -k deploy/k8s/overlays/prod
```

## Required Secrets

- `KAFKA_BOOTSTRAP_SERVERS`
- `REDIS_URL`
- `MONGO_URI`
- `MONGO_DB`
- `TELEGRAM_BOT_TOKEN`
- `LLM_HTTP_BASE_URL`
- `LLM_API_KEY`
- `OTEL_EXPORTER_OTLP_ENDPOINT`

## Rollback

Use the previous image tag in the relevant overlay, then re-apply the overlay:

```powershell
kubectl apply -k deploy/k8s/overlays/prod
kubectl rollout status deploy/smart-shopper-orchestrator -n smart-shopper
```
