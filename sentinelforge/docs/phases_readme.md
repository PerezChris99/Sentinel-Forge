# SentinelForge Delivery Phases

This README tracks the seven sequential phases required to deliver the full SentinelForge CCTV security platform. Each phase builds on the previous one so workstreams can run in parallel without rework.

**Overall Progress**: `[████████░░] 71%` (5 of 7 phases completed)

---

## Phase 1 – Project Setup & Planning
**Status**: `[✅ Completed]`
- **Objectives**: Establish repo, environments, TimescaleDB+pgvector schema, datasets, and architecture diagrams.
- **Deliverables**: Base folder tree, Alembic migrations for `persons`, `sightings`, `patterns`, `footage_refs`, `.env` template, PlantUML/Mermaid diagrams, dataset ingestion scripts.
- **Steps**: Scaffold directories; install pinned dependencies; enable DB extensions; create hypertables; load known faces; seed synthetic unknowns; record env variables.
- **Dependencies**: Git, Docker Desktop (Postgres/Redis), Python 3.11, PlantUML/Mermaid.
- **Testing/Validation**: `alembic upgrade head`; sample inserts; confirm vector + Timescale extensions.
- **Pitfalls & Fixes**: pgvector requires `CREATE EXTENSION`; Timescale on Docker needs `timescaledb-tune`; ARM builds for dlib require swap or precompiled wheels.

## Phase 2 – Detection Engine (CV Core)
**Status**: `[✅ Completed]`
- **Objectives**: Real-time face detection/classification pipeline with multi-camera ingest.
- **Deliverables**: `detection/engine.py`, preprocessing utilities, cascade configs, unit tests.
- **Steps**: Implement CLAHE preprocessing, Laplacian blur filtering, cascade detection, `face_recognition` embeddings, similarity scoring, DBSCAN clustering for unknowns, threaded capture.
- **Dependencies**: OpenCV 4.10+, dlib, face_recognition, NumPy, threading queues, optional CUDA.
- **Testing/Validation**: Pytest for frame detection; integration run against RTSP simulator; FPS >20 for 1080p streams on Pi 5.
- **Pitfalls & Fixes**: Stream drops → exponential backoff reconnect; low light → gain adjustment/IR filter; CPU overload → batch every 5 frames.

## Phase 3 – Logging & Storage Layer (FastAPI Backend)
**Status**: `[✅ Completed]`
- **Objectives**: Secure API for event ingestion, storage, privacy enforcement, and ALFIE hooks.
- **Deliverables**: `api/main.py`, Pydantic models, async SQLAlchemy layer, Celery tasks, JWT auth middleware, `/api/alfie/alert` webhook.
- **Steps**: Create `/log_sighting`; encrypt embeddings with Fernet; store event metadata; calculate flag levels; emit outbound webhook; schedule TTL purge for unknowns (>90 days); add rate limiting (SlowAPI) and Sentry logging.
- **Dependencies**: FastAPI, Uvicorn, SQLAlchemy[asyncio], Redis, Celery, Fernet, PyJWT.
- **Testing/Validation**: Postman test plan; load test (100 req/s) via Locust; ensure TTL cron removes stale rows.
- **Pitfalls & Fixes**: Async session leaks → sessionmaker per request; pgvector search latency → IVFFlat index; webhook retries via Celery.

