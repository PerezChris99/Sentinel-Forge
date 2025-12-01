# SentinelForge (Web App Focus)

SentinelForge is an OpenCV-powered CCTV intelligence platform. This iteration concentrates on **Phase 5 – Dashboard**, providing a Dash/Plotly front-end for live monitoring, forensic review, and reporting workflows. The remaining subsystems (detection, API, analytics) are stubbed through mock providers so the UI can be developed independently.

## Repo Layout

```
sentinelforge/
├── api/              # FastAPI backend (future work)
├── analytics/        # Pattern analysis jobs
├── dashboard/        # Dash web application (current focus)
│   ├── assets/       # CSS / static assets
│   ├── components/   # UI building blocks (coming soon)
│   └── services/     # API & socket helpers
├── db/               # Database migrations / schema
├── detection/        # OpenCV + embeddings engine
├── docs/             # Architecture & dashboard plan
├── docker/           # Deployment assets
├── src/              # Shared utilities
└── tests/            # Pytest suites
```

## Dashboard Quickstart

1. **Install dependencies** (Python 3.11+):
   ```powershell
   cd "<path-to-sentinelforge>"
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -e .[test]
   ```
2. **Configure env vars**: copy `.env.example` → `.env` (or export manually). For standalone mock mode leave defaults; to point at a live API update `DASHBOARD_API_URL`, `DASHBOARD_SOCKET_URL`, and `JWT_TOKEN`.
3. **Run the dashboard**:
   ```powershell
   $env:SENTINELFORGE_USE_MOCKS="1"   # optional (default)
   python -m dashboard.app
   ```
   Visit `http://127.0.0.1:8050`.

## Key Features Implemented

- **Overview tab** with KPI cards, activity heatmap, and alert ticker fed by WebSocket/mocked live events.
- **Persons tab** featuring consent/timeline context for known individuals.
- **Unknowns tab** presenting filtered galleries of unknown clusters (flag slider + manual refresh).
- **Reports tab** linking to CSV/PDF exports and ALFIE insight placeholder.
- **Live data plumbing** via `dashboard/services/api_client.py` and `socket_client.py` with seamless fallback to deterministic mock data.

## Configuration Flags

| Variable | Description | Default |
| --- | --- | --- |
| `SENTINELFORGE_USE_MOCKS` | Use built-in mock API/events instead of real backend | `1` |
| `SENTINELFORGE_ENABLE_SOCKET` | Enable Socket.IO client for live events | `0` |
| `SENTINELFORGE_MAX_EVENTS` | Number of live events retained in memory | `200` |
| `DASHBOARD_API_URL` | FastAPI base URL | `http://localhost:8000` |
| `DASHBOARD_SOCKET_URL` | Socket.IO endpoint | _empty_ |
| `JWT_TOKEN` | Bearer token for authenticated calls | `demo-token` |

## Testing

Run lightweight dashboard tests (layout + mock API):
```powershell
pytest tests/test_dashboard_app.py tests/test_api_client.py
```

## Next Steps

1. Wire the dashboard to the real FastAPI backend and pgvector data sources.
2. Expand components into reusable modules under `dashboard/components/` and add role-based visibility controls.
3. Integrate Socket.IO server emitted by FastAPI to replace the mock emitter.
4. Add end-to-end tests covering live event ingestion and export workflows.
