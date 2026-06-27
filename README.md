# Smart Shopper

Smart Shopper is a multi-agent shopping assistant for Morocco. A user sends a natural message in Darija, French, English, or mixed language through Telegram. The system understands the request, searches Moroccan marketplaces in parallel, ranks the best offers, and replies with a personalized recommendation.

Built as a **PFA (Final Year Project)** — event-driven, scalable, and designed for production deployment on AWS EKS.

---

## What It Does

| Step | What happens |
|------|----------------|
| 1. **Understand** | NER extracts product, brand, budget, color, city, and intent from messy user text |
| 2. **Route** | Orchestrator decides: chat reply, cache hit, or full product search |
| 3. **Search** | Web scraper queries up to 14 Moroccan sites in parallel |
| 4. **Rank** | Decision agent scores, deduplicates, and picks the top 3 offers |
| 5. **Respond** | Agent Generator writes a Darija/French/English reply (LLM or template) |
| 6. **Monitor** | Ambient scheduler can watch prices and notify users later |
| 7. **Govern** | Governance agent audits events for PII, rate limits, and robots.txt |

---

## Architecture

```text
Telegram User
     │
     ▼
Telegram Gateway ──► msg.inbound
     │
     ▼
Orchestrator ──► NER (gRPC) ──► ner.extracted
     │                │
     │         cache hit? ──► response.outbound
     │         chat only? ──► response.outbound
     │
     ▼
scrape.task.assigned
     │
     ▼
Web Scraping Agent (14 providers, parallel)
     │
     ▼
scrape.raw ──► Decision Agent (batch + score)
     │
     ▼
decision.ranked
     │
     ▼
Agent Generator (LLM + Darija copy)
     │
     ▼
response.outbound ──► Telegram Gateway ──► User
```

All agents communicate through **Apache Kafka**. Each service is independent, horizontally scalable, and can be deployed in Docker or Kubernetes.

---

## Agents

| Agent | Role |
|-------|------|
| **Telegram Gateway** | Receives messages, publishes to Kafka, delivers replies |
| **Orchestrator** | Calls NER, checks cache, routes to scrape or conversational reply |
| **NER Service** | Hugging Face model + product vocabulary for entity extraction |
| **Web Scraping** | Parallel search across 14 Moroccan marketplaces |
| **Decision** | Deduplication, fraud checks, 100-point scoring, source diversification |
| **Agent Generator** | Formats top 3 products into a user-friendly response |
| **Ambient Scheduler** | Background price watches and re-scrape notifications |
| **Governance** | PII scanning, rate limiting, robots.txt compliance, audit logs |

---

## Supported Marketplaces

```text
jumia          avito           electrosalam    mafiawaystore
moteur         mymarket        ultrapc         electroplanet
defacto        biougnach       marjane         decathlon
mubawab        ikea
```

Scraping uses **httpx** by default. Sites listed in `SCRAPE_PLAYWRIGHT_PROVIDERS` (default: `avito`) use **Playwright** for browser rendering.

---

## NER (Named Entity Recognition)

The NER service turns noisy user text into structured shopping data.

**Model:** `ElAtrachAMINE/darija-ner-xlmroberta` (XLM-RoBERTa, Hugging Face)

**Product vocabulary:** ~1,200 entries in `models/ner/resources/product_vocabulary.csv` — brands, products, colors, Darija/French/English aliases, and common typos. Fuzzy matching via `rapidfuzz`.

**Pipeline:**

```text
Raw text → vocabulary normalization → Hugging Face NER → entity cleanup → ProductQuery
```

**Example:**

```text
Input:  bghit samsong galaxi a15 kehla b 1500dh
Output: brand=Samsung, product=Galaxy A15, color=black, budget=1500 MAD
```

Main files: `models/ner/serve.py`, `models/ner/product_vocabulary.py`, `models/ner/grpc_server.py`

**External vocabulary:** Open Food Facts, Open Beauty Facts, and Open Products Facts exports can be converted into `models/ner/resources/external_vocabulary.csv`:

```powershell
python -m scripts.import_open_facts_vocabulary `
  --input https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz `
  --input https://static.openbeautyfacts.org/data/en.openbeautyfacts.org.products.csv.gz `
  --input https://static.openproductsfacts.org/data/en.openproductsfacts.org.products.csv.gz `
  --country morocco --country maroc --country france `
  --max-rows 200000 `
  --output models/ner/resources/external_vocabulary.csv
