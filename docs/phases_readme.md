# SentinelForge Delivery Phases

This README tracks the seven sequential phases required to deliver the full SentinelForge CCTV security platform. Each phase builds on the previous one so workstreams can run in parallel without rework.

---

## Phase 1 – Project Setup & Planning
- **Objectives**: Establish repo, environments, TimescaleDB+pgvector schema, datasets, and architecture diagrams.
- **Deliverables**: Base folder tree, Alembic migrations for `persons`, `sightings`, `patterns`, `footage_refs`, `.env` template, PlantUML/Mermaid diagrams, dataset ingestion scripts.
- **Steps**: Scaffold directories; install pinned dependencies; enable DB extensions; create hypertables; load known faces; seed synthetic unknowns; record env variables.
- **Dependencies**: Git, Docker Desktop (Postgres/Redis), Python 3.11, PlantUML/Mermaid.
- **Testing/Validation**: `alembic upgrade head`; sample inserts; confirm vector + Timescale extensions.
- **Pitfalls & Fixes**: pgvector requires `CREATE EXTENSION`; Timescale on Docker needs `timescaledb-tune`; ARM builds for dlib require swap or precompiled wheels.

## Phase 2 – Detection Engine (CV Core)
- **Objectives**: Real-time face detection/classification pipeline with multi-camera ingest.
- **Deliverables**: `detection/engine.py`, preprocessing utilities, cascade configs, unit tests.
- **Steps**: Implement CLAHE preprocessing, Laplacian blur filtering, cascade detection, `face_recognition` embeddings, similarity scoring, DBSCAN clustering for unknowns, threaded capture.
- **Dependencies**: OpenCV 4.10+, dlib, face_recognition, NumPy, threading queues, optional CUDA.
- **Testing/Validation**: Pytest for frame detection; integration run against RTSP simulator; FPS >20 for 1080p streams on Pi 5.
- **Pitfalls & Fixes**: Stream drops → exponential backoff reconnect; low light → gain adjustment/IR filter; CPU overload → batch every 5 frames.

## Phase 3 – Logging & Storage Layer (FastAPI Backend)
- **Objectives**: Secure API for event ingestion, storage, privacy enforcement, and ALFIE hooks.
- **Deliverables**: `api/main.py`, Pydantic models, async SQLAlchemy layer, Celery tasks, JWT auth middleware, `/api/alfie/alert` webhook.
- **Steps**: Create `/log_sighting`; encrypt embeddings with Fernet; store event metadata; calculate flag levels; emit outbound webhook; schedule TTL purge for unknowns (>90 days); add rate limiting (SlowAPI) and Sentry logging.
- **Dependencies**: FastAPI, Uvicorn, SQLAlchemy[asyncio], Redis, Celery, Fernet, PyJWT.
- **Testing/Validation**: Postman test plan; load test (100 req/s) via Locust; ensure TTL cron removes stale rows.
- **Pitfalls & Fixes**: Async session leaks → sessionmaker per request; pgvector search latency → IVFFlat index; webhook retries via Celery.

## Phase 4 – Analytics Engine (Pattern Detection)
- **Objectives**: Pattern mining, anomaly detection, clustering, bias audit.
- **Deliverables**: `analytics/engine.py`, Isolation Forest models, DBSCAN clustering routines, Celery beat schedule, audit scripts.
- **Steps**: Build Pandas feature extraction; train/test Isolation Forest for anomaly score; cluster unknown embeddings; publish metrics to `patterns` table; create bias audit harness using LFW/RFW.
- **Dependencies**: scikit-learn, Pandas, NumPy, optional Prophet, joblib for model persistence.
- **Testing/Validation**: Unit tests for compute functions; cron dry-runs; verify anomaly_score >0.7 triggers alerts.
- **Pitfalls & Fixes**: Overfitting → cross-validation; large embeddings → PCA to 50 dims; privacy → add differential noise before export.

## Phase 5 – Dashboard (Frontend UI)
- **Objectives**: Dash UI for live monitoring, timelines, unknown galleries, reports (current focus).
- **Deliverables**: `dashboard/app.py`, services (`api_client`, `socket_client`, `config`), CSS assets, tests.
- **Steps**: Implement Overview/Persons/Unknowns/Reports tabs; integrate Socket.IO; add KPI cards and heatmaps; build export buttons; enforce JWT usage; add role-aware toggles.
- **Dependencies**: Dash, Plotly, dash-bootstrap-components, python-socketio client.
- **Testing/Validation**: `dash.testing` callback tests; WebSocket mock harness; manual UX review (<2s load target).
- **Pitfalls & Fixes**: WebSocket disconnects → auto-reconnect; large galleries → pagination; RBAC compliance → hide unknown thumbnails by default.

## Phase 6 – Deployment, Testing & Monitoring
- **Objectives**: Containerize services, set up CI/CD, monitoring, and Raspberry Pi edge deploy.
- **Deliverables**: `docker-compose.yml`, Dockerfiles, GitHub Actions pipeline, Prometheus exporters, health endpoints, systemd scripts for Pi.
- **Steps**: Build multi-stage images; configure Celery worker/beat; wire Prometheus & Grafana; integrate Sentry; run e2e tests via ngrok for webhooks.
- **Dependencies**: Docker, docker-compose, GitHub Actions, Prometheus, Sentry.
- **Testing/Validation**: Smoke (`docker compose up`), stress test (10 cams), benchmark latency (<500ms e2e) and accuracy (>85%).
- **Pitfalls & Fixes**: Pi resource limits → TensorRT/TFLite; Docker image size → slim base + multi-stage build; webhook exposure → ngrok + IP allowlists.

## Phase 7 – Compliance, Ethics & Expansion
- **Objectives**: Finalize privacy compliance, “right to be forgotten” APIs, audit logs, documentation, and expansion playbook.
- **Deliverables**: Compliance report, bias audit results, opt-in/out APIs, audit logging middleware, final README updates, customer onboarding checklist.
- **Steps**: Implement GDPR-style deletion APIs; log every dashboard/data access; publish bias metrics; document cost model and scaling strategy; prep S3 lifecycle policies.
- **Dependencies**: Logging stack (ELK/Opensearch), legal review, documentation tooling (MkDocs/Sphinx).
- **Testing/Validation**: Automated deletion tests; audit-log integrity checks; manual compliance review sign-off.
- **Pitfalls & Fixes**: Data residuals → verify cascading deletes; audit volume storage → cold-tier logs; privacy vs analytics tension → configurable anonymization levels.
