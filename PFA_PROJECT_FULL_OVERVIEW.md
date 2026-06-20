# Smart Shopper PFA - Full Project Overview

## 1. Project Identity

**Project name:** Smart Shopper  
**Project type:** PFA / Final Year Project  
**Main objective:** Build an AI-powered shopping intelligence bot that receives a user product request, searches available offers, ranks the best options, generates a personalized response, and can monitor future price drops or better deals.

The project is designed as a **decentralized, event-driven, multi-agent system** using **Apache Kafka** as the communication backbone.

The first MVP target is simple:

```text
User sends a Telegram message -> system returns a product recommendation response
```

Example user request:

```text
Find me a Samsung phone under 3000 MAD
```

The final target system is broader:

```text
User request
-> AI understanding
-> web scraping
-> scoring and ranking
-> personalized response
-> background monitoring
-> governance and compliance
```

## 2. Source Documents Used

This overview combines information from three PFA files:

1. **PFA Architecture Report**
   - Formal explanation of the complete architecture.
   - Describes the final target system, agents, memory layers, technology stack, and benefits.

2. **Smart Shopper Interactive Architecture HTML**
   - Interactive visual simulator of the architecture.
   - Demonstrates event flow, Kafka topics, memory I/O, cache hit/miss behavior, scoring, scraping, generation, and governance.

3. **Smart Shopper Work Split Report**
   - MVP planning and team responsibility document.
   - Defines team roles, branches, ownership rules, task split, shared contracts, and first success target.

## 3. High-Level System Goal

Smart Shopper helps users find good shopping deals through a conversational interface.

The user can specify:

- Product type
- Brand preference
- Budget
- Currency
- Quality expectations
- Preferred sites
- Watch/monitoring intent

The system then:

1. Understands the message using NER.
2. Converts the request into structured data.
3. Checks whether fresh results already exist in cache.
4. Scrapes products if needed.
5. Normalizes product data.
6. Scores and ranks offers.
7. Generates a readable personalized response.
8. Sends the response back to the user.
9. Optionally monitors prices in the background.

## 4. MVP Flow

The MVP flow from the work-split report is:

```text
Telegram Gateway
-> Kafka msg.inbound
-> Orchestrator
-> Rule-based NER
-> Scraper
-> Decision Agent
-> Agent Generator
-> Kafka response.outbound
-> Telegram
```

Detailed MVP steps:

1. User sends a message through Telegram.
2. Telegram Gateway receives the message.
3. Gateway converts it into the shared `InboundMessage` format.
4. Gateway publishes it to Kafka topic `msg.inbound`.
5. Orchestrator receives the message.
6. Orchestrator calls the rule-based NER placeholder.
7. NER extracts product, brand, budget, currency, and intent.
8. Orchestrator creates a scraping task.
9. Scraper Agent produces mock product results at first.
10. Scraper publishes raw products to `scrape.raw`.
11. Decision Agent ranks products using the 100-point scoring system.
12. Decision Agent publishes ranked results to `decision.ranked`.
13. Agent Generator creates a readable response.
14. Agent Generator publishes final message to `response.outbound`.
15. Telegram Gateway sends the response back to the user.

The first success target is not perfect scraping or perfect AI. It is proving that the full architecture works end to end.

## 5. Final Target Architecture

The final architecture is a decentralized event-driven system.

Instead of services calling each other directly, agents communicate through Kafka topics. Each agent subscribes to the topics it needs and publishes new events when it completes work.

Main architectural properties:

- **Event-driven:** all communication goes through Kafka.
- **Decentralized:** agents are independent.
- **Scalable:** scraper and agent instances can scale horizontally.
- **Resilient:** one failing component does not stop the entire system.
- **Ambient:** background monitoring continues after the first request.
- **Governed:** a Governance Agent audits data, rate limits, robots.txt compliance, and privacy.
- **Cache-first:** Redis avoids unnecessary scraping when fresh results exist.

## 6. Kafka Topics

All components must use the same shared topic names:

