# Smart Shopper Project Architecture Guide

This document explains the full Smart Shopper project: architecture, components, technologies, memory, data flow, how to run it, how to test it, and how to deploy it.

## 1. Project Summary

Smart Shopper is an AI shopping assistant for Moroccan marketplace search.

A user sends a natural message in Darija, French, English, or mixed language. The system extracts product intent and constraints, searches marketplace providers, ranks offers, generates a response, and can monitor future price drops.

Example request:

```text
bghit samsung phone black f casablanca b 3000dh
```

Expected understanding:

```text
brand=Samsung
product=phone
color=black
city=casablanca
budget=3000 MAD
intent=search
```

## 2. High-Level Architecture

Smart Shopper is a decentralized, event-driven, multi-agent system. Services communicate through Kafka topics instead of direct service-to-service calls, except for the Orchestrator calling the NER model service through gRPC.

```text
Telegram / Frontend
-> User Proxy Gateway
-> Kafka msg.inbound
-> Orchestrator
-> NER gRPC service
-> Kafka scrape.task.assigned
-> WebScraping Agent
-> Kafka scrape.raw
-> Decision Agent
-> Kafka decision.ranked
-> Agent Generator
-> Kafka response.outbound
-> Telegram / Frontend
```

Background and governance flows:

```text
Orchestrator
-> Kafka ambient.watch
-> Ambient Scheduler
-> Kafka scrape.task.assigned

All important Kafka topics
-> Governance Agent
-> gov.audit / gov.violation
```

## 3. Main Components

### Gateway

Path:

```text
gateway/telegram_proxy.py
```

Responsibilities:

- Receive Telegram messages.
- Convert messages into `InboundMessage`.
- Publish to `msg.inbound`.
- Consume `response.outbound`.
- Send responses back to Telegram.
- Record user history in per-user memory.

Important technology:

- `python-telegram-bot`
- Kafka producer/consumer
- MongoDB user history

### Orchestrator

Paths:

```text
agents/orchestrator/agent.py
agents/orchestrator/service.py
agents/orchestrator/tools/ner_client.py
agents/orchestrator/tools/task_router.py
agents/orchestrator/tools/cache_lookup.py
```

Responsibilities:

- Consume `msg.inbound`.
- Call the NER service.
- Publish `ner.extracted`.
- Convert entities into `ProductQuery`.
- Apply user memory preferences when fields are missing.
- Check Redis cache.
- Publish `scrape.task.assigned`.
- Publish `ambient.watch` when the user asks for monitoring.

Important technology:

- Kafka
- Redis
- gRPC client
- Pydantic contracts

### NER Model Service

Paths:

```text
models/ner/serve.py
models/ner/grpc_server.py
proto/ner.proto
generated/ner/v1/
```

Responsibilities:

- Preprocess noisy Darija/French/English text.
- Remove accents.
- Normalize misspellings.
- Run Hugging Face token classification.
- Normalize labels into shared entity types.
- Add context enrichment.
- Filter weak hallucinated predictions.
- Return final entities to the Orchestrator.

Model:

```text
ElAtrachAMINE/darija-ner-xlmroberta
```

Important libraries:

- `transformers`
- `torch`
- `safetensors`
- `rapidfuzz`
- `grpcio`
- `protobuf`

### WebScraping Agent

Paths:

```text
agents/webscraping/agent.py
agents/webscraping/spiders/
agents/webscraping/tools/
```

Responsibilities:

- Consume `scrape.task.assigned`.
- Run marketplace-specific scrapers.
- Normalize listings into `RawProduct`.
- Publish `scrape.raw`.
- Fall back to deterministic mock products if providers fail or return no data.

Registered providers:

```text
jumia
avito
electrosalam
mafiawaystore
moteur
mymarket
ultrapc
electroplanet
defacto
biougnach
marjane
decathlon
mubawab
ikea
```

Important technology:

