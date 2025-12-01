# SentinelForge Extended Features

## 🚀 Overview
This document outlines the comprehensive feature set added to SentinelForge, transforming it from a basic CCTV detection system into a full-featured security intelligence platform.

## ✅ Implemented Features

### 1. **Real-Time WebSocket Communication**
- **Technology**: Socket.IO with asyncio support
- **Location**: `api/websocket.py`
- **Features**:
  - Live alert broadcasts
  - Real-time sighting notifications
  - Camera status updates
  - User-specific room subscriptions
  - Connection health monitoring (ping/pong)
- **Events**:
  - `connect` / `disconnect`
  - `subscribe` / `unsubscribe`
  - `new_alert` - Real-time alert notifications
  - `new_sighting` - Live sighting events
  - `camera_status` - Camera online/offline updates

### 2. **Authentication & Authorization (RBAC)**
- **Technology**: JWT (HS256) + passlib/bcrypt
- **Location**: `api/auth.py`
- **Features**:
  - User registration with email validation
  - Secure login with JWT token generation (24h expiry)
  - Password hashing using bcrypt
  - Role-based access control (RBAC)
  - User role hierarchy: Admin > Operator > Viewer
  - Endpoint protection with `require_role()` dependency
- **Endpoints**:
  - `POST /api/auth/register` - Create new user account
  - `POST /api/auth/login` - Authenticate and get JWT token
  - `GET /api/auth/me` - Get current user profile

### 3. **Camera Management**
- **Location**: `api/extended.py`, `dashboard/index.html`
- **Features**:
  - Add/edit/delete cameras
  - IP Webcam Pro integration
  - Stream URL configuration
  - Camera health monitoring (last seen, status)
  - Location and zone assignment
  - Live stream viewing in dashboard
  - Camera heartbeat endpoint
- **Endpoints**:
  - `GET /api/cameras` - List all cameras
  - `POST /api/cameras` - Add new camera
  - `GET /api/cameras/{camera_id}` - Get camera details
  - `PUT /api/cameras/{camera_id}` - Update camera settings
  - `DELETE /api/cameras/{camera_id}` - Remove camera
  - `POST /api/cameras/{camera_id}/heartbeat` - Update last seen
- **Dashboard**:
  - Camera grid view with status indicators
  - "Add Camera" modal with IP Webcam URL input
  - Live stream viewer with MJPEG support
  - Status badges (Online/Offline/Error)

### 4. **Enhanced Person Management**
- **Location**: `api/extended.py`, `db/models.py`
- **Features**:
  - Person CRUD operations
  - Photo upload with face embedding extraction
  - Multiple photos per person
  - Notes and metadata tracking
  - Archive functionality (soft delete)
  - Consent tracking
  - Full-text search
- **Endpoints**:
  - `GET /api/persons` - List persons with search/filter
  - `POST /api/persons` - Create new person
  - `GET /api/persons/{person_id}` - Get person details with sighting count
  - `PUT /api/persons/{person_id}` - Update person info
  - `POST /api/persons/{person_id}/photos` - Upload photo and extract embedding
  - `DELETE /api/persons/{person_id}` - Archive person
- **New Database Fields**:
  - `notes` (Text) - Additional person information
  - `photo_urls` (JSONB Array) - Multiple photo storage
  - `is_archived` (Boolean) - Soft delete flag

### 5. **Alert Management System**
- **Location**: `api/extended.py`, `dashboard/index.html`
- **Features**:
  - Alert creation with severity levels (1-4)
  - Alert lifecycle: NEW → ACKNOWLEDGED → DISMISSED/ESCALATED
  - Assignment to operators
  - Severity filtering
  - Status tracking
  - Real-time notifications via WebSocket
- **Endpoints**:
  - `GET /api/alerts` - List alerts with filters (status, severity)
  - `POST /api/alerts/{alert_id}/acknowledge` - Acknowledge alert
  - `POST /api/alerts/{alert_id}/dismiss` - Dismiss alert
  - `POST /api/alerts/{alert_id}/escalate` - Escalate severity
- **Dashboard**:
  - Alert table with filtering
  - Action buttons (Acknowledge, Dismiss)
  - Severity badges
  - Real-time updates

### 6. **Incident Management Workflow**
- **Location**: `api/extended.py`, `dashboard/index.html`
- **Features**:
  - Incident creation and tracking
  - Event timeline for each incident
  - Attach sightings to incidents
  - Incident status workflow: OPEN → INVESTIGATING → RESOLVED → CLOSED
  - Severity levels (1-4)
  - Assignment to users
  - Notes and description
- **Endpoints**:
  - `GET /api/incidents` - List incidents with status filter
  - `POST /api/incidents` - Create new incident
  - `GET /api/incidents/{incident_id}` - Get incident with event timeline
  - `PUT /api/incidents/{incident_id}` - Update incident (auto-creates status change event)
  - `POST /api/incidents/{incident_id}/events` - Add event to incident
- **Dashboard**:
  - Incident table with status/severity
  - "Create Incident" modal
  - Incident detail view with event timeline

### 7. **Advanced Search**
- **Location**: `api/extended.py`
- **Features**:
  - Full-text search across persons, incidents, sightings
  - Search query logging
  - Result counting
  - Multi-entity search results
- **Endpoints**:
  - `GET /api/search?query={text}` - Search all entities

### 8. **Data Export**
- **Location**: `api/extended.py`
- **Features**:
  - CSV export of sightings with date range filtering
  - PDF report generation (prepared for ReportLab integration)
  - Export limits (10,000 records)
- **Endpoints**:
  - `GET /api/export/csv?start_date={date}&end_date={date}` - Export to CSV

