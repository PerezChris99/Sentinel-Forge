# SentinelForge Engineering Delivery Plan

This document is the authoritative implementation roadmap. It separates repository-complete engineering from environment-dependent infrastructure and third-party work.

## Phase 1 — Canonical Architecture
**Status: Complete**

- Consolidated the most complete implementation into the repository root.
- Removed the duplicated nested application tree.
- Removed generated egg-info artifacts.
- Established one authoritative code path.

## Phase 2 — Packaging and CI Foundation
**Status: Complete**

- Normalized pyproject metadata and dependency groups.
- Added deterministic pytest configuration.
- Repaired the stale dashboard test.
- Added GitHub Actions for tests, compilation, and linting.

## Phase 3 — Runtime Safety, Health, and Privacy
**Status: Complete**

- Centralized runtime configuration.
- Added production secret validation.
- Added explicit production CORS requirements.
- Prevented silent SQLite fallback in production.
- Added /live, /ready, /health, and /metrics.
- Added privacy deletion and retention APIs.
- Added runtime regression tests.

## Phase 4 — Containerization and Service Orchestration
**Status: Complete**

- Added production Dockerfile.
- Added PostgreSQL/TimescaleDB service.
- Added Redis service.
- Added FastAPI service.
- Added Celery worker and beat services.
- Added health checks.
- Added migration-aware startup entrypoint.

## Phase 5 — Persistence Correctness and Smoke Coverage
**Status: Complete**

- Aligned Pattern ORM fields with analytics tasks and migration history.
- Added nullable pattern ownership for anonymous analytics.
- Added migration 003.
- Hardened Celery retention execution against event-loop misuse.
- Added API liveness/root smoke coverage.

## Phase 6 — Security and Audit Hardening
**Status: Complete**

- Added protected audit-log review.
- Added authentication audit events.
- Added request-level audit middleware.
- Prevented public administrator self-assignment.
- Added controlled first-admin bootstrap.
- Documented bootstrap and production security requirements.

## Phase 7 — Documentation and CI Stabilization
**Status: In progress**

- Replaced the stale README with an architecture-first engineering document.
- Added Mermaid architecture, event-lifecycle, investigation, and intelligence-flow diagrams.
- Corrected roadmap language so application completeness is not confused with deployed production readiness.
- Stabilize CI until the complete application test gate is green.

## Phase 8 — Environment and Observability
**Status: Environment-dependent**

Repository-side code is prepared for:

- Prometheus-compatible scraping.
- Container health checks.
- Redis-backed workers.
- PostgreSQL/TimescaleDB.
- Sentry or equivalent external error monitoring.

Remaining work requires deployment resources, credentials, DNS/TLS, monitoring infrastructure, and operational policy.

## Phase 9 — Real-World Validation
**Status: Environment-dependent**

- Connect real RTSP/IP cameras.
- Validate reconnect and stream-loss behavior.
- Benchmark multiple simultaneous cameras.
- Measure end-to-end event latency.
- Measure detection/tracking accuracy against a representative validation set.
- Validate backups and restores.
- Conduct security testing.
- Complete legal/privacy review.
- Validate GPU/edge deployments where required.

## Definition of Done

A repository phase is complete only when:

1. Implementation exists.
2. Tests cover the critical behavior.
3. CI can execute the validation.
4. Failure behavior is defined.
5. Documentation reflects reality.
6. The phase does not depend on an unimplemented earlier phase.

A deployment phase is complete only after the actual target environment has been provisioned and validated.

## Git workflow

Every engineering phase follows:

~~~text
Perez branch
    ↓
Detailed commits
    ↓
Pull request to main
    ↓
CI / validation
    ↓
Merge
    ↓
Next phase starts from updated main
~~~

No phase is considered merged until its changes are present on main.
