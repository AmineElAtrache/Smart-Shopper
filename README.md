# Smart Shopper — scaffold

This repository contains the **folder layout**, **Python dependency manifest** (`pyproject.toml`), **Docker Compose** for local Kafka/Redis/Mongo (and optional Jaeger), **Protobuf contract** for the NER service, and **empty placeholders** for agents and shared modules.

Implementation is intentionally deferred: wire Kafka topics, memory clients, and serving images according to your architecture document.

## Quick start (infrastructure only)

```bash
copy .env.example .env
docker compose up -d kafka redis mongodb
```

Optional tracing profile:

```bash
docker compose --profile observability up -d
```

## Layout

See the architecture document you provided for topic names, agent boundaries, and memory tiers. The tree under `agents/`, `gateway/`, `models/`, `shared/`, and `k8s/` mirrors that specification.