- `httpx`
- `beautifulsoup4`
- `playwright`
- optional `scrapy`

### Decision Agent

Paths:

```text
agents/decision/agent.py
agents/decision/service.py
agents/decision/tools/scoring_engine.py
agents/decision/tools/dedup_engine.py
agents/decision/tools/fraud_detector.py
```

Responsibilities:

- Consume `scrape.raw`.
- Batch products per request.
- Deduplicate listings.
- Detect fraud/risk signals.
- Score products using the 100-point scoring system.
- Publish `decision.ranked`.

Scoring:

```text
Price:        40 points
Trust:        30 points
Quality:      20 points
Availability: 10 points
Total:       100 points
```

### Agent Generator

Paths:

```text
agents/agent_generator/agent.py
agents/agent_generator/tools/llm_client.py
agents/agent_generator/tools/behavior_analyzer.py
```

Responsibilities:

- Consume `decision.ranked`.
- Build a final user response.
- Use template fallback by default.
- Optionally call Gemini/Groq-style HTTP LLM providers.
- Use private behavioral memory for tone and language context.
- Publish `response.outbound`.
- Write successful final responses into global Redis cache.

Important technology:

- `httpx`
- LLM HTTP provider
- MongoDB private behavioral memory
- Redis global response cache

### Ambient Scheduler

Path:

```text
agents/ambient_scheduler/scheduler.py
```

Responsibilities:

- Consume `ambient.watch`.
- Persist watch state in MongoDB.
- Store watch metadata in per-user memory.
- Re-emit `scrape.task.assigned` when a watch is due.

Purpose:

This enables future background monitoring for price drops or better offers.

### Governance Agent

Paths:

```text
agents/governance/agent.py
agents/governance/rules/pii_scanner.py
agents/governance/rules/rate_limiter.py
agents/governance/rules/robots_checker.py
```

Responsibilities:

- Audit important Kafka events.
- Detect sensitive data.
- Mask PII in audit payloads.
- Publish `gov.audit`.
- Publish `gov.violation`.
- Provide rate-limit and robots.txt rule helpers.

Purpose:

Governance protects privacy and makes scraping behavior auditable.

## 4. Three-Tier Memory Architecture

### Tier 1: Global Shared Memory

Implementation:

```text
shared/memory/global_memory.py
```

Backing store:

```text
Redis
```

Stores:

- Product-query response cache.
- Price history.
- Site health.
- Robots.txt snapshots.

Used by:

- Orchestrator cache lookup.
- Agent Generator response cache write.
- Future scraper/governance site health flows.

### Tier 2: Per-User Shared Memory

Implementation:

```text
shared/memory/user_memory.py
```

Backing stores:

```text
MongoDB
Redis hot profile cache
```

Stores:

- User profile.
- Preferred city.
- Preferred budget.
- Preferred currency.
- Preferred sites.
- Search history.
- Response history.
- Watch metadata.

Used by:

- Gateway.
- Orchestrator.
- Ambient Scheduler.

### Tier 3: Private Behavioral Memory

Implementation:

```text
shared/memory/behavioral_memory.py
```

Backing store:

```text
MongoDB
```

Stores:

- Tone preference.
- Language preference.
- Preferred sources.
- Response count.
- Generator interactions.

Used by:

- Agent Generator only.

Purpose:

This memory is private so behavioral personalization does not leak into scraping, ranking, or governance decisions.

## 5. Kafka Topics

```text
msg.inbound
ner.extracted
scrape.task.assigned
scrape.raw
decision.ranked
response.outbound
ambient.watch
ambient.tick
price.history
cache.write
gov.audit
gov.violation
error.dead_letter
```

Topic constants:

```text
shared/events/topics.py
```

Schemas:

```text
shared/events/schemas.py
```

## 6. Main Technologies

Language:

- Python 3.11+

Data contracts:

- Pydantic

Event bus:

- Apache Kafka
- `aiokafka`

