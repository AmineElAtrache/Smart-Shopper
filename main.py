"""
main.py
────────
Telegram bot entry point.

Run with:
    python main.py

The bot starts polling Telegram for new messages.
Every message triggers the full agent pipeline.
"""

import asyncio
import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from agents.ner_agent    import NERAgent
from agents.orchestrator import Orchestrator
from utils               import log_user_interaction

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Load environment variables ────────────────────────────────────────────────
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not set in .env file")

# ── Load NER model once at startup ────────────────────────────────────────────
# (expensive — ~30 seconds first time, cached after)
logger.info("Loading NER model at startup...")
ner_agent    = NERAgent()
orchestrator = Orchestrator(ner_agent)
logger.info("All agents ready.")


# ── Telegram handlers ─────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    await update.message.reply_text(
        "👋 *Darija NER Shopping Assistant*\n\n"
        "Tell me what you're looking for in Darija — Arabic or Latin script!\n\n"
        "*Examples:*\n"
        "  • `bghit sneakers Nike f Casablanca b 300 dh`\n"
        "  • `بغيت نشري تيشرت نايك أحمر ف الدار البيضاء`\n"
        "  • `wach kayn laptop Samsung f Rabat b 8000 dh`\n\n"
        "_I will extract what you want, search the web, compare prices, and recommend the best option._",
        parse_mode=ParseMode.MARKDOWN,
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    await update.message.reply_text(
        "ℹ️ *How to use:*\n\n"
        "Just type your query in Darija. I understand:\n"
        "  🛍️ *Products* — sneakers, laptop, telfon, جلابة...\n"
        "  🏷️ *Brands* — Nike, Samsung, Zara, نايك...\n"
        "  💰 *Prices* — 300 dh, 1000-2000 dh, ألف درهم...\n"
        "  📍 *Cities* — Casablanca, Rabat, الرباط...\n"
        "  🎨 *Colors* — rouge, أحمر, akhdar...\n\n"
        "*Commands:*\n"
        "  /start — welcome message\n"
        "  /help  — this message\n"
        "  /debug — show raw NER output for your last query",
        parse_mode=ParseMode.MARKDOWN,
    )


async def debug_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /debug command — show raw NER output."""
    last_query = context.user_data.get("last_query")
    if not last_query:
        await update.message.reply_text("Send a query first, then /debug to see the NER output.")
        return

    entities = ner_agent.extract(last_query)
    summary  = ner_agent.format_summary(entities)
    raw_text = "\n".join(
        f"  [{e['entity_group']}] '{e['word']}' ({e['score']:.3f})"
        for e in entities.get("raw", [])
    )

    await update.message.reply_text(
        f"🔬 *NER Debug for:* `{last_query}`\n\n"
        f"```\n{summary}\n```\n\n"
        f"*Raw entities:*\n```\n{raw_text or '(none)'}\n```",
        parse_mode=ParseMode.MARKDOWN,
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle every text message — main pipeline."""
    query = update.message.text.strip()
    user  = update.effective_user
    logger.info(f"Message from {user.first_name} ({user.id}): '{query}'")

    # Save for /debug
    context.user_data["last_query"] = query

    # Show typing indicator while processing
    await update.message.chat.send_action("typing")

    # Run full agent pipeline
    try:
        response = await orchestrator.handle(query)
        
        # Extract entities for logging
        entities = ner_agent.extract(query)
        
        # Log user interaction with entities
        log_user_interaction(user, query, entities, response)
        
    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
        response = "❌ Something went wrong. Please try again."

    # Send response (Telegram Markdown)
    try:
        await update.message.reply_text(
            response,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=False,
        )
    except Exception as e:
        # Fallback: send without markdown if formatting fails
        logger.warning(f"Markdown send failed, sending plain: {e}")
        await update.message.reply_text(response)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help",  help_cmd))
    app.add_handler(CommandHandler("debug", debug_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is running — press Ctrl+C to stop")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