| Topic | Purpose |
|---|---|
| `msg.inbound` | New user messages from the gateway |
| `ner.extracted` | Extracted entities from the user request |
| `scrape.task.assigned` | Scraping task assigned to scraper agents |
| `scrape.raw` | Raw product data collected from websites |
| `decision.ranked` | Ranked and scored product recommendations |
| `response.outbound` | Final response ready to send to the user |
| `ambient.watch` | Background monitoring / price watch tasks |
| `gov.audit` | Governance audit logs |
| `gov.violation` | Governance policy violations |

Important note: the interactive HTML file uses `nat.extracted`, but the PDF, work-split report, and current code use `ner.extracted`. The correct topic should be `ner.extracted`.

## 7. Shared Message Contracts

### 7.1 Inbound Message

Used between Telegram Gateway and Orchestrator.

```json
{
  "request_id": "req_001",
  "user_id": "telegram_123",
  "channel": "telegram",
  "text": "Samsung phone under 3000 MAD",
  "timestamp": "2026-06-18T15:00:00Z"
}
```

### 7.2 Scraping Task

Used between Orchestrator and Scraper Agent.

```json
{
  "request_id": "req_001",
  "user_id": "telegram_123",
  "product": "phone",
  "brand": "Samsung",
  "budget": 3000,
  "currency": "MAD",
  "sites": ["jumia", "avito"]
}
```

In the current codebase, this is represented as `ScrapeTaskAssigned` containing a nested `ProductQuery`.

### 7.3 Raw Product

Used between Scraper Agent and Decision Agent.

```json
{
  "request_id": "req_001",
  "source": "jumia",
  "title": "Samsung Galaxy A15 128GB",
  "price": 2499,
  "currency": "MAD",
  "url": "https://example.com/product",
  "availability": "in_stock",
  "seller": "Jumia",
  "rating": 4.5
}
```

### 7.4 Ranked Result

Used between Decision Agent and Agent Generator.

```json
{
  "request_id": "req_001",
  "user_id": "telegram_123",
  "products": [
    {
      "title": "Samsung Galaxy A15 128GB",
      "price": 2499,
      "source": "jumia",
      "url": "https://example.com/product",
      "score": 87,
      "score_breakdown": {
        "price": 36,
        "trust": 27,
        "quality": 16,
        "availability": 8
      }
    }
  ]
}
```

### 7.5 Outbound Response

Used between Agent Generator and Telegram Gateway.

```json
{
  "request_id": "req_001",
  "user_id": "telegram_123",
  "channel": "telegram",
  "message": "I found 3 good Samsung phones under 3000 MAD..."
}
```

## 8. Main Agents and Components

### 8.1 User-Proxy Gateway

The gateway is the only component that communicates directly with the outside user channel.

MVP channel:

- Telegram

Future channel:

- WhatsApp

Responsibilities:

- Receive user messages.
- Convert Telegram messages into shared internal event format.
- Publish inbound messages to `msg.inbound`.
- Subscribe to `response.outbound`.
- Send final responses back to Telegram.
- Keep user/channel mapping.

Current repo status:

- `gateway/telegram_proxy.py` exists but is still a stub.

### 8.2 Orchestrator Agent

The Orchestrator is the brain of the internal pipeline.

Responsibilities:

- Subscribe to `msg.inbound`.
- Read inbound user requests.
- Call the NER service.
- Publish extracted entities to `ner.extracted`.
- Build structured product queries.
- Check Redis cache.
- Create scraping tasks.
- Publish tasks to `scrape.task.assigned`.
- Create ambient watches if the user asks for monitoring.

Current repo status:

- `agents/orchestrator/agent.py` is implemented.
- `agents/orchestrator/tools/ner_client.py` is implemented.
- `agents/orchestrator/tools/task_router.py` is implemented.
- `agents/orchestrator/tools/cache_lookup.py` is implemented.
- Kafka runtime loop is not implemented yet.

### 8.3 NER Model Service

NER means Named Entity Recognition.

Its role is to extract structured information from natural user text.

Entities include:

- Product
- Target
- Brand
- Budget
- Currency
- Quality
- Intent
- Site / locale hint

Final target:

- Fine-tuned XLM-RoBERTa model.
- Understand Arabic, French, and Darija.
- Exposed through gRPC and REST.
- Stateless model service, not an autonomous agent.

