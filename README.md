# Darija NER Shopping Assistant — MVP

Multi-agent Telegram bot that understands Moroccan Darija queries,
searches real e-commerce sites, compares prices, and recommends the best product.

## Architecture

```
User (Telegram)
    ↓
Telegram Bot  (main.py)
    ↓
NER Agent     (agents/ner_agent.py)       ← your XLM-RoBERTa model
    ↓
Orchestrator  (agents/orchestrator.py)    ← coordinates all agents
    ↓
Research Agent (agents/research_agent.py) ← builds queries + scrapes
    ├── Google Shopping  (scrapers/google_shopping.py)
    └── Avito.ma         (scrapers/avito.py)
    ↓
Market Agent  (agents/market_agent.py)    ← normalizes + compares prices
    ↓
Decision Agent (agents/decision_agent.py) ← scores + picks best
    ↓
Telegram User ← formatted recommendation
```

## Setup (5 steps)

### 1. Clone / download this project
```bash
cd your-projects-folder
# put all these files here
```

### 2. Create virtual environment
```bash
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Create your .env file
```bash
cp .env.example .env
```
Then edit `.env`:
```
TELEGRAM_BOT_TOKEN=your_token_from_@BotFather
HF_MODEL_NAME=your-username/darija-ner-xlmroberta
```

**How to get a Telegram bot token:**
1. Open Telegram → search `@BotFather`
2. Send `/newbot`
3. Choose a name and username
4. Copy the token → paste in `.env`

### 5. Run
```bash
python main.py
```

First launch downloads your model from HuggingFace (~1 GB, takes ~1 min).
After that it starts instantly from cache.

## Usage

Open your bot on Telegram and type:

| Query | What happens |
|-------|-------------|
| `bghit sneakers Nike f Casablanca b 300 dh` | Finds Nike sneakers near 300 MAD in Casablanca |
| `بغيت نشري تيشرت نايك أحمر ف الدار البيضاء` | Arabic Darija, finds red Nike t-shirts |
| `wach kayn laptop Samsung f Rabat b 8000 dh` | Samsung laptops ~8000 MAD in Rabat |

**Commands:**
- `/start` — welcome message
- `/help`  — usage guide
- `/debug` — shows raw NER output for your last query (for testing)

## Project structure

```
darija_ner_mvp/
├── main.py                      ← Telegram bot + entry point
├── requirements.txt
├── .env.example                 ← copy to .env and fill in tokens
├── agents/
│   ├── ner_agent.py             ← loads your HuggingFace model
│   ├── orchestrator.py          ← coordinates all agents
│   ├── research_agent.py        ← builds queries + calls scrapers
│   ├── market_agent.py          ← normalizes prices + filters
│   └── decision_agent.py        ← scores + picks best product
└── scrapers/
    ├── google_shopping.py       ← Google Shopping scraper
    └── avito.py                 ← Avito.ma scraper
```

## Troubleshooting

**Model takes too long to load:**
Set `device=-1` in `ner_agent.py` to force CPU (already the default).
For GPU, set `device=0` if you have CUDA.

**Google Shopping returns no results:**
Google changes its HTML structure frequently.
Open `scrapers/google_shopping.py`, inspect the CSS selectors,
and update `cards = soup.select("...")` to match current HTML.

**Avito returns no results:**
Same approach — inspect Avito.ma in browser, update selectors.

**Bot doesn't respond:**
Check `TELEGRAM_BOT_TOKEN` in `.env` is correct.
Run `python main.py` and watch the logs.
