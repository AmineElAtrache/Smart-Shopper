# Implemented Plan Explanation

This document explains the deployment-readiness plan that was implemented for Smart Shopper. It describes what each phase added, why it exists, and which files are responsible for it.

Important status note: the project has been expanded toward production readiness, but runtime readiness must still be proven by running tests, Docker builds, and end-to-end Kafka smoke checks on the target machine.

## 1. Stabilized Current MVP

Goal: make the existing MVP clearer, more consistent, and easier to verify before adding production architecture.

Implemented work:

- Updated dependency alignment for generated gRPC code.
- Updated project documentation to reflect the newer NER, gateway, scraper, generator, governance, memory, and deployment work.
- Added explicit deployment and operations documentation.

Important files:

- `pyproject.toml`
- `requirements.txt`
- `README.md`
- `PFA_PROJECT_FULL_OVERVIEW.md`
- `docs/deployment.md`
- `docs/runbook.md`

Why it matters:

The generated file `generated/ner/v1/ner_pb2_grpc.py` requires `grpcio>=1.81.1`. The Python dependencies now match that requirement, reducing the chance that the NER gRPC service fails at import time.

## 2. Runtime Contracts

Goal: make services behave like deployable long-running workers instead of only local scripts.

Implemented work:

- Added shared runtime utilities for health checks, metrics, retry helpers, and structured logging.
- Added `/healthz`, `/readyz`, and `/metrics` support to long-running service entrypoints.
- Improved Kafka producer behavior with retry support and per-topic metrics.
- Added production-oriented settings for service names, metrics, scraping, LLM, NER, cache, and group IDs.

Important files:

- `shared/runtime/health.py`
- `shared/runtime/metrics.py`
- `shared/runtime/retry.py`
- `shared/runtime/logging.py`
- `shared/events/kafka.py`
- `shared/config/settings.py`
- `.env.example`

Why it matters:

Kubernetes needs health and readiness probes. Prometheus needs metrics. Long-running Kafka workers need retry behavior and clear runtime settings.

## 3. Event Contracts And Topics

Goal: support the full PFA architecture with event contracts, not just the original MVP topics.

Implemented work:

- Added topics for ambient ticks, price history, cache writes, and dead-letter errors.
- Added schemas for watch state, cache writes, price snapshots, governance severity, and error events.

Important files:

- `shared/events/topics.py`
- `shared/events/schemas.py`

Important topics:

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

Why it matters:

The final architecture needs more than the basic request-response flow. It needs background monitoring, cache persistence, auditability, and error handling.

## 4. Core Pipeline Hardening

Goal: make the MVP pipeline closer to production behavior.

Implemented work:

- NER gRPC service now performs model warmup.
- Decision events now preserve the original query so downstream services can cache and personalize correctly.
- Deduplication was moved into a standalone decision tool.
- Fraud/risk checks were added and integrated into trust scoring.
- Agent Generator now supports template fallback plus optional HTTP LLM generation.
- Generator writes final responses to global Redis cache.

Important files:

- `models/ner/grpc_server.py`
- `agents/decision/agent.py`
- `agents/decision/tools/dedup_engine.py`
- `agents/decision/tools/fraud_detector.py`
- `agents/decision/tools/scoring_engine.py`
- `agents/agent_generator/agent.py`
- `agents/agent_generator/tools/llm_client.py`

Why it matters:

The system can now preserve enough context to cache responses, personalize output, and penalize risky listings.

## 5. Three-Tier Memory Architecture

Goal: implement the PFA memory design in a clean, reusable way.

### Tier 1: Global Shared Memory

Purpose:

- Shared across users.
- Stores product response cache, price history, site health, and robots snapshots.

Implementation:

- `shared/memory/global_memory.py`

Backing store:

- Redis.

Used by:

- Agent Generator for response cache writes.
- Orchestrator through product cache lookup.
- Future scraper/governance flows for site health and robots cache.

### Tier 2: Per-User Shared Memory

Purpose:

- Shared user memory across agents.
- Stores user preferences, history, preferred city, preferred budget, preferred sites, and watches.

Implementation:

- `shared/memory/user_memory.py`

Backing stores:

- MongoDB for persistent data.
- Redis for hot user profile cache.

Used by:

- Gateway records inbound and outbound user history.
- Orchestrator applies remembered preferences to incomplete queries.
- Ambient Scheduler stores watch metadata per user.

### Tier 3: Private Behavioral Memory

Purpose:

- Private to Agent Generator.
- Stores tone, language, preferred sources, response count, and generated-response interactions.

Implementation:

- `shared/memory/behavioral_memory.py`
- `agents/agent_generator/tools/behavior_analyzer.py`

Backing store:

- MongoDB.

Used by:

- Agent Generator to build private behavior context for LLM response generation.

Factory:

- `shared/memory/factory.py`

Tests:

- `tests/unit/test_memory_tiers.py`

Why it matters:

This separates global reusable knowledge from user-specific memory and private behavioral personalization. That separation is important for privacy, maintainability, and the multi-agent architecture.

## 6. Scraping Layer Production Support

Goal: prepare scrapers for safer and more scalable production operation.

Implemented work:

