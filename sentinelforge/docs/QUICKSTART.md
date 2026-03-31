# SentinelForge - Quick Start Guide

## Prerequisites
- Python 3.11+
- PostgreSQL 15+ with TimescaleDB and pgvector extensions
- Redis 6+
- Android device with IP Webcam Pro (for live camera feeds)

## Installation

### 1. Install Dependencies

```bash
cd sentinelforge

# Install all dependencies
pip install -e ".[backend,cv,analytics]"

# Or install individually
pip install python-socketio[asyncio]>=5.11
pip install passlib[bcrypt]>=1.7
pip install python-multipart>=0.0.6
pip install aiofiles>=23.2
pip install reportlab>=4.0
```

### 2. Database Setup

```bash
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

### 3. Configuration

Create `.env` file:

```env
SECRET_KEY=your-super-secret-key-change-this
DB_URL=postgresql+asyncpg://sentinelforge:sentinelforge@localhost:5432/sentinelforge
REDIS_URL=redis://localhost:6379/0
FERNET_KEY=generate-with-python-cryptography-fernet
```

Generate Fernet key:
```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```

### 4. Start Services

**Terminal 1: Redis**
```bash
redis-server
```

**Terminal 2: PostgreSQL** (if not running as service)
```bash
# Usually auto-starts, verify with:
pg_isready
```

**Terminal 3: FastAPI Backend**
```bash
cd sentinelforge
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 4: Celery Worker** (for analytics)
```bash
cd sentinelforge
celery -A api.celery_app worker --loglevel=info
```

### 5. Access Dashboard

Open browser: `http://localhost:8000/dashboard/index.html`

## First Time Setup

### Create Admin User

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "email": "admin@sentinelforge.local",
    "password": "ChangeMe123!",
    "full_name": "System Administrator",
    "role": "ADMIN"
  }'
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "uuid-here",
    "username": "admin",
    "email": "admin@sentinelforge.local",
    "role": "ADMIN"
  }
}
```

Save the `access_token` for API requests.

### Configure IP Webcam

1. **Install IP Webcam Pro** on Android device
2. **Start Server** in app (note the URL shown, e.g., `http://192.168.1.100:8080`)
3. **Add Camera in Dashboard**:
   - Go to Cameras tab
   - Click "Add Camera"
   - Fill in details:
     - **Name**: Front Door Camera
     - **Camera ID**: CAM001
     - **IP Webcam URL**: `http://192.168.1.100:8080/video` (MJPEG stream)
     - **Location**: Main Entrance
     - **Zone**: Building A
   - Click Save

4. **View Live Stream**:
   - Click "View Stream" button on camera card
   - Live MJPEG feed will appear in modal

### Add Known Persons

```bash
curl -X POST http://localhost:8000/api/persons \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{
    "name": "John Doe",
    "role": "Employee",
    "notes": "Software Engineer, Building A access",
    "consent_given": true
  }'
```

### Upload Person Photo

```bash
curl -X POST http://localhost:8000/api/persons/PERSON_UUID/photos \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -F "file=@/path/to/photo.jpg"
```

This will:
- Upload the photo
- Extract face embedding using face_recognition
- Store embedding for future matching

## Using the Dashboard

### Overview Tab
- View KPIs (Total Sightings, Known Persons, Unknowns, Flagged Events)
- Recent sightings list
- Live alerts ticker
- Camera activity chart (24h)

### Cameras Tab
- View all configured cameras
- Camera status indicators (Online/Offline)
- Add new cameras
- View live streams
- Edit camera settings

### Persons Tab
- Browse known persons
- Filter by status
- View person details
- Photo gallery
- Sighting history

### Alerts Tab
- View active alerts with severity filtering
- Acknowledge alerts
- Dismiss alerts
- Escalate critical alerts
- Real-time updates via WebSocket

### Incidents Tab
- Create incidents
- Track incident workflow (Open → Investigating → Resolved → Closed)
- View incident timeline
- Assign incidents to operators
- Attach sightings to incidents

