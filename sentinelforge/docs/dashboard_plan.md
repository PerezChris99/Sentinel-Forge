# SentinelForge Dashboard (Phase 5) – Implementation Blueprint

_Updated: 2025-12-01_

## Objectives
- Deliver the Dash-based "SentinelForge" web application as the primary operator interface.
- Provide real-time monitoring, forensic review, and reporting workflows aligned with privacy, compliance, and scalability requirements.
- Ensure the dashboard can be developed and tested ahead of the rest of the stack by using mocked APIs/WebSocket streams, enabling parallel workstreams.

## Core Views & Components
1. **Overview Tab**
   - Live camera grid (base64 still frames refreshed via Socket.IO or HTTP polling fallback).
   - Alert ticker showing latest flagged events (`flag_level >= 2`).
   - KPI cards (active cameras, sightings in last hour, unknowns pending review).
2. **Persons Tab**
   - Searchable dropdown of known persons (populated from `/api/persons?status=known`).
   - Timeline visualization (Plotly scatter) per person showing timestamp vs. camera ID.
   - Panels for consent status, last sighting, anomaly summaries.
3. **Unknowns Tab**
   - Paginated gallery of unknown clusters with face thumbnails and metadata.
   - Filters for date range, flag level, camera, and cluster ID.
   - Action drawer to label/merge clusters into known persons via API call.
4. **Reports Tab**
   - Buttons to export CSV/PDF via `/api/reports` endpoints.
   - Embeddable analytics widgets (pattern heatmaps, anomaly distribution).
   - "ALFIE summary" placeholder to display incoming assistant insights when available.

## Data & API Contracts
- **Live Events WebSocket**: `/ws/events`
  - Message schema: `{ "event": "sighting", "person_id": "uuid|null", "camera_id": "cam-01", "flag_level": 0-3, "thumbnail_b64": "...", "timestamp": "ISO8601" }`.
- **REST Endpoints (FastAPI)**
  - `GET /api/persons?status=known|unknown` → list for dropdowns.
  - `GET /api/sightings?person_id=&range=` → timeline data.
  - `GET /api/unknown-clusters?page=&flag_level=` → gallery payloads.
  - `POST /api/unknown-clusters/{id}/label` → convert cluster to known person.
  - `GET /api/reports/daily.csv` & `/api/reports/daily.pdf` → downloads.
  - `POST /api/alfie/alert` (outbound hook triggered elsewhere; dashboard visualizes ack status).

## State Management Strategy
- Central `Store` class (in-memory) fed by WebSocket updates; fall back to periodic REST refresh (every 30 s) to correct drift.
- Dash callbacks read from `dcc.Store` components (e.g., `id="live-events-store"`).
- Use `diskcache` or Redis-backed caching when running under Gunicorn for production-safe callbacks.

## Privacy & Security Considerations
- Mask/blur UI thumbnails for unknowns until explicit reveal (toggle in UI respecting RBAC).
- Enforce JWT for all API calls (frontend stores tokens in memory, not local storage).
- Auto-hide data older than TTL (UI requests include `?min_timestamp=` ensuring backend purges propagate).
- Log all dashboard queries (for audit) via middleware hook.

## Performance Targets
- Initial load < 2 s on LAN for 5 cameras (prefetch summary data in single bulk request).
- Live updates < 250 ms from event ingestion to UI render (Socket.IO + lightweight DOM updates).
- Pagination to limit gallery payload to ≤ 20 items/page.

## Testing Plan
- Component tests with `dash.testing` for callbacks and state transitions.
- Visual regression via Snapshot of graph JSON structures (stored under `tests/__snapshots__`).
- WebSocket test harness using `pytest-asyncio` to emit fake events and assert UI store updates.

## Dependencies & Tooling
- Dash 2.15+, Plotly 5+, dash-bootstrap-components, python-socketio client, requests, authlib (JWT verification helper).
- For local dev, mock backend via `uvicorn mock_api:app --reload` and `socket.io` test server script under `dashboard/services/mocks/`.

## Delivery Checklist
- `dashboard/app.py` with layout, callbacks, and data services.
- `dashboard/services/api_client.py` for REST interactions with JWT handling.
- `dashboard/services/socket_client.py` for live updates.
- `dashboard/assets/` for CSS, favicon, etc.
- Unit/integration tests under `tests/test_dashboard_*.py` covering callbacks and data transforms.
- README section describing dashboard setup, env vars (`DASHBOARD_API_URL`, `DASHBOARD_SOCKET_URL`, `JWT_TOKEN`).