## Phase 4 – Analytics Engine (Pattern Detection)
**Status**: `[✅ Completed]`
- **Objectives**: Pattern mining, anomaly detection, clustering, and bias audit capabilities.
- **Deliverables**: `analytics/engine.py` (AnalyticsEngine + BiasAuditor classes), `analytics/tasks.py` (Celery beat schedule), `tests/test_analytics.py`, comprehensive README, models directory.
- **Steps**: Built Pandas feature extraction (temporal, behavioral); trained/tested Isolation Forest for anomaly scoring; implemented DBSCAN clustering for unknowns; created 5 pattern types (frequent visitor, unusual hours, multi-camera, anomaly, unknown cluster); added bias audit harness with disparate impact calculation; integrated Celery beat schedule (4 periodic tasks); added model persistence with joblib.
- **Dependencies**: scikit-learn 1.3+, Pandas 2.0+, NumPy 1.24+, joblib 1.3+, PCA preprocessing optional.
- **Testing/Validation**: Unit tests for AnalyticsEngine and BiasAuditor (16 test cases); verify anomaly_score >0.7 triggers alerts; silhouette score validation for clustering; disparate impact 80% rule compliance.
- **Pitfalls & Fixes**: Overfitting → PCA to 50 dims for large embeddings; async session management in Celery tasks → proper asyncio.run() wrapper; model training requires ≥100 samples → graceful degradation; clustering noise handling → -1 label exclusion.

## Phase 5 – Dashboard (Frontend UI)
**Status**: `[✅ Completed]`
- **Objectives**: Minimalist HTML/CSS/JavaScript dashboard with Bootstrap and paper theme for live monitoring, timelines, unknown galleries, and reports.
- **Deliverables**: `dashboard/index.html`, `assets/custom.css` (paper theme), `assets/app.js` (vanilla JS), comprehensive API endpoints in FastAPI backend, README.
- **Steps**: Replaced Dash with vanilla HTML/CSS/JS; implemented Bootstrap-based grid layout; created paper theme with white/black minimalist aesthetic; built Overview/Persons/Unknowns/Reports tabs; integrated Chart.js for visualizations; added auto-refresh (5s interval); connected to FastAPI REST endpoints.
- **Dependencies**: Bootstrap 5.3, Chart.js 4.4, Inter font, vanilla JavaScript ES6+, FastAPI backend endpoints.
- **Testing/Validation**: Manual browser testing; API endpoint validation; responsive design check; auto-refresh verification.
- **Pitfalls & Fixes**: Initial Dash implementation replaced per user requirement; CSS file conflict resolved with replace_string_in_file; CORS enabled in FastAPI; comprehensive dashboard API endpoints added to main.py.

## Phase 6 – Deployment, Testing & Monitoring
**Status**: `[📅 Pending]`
- **Objectives**: Containerize services, set up CI/CD, monitoring, and Raspberry Pi edge deploy.
- **Deliverables**: `docker-compose.yml`, Dockerfiles, GitHub Actions pipeline, Prometheus exporters, health endpoints, systemd scripts for Pi.
- **Steps**: Build multi-stage images; configure Celery worker/beat; wire Prometheus & Grafana; integrate Sentry; run e2e tests via ngrok for webhooks.
- **Dependencies**: Docker, docker-compose, GitHub Actions, Prometheus, Sentry.
- **Testing/Validation**: Smoke (`docker compose up`), stress test (10 cams), benchmark latency (<500ms e2e) and accuracy (>85%).
- **Pitfalls & Fixes**: Pi resource limits → TensorRT/TFLite; Docker image size → slim base + multi-stage build; webhook exposure → ngrok + IP allowlists.

## Phase 7 – Compliance, Ethics & Expansion
**Status**: `[📅 Pending]`
- **Objectives**: Finalize privacy compliance, “right to be forgotten” APIs, audit logs, documentation, and expansion playbook.
- **Deliverables**: Compliance report, bias audit results, opt-in/out APIs, audit logging middleware, final README updates, customer onboarding checklist.
- **Steps**: Implement GDPR-style deletion APIs; log every dashboard/data access; publish bias metrics; document cost model and scaling strategy; prep S3 lifecycle policies.
- **Dependencies**: Logging stack (ELK/Opensearch), legal review, documentation tooling (MkDocs/Sphinx).
- **Testing/Validation**: Automated deletion tests; audit-log integrity checks; manual compliance review sign-off.
- **Pitfalls & Fixes**: Data residuals → verify cascading deletes; audit volume storage → cold-tier logs; privacy vs analytics tension → configurable anonymization levels.