### Reports Tab
- Generate date-range reports
- Export data to CSV
- View flagged events

## Real-Time Features

The dashboard automatically connects via WebSocket and receives:
- **New Alerts**: Instant notifications for flagged events
- **New Sightings**: Live updates when faces detected
- **Camera Status**: Online/offline state changes

No page refresh needed!

## Detection Integration

### Start Detection Engine

```bash
cd sentinelforge
python -c "
from detection.engine import FaceDetectionEngine
import cv2

engine = FaceDetectionEngine(db_url='your_db_url')
cap = cv2.VideoCapture('http://192.168.1.100:8080/video')

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    results = engine.process_frame(frame, 'CAM001')
    print(f'Detected {len(results)} faces')
"
```

This will:
1. Connect to IP Webcam stream
2. Detect faces in each frame
3. Match against known persons
4. Log sightings to database
5. Trigger alerts for unknowns/flagged persons

## API Usage Examples

### List Cameras
```bash
curl http://localhost:8000/api/cameras
```

### Get Alerts
```bash
curl http://localhost:8000/api/alerts?severity=3&status=NEW \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Create Incident
```bash
curl -X POST http://localhost:8000/api/incidents \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "title": "Unauthorized Access Attempt",
    "description": "Unknown person detected at restricted entrance",
    "severity": 3,
    "camera_id": "CAM001"
  }'
```

### Search
```bash
curl "http://localhost:8000/api/search?query=john" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Troubleshooting

### WebSocket Not Connecting
- Check Redis is running: `redis-cli ping`
- Verify Socket.IO endpoint: `http://localhost:8000/ws/socket.io/`
- Check browser console for connection errors

### Camera Stream Not Loading
- Ensure Android device and server are on same network
- Verify IP Webcam URL in browser first
- Check firewall allows port 8080
- Try alternative stream URLs:
  - MJPEG: `http://[IP]:8080/video`
  - Snapshot: `http://[IP]:8080/shot.jpg`

### Face Detection Not Working
- Verify `dlib` and `face_recognition` installed
- Check model files downloaded
- Ensure OpenCV can access camera stream
- Test with: `python -c "import face_recognition; print('OK')"`

### Database Errors
- Run migrations: `alembic upgrade head`
- Check PostgreSQL extensions: `SELECT * FROM pg_extension;`
- Verify connection string in `.env`

## Production Deployment

### Security Checklist
- [ ] Change `SECRET_KEY` to strong random value
- [ ] Generate new `FERNET_KEY`
- [ ] Use PostgreSQL SSL connections
- [ ] Enable Redis authentication
- [ ] Restrict CORS origins in `api/main.py`
- [ ] Use HTTPS for all endpoints
- [ ] Set strong admin password
- [ ] Configure firewall rules
- [ ] Enable rate limiting (already configured with SlowAPI)

### Performance Optimization
- [ ] Use Gunicorn/Uvicorn workers: `gunicorn api.main:app -k uvicorn.workers.UvicornWorker -w 4`
- [ ] Enable TimescaleDB compression for old sightings
- [ ] Configure PostgreSQL connection pooling
- [ ] Use Redis cluster for high availability
- [ ] Enable Celery autoscaling
- [ ] CDN for static assets

## Next Steps

1. **Add More Cameras**: Repeat IP Webcam setup for additional locations
2. **Train Analytics**: Let system run for 7 days to build pattern models
3. **Configure Alerts**: Set up custom alert rules based on zones/times
4. **Create Operators**: Add more users with OPERATOR role
5. **Schedule Reports**: Configure automated daily/weekly reports

## Support

For issues or questions:
- Check `FEATURES.md` for full feature documentation
- Review API docs: `http://localhost:8000/docs`
- Check logs: `tail -f logs/sentinelforge.log`

**Deployment Status**: ✅ All core features implemented and ready for use!