```

Run this on a machine with good network/storage. The script streams remote gzip exports and writes only the compact generated CSV loaded by the NER service. Raw Open Facts files are not committed.

---

## Decision Scoring

Products are ranked with a **100-point system**:

- Price vs budget fit
- Source trust (Jumia, Avito, official sellers)
- Title relevance and product aliases
- Availability and seller rating
- Fraud penalty for suspicious listings

The engine filters accessories/noise, deduplicates similar listings, and **diversifies the top 3** (max 2 from the same source). The Decision agent waits up to `DECISION_BATCH_WAIT_SECONDS` (default 8s) for slow scrapers before ranking.

---

## Response Generation

The Agent Generator produces the final Telegram message:

- **Template mode** — structured product blocks without an external LLM
- **LLM mode** — Groq, OpenAI, or Gemini for natural Darija/French/English replies
- Validates output against ranked products (no hallucinated listings)
- Uses behavioral memory for tone and language preferences

Supported providers: `template`, `groq`, `openai`, `openai-compatible`, `gemini`

---

## Three-Tier Memory

| Tier | Storage | Purpose |
|------|---------|---------|
| **Global** | Redis | Product response cache, price history, site health, robots.txt |
| **User** | MongoDB + Redis | Profiles, search history, preferences, price watches |
| **Behavioral** | MongoDB (private) | Generator-only context: tone, language, preferred sources |

Integrated in: gateway, orchestrator, ambient scheduler, and agent generator.

---

## Governance

The Governance agent listens to all Kafka topics and enforces:

- **PII scanning** — quarantine messages containing personal data
- **Rate limiting** — per-user and per-domain limits (Redis-backed)
- **Robots.txt** — optional strict compliance checks
- **Audit trail** — publishes to `gov.audit` and `gov.violation`

---

## Project Structure

```text
agents/
  orchestrator/       Route messages, NER, cache, conversational LLM
  webscraping/        14 marketplace spiders + Playwright/httpx tools
  decision/           Scoring, dedup, fraud detection
  agent_generator/    Final response formatting + LLM client
  ambient_scheduler/  Price watch background jobs
  governance/         Policy engine, PII, rate limits, robots
gateway/
  telegram_proxy.py   Telegram ↔ Kafka bridge
models/
  ner/                NER model, vocabulary, gRPC server
shared/
  config/             Pydantic settings from .env
  events/             Kafka wrappers, Pydantic schemas, topic names
  memory/             Global, user, and behavioral memory tiers
  runtime/            Health checks, metrics, logging, retry
scripts/              Local pipeline, smoke tests, cache clear, audits
deploy/k8s/           Kubernetes base + dev/staging/prod overlays
docker/               Service and NER Dockerfiles
monitoring/           Prometheus alerts + Grafana dashboard
tests/unit/           29 unit test modules (scrapers, agents, NER, memory)
docs/                 Deployment guide and operations runbook
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.11+ |
| Messaging | Apache Kafka (aiokafka) |
| Cache | Redis |
| Database | MongoDB |
| NER | Hugging Face Transformers, XLM-RoBERTa, gRPC |
| Scraping | httpx, BeautifulSoup, Playwright |
| LLM | Groq / OpenAI / Gemini (HTTP) |
| Bot | python-telegram-bot |
| Observability | Prometheus metrics, OpenTelemetry, structlog |
| Deployment | Docker, Docker Compose, Kubernetes (Kustomize) |
| CI | GitHub Actions (tests + Docker build) |

---

## Quick Start

### 1. Clone and configure

```powershell
copy .env.example .env
# Edit .env: set TELEGRAM_BOT_TOKEN, optional LLM_API_KEY
```

### 2. Install

```powershell
python -m pip install -e ".[dev]"
python -m playwright install chromium
```

The first NER run downloads the Hugging Face model (~1 GB). After that, the local cache is reused.

### 3. Start infrastructure

```powershell
docker compose up -d kafka redis mongodb
```

### 4. Run services (separate terminals)

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

Or use the helper script:

```powershell
.\scripts\start_e2e_local.ps1
```

### 5. Test without Telegram

```powershell
python -m scripts.run_local_pipeline
python -m scripts.smoke_kafka_flow
```

### 6. Full stack with Docker

```powershell
docker compose -f docker-compose.full.yml up --build
python -m scripts.smoke_kafka_flow
```

---