### 9. **Extended Database Schema**
- **Location**: `db/models.py`, `alembic/versions/002_extended_features.py`
- **New Tables**:
  - `users` - User accounts with roles
  - `cameras` - Camera registry and configuration
  - `alerts` - Alert tracking
  - `incidents` - Incident management
  - `incident_events` - Incident event timeline
  - `audit_logs` - System activity audit trail
  - `search_queries` - Search history logging
- **Enums**:
  - `UserRole` - ADMIN, OPERATOR, VIEWER
  - `CameraStatus` - ONLINE, OFFLINE, ERROR, DISABLED
  - `IncidentStatus` - OPEN, INVESTIGATING, RESOLVED, CLOSED
  - `AlertStatus` - NEW, ACKNOWLEDGED, DISMISSED, ESCALATED

### 10. **IP Webcam Pro Integration**
- **Location**: Dashboard modals, camera management
- **Features**:
  - Stream URL input field in Add Camera modal
  - Support for HTTP MJPEG streams
  - Live stream viewing in modal
  - Error handling for offline streams
  - Connection validation
- **Supported URLs**:
  - MJPEG: `http://[IP]:8080/video`
  - Videofeed: `http://[IP]:8080/videofeed`

## 📦 Dependencies Added

```toml
# pyproject.toml [project.optional-dependencies.backend]
"python-socketio[asyncio]>=5.11"  # WebSocket server
"passlib[bcrypt]>=1.7"             # Password hashing
"python-multipart>=0.0.6"          # File uploads
"aiofiles>=23.2"                   # Async file operations
"reportlab>=4.0"                   # PDF generation
```

## 🎨 Dashboard Enhancements

### New Tabs
1. **Cameras** - Manage IP Webcam streams
2. **Alerts** - View and manage active alerts
3. **Incidents** - Incident workflow management

### New Components
- Camera grid with status indicators
- Alert table with action buttons
- Incident creation modal
- Camera stream viewer modal
- Toast notifications
- Real-time updates via WebSocket

### JavaScript Features
- Socket.IO client integration
- Real-time event handling
- Modal management (Bootstrap 5)
- Dynamic content loading
- API client with GET/POST methods

## 🔒 Security Features

1. **Password Security**
   - Bcrypt hashing with configurable rounds
   - No plaintext password storage
   - Password verification using timing-safe comparison

2. **JWT Authentication**
   - HS256 algorithm
   - 24-hour token expiration
   - Token-based API authorization
   - Stateless authentication

3. **Role-Based Access Control**
   - Hierarchical permissions
   - Endpoint-level authorization
   - User role enforcement
   - Admin-only operations (delete, critical updates)

4. **Data Protection**
   - Soft deletes (archiving) for persons
   - Audit logging (prepared)
   - Input validation (Pydantic models)

## 📊 Database Migration

```bash
# Run migration to apply new schema
cd sentinelforge
alembic upgrade head
```

This will:
- Create 7 new tables
- Add 4 PostgreSQL enums
- Extend Person table with notes, photo_urls, is_archived
- Extend Pattern table with pattern_type, confidence, detected_at
- Create indexes on created_at and status columns

## 🚀 Usage

### Start Backend
```bash
cd sentinelforge
uvicorn api.main:app --reload
```

### Access Dashboard
```
http://localhost:8000/dashboard/
```

### Configure IP Webcam
1. Install IP Webcam Pro on Android device
2. Start server in app
3. Note the IP address (e.g., `http://192.168.1.100:8080`)
4. In dashboard: Cameras tab → Add Camera
5. Enter stream URL: `http://[IP]:8080/video`
6. Click "View Stream" to see live footage

### Create First User
```bash
POST /api/auth/register
{
  "username": "admin",
  "email": "admin@example.com",
  "password": "SecurePassword123!",
  "role": "ADMIN"
}
```

### Authenticate
```bash
POST /api/auth/login
{
  "username": "admin",
  "password": "SecurePassword123!"
}

# Returns: {"access_token": "eyJ...", "token_type": "bearer", "user": {...}}
```

### Add Camera
```bash
POST /api/cameras
Authorization: Bearer eyJ...

{
  "name": "Front Door",
  "camera_id": "CAM001",
  "stream_url": "http://192.168.1.100:8080/video",
  "location": "Main Entrance",
  "zone": "Building A"
}
```

## 🔄 Real-Time Features

### WebSocket Connection (Dashboard)
```javascript
const socket = io('http://localhost:8000', {
    path: '/ws/socket.io'
});

socket.on('new_alert', (alert) => {
    console.log('Alert:', alert);
});

socket.on('new_sighting', (sighting) => {
    console.log('Sighting:', sighting);
});
```

### Broadcasting Alerts (Backend)
```python
from api.websocket import ws_manager

await ws_manager.broadcast_alert({
    "id": str(alert.id),
    "message": "Unknown person detected",
    "severity": 3,
    "timestamp": datetime.utcnow().isoformat()
})
```

## 📈 Next Steps

1. **Mobile Optimization**
   - Add PWA manifest
   - Service worker for offline support
   - Responsive design improvements

2. **Advanced Analytics**
   - Dashboard widgets integration
   - Pattern detection visualization
   - Heat maps for camera activity

3. **Reporting**
   - PDF report generation with ReportLab
   - Scheduled email reports
   - Custom report templates

4. **Integration**
   - SMTP configuration for email alerts
   - Slack/Teams webhooks
   - External API integrations

## 🐛 Known Limitations

1. WebSocket requires `python-socketio[asyncio]` and `redis.asyncio` installation
2. PDF export requires `reportlab` installation
3. Photo upload currently stores base64 in database (consider file storage service)
4. IP Webcam stream requires same network access
5. No authentication UI yet (login page planned)

## 📝 API Documentation

Full OpenAPI documentation available at:
- Interactive Docs: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

All new endpoints are tagged and documented with request/response schemas.