MVP:

- Rule-based NER placeholder.

Current repo status:

- `models/ner/serve.py` contains rule-based extraction.
- `proto/ner.proto` defines the future gRPC contract.

### 8.4 WebScraping Agents

Scrapers collect product data from e-commerce and social commerce sources.

Target sources:

- Jumia
- Avito
- Facebook Marketplace
- Instagram stores
- WhatsApp stores
- Other e-commerce sites

Responsibilities:

- Subscribe to `scrape.task.assigned`.
- Run site-specific scraping.
- Use Playwright or Scrapy.
- Use proxy rotation.
- Respect robots.txt and rate limits.
- Normalize raw listing data.
- Publish raw products to `scrape.raw`.

Final target:

- Horizontally scalable scraper pools.
- Sandboxed containers or Firecracker microVMs.
- Site-specific scraper pools.

Example pools from the architecture:

- Jumia pool: API access / fast parsing.
- Avito pool: JavaScript rendering / anti-bot rotation.
- Social pool: Facebook Marketplace, Instagram, WhatsApp.

MVP:

- Mock Scraper Agent first.
- Real Jumia and Avito scrapers later.

Current repo status:

- `agents/webscraping/` exists but is mostly stubs.

### 8.5 Decision Agent

The Decision Agent evaluates scraped products and decides which products are best.

Responsibilities:

- Subscribe to `scrape.raw`.
- Aggregate product results.
- Deduplicate listings.
- Normalize currencies.
- Detect fraud or suspicious listings.
- Score products using the 100-point system.
- Publish ranked results to `decision.ranked`.

Current repo status:

- `agents/decision/agent.py` is implemented.
- `agents/decision/tools/scoring_engine.py` is implemented.
- `fraud_detector.py` and standalone `dedup_engine.py` are still stubs.

### 8.6 Agent Generator

The Agent Generator creates the final response that the user reads.

Responsibilities:

- Subscribe to `decision.ranked`.
- Read user behavioral profile.
- Generate natural language response.
- Match user tone, language, and preferred format.
- Verify recommended URLs before sending.
- Publish final response to `response.outbound`.

Final target:

- Use Gemini or Groq LLaMA.
- Use private memory for personalization.
- Live-verify product links before recommending them.

MVP:

- Template-based generator.

Current repo status:

- `agents/agent_generator/` exists but is still stubs.

### 8.7 Ambient Scheduler

The Ambient Scheduler enables background monitoring.

Responsibilities:

- Subscribe to `ambient.watch`.
- Store active watches.
- Periodically re-trigger scraping.
- Compare new results with previous results.
- Detect price drops.
- Detect better products.
- Notify the user when useful changes happen.

Final behavior:

- Hourly checks by default.
- Watch lifecycle: created, active, paused, expired.

Current repo status:

- `agents/ambient_scheduler/` exists but is still stubs.

### 8.8 Governance Agent

The Governance Agent monitors all system activity.

Responsibilities:

- Subscribe to all Kafka topics.
- Audit all events.
- Enforce Moroccan Law 09-08.
- Prevent personal data leakage.
- Enforce robots.txt compliance.
- Apply rate limits per domain.
- Detect abusive or fraudulent behavior.
- Warn, throttle, halt, quarantine, or audit agents.

Current repo status:

- `agents/governance/` exists but is still stubs.

## 9. 100-Point Scoring System

The Decision Agent ranks each product out of 100 points.

| Criterion | Points |
|---|---:|
| Price | 40 |
| Trust / Source | 30 |
| Quality | 20 |
| Availability | 10 |
| Total | 100 |

Example from the interactive HTML:

| Criterion | Score |
|---|---:|
| Price match | 36 / 40 |
| Trust / source | 27 / 30 |
| Quality | 17 / 20 |
| Availability | 8 / 10 |
| Total | 88 / 100 |

Current code uses this same scoring structure.

The current implementation gives high trust to sources such as:

- Jumia
- Official sellers
- Avito
- Facebook
- Instagram

## 10. Memory Architecture

The project uses a three-tier memory architecture.

### 10.1 Tier 1 - Global Shared Memory