Cache and hot memory:

- Redis
- `redis[hiredis]`

Persistent storage:

- MongoDB
- `pymongo`

NER:

- Hugging Face Transformers
- XLM-RoBERTa
- Torch
- Safetensors
- RapidFuzz
- gRPC / Protobuf

Scraping:

- Playwright
- HTTPX
- BeautifulSoup
- Optional Scrapy

Gateway:

- Telegram Bot API
- `python-telegram-bot`

Observability:

- Prometheus
- Grafana
- OpenTelemetry
- Jaeger

Deployment:

- Docker
- Docker Compose
- Kubernetes
- AWS EKS
- AWS MSK or Strimzi Kafka
- AWS ElastiCache Redis
- MongoDB Atlas or validated compatible MongoDB service
- AWS ECR
- AWS Secrets Manager / External Secrets Operator

## 7. Local Environment Setup

Create `.env`:

```powershell
copy .env.example .env
```

Install dependencies:

```powershell
python -m pip install -e ".[dev]"
python -m playwright install chromium
```

Alternative:

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Important variables:

```env
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
REDIS_URL=redis://localhost:6379/0
MONGO_URI=mongodb://localhost:27017
MONGO_DB=smart_shopper
NER_GRPC_HOST=localhost
NER_GRPC_PORT=50051
SMART_SHOPPER_NER_BACKEND=auto
SMART_SHOPPER_NER_MODEL=ElAtrachAMINE/darija-ner-xlmroberta
TELEGRAM_BOT_TOKEN=
LLM_PROVIDER=template
```

Never commit real `.env` files or tokens.

## 8. How To Run Locally Without Kafka

Use the local in-process pipeline:

```powershell
python -m scripts.run_local_pipeline
```

This checks:

```text
InboundMessage
-> Orchestrator + NER
-> Mock scraper products
-> Decision ranking
-> Agent Generator response
```

Use this first because it is faster than running Kafka and Docker.

## 9. How To Run With Local Infrastructure

Start infrastructure:

```powershell
docker compose up -d kafka redis mongodb
```

Run services in separate terminals:

```powershell
python -m models.ner.grpc_server
python -m agents.orchestrator.service
python -m agents.webscraping.agent
python -m agents.decision.service
python -m agents.agent_generator.agent
python -m agents.ambient_scheduler.scheduler
python -m agents.governance.agent
python -m gateway.telegram_proxy
```

The gateway requires:

```env
TELEGRAM_BOT_TOKEN=your_real_token
```

## 10. How To Run Production-Like With Docker Compose

Build and run all services:

```powershell
docker compose -f docker-compose.full.yml up --build
```

Run a Kafka smoke test:

```powershell
python -m scripts.smoke_kafka_flow
```

The smoke test publishes one `msg.inbound` event and waits for the matching `response.outbound`.

## 11. How To Test

Install dev dependencies:

```powershell
python -m pip install -e ".[dev]"
```

Run all unit tests:

```powershell
python -m pytest tests\unit -q
```

Run focused tests:

```powershell
python -m pytest tests\unit\test_ner_and_orchestrator.py -q
python -m pytest tests\unit\test_memory_tiers.py -q
python -m pytest tests\unit\test_deployment_readiness.py -q
```

Test NER directly:

```powershell
python -c "from models.ner.serve import extract_entities; print([e.model_dump() for e in extract_entities('bghit hp omen f fes b 6000dh')])"
```

Test local pipeline:

```powershell
python -m scripts.run_local_pipeline
```

Test full Kafka flow:

```powershell
python -m scripts.smoke_kafka_flow
```

## 12. How To Deploy

### Build Images

```powershell
docker build -f docker/Dockerfile.service -t smart-shopper/service:dev .
docker build -f docker/Dockerfile.ner -t smart-shopper/ner:dev .
```

### Push To AWS ECR

Typical steps:

```powershell
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
docker tag smart-shopper/service:dev <account>.dkr.ecr.<region>.amazonaws.com/smart-shopper/service:dev
docker tag smart-shopper/ner:dev <account>.dkr.ecr.<region>.amazonaws.com/smart-shopper/ner:dev
docker push <account>.dkr.ecr.<region>.amazonaws.com/smart-shopper/service:dev
docker push <account>.dkr.ecr.<region>.amazonaws.com/smart-shopper/ner:dev
```

### Configure Kubernetes Secrets

Create a real secret from your production values. Do not apply `secrets.example.yaml` unchanged.

Required values:

```text
KAFKA_BOOTSTRAP_SERVERS
REDIS_URL
MONGO_URI
MONGO_DB
TELEGRAM_BOT_TOKEN
LLM_HTTP_BASE_URL
LLM_API_KEY
OTEL_EXPORTER_OTLP_ENDPOINT
```

### Apply Kubernetes Manifests

Render base:

```powershell
kubectl kustomize deploy/k8s/base
```

Apply an environment:

```powershell
kubectl apply -k deploy/k8s/overlays/dev
kubectl apply -k deploy/k8s/overlays/staging
kubectl apply -k deploy/k8s/overlays/prod
```

Check rollout:

```powershell
kubectl get pods -n smart-shopper
kubectl rollout status deploy/smart-shopper-orchestrator -n smart-shopper
```

## 13. Observability

Every long-running service exposes:

```text
/healthz
/readyz
/metrics
```

Monitoring files:

```text
monitoring/prometheus.yml
monitoring/alerts.yml
monitoring/grafana-dashboard.json
```

Important alerts:

- Service down.
- High error rate.
- No outbound responses.

Useful commands:

```powershell
kubectl logs deploy/smart-shopper-orchestrator -n smart-shopper
kubectl logs deploy/smart-shopper-scraper -n smart-shopper
kubectl logs deploy/smart-shopper-generator -n smart-shopper
```

## 14. CI/CD

Workflow:

```text
.github/workflows/ci.yml
```

CI checks:

- Install project.
- Run unit tests.
- Render Kubernetes manifests.
- Build service Docker image.
- Build NER Docker image.

## 15. Repository Structure

```text
agents/
  orchestrator/
  webscraping/
  decision/
  agent_generator/
  ambient_scheduler/
  governance/

gateway/
  telegram_proxy.py

models/
  ner/

shared/
  config/
  events/
  memory/
  runtime/

generated/
  ner/

proto/
  ner.proto

scripts/
  run_local_pipeline.py
  smoke_kafka_flow.py

docker/
  Dockerfile.service
  Dockerfile.ner
  Dockerfile.python.base

deploy/
  k8s/

monitoring/

docs/

tests/
```

## 16. Known Risks And Required Verification

The project is deployment-prepared, but it must be proven by running checks.

Must pass before calling it ready:

```powershell
python -m pytest tests\unit -q
python -m scripts.run_local_pipeline
docker compose -f docker-compose.full.yml up --build
python -m scripts.smoke_kafka_flow
kubectl kustomize deploy/k8s/base
```

Known risks:

- NER image is large because of the Hugging Face model.
- Some providers may change website HTML and break parsing.
- Live scraping needs robots/rate-limit policy validation.
- Telegram gateway requires a valid token.
- Kubernetes secrets must be created with real production values.
- Full AWS runtime has not been proven until EKS/MSK/Redis/Mongo are connected and smoke-tested.

## 17. Recommended Work Order For New Developers

1. Read `README.md`.
2. Read this file.
3. Install the project with `python -m pip install -e ".[dev]"`.
4. Run unit tests.
5. Run `python -m scripts.run_local_pipeline`.
6. Start local infra with Docker Compose.
7. Run the full services.
8. Run `python -m scripts.smoke_kafka_flow`.
9. Only then start AWS/Kubernetes deployment work.
