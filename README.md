# SentinelForge

**CCTV intelligence, real-time security operations, analytics, and investigation platform.**

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15%2B-336791)
![CI](https://img.shields.io/badge/CI-GitHub%20Actions-2088FF)
![Status](https://img.shields.io/badge/Status-Application%20Hardening%20Complete%20%7C%20Infra%20Pending-orange)

SentinelForge is a security-operations platform for ingesting camera events, detecting and tracking people and objects, correlating activity across cameras, generating alerts, managing incidents, and investigating relationships between entities.

The application is being hardened to production standards first. Live camera infrastructure, GPU/edge hardware, hosted observability, credentials, external integrations, and jurisdiction-specific governance remain environment-specific.

## What SentinelForge does

- Camera intelligence for IP, RTSP, USB, and file sources.
- Face detection, embeddings, and known/unknown classification.
- YOLO object detection with dependency-safe fallback.
- Multi-object tracking with IoU, optional ReID, dwell time, velocity, and cross-camera reconciliation.
- Behavior analytics for loitering, crowd density, speed/direction, wrong-way movement, intrusion, tailgating, and stopped vehicles.
- Vehicle intelligence including plate-region extraction, optional OCR, plate validation, vehicle type, and color classification.
- Geospatial intelligence including zones, occupancy, heatmaps, camera placement, and trajectories.
- Knowledge graph analysis with typed relationships, temporal correlation, shortest paths, connected components, and link strength.
- Security operations with RBAC, alerts, incidents, search, exports, audit trails, and real-time events.
- Privacy controls for subject deletion and unknown-data retention.
- Browser dashboard for operations and investigation.

## Architecture

~~~mermaid
flowchart LR
    CAM[IP / RTSP / USB / File Cameras]
    ING[Ingestion & Detection]
    TRK[Tracking + ReID]
    INT[Intelligence Engines]
    DB[(PostgreSQL + pgvector + TimescaleDB)]
    REDIS[(Redis)]
    API[FastAPI API]
    CEL[Celery Worker / Beat]
    WS[Socket.IO]
    UI[Security Operations Dashboard]
    AUD[Audit & Privacy Controls]

    CAM --> ING
    ING --> TRK
    TRK --> INT
    INT --> DB
    API --> DB
    API --> REDIS
    CEL --> DB
    CEL --> REDIS
    API --> WS
    WS --> UI
    DB --> UI
    API --> AUD
    AUD --> DB
~~~

### Event lifecycle

~~~mermaid
sequenceDiagram
    participant C as Camera
    participant D as Detection
    participant T as Tracker
    participant A as Analytics
    participant API as FastAPI
    participant DB as PostgreSQL
    participant UI as Dashboard

    C->>D: Frame / stream data
    D->>T: Objects + embeddings
    T->>A: Tracks + movement context
    A->>API: Security events
    API->>DB: Persist event
    API->>UI: Real-time event
    UI-->>API: Operator action
    API->>DB: Alert / incident / audit record
~~~

### Investigation model

~~~mermaid
flowchart TD
    P[Person]
    V[Vehicle]
    C[Camera]
    Z[Zone]
    T[Track]
    I[Incident]

    P -->|seen_with| V
    P -->|detected_by| C
    P -->|entered_zone| Z
    P -->|has_track| T
    T -->|detected_by| C
    V -->|detected_by| C
    P -->|involved_in| I
    V -->|associated_with| I
~~~

## Engineering status

| Phase | Area | Status |
|---|---|---|
| 1 | Canonical architecture | Complete |
| 2 | Packaging + CI foundation | Complete |
| 3 | Runtime safety + health + privacy | Complete |
| 4 | Containerization + service orchestration | Complete |
| 5 | Persistence correctness + smoke coverage | Complete |
| 6 | Audit + authentication hardening | Complete |
| 7 | Documentation + CI stabilization | In progress |
| 8 | Deployment / observability / edge | Environment-dependent |
| 9 | External integrations | Environment-dependent |

"Complete" means implemented in source control. It does not mean a production environment has been provisioned or real cameras, GPU hardware, hosted services, or external integrations have been connected.

## Repository structure

~~~text
.
├── api/
│   ├── main.py          # FastAPI application and runtime endpoints
│   ├── auth.py          # JWT, password hashing, RBAC
│   ├── audit.py         # Request-level audit middleware
│   ├── privacy.py       # Deletion and retention controls
│   ├── extended.py      # Security operations API
│   ├── websocket.py     # Real-time Socket.IO events
│   ├── celery_app.py    # Celery worker/beat configuration
│   └── tasks.py         # Background operational tasks
├── analytics/
│   ├── engine.py        # Pattern/anomaly analytics
│   ├── behavior.py      # Behavior intelligence
│   ├── geospatial.py    # Zones, heatmaps, trajectories
│   └── knowledge_graph.py
├── detection/
│   ├── engine.py        # Face detection pipeline
│   ├── yolo_engine.py   # Object detection
│   ├── tracker.py       # MOT + optional ReID
│   ├── vehicle.py       # Vehicle/LPR intelligence
│   └── sources.py       # Camera source abstractions
├── dashboard/           # Security operations console
├── db/                  # SQLAlchemy models
├── alembic/             # Database migrations
├── tests/               # Unit and application smoke tests
├── scripts/             # Deployment/startup helpers
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
~~~

## Local development

### Requirements

- Python 3.11+
- Git
- PostgreSQL 15+ with pgvector and TimescaleDB for production-like development
- Redis 7+ for background jobs and live events
- Optional CV dependencies for full camera intelligence

### Install

~~~bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test,cv]"
~~~

Windows PowerShell:

~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[test,cv]"
~~~

Copy .env.example to .env and configure local values.

For development, SentinelForge may fall back to SQLite when PostgreSQL is unavailable. Production mode explicitly refuses that fallback.

Start the API:

~~~bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
~~~

Endpoints:

- Dashboard: /dashboard/
- OpenAPI: /docs
- Liveness: /live
- Readiness: /ready
- Health: /health
- Metrics: /metrics

## Production-like container stack

The repository includes Compose services for PostgreSQL/TimescaleDB, Redis, FastAPI, Celery worker, and Celery beat.

~~~bash
cp .env.example .env
docker compose up --build
~~~

The API container applies Alembic migrations before startup. Worker and beat containers are configured not to race migrations.

Deployment credentials, TLS, DNS, firewall rules, camera credentials, backups, GPU drivers, and hosted observability remain deployment responsibilities.

## Security model

### Authentication

- JWT access tokens.
- Issuer and audience validation.
- Configurable token expiration.
- bcrypt password hashing.
- Inactive-account enforcement.

### Authorization

| Role | Intended access |
|---|---|
| viewer | Read-only operational visibility |
| operator | Operational response and incident handling |
| admin | Configuration, user administration, privacy, audit, and system control |

Public registration can only create viewer accounts.

The first administrator is created through the controlled bootstrap endpoint using BOOTSTRAP_ADMIN_TOKEN. Client input cannot self-assign administrator privileges.

### Runtime safety

Production requires:

- persistent SECRET_KEY
- persistent FERNET_KEY
- explicit CORS_ORIGINS
- PostgreSQL
- SENTINELFORGE_ENV=production

Unsafe production configurations fail fast instead of silently entering development mode.

## Privacy and compliance controls

Implemented application controls include:

- Permanent person deletion.
- Deletion of directly associated sightings.
- Deletion of associated analytics records.
- Knowledge-graph relationship cleanup.
- Configurable purge of old unknown sightings.
- Preserved administrative deletion audit records.
- Request-level audit logging.
- Administrator-only audit-log access.

Example endpoints:

~~~text
DELETE /api/privacy/person/{person_id}
POST   /api/privacy/retention/purge
GET    /api/privacy/policy
GET    /api/audit/logs
~~~

Legal/compliance certification, lawful-basis assessment, signage, retention approval, and organizational governance remain deployment and legal responsibilities.

## Testing and quality gates

~~~bash
pytest -q
python -m compileall -q api analytics dashboard db detection
~~~

GitHub Actions validates dependency installation, automated tests, Python compilation, and the hardened production surface with Ruff.

## Operational health

- /live — process liveness probe.
- /ready — database readiness probe.
- /health — application/database/Redis state.
- /metrics — stable Prometheus-compatible application availability metric.

Full infrastructure telemetry belongs in the deployment monitoring stack.

## Data and intelligence flow

~~~mermaid
flowchart TB
    F[Camera Frame]
    PRE[Pre-processing]
    FACE[Face Detection]
    OBJ[Object Detection]
    EMB[Embedding / ReID]
    TRACK[Track State]
    BEHAV[Behavior Analysis]
    VEH[Vehicle Intelligence]
    GEO[Geospatial Correlation]
    GRAPH[Knowledge Graph]
    EVENT[Security Event]
    ALERT[Alert]
    INCIDENT[Incident]
    AUDIT[Audit Record]

    F --> PRE
    PRE --> FACE
    PRE --> OBJ
    FACE --> EMB
    OBJ --> TRACK
    EMB --> TRACK
    TRACK --> BEHAV
    TRACK --> VEH
    TRACK --> GEO
    BEHAV --> EVENT
    VEH --> EVENT
    GEO --> EVENT
    EVENT --> GRAPH
    EVENT --> ALERT
    ALERT --> INCIDENT
    ALERT --> AUDIT
    INCIDENT --> AUDIT
~~~

## Roadmap

### Application engineering

- [x] Canonicalize duplicated application trees.
- [x] Normalize packaging and dependencies.
- [x] Establish GitHub Actions CI.
- [x] Production runtime safety validation.
- [x] Health and readiness endpoints.
- [x] Containerization.
- [x] Database migration alignment.
- [x] Privacy deletion and retention APIs.
- [x] Authentication audit trail.
- [x] Request audit middleware.
- [x] Controlled administrator bootstrap.
- [ ] Stabilize CI with all checks green.
- [ ] Complete camera-to-dashboard integration tests.
- [ ] Complete application performance benchmarks.
- [ ] Complete production observability dashboards.

### Environment and infrastructure

These cannot be truthfully completed in source control alone:

- [ ] Production PostgreSQL/TimescaleDB provisioning.
- [ ] Production Redis provisioning.
- [ ] TLS certificates and DNS.
- [ ] Secret-manager integration.
- [ ] Object/footage storage.
- [ ] Prometheus/Grafana/Sentry hosted configuration.
- [ ] Real RTSP camera fleet.
- [ ] GPU/edge hardware.
- [ ] Backup and disaster recovery infrastructure.
- [ ] Network/firewall policy.
- [ ] External ALFIE integration.
- [ ] OCR/model provider credentials.
- [ ] Legal/compliance sign-off.

## Operations

See [docs/OPERATIONS.md](docs/OPERATIONS.md) for the production startup, backup/restore, camera reliability, security operations, scaling, and acceptance runbook.

## Engineering principle

SentinelForge follows one rule:

> Do not call a feature production-ready merely because the code exists.

The complete readiness chain is:

~~~text
Code
  ↓
Tests
  ↓
CI
  ↓
Packaging
  ↓
Deployment
  ↓
Health checks
  ↓
Observability
  ↓
Security
  ↓
Recovery
  ↓
Real-world validation
~~~

## License

MIT