## Key Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker |
| `REDIS_URL` | `redis://localhost:6379/0` | Cache and rate limits |
| `MONGO_URI` | `mongodb://localhost:27017` | User memory and watches |
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot token (required for gateway) |
| `NER_GRPC_HOST` / `PORT` | `localhost:50051` | NER gRPC service |
| `SMART_SHOPPER_NER_MODEL` | `ElAtrachAMINE/darija-ner-xlmroberta` | NER model |
| `SMART_SHOPPER_VOCAB_PATH` | `models/ner/resources/product_vocabulary.csv` | Product vocabulary |
| `SMART_SHOPPER_EXTERNAL_VOCAB_PATHS` | `models/ner/resources/external_vocabulary.csv` | Generated Open Facts vocabulary files |
| `LLM_PROVIDER` | `template` | `groq`, `openai`, `gemini`, or `template` |
| `LLM_API_KEY` | — | API key for LLM provider |
| `SCRAPE_MAX_CONCURRENCY` | `8` | Parallel site scrapes |
| `SCRAPE_TIMEOUT_SECONDS` | `40` | Per-site timeout |
| `SCRAPE_ROUTE_PROVIDERS` | `true` | Route queries to relevant marketplaces only |
| `SCRAPE_ROUTE_USE_LLM` | `false` | Use `LLM_PROVIDER` to classify product category for routing |
| `SCRAPE_COLLECTION_GRACE_SECONDS` | `10` | Batch grace after per-site timeout |
| `SCRAPE_PLAYWRIGHT_PROVIDERS` | `avito` | Comma-separated Playwright sites |
| `DECISION_BATCH_WAIT_SECONDS` | `8` | Wait for slow scrapers before ranking |
| `CACHE_TTL_SECONDS` | `1800` | Response cache TTL (30 min) |

See `.env.example` for the full list. **Never commit `.env` or real API tokens.**

---

## Kafka Topics

```text
msg.inbound          User messages from gateway
ner.extracted        NER entity extraction results
scrape.task.assigned Scraping tasks for the web scraper
scrape.raw           Raw products from each site
decision.ranked      Scored and ranked top products
response.outbound    Final reply for the user
ambient.watch        Price watch registration
ambient.tick         Scheduled re-scrape triggers
price.history        Price snapshot events
cache.write          Cache update events
gov.audit            Governance audit logs
gov.violation        Policy violation events
error.dead_letter    Failed message dead letter
```

Shared schemas: `shared/events/schemas.py` · Topic constants: `shared/events/topics.py`

---

## Testing

```powershell
python -m pytest tests/unit -q
```

The suite covers NER, orchestrator, all 14 scrapers, decision scoring, generator, governance, memory tiers, ambient scheduler, and deployment readiness.

Test NER directly:

```powershell
python -c "from models.ner.serve import extract_entities; print([e.model_dump() for e in extract_entities('bghit samsong galaxi a15 kehla b 1500dh')])"
```

Audit scraper providers:

```powershell
python -m scripts.audit_scrape_providers
```

Clear stale cached responses:

```powershell
python -m scripts.clear_response_cache
```

---

## Deployment

| Artifact | Purpose |
|----------|---------|
| `docker/Dockerfile.service` | Reusable Python service image |
| `docker/Dockerfile.ner` | NER image with model cache warmup |
| `docker-compose.full.yml` | Local production-like full stack |
| `deploy/k8s/base/` | Kubernetes base manifests |
| `deploy/k8s/overlays/` | dev, staging, prod environment overlays |
| `monitoring/prometheus.yml` | Prometheus scrape config |
| `monitoring/grafana-dashboard.json` | Grafana dashboard |
| `monitoring/alerts.yml` | Alert rules |

Production target: **AWS EKS** with MSK Kafka, ElastiCache Redis, MongoDB Atlas, and ECR images.

Detailed guides:

- [docs/deployment.md](docs/deployment.md) — AWS/EKS deployment
- [docs/runbook.md](docs/runbook.md) — operations and incident response
- [PFA_PROJECT_FULL_OVERVIEW.md](PFA_PROJECT_FULL_OVERVIEW.md) — full architecture reference

---

## Health and Monitoring

Every long-running service exposes:

- `/healthz` — process alive
- `/readyz` — ready to serve
- `/metrics` — Prometheus text metrics

---

## CI

GitHub Actions (`.github/workflows/ci.yml`):

1. Install dependencies and run unit tests
2. Validate Kubernetes manifests render with Kustomize
3. Build service and NER Docker images

---

## License

Proprietary — ENIAD IA