Technology:

- Redis Cluster

Used by:

- Orchestrator
- WebScraping Agents
- Decision Agent

Stores:

- Product cache
- Product JSON
- Price history
- Site health status
- Robots.txt cache

Example keys:

```text
products:{site}:{sku}
prices:{sku}:history
sites:{domain}:health
sites:{domain}:robots
```

Purpose:

- Speed up repeated queries.
- Avoid scraping if fresh data exists.
- Share product data across all users.

### 10.2 Tier 2 - Per-User Shared Memory

Technology:

- Redis
- MongoDB

Used by:

- Orchestrator
- WebScraping Agents
- Decision Agent

Stores:

- User preferences
- Budget constraints
- Preferred sites
- Search history
- Active watchlists

Example keys:

```text
user:{id}:prefs
user:{id}:sites
user:{id}:budget
user:{id}:history
user:{id}:watches
```

Purpose:

- Personalize decisions.
- Remember user-specific constraints.
- Support watchlists.

### 10.3 Tier 3 - Private Behavioral Memory

Technology:

- MongoDB
- Agent-local private storage

Used by:

- Agent Generator only

Stores:

- Tone preferences
- Language preferences
- Query history
- Click-through rates
- Interaction history
- Behavioral profile

Example keys:

```text
behaviors:{user_id}
user:{id}:tone
user:{id}:history
```

Purpose:

- Personalize the final text response.
- Keep behavioral data private to the Agent Generator.

## 11. Cache Behavior

The system follows a cache-first strategy.

Flow:

1. Orchestrator extracts structured product query.
2. Orchestrator checks Redis global product cache.
3. If a fresh cache entry exists, scraping is skipped.
4. If no fresh entry exists, scraping tasks are assigned.

The architecture report says cache can reduce scraping for popular products by 60-80%.

Current repo status:

- Cache key generation and Redis helper exist in `agents/orchestrator/tools/cache_lookup.py`.
- Full integration into Kafka runtime is not implemented yet.

## 12. Technology Stack

Target stack:

| Technology | Role |
|---|---|
| Python | Main implementation language |
| Apache Kafka | Event bus and inter-agent communication |
| Redis Cluster | Cache, shared memory, rate limiting |
| MongoDB Replica Set | Persistent user data and behavioral profiles |
| Kubernetes | Deployment, scaling, orchestration |
| XLM-RoBERTa | NER model for Arabic/French/Darija |
| Gemini | LLM response generation |
| Groq LLaMA | LLM fallback |
| Playwright | JavaScript-heavy scraping |
| Scrapy | Structured scraping |
| Firecracker | Secure scraper sandboxing |
| Prometheus | Metrics |
| Grafana | Dashboards |
| Jaeger | Distributed tracing |
| Triton / TorchServe | Model serving |
| Telegram Bot API | MVP user channel |
| WhatsApp adapter | Future user channel |

Current repo stack:

- Python
- Pydantic
- aiokafka
- Redis client
- PyMongo
- gRPC / Protobuf dependencies
- OpenTelemetry dependencies
- Telegram bot dependency
- Docker Compose for Kafka, Redis, MongoDB, and Jaeger

## 13. Team Roles and Work Split

### 13.1 Team Members

From the work-split report:

- **Amine El Atrach**
- **Mounim**

The architecture report also mentions:

- **El Atrach Mohammed Amine**
- **Rhouli Mohamed Mounim**
- **Prof. Mohamed Khalifa BOUTAHIR** as project supervisor

### 13.2 Branch Strategy

Do not work directly on `master`.

Branches:

```text
master
feature/core-pipeline                 -> Amine
feature/gateway-scraper-generator     -> Mounim
```

### 13.3 Amine's Role

Amine owns the internal intelligence pipeline.

Branch:

```text
feature/core-pipeline
```

Owned folders:

```text
shared/
agents/orchestrator/
agents/decision/
models/ner/
```

Main flow:

```text
msg.inbound
-> Orchestrator
-> NER
-> scrape.task.assigned
-> scrape.raw
-> Decision Agent
-> decision.ranked
```

Tasks:

- Create shared Kafka topic names.
- Create shared message schemas.
- Build Kafka producer/consumer helpers.
- Build rule-based NER service using `proto/ner.proto`.
- Build Orchestrator Agent.
- Add Redis cache check.
- Build Decision Agent.
- Implement 100-point scoring system.

Expected output:

- When a message appears in `msg.inbound`, Orchestrator extracts product info and creates a scraping task.
- When products appear in `scrape.raw`, Decision Agent ranks them and publishes to `decision.ranked`.

### 13.4 Mounim's Role

Mounim owns the user side, scraper side, and response side.

Branch:

```text
feature/gateway-scraper-generator
```

Owned folders according to the work-split report:

```text
gateway/
agents/scraper/
agents/generator/
```

Equivalent folders in the current repo:

```text
gateway/
agents/webscraping/
agents/agent_generator/
```

Main flow:

```text
Telegram Gateway
-> msg.inbound
-> Scraper Agent
-> scrape.raw
-> Agent Generator
-> response.outbound
-> Telegram
```

Tasks:

- Build Telegram Gateway.
- Convert Telegram messages to shared Kafka format.
- Publish messages to `msg.inbound`.
- Build mock Scraper Agent first.
- Later replace mock scraper with Jumia / Avito scraping.
- Normalize product results.
- Build template-based Agent Generator.
- Publish final response to `response.outbound`.
- Send final response back to Telegram.
- Store simple user/search history in MongoDB.

Expected output:

- User sends a Telegram message.
- Gateway publishes it to Kafka.
- Scraper produces mock product data.
- Generator creates a readable response.
- Gateway sends the response back to Telegram.

### 13.5 Shared Files - Change Carefully

Both members may need these files, so they must be modified carefully:

```text
.env.example
docker-compose.yml
pyproject.toml
README.md
```

## 14. Development Order

Recommended order:

1. Shared contracts
   - Kafka topic names
   - Message formats
   - Folder structure
   - Environment variable names

2. Amine starts Task A
   - Create `feature/core-pipeline`
   - Shared schemas and Kafka helpers
   - NER placeholder
   - Orchestrator
   - Decision Agent

3. Mounim starts Task B
   - Create `feature/gateway-scraper-generator`
   - Telegram Gateway
   - Mock scraper
   - Generator
   - Telegram response

4. Integration
   - Merge Amine branch into `master`
   - Merge Mounim branch into `master`
   - Resolve conflicts
   - Test full flow

## 15. Current Repository Structure

Current repo path:

```text
Smart-Shopper/
```

Important folders:

```text
agents/
  orchestrator/
  decision/
  webscraping/
  agent_generator/
  ambient_scheduler/
  governance/

gateway/
  telegram_proxy.py

models/
  ner/

shared/
  events/

proto/
  ner.proto

docker/
  Dockerfile.python.base

monitoring/
  prometheus.yml
  alerts.yml

tests/
  unit/
  integration/
  e2e/
```

## 16. Current Repo Implementation Status

### Implemented

- Shared Kafka topic constants.
- Shared Pydantic event schemas.
- JSON event encode/decode helpers.
- Kafka producer and consumer wrappers.
- Rule-based NER placeholder.
- NER client abstraction.
- Orchestrator Agent core method.
- Product query builder.
- Scrape task builder.
- Redis product cache helper.
- Decision Agent wrapper.
- 100-point scoring engine.
- Product deduplication inside scoring engine.
- Unit tests for shared contracts, NER/orchestrator, and decision ranking.
- Docker Compose for Kafka, Redis, MongoDB, and Jaeger.
- Protobuf NER service contract.

### Mostly Stubbed

- Telegram Gateway.
- WebScraping Agent.
- Jumia spider.
- Avito spider.
- Social spider.
- Playwright scraper tool.
- Scrapy runner.
- Proxy rotator.
- Agent Generator.
- LLM client.
- Response validator.
- Behavior analyzer.
- Ambient Scheduler.
- Governance Agent.
- PII scanner.
- Rate limiter.
- Robots checker.
- Fraud detector.
- Standalone dedup engine.
- Real NER model server.
- Kubernetes manifests.
- Prometheus app metrics.
- Grafana dashboards.

