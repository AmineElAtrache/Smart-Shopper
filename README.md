# Smart Shopper

Smart Shopper is a multi-agent shopping intelligence MVP for Moroccan marketplace search. A user sends a natural message in Darija, French, English, or mixed language, and the system extracts the shopping intent, searches supported websites, ranks products, and generates a response.

Current high-level flow:

```text
Telegram / Frontend
-> User Proxy Gateway
-> Kafka msg.inbound
-> Orchestrator + NER
-> Kafka scrape.task.assigned
-> WebScraping Agent
-> Kafka scrape.raw
-> Decision Agent
-> Kafka decision.ranked
-> Agent Generator
-> Kafka response.outbound
-> Telegram / Frontend
```

## Current Status

Implemented so far:

- Shared Pydantic event contracts for all agents.
- Kafka producer/consumer wrappers and topic constants.
- Orchestrator agent that calls NER and builds `ProductQuery`.
- Hugging Face Darija NER model integration with preprocessing and context enrichment.
- Live scraper providers for Moroccan marketplaces.
- Decision agent with deduplication and 100-point scoring.
- Agent generator that formats final recommendations.
- Telegram gateway skeleton/runtime.
- Local no-Kafka integration runner for quick testing.
- Docker Python base image with Playwright support.

Supported scraper providers currently registered:

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

## NER Model

The NER service is the part that converts messy user text into clean shopping entities.

Model used:

```text
ElAtrachAMINE/darija-ner-xlmroberta
```

Main file:

```text
models/ner/serve.py
```

Libraries used:

```text
transformers     Hugging Face model/tokenizer loading
torch            XLM-RoBERTa inference runtime
safetensors      model weight loading
rapidfuzz        typo and fuzzy matching
unicodedata      accent cleanup
re               token and price parsing
pydantic         shared entity schemas
```

### NER Flow

![NER Model Flow](<ner model flow.png>)

```text
Raw user text
-> preprocessing / normalization
-> Hugging Face NER model
-> entity normalization
-> context enrichment
-> weak prediction filtering
-> final entities
-> Orchestrator ProductQuery
```

Example raw input:

```text
bghit samsng phne black f casaa b 3000dh
```

Preprocessing normalizes noisy text:

```text
samsng -> samsung
phne -> phone
casaa -> casablanca
fes -> fes
kehla / k7la -> black
tomobil / tonobil -> voiture
telaja / frigo / refrigerateur -> fridge
```

Normalized input:

```text
bghit samsung phone black f casablanca b 3000dh
```

The Hugging Face model extracts entities such as:

```text
BRAND
PRODUCT
PRICE
CITY
COLOR
QUALITY
```

Entity normalization converts model output to the shared contract:

```json
[
  {"type": "brand", "value": "Samsung"},
  {"type": "product", "value": "phone"},
  {"type": "color", "value": "black"},
  {"type": "city", "value": "casablanca"},
  {"type": "budget", "value": "3000.0", "attributes": {"currency": "MAD"}},
  {"type": "intent", "value": "search"}
]
```

Context enrichment fills shopping-specific gaps the model may miss. For example:

```text
bghit hp omen f fes b 6000dh
```

If the model extracts `HP`, `fes`, and `6000dh` but misses `omen`, enrichment applies:

```text
known brand + next unknown word = product/model
```

Final result:

```text
brand=HP
product=omen
city=fes
budget=6000 MAD
intent=search
```

Weak prediction filtering removes low-confidence false entities. Example: the Darija word `ykone` was sometimes predicted as brand `Kone`; unknown brands below confidence `0.8` are rejected.

The final entities are passed to the Orchestrator and converted into:

```python
ProductQuery(
    product="phone",
    brand="Samsung",
    budget=3000.0,
    currency="MAD",
    city="casablanca",
    color="black",
    quality=None,
)
```

## Environment Setup

Create your local `.env`:

```powershell
copy .env.example .env
```

Important variables:

```env
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
TELEGRAM_BOT_TOKEN=replace_with_your_token
MONGO_URI=mongodb://localhost:27017
MONGO_DB=smart_shopper

NER_GRPC_HOST=localhost
NER_GRPC_PORT=50051
SMART_SHOPPER_NER_BACKEND=auto
SMART_SHOPPER_NER_MODEL=ElAtrachAMINE/darija-ner-xlmroberta
HF_HOME=.cache/huggingface
TOKENIZERS_PARALLELISM=false
```

NER backend modes:

```text
auto = download/use the Hugging Face model, then reuse the local cache
hf   = same model path, intended for explicit live validation
```

