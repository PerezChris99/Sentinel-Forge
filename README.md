# SentinelForge

**Advanced CCTV Intelligence Platform with Real-Time Analytics & Face Recognition**

SentinelForge is a comprehensive security platform combining OpenCV-powered face detection, real-time WebSocket notifications, role-based access control, and live IP camera streaming. The system provides complete incident management, alert workflows, and advanced pattern analytics for enterprise security operations.

## 🚀 Latest Updates (December 2025)

### ✅ Fully Implemented Features

- **Real-Time WebSocket Communication** - Socket.IO server with live alerts, sightings, and camera status broadcasts
- **Authentication & RBAC** - JWT-based auth with Admin/Operator/Viewer roles and bcrypt password hashing
- **Camera Management** - Full CRUD for IP cameras with IP Webcam Pro integration and live MJPEG streaming
- **Enhanced Person Management** - Photo uploads with automatic face embedding extraction, notes, archiving
- **Alert Management** - Severity-based alerts with acknowledge/dismiss/escalate workflows and real-time updates
- **Incident Management** - Complete incident lifecycle with event timelines, sighting attachments, and status tracking
- **Advanced Search** - Full-text search across persons, incidents, and sightings with query logging
- **Data Export** - CSV export with date range filtering (PDF reports prepared)
- **Extended Database Schema** - 7 new tables, 4 enums, comprehensive audit logging
- **Modern Dashboard** - Vanilla JS/Bootstrap 5 UI with 6 tabs, real-time updates, and mobile-responsive design

See **[FEATURES.md](FEATURES.md)** for complete technical documentation and **[QUICKSTART.md](../QUICKSTART.md)** for installation guide.

## 📁 Repository Structure

```
sentinelforge/
├── api/              # FastAPI backend with 40+ REST endpoints
│   ├── main.py       # Core API application
│   ├── extended.py   # Auth, cameras, alerts, incidents, search
│   ├── auth.py       # JWT + RBAC utilities
│   ├── websocket.py  # Socket.IO server for real-time updates
│   └── celery_app.py # Background task processing
├── analytics/        # ML-based pattern detection engine
│   ├── engine.py     # Anomaly detection, clustering
│   └── models/       # Trained models and vectorizers
├── dashboard/        # Vanilla JS/Bootstrap 5 web dashboard
│   ├── index.html    # Main dashboard (6 tabs)
│   ├── assets/
│   │   ├── app.js    # Dashboard logic + WebSocket client
│   │   └── custom.css # Styling
│   └── services/     # API client utilities
├── db/               # SQLAlchemy models + Alembic migrations
│   └── models.py     # 15+ tables with pgvector support
├── detection/        # Face detection & recognition engine
│   └── engine.py     # OpenCV + dlib + face_recognition
├── alembic/          # Database migrations
│   └── versions/
│       ├── 001_initial_schema.py
│       └── 002_extended_features.py  # Latest: users, cameras, alerts, incidents
├── docs/             # Architecture documentation
├── tests/            # Pytest suites
└── pyproject.toml    # Dependencies + build config
```

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 15+ with TimescaleDB and pgvector extensions
- Redis 6+
- (Optional) Android device with IP Webcam Pro for live camera feeds

### 1. Install Dependencies

```powershell
cd "d:\NEW PROJECTS\Sentinel Forge\sentinelforge"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[backend,cv,analytics]"
```

### 2. Database Setup

```powershell
# Create database
createdb sentinelforge

# Install extensions
psql sentinelforge
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS timescaledb;
\q

# Run migrations
alembic upgrade head
```

### 3. Configure Environment

Create `.env` file:

```env
SECRET_KEY=your-super-secret-key-change-this
DB_URL=postgresql+asyncpg://sentinelforge:sentinelforge@localhost:5432/sentinelforge
REDIS_URL=redis://localhost:6379/0
FERNET_KEY=generate-with-cryptography-fernet
```

### 4. Start Services

```powershell
# Terminal 1: Redis
redis-server

# Terminal 2: FastAPI Backend
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 3: Celery Worker (analytics)
celery -A api.celery_app worker --loglevel=info
```

### 5. Access Dashboard

Open browser: **http://localhost:8000/dashboard/index.html**

### 6. Create First User

```powershell
curl -X POST http://localhost:8000/api/auth/register `
  -H "Content-Type: application/json" `
  -d '{
    "username": "admin",
    "email": "admin@sentinelforge.local",
    "password": "ChangeMe123!",
    "full_name": "Administrator",
    "role": "ADMIN"
  }'
```

