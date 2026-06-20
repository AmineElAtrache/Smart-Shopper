# Smart Shopper

Smart Shopper is a PFA MVP for an AI shopping intelligence bot. The first goal is to prove this flow:

```text
Telegram -> Kafka -> Orchestrator -> Mock Scraper -> Decision Agent -> Agent Generator -> Telegram
```

This branch implements **Mounim's MVP part**:

- Telegram Gateway: receives Telegram messages and publishes `msg.inbound`.
- Mock WebScraping Agent: consumes `scrape.task.assigned` and publishes mock `scrape.raw` products.
- Template Agent Generator: consumes `decision.ranked` and publishes `response.outbound`.
- Local `.env` loading for runtime configuration.
- Unit tests for Telegram conversion, mock product generation, and response generation.

## Mounim MVP Components

### Telegram Gateway

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

### Mock WebScraping Agent

File:

```text
agents/webscraping/agent.py
```

Responsibilities:

- Consumes scraping tasks from `scrape.task.assigned`.
- Generates deterministic mock Jumia and Avito products.
- Publishes `RawProduct` events to `scrape.raw`.

This is intentionally mock data for the first MVP. Real Jumia/Avito scraping is future work.

### Template Agent Generator

File:

```text
agents/agent_generator/agent.py
```

Responsibilities:

- Consumes ranked product results from `decision.ranked`.
- Builds a readable recommendation message.
- Publishes `OutboundResponse` to `response.outbound`.

This is intentionally template-based for the first MVP. Gemini/Groq LLM generation is future work.

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

Important: never commit your real Telegram token. `.env` is ignored by Git.

## Install Dependencies

```powershell
python -m pip install -e ".[dev]"
```

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

## Full MVP Integration

Mounim's services cover:

```text
Telegram -> msg.inbound
scrape.task.assigned -> Mock Scraper -> scrape.raw
decision.ranked -> Agent Generator -> response.outbound -> Telegram
```

The complete final recommendation also needs Amine's runtime services:

```text
msg.inbound -> Orchestrator -> scrape.task.assigned
scrape.raw -> Decision Agent -> decision.ranked
```

Until those runtime loops are running, the Telegram bot can confirm that a request was received, while the scraper and generator wait for their Kafka events.

## Run Tests

```powershell
pytest -q
```

Current expected result:

```text
9 passed
```

## Useful Topics

The MVP uses these Kafka topics:

```text
msg.inbound
scrape.task.assigned
scrape.raw
decision.ranked
response.outbound
```

Shared schemas live in:

```text
shared/events/schemas.py
```

Shared topic constants live in:

```text
shared/events/topics.py
```
