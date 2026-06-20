"""Application settings loaded from environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    kafka_bootstrap_servers: str = Field(default="localhost:9092", alias="KAFKA_BOOTSTRAP_SERVERS")
    kafka_client_id: str = Field(default="smart-shopper-dev", alias="KAFKA_CLIENT_ID")

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    mongo_uri: str = Field(default="mongodb://localhost:27017", alias="MONGO_URI")
    mongo_db: str = Field(default="smart_shopper", alias="MONGO_DB")

    ner_grpc_host: str = Field(default="localhost", alias="NER_GRPC_HOST")
    ner_grpc_port: int = Field(default=50051, alias="NER_GRPC_PORT")

    orchestrator_group_id: str = Field(
        default="orchestrator-agent",
        alias="ORCHESTRATOR_GROUP_ID",
    )
    decision_group_id: str = Field(default="decision-agent", alias="DECISION_GROUP_ID")
    decision_batch_wait_seconds: float = Field(default=2.0, alias="DECISION_BATCH_WAIT_SECONDS")


def get_settings() -> Settings:
    return Settings()
