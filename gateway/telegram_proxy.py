"""Telegram gateway for the Smart Shopper MVP.

The module keeps Telegram, Kafka, and MongoDB imports inside runtime paths so
unit tests can validate message conversion without requiring external services.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from shared.events.kafka import KafkaEventConsumer, KafkaEventProducer
from shared.events.schemas import Channel, InboundMessage, OutboundResponse
from shared.events.topics import MSG_INBOUND, RESPONSE_OUTBOUND
from shared.config.env import load_env_file
from shared.config import get_settings
from shared.memory import UserMemory
from shared.memory.factory import create_user_memory
from shared.runtime import HealthServer

DEFAULT_KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
DEFAULT_MONGODB_URI = "mongodb://localhost:27017"
DEFAULT_MONGODB_DATABASE = "smart_shopper"


def build_inbound_message(*, chat_id: int | str, text: str) -> InboundMessage:
    """Convert a Telegram message into the shared inbound contract."""
    return InboundMessage(
        user_id=f"telegram_{chat_id}",
        channel=Channel.TELEGRAM,
        text=text,
    )


def chat_id_from_user_id(user_id: str) -> int | None:
    """Recover a Telegram chat id from the stored Smart Shopper user id."""
    prefix = "telegram_"
    if not user_id.startswith(prefix):
        return None
    raw_chat_id = user_id.removeprefix(prefix)
    try:
        return int(raw_chat_id)
    except ValueError:
        return None


class MongoHistoryStore:
    """Small MongoDB history writer used by the gateway.

    If pymongo is unavailable or MongoDB cannot be reached during construction,
    the store becomes a no-op so the Telegram/Kafka MVP can still run locally.
    """

    def __init__(
        self,
        *,
        uri: str = DEFAULT_MONGODB_URI,
        database: str = DEFAULT_MONGODB_DATABASE,
        enabled: bool = True,
    ) -> None:
        self._collection: Any | None = None
        if not enabled:
            return

        try:
            from pymongo import MongoClient
        except ModuleNotFoundError:
            return

        client = MongoClient(uri, serverSelectionTimeoutMS=1000)
        self._collection = client[database]["telegram_history"]

    def record_inbound(self, event: InboundMessage, *, chat_id: int | str) -> None:
        if self._collection is None:
            return
        try:
            self._collection.insert_one(
                {
                    "request_id": event.request_id,
                    "user_id": event.user_id,
                    "chat_id": str(chat_id),
                    "direction": "inbound",
                    "text": event.text,
                    "timestamp": datetime.now(UTC),
                }
            )
        except Exception as exc:  # pragma: no cover - depends on external MongoDB state
            print(f"Could not record inbound Telegram history: {exc}")

    def record_outbound(self, event: OutboundResponse, *, chat_id: int) -> None:
        if self._collection is None:
            return
        try:
            self._collection.insert_one(
                {
                    "request_id": event.request_id,
                    "user_id": event.user_id,
                    "chat_id": str(chat_id),
                    "direction": "outbound",
                    "message": event.message,
                    "timestamp": datetime.now(UTC),
                }
            )
        except Exception as exc:  # pragma: no cover - depends on external MongoDB state
            print(f"Could not record outbound Telegram history: {exc}")


@dataclass(frozen=True)
class TelegramGatewayConfig:
    token: str
    kafka_bootstrap_servers: str = DEFAULT_KAFKA_BOOTSTRAP_SERVERS
    mongodb_uri: str = DEFAULT_MONGODB_URI
    mongodb_database: str = DEFAULT_MONGODB_DATABASE

    @classmethod
    def from_env(cls) -> TelegramGatewayConfig:
        load_env_file()
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is required to run the Telegram gateway.")
        return cls(
            token=token,
            kafka_bootstrap_servers=os.getenv(
                "KAFKA_BOOTSTRAP_SERVERS", DEFAULT_KAFKA_BOOTSTRAP_SERVERS
            ),
            mongodb_uri=os.getenv("MONGO_URI", DEFAULT_MONGODB_URI),
            mongodb_database=os.getenv("MONGO_DB", DEFAULT_MONGODB_DATABASE),
        )


class TelegramGateway:
    def __init__(
        self,
        *,
        config: TelegramGatewayConfig,
        producer: KafkaEventProducer | None = None,
        history_store: MongoHistoryStore | None = None,
        user_memory: UserMemory | None = None,
    ) -> None:
        self._config = config
        self._producer = producer or KafkaEventProducer(
            config.kafka_bootstrap_servers,
            client_id="telegram-gateway",
        )
        self._history_store = history_store or MongoHistoryStore(
            uri=config.mongodb_uri,
            database=config.mongodb_database,
        )
        self._user_memory = user_memory

    async def publish_telegram_text(self, *, chat_id: int | str, text: str) -> InboundMessage:
        event = build_inbound_message(chat_id=chat_id, text=text)
        await self._producer.publish(MSG_INBOUND, event, key=event.request_id)
        self._history_store.record_inbound(event, chat_id=chat_id)
        if self._user_memory is not None:
            try:
                await self._user_memory.record_search(event)
            except Exception as exc:  # pragma: no cover - external memory availability
                print(f"Could not record inbound user memory: {exc}")
        return event

    async def start(self) -> None:
        from telegram import Update
        from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

        application = ApplicationBuilder().token(self._config.token).build()

        async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            del context
            if update.effective_chat is None or update.message is None or update.message.text is None:
                return
            event = await self.publish_telegram_text(
                chat_id=update.effective_chat.id,
                text=update.message.text,
            )
            await update.message.reply_text(
                f"Request received ({event.request_id}). I am looking for offers now."
            )

        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

        await self._producer.start()
        consumer_task: asyncio.Task[None] | None = None
        try:
            await application.initialize()
            await application.start()
            if application.updater is None:
                raise RuntimeError("Telegram application updater is not available.")
            await application.updater.start_polling()
            print("Telegram gateway started. Listening for messages and outbound responses.")

            consumer_task = asyncio.create_task(self._consume_outbound(application.bot))
            await asyncio.Event().wait()
        finally:
            if consumer_task is not None:
                consumer_task.cancel()
                try:
                    await consumer_task
                except asyncio.CancelledError:
                    pass
            if application.updater is not None:
                await application.updater.stop()
            await application.stop()
            await application.shutdown()
            await self._producer.stop()

    async def _consume_outbound(self, bot: Any) -> None:
        consumer = KafkaEventConsumer(
            RESPONSE_OUTBOUND,
            bootstrap_servers=self._config.kafka_bootstrap_servers,
            group_id="telegram-gateway",
            client_id="telegram-gateway",
        )
        await consumer.start()
        try:
            async for event in consumer.events(OutboundResponse):
                chat_id = chat_id_from_user_id(event.user_id)
                if chat_id is None:
                    print(f"Skipping outbound response with unknown Telegram user_id: {event.user_id}")
                    continue
                await bot.send_message(chat_id=chat_id, text=event.message)
                self._history_store.record_outbound(event, chat_id=chat_id)
                if self._user_memory is not None:
                    try:
                        await self._user_memory.record_response(event)
                    except Exception as exc:  # pragma: no cover - external memory availability
                        print(f"Could not record outbound user memory: {exc}")
        finally:
            await consumer.stop()


async def main() -> None:
    settings = get_settings()
    health = HealthServer(host=settings.metrics_host, port=settings.metrics_port)
    await health.start()
    gateway = TelegramGateway(
        config=TelegramGatewayConfig.from_env(),
        user_memory=create_user_memory(settings),
    )
    try:
        await gateway.start()
    finally:
        await health.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Telegram gateway stopped.")