### 7. Configure IP Webcam

1. Install **IP Webcam Pro** on Android device
2. Start server in app (note IP address)
3. In dashboard → **Cameras** tab → **Add Camera**
4. Enter stream URL: `http://192.168.1.100:8080/video`
5. Click **View Stream** to see live footage

See **[QUICKSTART.md](../QUICKSTART.md)** for detailed setup instructions.

## 🎯 Key Features

### Real-Time Communication
- **WebSocket Server** (Socket.IO) for live alerts, sightings, and camera status updates
- **Event Broadcasting** to subscribed users and rooms
- **Auto-reconnection** and connection health monitoring

### Security & Authentication
- **JWT Authentication** with HS256 algorithm and 24-hour token expiration
- **Role-Based Access Control** (Admin, Operator, Viewer) with hierarchical permissions
- **Bcrypt Password Hashing** for secure credential storage
- **Endpoint Protection** with role requirements and authorization checks

### Camera Management
- **IP Webcam Pro Integration** for live MJPEG streaming
- **Camera CRUD** operations with status tracking (Online/Offline/Error/Disabled)
- **Live Stream Viewer** built into dashboard
- **Heartbeat Monitoring** with last-seen timestamps
- **Location & Zone Assignment** for spatial organization

### Person Management
- **Photo Upload** with automatic face embedding extraction
- **Multiple Photos** per person with JSONB array storage
- **Full-Text Search** across person attributes
- **Soft Delete** (archiving) for data retention
- **Notes & Metadata** tracking
- **Consent Management** with boolean flags

### Alert System
- **Severity Levels** (1-4: Low, Medium, High, Critical)
- **Alert Lifecycle** (New → Acknowledged → Dismissed/Escalated)
- **Assignment** to specific operators
- **Real-Time Notifications** via WebSocket
- **Filtering** by severity, status, and type

### Incident Management
- **Complete Workflow** (Open → Investigating → Resolved → Closed)
- **Event Timeline** with automatic status change logging
- **Sighting Attachments** to link events to incidents
- **User Assignment** and tracking
- **Severity Scoring** with escalation support

### Analytics Engine
- **Pattern Detection** using Isolation Forest and DBSCAN clustering
- **Anomaly Scoring** for unusual activity identification
- **Time-Series Analysis** with hourly/daily aggregations
- **Repeat Offender Flagging** (>3 appearances in 24h)
- **Confidence Thresholds** for detection accuracy

### Data Export
- **CSV Export** with date range filtering
- **PDF Reports** (ReportLab integration prepared)
- **Scheduled Exports** via Celery tasks
- **10,000 Record Limit** for performance

### Dashboard Features
- **6 Tabs**: Overview, Cameras, Persons, Unknowns, Alerts, Incidents, Reports
- **Live KPI Cards** with real-time statistics
- **Camera Activity Charts** (Chart.js)
- **Recent Sightings Feed** with auto-refresh
- **Modal Dialogs** for camera/incident creation
- **Toast Notifications** for user feedback
- **Responsive Design** with Bootstrap 5

### Database Architecture
- **PostgreSQL 15+** with TimescaleDB for time-series optimization
- **pgvector Extension** for face embedding similarity search
- **15+ Tables** including users, cameras, alerts, incidents, persons, sightings
- **Alembic Migrations** for version control
- **JSONB Fields** for flexible metadata storage
- **Indexed Queries** on created_at, status columns

## 🔧 API Endpoints

### Authentication
- `POST /api/auth/register` - Create new user account
- `POST /api/auth/login` - Authenticate and get JWT token
- `GET /api/auth/me` - Get current user profile

### Camera Management
- `GET /api/cameras` - List all cameras
- `POST /api/cameras` - Add new camera
- `GET /api/cameras/{camera_id}` - Get camera details
- `PUT /api/cameras/{camera_id}` - Update camera settings
- `DELETE /api/cameras/{camera_id}` - Remove camera
- `POST /api/cameras/{camera_id}/heartbeat` - Update last seen

### Person Management
- `GET /api/persons` - List persons with search/filter
- `POST /api/persons` - Create new person
- `GET /api/persons/{person_id}` - Get person details
- `PUT /api/persons/{person_id}` - Update person info
- `POST /api/persons/{person_id}/photos` - Upload photo and extract embedding
- `DELETE /api/persons/{person_id}` - Archive person