## 17. Important Current Code Mapping

| Architecture Concept | Current File |
|---|---|
| Kafka topic names | `shared/events/topics.py` |
| Event contracts | `shared/events/schemas.py` |
| Kafka helpers | `shared/events/kafka.py` |
| Orchestrator Agent | `agents/orchestrator/agent.py` |
| NER client | `agents/orchestrator/tools/ner_client.py` |
| Task router | `agents/orchestrator/tools/task_router.py` |
| Redis cache helper | `agents/orchestrator/tools/cache_lookup.py` |
| Rule-based NER | `models/ner/serve.py` |
| NER protobuf contract | `proto/ner.proto` |
| Decision Agent | `agents/decision/agent.py` |
| Scoring engine | `agents/decision/tools/scoring_engine.py` |
| Telegram gateway placeholder | `gateway/telegram_proxy.py` |
| Web scraping placeholders | `agents/webscraping/` |
| Agent generator placeholders | `agents/agent_generator/` |
| Governance placeholders | `agents/governance/` |
| Ambient scheduler placeholder | `agents/ambient_scheduler/` |
| Local infra | `docker-compose.yml` |
| Python dependencies | `pyproject.toml` |

## 18. Current Test Status

The current unit tests pass when the repository root is added to `PYTHONPATH`.

Command:

```powershell
$env:PYTHONPATH='.'; pytest -q
```

Result:

```text
5 passed
```

Plain `pytest -q` may fail in this local environment because Python cannot import local packages such as `agents` and `shared` unless the repo root is on `PYTHONPATH` or the package is installed in editable mode.

## 19. Known Inconsistencies Between Documents

### 19.1 WhatsApp vs Telegram

The architecture PDF mostly describes WhatsApp.

The work-split report and HTML focus on Telegram for the MVP.

The current repo also has:

```text
gateway/telegram_proxy.py
```

Conclusion:

- MVP should use Telegram.
- WhatsApp can be a future adapter.
- Documentation should clarify that both can be supported through the User-Proxy Gateway.

### 19.2 `nat.extracted` vs `ner.extracted`

The HTML uses:

```text
nat.extracted
```

The PDF, work-split report, and code use:

```text
ner.extracted
```

Conclusion:

- Use `ner.extracted`.
- Update the HTML if it becomes part of the deliverables.

### 19.3 Folder Names

The work-split report says:

```text
agents/scraper/
agents/generator/
```

The current repo uses:

```text
agents/webscraping/
agents/agent_generator/
```

Conclusion:

- Either keep current repo names and update docs, or rename folders before implementation grows.

### 19.4 ENIAD / ENSAO Metadata

The PDF says ENIAD / UMP / academic year 2025-2026.

The HTML says ENSAO / 2024/25 in places.

Conclusion:

- Architecture logic is still consistent.
- Report metadata should be corrected for final submission.

## 20. Future Roadmap

After MVP:

1. Build real Jumia scraper.
2. Build real Avito scraper.
3. Improve Redis product cache.
4. Add MongoDB user/search history.
5. Build Ambient Scheduler for price monitoring.
6. Build Governance Agent for audit and policy checks.
7. Add LLM response generation with Gemini / Groq.
8. Fine-tune XLM-RoBERTa NER model.
9. Add WhatsApp adapter.
10. Add monitoring with Prometheus, Grafana, and Jaeger.
11. Add Kubernetes deployment manifests.
12. Add sandboxed scraping with Firecracker or equivalent isolation.
13. Add integration and end-to-end tests.

## 21. Final Understanding

Smart Shopper is a PFA project for an AI shopping assistant.

The architecture is designed to be serious and scalable: Kafka-based, agent-oriented, cache-first, privacy-aware, observable, and ready for background monitoring.

The current MVP should focus on proving one complete path:

```text
Telegram message
-> Kafka
-> Orchestrator
-> rule-based NER
-> mock scraper
-> Decision Agent
-> template Agent Generator
-> Telegram response
```

The current repository already implements much of the internal pipeline owned by Amine. The main remaining MVP work is the gateway, mock scraper, agent generator, and runtime Kafka wiring so that all implemented pieces communicate end to end.

