# Smart Shopper Runbook

## Health Checks

Every long-running service exposes:

- `/healthz`: process is alive.
- `/readyz`: process is ready.
- `/metrics`: Prometheus text metrics.

## Common Incidents

### No Telegram Responses

1. Check gateway logs.
2. Confirm `TELEGRAM_BOT_TOKEN` exists.
3. Run `python -m scripts.smoke_kafka_flow`.
4. Check Kafka topics in order: `msg.inbound`, `scrape.task.assigned`, `scrape.raw`, `decision.ranked`, `response.outbound`.

### NER Service Fails To Start

1. Check model cache volume or NER image build logs.
2. Verify `SMART_SHOPPER_NER_MODEL`.
3. Confirm `grpcio` runtime is compatible with generated bindings.

### Scrapers Return Empty Results

1. Check provider-specific logs.
2. Check governance violations for robots/rate-limit blocks.
3. Verify Playwright browser installation in the service image.
4. Fall back to fixture parser tests before changing selectors.

### High Kafka Lag

1. Scale scraper and generator deployments.
2. Inspect provider latency and LLM latency.
3. Check Redis/Mongo latency.

### Cache Not Working

1. Check Redis connectivity.
2. Confirm `DecisionRanked.query` is present.
3. Confirm Agent Generator can write to Redis after producing `response.outbound`.

## Operational Commands

```powershell
kubectl get pods -n smart-shopper
kubectl logs deploy/smart-shopper-orchestrator -n smart-shopper
kubectl rollout restart deploy/smart-shopper-scraper -n smart-shopper
kubectl rollout status deploy/smart-shopper-generator -n smart-shopper
```