- Added Redis-backed rate limiter.
- Added robots.txt checker with Redis caching.
- Added PII scanner for governance.
- Added proxy rotator helper.
- Added optional Scrapy runner helper.

Important files:

- `agents/governance/rules/pii_scanner.py`
- `agents/governance/rules/rate_limiter.py`
- `agents/governance/rules/robots_checker.py`
- `agents/webscraping/tools/proxy_rotator.py`
- `agents/webscraping/tools/scrapy_runner.py`

Why it matters:

Scraping needs legal and operational controls: rate limits, robots policy checks, proxy support, and auditable violations.

## 7. Ambient Scheduler

Goal: implement background price monitoring from the PFA architecture.

Implemented work:

- Added an Ambient Scheduler service.
- Consumes `ambient.watch`.
- Persists watches in MongoDB.
- Re-emits scrape tasks when watches are due.
- Mirrors watch metadata into per-user memory.

Important file:

- `agents/ambient_scheduler/scheduler.py`

Why it matters:

This enables background monitoring for price drops and future deal discovery instead of only one-time searches.

## 8. Governance Agent

Goal: add audit and policy controls around the event-driven architecture.

Implemented work:

- Added Governance Agent runtime.
- Consumes core topics.
- Publishes `gov.audit`.
- Publishes `gov.violation` when PII is detected.
- Uses PII masking to avoid storing sensitive data directly in audit payloads.

Important files:

- `agents/governance/agent.py`
- `agents/governance/rules/pii_scanner.py`

Why it matters:

Governance makes the system auditable and safer, especially when scraping external sources and storing user data.

## 9. Containers

Goal: make every service container-buildable.

Implemented work:

- Added reusable service Dockerfile.
- Added dedicated NER Dockerfile that pre-downloads the Hugging Face model.
- Added full local compose graph for production-like smoke testing.

Important files:

- `docker/Dockerfile.service`
- `docker/Dockerfile.ner`
- `docker-compose.full.yml`

Why it matters:

NER has different runtime requirements from smaller agents. The model should be cached or baked into the image so production containers do not redownload it on every startup.

## 10. Kubernetes And AWS Deployment

Goal: add EKS-ready deployment structure.

Implemented work:

- Added Kubernetes base manifests.
- Added dev, staging, and prod overlays.
- Added deployments, services, config map, HPA, namespace, and secret example.

Important files:

- `deploy/k8s/base/kustomization.yaml`
- `deploy/k8s/base/namespace.yaml`
- `deploy/k8s/base/configmap.yaml`
- `deploy/k8s/base/secrets.example.yaml`
- `deploy/k8s/base/deployments.yaml`
- `deploy/k8s/base/services.yaml`
- `deploy/k8s/base/hpa.yaml`
- `deploy/k8s/overlays/dev/kustomization.yaml`
- `deploy/k8s/overlays/staging/kustomization.yaml`
- `deploy/k8s/overlays/prod/kustomization.yaml`

Recommended AWS services:

- EKS for Kubernetes.
- MSK or Strimzi Kafka for Kafka.
- ElastiCache Redis for cache and rate limits.
- MongoDB Atlas or validated DocumentDB-compatible storage.
- ECR for container images.
- Secrets Manager or External Secrets Operator for credentials.
- S3 or baked images for model artifacts.

Why it matters:

The repo now has a real deployment structure instead of only local scripts.

## 11. Observability

Goal: support production monitoring and operations.

Implemented work:

- Prometheus config now includes Smart Shopper service targets.
- Alert rules were added.
- Starter Grafana dashboard was added.
- Service entrypoints expose `/healthz`, `/readyz`, and `/metrics`.

Important files:

- `monitoring/prometheus.yml`
- `monitoring/alerts.yml`
- `monitoring/grafana-dashboard.json`
- `shared/runtime/health.py`
- `shared/runtime/metrics.py`

Why it matters:

Without observability, it is very difficult to know whether Kafka, scraping, NER, generator, or gateway is the source of a production problem.

## 12. CI/CD And Smoke Testing

Goal: create a basic path from code to verification.

Implemented work:

- Added GitHub Actions workflow for tests, Kubernetes manifest rendering, and Docker builds.
- Added Kafka smoke test script.
- Added deployment readiness tests.

Important files:

- `.github/workflows/ci.yml`
- `scripts/smoke_kafka_flow.py`
- `tests/unit/test_deployment_readiness.py`
- `tests/unit/test_memory_tiers.py`

Why it matters:

CI helps prevent broken imports, failing tests, invalid manifests, or broken Docker builds from reaching deployment.

## 13. Verification Still Required

The architecture and implementation were added, but the project must still be verified on the machine or CI runner.

Minimum commands:

```powershell
python -m pip install -e ".[dev]"
python -m pytest tests\unit -q
python -m scripts.run_local_pipeline
docker compose -f docker-compose.full.yml up --build
python -m scripts.smoke_kafka_flow
kubectl kustomize deploy/k8s/base
```

Expected outcome:

- Unit tests pass.
- Local no-Kafka pipeline returns a final response.
- Docker Compose starts all services.
- Kafka smoke test receives `response.outbound`.
- Kubernetes manifests render successfully.

Until those checks pass, the project should be considered deployment-prepared, not deployment-proven.