### Alert Management
- `GET /api/alerts` - List alerts with filters
- `POST /api/alerts/{alert_id}/acknowledge` - Acknowledge alert
- `POST /api/alerts/{alert_id}/dismiss` - Dismiss alert
- `POST /api/alerts/{alert_id}/escalate` - Escalate severity

### Incident Management
- `GET /api/incidents` - List incidents
- `POST /api/incidents` - Create new incident
- `GET /api/incidents/{incident_id}` - Get incident with timeline
- `PUT /api/incidents/{incident_id}` - Update incident
- `POST /api/incidents/{incident_id}/events` - Add event to incident

### Search & Export
- `GET /api/search?query={text}` - Full-text search
- `GET /api/export/csv` - Export sightings to CSV

Full API documentation: **http://localhost:8000/docs**

## 🧪 Testing

Run test suites:

```powershell
# All tests
pytest

# Specific test files
pytest tests/test_detection.py
pytest tests/test_analytics.py
pytest tests/test_api_client.py
pytest tests/test_dashboard_app.py
```

## 📚 Documentation

- **[FEATURES.md](FEATURES.md)** - Complete technical feature documentation
- **[QUICKSTART.md](../QUICKSTART.md)** - Installation and setup guide
- **[Architecture Docs](docs/architecture.md)** - System design and data flow
- **[API Docs](http://localhost:8000/docs)** - Interactive OpenAPI documentation

## 🛠️ Technology Stack

**Backend:**
- FastAPI 0.112+ (async REST API)
- Python-SocketIO (WebSocket server)
- SQLAlchemy 2.0+ (ORM with asyncio)
- PostgreSQL 15+ (database)
- TimescaleDB (time-series optimization)
- pgvector (vector similarity search)
- Redis 6+ (caching & Celery broker)
- Celery 5.4+ (background tasks)
- Alembic 1.13+ (migrations)

**Computer Vision:**
- OpenCV 4.10+ (video processing)
- dlib 19.24+ (face detection)
- face_recognition 1.3+ (embeddings)
- scikit-learn 1.4+ (ML models)

**Security:**
- PyJWT 2.8+ (JWT tokens)
- passlib + bcrypt (password hashing)
- python-jose (cryptography)
- Fernet encryption (embeddings)
- SlowAPI (rate limiting)

**Frontend:**
- Vanilla JavaScript (no framework)
- Bootstrap 5.3 (UI components)
- Chart.js 4.4 (visualizations)
- Socket.IO Client 4.7 (WebSocket)

## 📊 Database Schema

**Core Tables:**
- `users` - User accounts with roles
- `persons` - Known individuals with embeddings
- `sightings` - Face detection events
- `cameras` - IP camera registry
- `alerts` - Security alerts
- `incidents` - Incident tracking
- `incident_events` - Event timelines
- `patterns` - Analytics patterns
- `audit_logs` - System activity
- `search_queries` - Search history

**Enums:**
- `UserRole` - ADMIN, OPERATOR, VIEWER
- `CameraStatus` - ONLINE, OFFLINE, ERROR, DISABLED
- `IncidentStatus` - OPEN, INVESTIGATING, RESOLVED, CLOSED
- `AlertStatus` - NEW, ACKNOWLEDGED, DISMISSED, ESCALATED

## 🚀 Deployment

### Production Checklist
- [ ] Change `SECRET_KEY` to strong random value
- [ ] Generate new `FERNET_KEY`
- [ ] Use PostgreSQL SSL connections
- [ ] Enable Redis authentication
- [ ] Restrict CORS origins
- [ ] Use HTTPS for all endpoints
- [ ] Configure strong passwords
- [ ] Set up firewall rules
- [ ] Enable database backups

### Performance Optimization
- Use Gunicorn with Uvicorn workers: `gunicorn api.main:app -k uvicorn.workers.UvicornWorker -w 4`
- Enable TimescaleDB compression for old sightings
- Configure PostgreSQL connection pooling
- Use Redis cluster for HA
- Enable Celery autoscaling

## 📝 License

[Your License Here]

## 🤝 Contributing

Contributions welcome! Please read contributing guidelines before submitting PRs.

## 📞 Support

For issues or questions:
- Check documentation in `docs/`
- Review API docs: `http://localhost:8000/docs`
- Open an issue on GitHub

---

**Status**: ✅ Production-ready with all core features implemented (December 2025)