Important: never commit your real `.env` or Telegram token.

## Install Dependencies

Recommended:

```powershell
python -m pip install -e ".[dev]"
python -m playwright install chromium
```

Alternative:

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
```

The first NER run may download the Hugging Face model. After that, the local Hugging Face cache is reused.

## Test NER Locally

Run from the project root:

```powershell
$env:SMART_SHOPPER_NER_BACKEND="auto"
$env:SMART_SHOPPER_NER_MODEL="ElAtrachAMINE/darija-ner-xlmroberta"
```

Messy spelling test:

```powershell
python -c "from models.ner.serve import extract_entities; print([e.model_dump() for e in extract_entities('bghit samsng phne black f casaa b 3000dh')])"
```

Expected important entities:

```text
brand=Samsung
product=phone
color=black
city=casablanca
budget=3000 MAD
```

Product model test:

```powershell
python -c "from models.ner.serve import extract_entities; print([e.model_dump() for e in extract_entities('bghit hp omen f fes b 6000dh')])"
```

Expected:

```text
brand=HP
product=omen
city=fes
budget=6000 MAD
```

Appliance query test:

```powershell
python -c "from models.ner.serve import extract_entities; print([e.model_dump() for e in extract_entities('kan9lebe 3la chi telaja fes tkone jdida we maghalyach')])"
```

Expected:

```text
product=fridge
city=fes
quality=new
intent=search
```

Budget query test:

```powershell
python -c "from models.ner.serve import extract_entities; print([e.model_dump() for e in extract_entities('kan9lebe 3la chi pc ykone nadi mayfotch 3000ddh')])"
```

Expected:

```text
product=laptop
budget=3000 MAD
intent=search
```

## Run Local Pipeline

A no-Telegram, no-Kafka local integration check is available:

```powershell
python -m scripts.run_local_pipeline
```

It runs:

```text
InboundMessage
-> Orchestrator + NER
-> ScrapeTaskAssigned
-> WebScraping/mock products
-> Decision ranking
-> Agent Generator response
```

## Run Services With Infrastructure

Start infrastructure:

```powershell
docker compose up -d kafka redis mongodb
```

Then run services in separate terminals:

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

Production-like local smoke:

```powershell
docker compose -f docker-compose.full.yml up --build
python -m scripts.smoke_kafka_flow
```

## Docker / AWS Notes

The NER model is large, so production should avoid downloading it on every container start.

Recommended production approach:

```text
build Docker image
-> pre-download/cache Hugging Face model
-> run NER as its own service/container
-> other agents call NER through gRPC
```

Important environment variables for containers:

```env
SMART_SHOPPER_NER_BACKEND=auto
SMART_SHOPPER_NER_MODEL=ElAtrachAMINE/darija-ner-xlmroberta
HF_HOME=.cache/huggingface
TOKENIZERS_PARALLELISM=false
```

Only the NER service should load the model. Other agents should not each load the 1GB+ model into memory.

Deployment artifacts:

```text
docker/Dockerfile.service       reusable Python service image
docker/Dockerfile.ner           NER image with model cache warmup
docker-compose.full.yml         local production-like service graph
deploy/k8s/base/                Kubernetes base manifests
deploy/k8s/overlays/            dev, staging, and prod overlays
docs/deployment.md              AWS/EKS deployment guide
docs/runbook.md                 operations runbook
```

## Run Tests

```powershell
python -m pytest tests\unit -q
```

The suite should pass after installing the project with the `dev` extra.

## Three-Tier Memory

Smart Shopper implements the memory architecture described in the PFA:

```text
Tier 1 - Global shared memory
  shared/memory/global_memory.py
  Redis-backed product response cache, price history, site health, and robots snapshots.

Tier 2 - Per-user shared memory
  shared/memory/user_memory.py
  MongoDB-backed user profiles, search/response history, preferences, and watches with Redis hot profile cache.

Tier 3 - Private behavioral memory
  shared/memory/behavioral_memory.py
  Generator-private behavioral profile, tone/language context, preferred sources, and response interactions.
```

Main integrations:

```text
gateway/telegram_proxy.py                 records inbound/outbound user history
agents/orchestrator/service.py            applies user preferences and records structured searches
agents/ambient_scheduler/scheduler.py     stores user watch metadata
agents/agent_generator/agent.py           uses private behavior context and writes global response cache
```

## Kafka Topics

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

Shared schemas:

```text
shared/events/schemas.py
```

Topic constants:

```text
shared/events/topics.py
```