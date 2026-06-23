# Smart Shopper

Smart Shopper is a PFA MVP for an AI shopping intelligence bot. The first goal is to prove this flow:

```text
Telegram -> Kafka -> Orchestrator -> Mock Scraper -> Decision Agent -> Agent Generator -> Telegram
```

The project is split into two main development parts:

- **Amine's part:** core intelligence pipeline.
- **Mounim's part:** Telegram gateway, scraper side, and response generation side.

## Project Flow

```text
Telegram user
-> Telegram Gateway
-> Kafka msg.inbound
-> Orchestrator + NER
-> Kafka scrape.task.assigned
-> Mock WebScraping Agent
-> Kafka scrape.raw
-> Decision Agent
-> Kafka decision.ranked
-> Agent Generator
-> Kafka response.outbound
-> Telegram Gateway
-> Telegram user
```

## Amine's Part - Core Pipeline

Amine owns the internal intelligence pipeline: understanding the user request, building the product query, and ranking scraped products.

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

### Implemented Components

#### Shared Contracts

Files:

```text
shared/events/schemas.py
shared/events/topics.py
shared/events/kafka.py
```

Responsibilities:

- Defines shared Pydantic event schemas.
- Defines Kafka topic constants.
- Provides JSON encode/decode helpers.
- Provides Kafka producer/consumer wrappers.

#### Hugging Face NER With Local Fallback

File:

```text
models/ner/serve.py
```

Responsibilities:

- Uses the fine-tuned Hugging Face model `ElAtrachAMINE/darija-ner-xlmroberta` when enabled.
- Normalizes NER output into the shared entity contract used by the Orchestrator.
- Falls back to deterministic local rules when model dependencies or weights are not available.
- Extracts brand, product, budget, currency, city, color, quality, intent, and site hints.

Example:

```text
Find me a Samsung phone under 3000 MAD
```

Extracted entities:

```text
brand=Samsung
product=phone
budget=3000
currency=MAD
intent=search
```

#### Orchestrator Agent

Files:

```text
agents/orchestrator/agent.py
agents/orchestrator/tools/ner_client.py
agents/orchestrator/tools/task_router.py
agents/orchestrator/tools/cache_lookup.py
```

Responsibilities:

- Receives an `InboundMessage`.
- Calls the NER client.
- Creates a `NerExtracted` event.
- Builds a `ScrapeTaskAssigned` event.
- Converts extracted entities into a structured `ProductQuery`.
- Provides Redis cache key/helper logic for product queries.

Current status:

- Core Orchestrator logic is implemented.
- Long-running Kafka runtime loop is not implemented yet.

#### Decision Agent

Files:

```text
agents/decision/agent.py
agents/decision/tools/scoring_engine.py
```

Responsibilities:

- Receives raw scraped products.
- Deduplicates products.
- Scores products using the 100-point scoring model.
- Returns a `DecisionRanked` event.

Scoring model:

```text
Price:        40 points
Trust/source: 30 points
Quality:      20 points
Availability: 10 points
Total:       100 points
```

Current status:

- Core Decision logic is implemented.
- Long-running Kafka runtime loop is not implemented yet.

## Mounim's Part - Gateway, Scraper, Generator

Mounim owns the user side, scraper side, and response side.

Main flow:

```text
Telegram Gateway
-> msg.inbound
scrape.task.assigned
-> Mock Scraper
-> scrape.raw
decision.ranked
-> Agent Generator
-> response.outbound
-> Telegram Gateway
-> Telegram user
```

### Implemented Components

#### Telegram Gateway

File:

```text
gateway/telegram_proxy.py
```

Responsibilities:

- Starts a Telegram bot using `python-telegram-bot`.
- Converts user text into the shared `InboundMessage` schema.
- Publishes messages to Kafka topic `msg.inbound`.
- Consumes final responses from `response.outbound`.
- Sends final messages back to the Telegram user.
- Stores simple inbound/outbound history in MongoDB when available.

#### Mock WebScraping Agent

File:

```text
agents/webscraping/agent.py
```

Responsibilities:

- Consumes scraping tasks from `scrape.task.assigned`.
- Generates deterministic mock Jumia and Avito products.
- Publishes `RawProduct` events to `scrape.raw`.

This is intentionally mock data for the first MVP. Real Jumia/Avito scraping is future work.

