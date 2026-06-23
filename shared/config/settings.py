"""Application settings loaded from environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    service_name: str = Field(default="smart-shopper", alias="SERVICE_NAME")
    environment: str = Field(default="local", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    metrics_host: str = Field(default="0.0.0.0", alias="METRICS_HOST")
    metrics_port: int = Field(default=8000, alias="METRICS_PORT")

    kafka_bootstrap_servers: str = Field(default="localhost:9092", alias="KAFKA_BOOTSTRAP_SERVERS")
    kafka_client_id: str = Field(default="smart-shopper-dev", alias="KAFKA_CLIENT_ID")
    kafka_dead_letter_enabled: bool = Field(default=True, alias="KAFKA_DEAD_LETTER_ENABLED")

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    cache_ttl_seconds: int = Field(default=1800, alias="CACHE_TTL_SECONDS")

    mongo_uri: str = Field(default="mongodb://localhost:27017", alias="MONGO_URI")
    mongo_db: str = Field(default="smart_shopper", alias="MONGO_DB")
    mongo_connect_timeout_ms: int = Field(default=1000, alias="MONGO_CONNECT_TIMEOUT_MS")

    ner_grpc_host: str = Field(default="localhost", alias="NER_GRPC_HOST")
    ner_grpc_port: int = Field(default=50051, alias="NER_GRPC_PORT")
    ner_grpc_timeout_seconds: float = Field(default=5.0, alias="NER_GRPC_TIMEOUT_SECONDS")
    ner_warmup_text: str = Field(default="Bghit Samsung phone b 3000 dh", alias="NER_WARMUP_TEXT")

    orchestrator_group_id: str = Field(
        default="orchestrator-agent",
        alias="ORCHESTRATOR_GROUP_ID",
    )
    decision_group_id: str = Field(default="decision-agent", alias="DECISION_GROUP_ID")
    decision_batch_wait_seconds: float = Field(default=2.0, alias="DECISION_BATCH_WAIT_SECONDS")
    scraper_group_id: str = Field(default="webscraping-agent", alias="SCRAPER_GROUP_ID")
    generator_group_id: str = Field(default="agent-generator", alias="GENERATOR_GROUP_ID")
    gateway_group_id: str = Field(default="telegram-gateway", alias="GATEWAY_GROUP_ID")
    ambient_group_id: str = Field(default="ambient-scheduler", alias="AMBIENT_GROUP_ID")
    governance_group_id: str = Field(default="governance-agent", alias="GOVERNANCE_GROUP_ID")

    scrape_timeout_seconds: float = Field(default=20.0, alias="SCRAPE_TIMEOUT_SECONDS")
    scrape_max_concurrency: int = Field(default=8, alias="SCRAPE_MAX_CONCURRENCY")
    domain_rate_limit_per_minute: int = Field(default=30, alias="DOMAIN_RATE_LIMIT_PER_MINUTE")

    llm_provider: str = Field(default="template", alias="LLM_PROVIDER")
    llm_http_base_url: str = Field(default="http://localhost:8081", alias="LLM_HTTP_BASE_URL")
    llm_api_key: str | None = Field(default=None, alias="LLM_API_KEY")
    llm_model: str = Field(default="llama-3.1-8b-instant", alias="LLM_MODEL")
    llm_timeout_seconds: float = Field(default=10.0, alias="LLM_TIMEOUT_SECONDS")

    telegram_bot_token: str | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    otel_exporter_otlp_endpoint: str | None = Field(
        default=None,
        alias="OTEL_EXPORTER_OTLP_ENDPOINT",
    )


def get_settings() -> Settings:
    return Settings()