#### Template Agent Generator

File:

```text
agents/agent_generator/agent.py
```

Responsibilities:

- Consumes ranked product results from `decision.ranked`.
- Builds a readable recommendation message.
- Publishes `OutboundResponse` to `response.outbound`.

This is intentionally template-based for the first MVP. Gemini/Groq LLM generation is future work.

#### Local Environment Loader

File:

```text
shared/config/env.py
```

Responsibilities:

- Loads local `.env` values for MVP services.
- Allows services to run without manually setting every environment variable in PowerShell.

## Environment Setup

Create a local `.env` file from the example:

```powershell
copy .env.example .env
```

Required variables:

```text
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
TELEGRAM_BOT_TOKEN=replace_with_your_telegram_bot_token
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=smart_shopper
```

NER model variables:

```text
SMART_SHOPPER_NER_BACKEND=auto
SMART_SHOPPER_NER_MODEL=ElAtrachAMINE/darija-ner-xlmroberta
```

Backend modes:

```text
rules = use only the local rule fallback
auto = use cached Hugging Face model if present, otherwise fallback rules
hf    = download/use the Hugging Face model and fail loudly if it cannot load
```

Important: never commit your real Telegram token. `.env` is ignored by Git.

## Install Dependencies

Recommended install for local development:

```powershell
python -m pip install -e ".[dev]"
python -m playwright install chromium
```

The first command installs the Python package, including scraping dependencies such as Playwright and BeautifulSoup. The second command installs the local Chromium browser used by Playwright for live marketplace scraping.

Alternative requirements-file install:

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
```
## Docker Python Image

The Python base image installs the project dependencies and Playwright Chromium runtime:

```powershell
docker build -f docker/Dockerfile.python.base -t smart-shopper-python-base .
```

Use this image as the base for scraper, orchestrator, gateway, and agent containers.

## Start Infrastructure

```powershell
docker compose up -d kafka redis mongodb
```

Check that services are running:

```powershell
docker compose ps
```

Expected services:

- Kafka on `localhost:9092`
- Redis on `localhost:6379`
- MongoDB on `localhost:27017`

## Run Mounim's Services

Open three PowerShell terminals from the project root.

Terminal 1:

```powershell
python -m agents.webscraping.agent
```

Expected:

```text
Mock scraper agent started. Waiting for scrape.task.assigned events.
```

Terminal 2:

```powershell
python -m agents.agent_generator.agent
```

Expected:

```text
Agent generator started. Waiting for decision.ranked events.
```

Terminal 3:

```powershell
python -m gateway.telegram_proxy
```

Expected:

```text
Telegram gateway started. Listening for messages and outbound responses.
```

Then send a message to the Telegram bot:

```text
Find me a Samsung phone under 3000 MAD
```

Expected immediate reply:

```text
Request received (req_...). I am looking for offers now.
```

## Full MVP Integration Status

The code from both parts now works together in-process and has Kafka runtime loops for the core agents:

```text
InboundMessage
-> Orchestrator + NER
-> ScrapeTaskAssigned
-> Mock Scraper
-> RawProduct
-> Decision Agent
-> DecisionRanked
-> Agent Generator
-> OutboundResponse
```

A no-Telegram integration runner is available for quick checks without Docker or Kafka:

```powershell
python -m scripts.run_local_pipeline
```

Expected result:

```text
[integration] extracted ... entities
[integration] mock scraper produced 3 products
[integration] decision ranked 3 products

=== Final response ===
I found 3 good options for you:
...
```

For the live Kafka version, run these services in separate terminals after starting Kafka, Redis, and MongoDB:

```powershell
python -m models.ner.grpc_server
python -m agents.orchestrator.service
python -m agents.webscraping.agent
python -m agents.decision.service
python -m agents.agent_generator.agent
python -m gateway.telegram_proxy
```
## Run Tests

```powershell
pytest -q
```

Current expected result:

```text
77 passed
```

## Useful Kafka Topics

The MVP uses these Kafka topics:

```text
msg.inbound
ner.extracted
scrape.task.assigned
scrape.raw
decision.ranked
response.outbound
ambient.watch
gov.audit
gov.violation
```

Shared schemas live in:

```text
shared/events/schemas.py
```

Shared topic constants live in:

```text
shared/events/topics.py
```
