# SentinelForge Dashboard - Quick Start Guide

## Overview

The SentinelForge dashboard has been redesigned with a minimalist paper theme using vanilla HTML, CSS, and JavaScript. This guide will help you get it running.

## What Was Built

### Files Created
- `dashboard/index.html` - Main dashboard interface with 4 tabs
- `dashboard/assets/custom.css` - Paper theme CSS (white/black minimalist design)
- `dashboard/assets/app.js` - Vanilla JavaScript application logic
- `dashboard/README.md` - Comprehensive documentation

### Files Modified
- `api/main.py` - Added 8 new dashboard API endpoints
- `docs/phases_readme.md` - Updated Phase 5 status

### Design Theme
**Paper & Ink**: Clean, professional interface inspired by paper documents
- Background: Soft white (#fafafa)
- Text: Ink black (#1a1a1a)
- Accents: Subtle shadows and minimal borders
- Typography: Inter font family

## Running the Dashboard

### Option 1: Direct File Open (Quick Test)
```powershell
# Open in default browser
Start-Process "d:/NEW PROJECTS/Sentinel Forge/sentinelforge/dashboard/index.html"
```

**Note**: The dashboard will show mock data or loading states without the backend running.

### Option 2: With HTTP Server (Recommended)
```powershell
# Navigate to dashboard directory
cd "d:/NEW PROJECTS/Sentinel Forge/sentinelforge/dashboard"

# Start simple HTTP server
python -m http.server 8080
```

Then open `http://localhost:8080` in your browser.

### Option 3: Full Stack (Backend + Dashboard)

**Terminal 1 - Start FastAPI Backend:**
```powershell
cd "d:/NEW PROJECTS/Sentinel Forge/sentinelforge"

# Make sure dependencies are installed
pip install fastapi uvicorn sqlalchemy asyncpg redis cryptography python-jose slowapi

# Start the API server
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 - Serve Dashboard:**
```powershell
cd "d:/NEW PROJECTS/Sentinel Forge/sentinelforge/dashboard"
python -m http.server 8080
```

**Browser:**
Open `http://localhost:8080`

## Dashboard Tabs

### 1. Overview Tab (Default)
- **Header Stats**: Total persons, today's sightings, active flags
- **KPI Cards**: 4 metric cards showing system-wide statistics
- **Recent Sightings**: Last 10 detection events
- **Live Alerts**: Flagged events ticker
- **Camera Activity Chart**: 24-hour line chart

### 2. Persons Tab
- **Gallery View**: Grid of all known persons
- **Filter Options**: All, Flagged Only, Recent Activity
- **Person Info**: Last seen date, sighting count, flag badges

### 3. Unknowns Tab
- **90-Day Window**: Unknown individuals within retention period
- **Gallery Format**: Similar layout to persons tab
- **Metadata**: Timestamp, camera ID, confidence score

### 4. Reports Tab
- **Date Range Picker**: Select start and end dates
- **Summary Metrics**: Total events, unique persons, avg confidence
- **Event Table**: Detailed log with sorting capabilities

## API Endpoints

The dashboard consumes these FastAPI endpoints (all prefixed with `http://localhost:8000`):

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/stats/overview` | Header statistics |
| GET | `/api/stats/kpis` | KPI card data |
| GET | `/api/sightings/recent` | Recent sightings (limit=10) |
| GET | `/api/alerts/recent` | Recent flagged events (limit=20) |
| GET | `/api/stats/camera_activity?hours=24` | Chart data |
| GET | `/api/persons?filter=all` | Person gallery |
| GET | `/api/unknowns?days=90` | Unknown sightings |
| GET | `/api/reports/events?start=2024-01-01&end=2024-01-31` | Event report |

## Testing Without Database

To test the dashboard UI without a running PostgreSQL database:

1. Edit `dashboard/assets/app.js`
2. Scroll to the bottom
3. Uncomment the "Mock Data Fallback" section
4. Refresh the browser

This will populate the dashboard with fake data for UI testing.

## Troubleshooting

### Dashboard shows "Loading..." forever
- **Cause**: Backend not running or wrong API URL
- **Fix**: Start the FastAPI server or enable mock data mode

### CORS errors in browser console
- **Cause**: CORS middleware configuration
- **Fix**: Already configured in `api/main.py` with `allow_origins=["*"]`

### Charts not rendering
- **Cause**: Chart.js CDN blocked or API returned invalid data
- **Fix**: Check browser DevTools console for errors

### Styles look broken
- **Cause**: CSS file not loading
- **Fix**: Ensure `custom.css` path is correct relative to `index.html`

## Next Steps

### Immediate (Can Do Now)
1. **Test the UI**: Open `index.html` in browser to see the design
2. **Review the code**: Check the clean vanilla JavaScript implementation
3. **Customize colors**: Edit CSS variables in `custom.css`

### Requires Backend Setup
4. **Set up PostgreSQL**: Create database with TimescaleDB and pgvector
5. **Run migrations**: `alembic upgrade head`
6. **Start FastAPI**: `uvicorn api.main:app --reload`
7. **Insert test data**: Use the detection engine or manual SQL inserts
8. **Connect dashboard**: Access full functionality with real data

### Future Enhancements
- Person detail modal with sighting timeline
- Event detail modal with footage preview
- CSV/PDF report export
- Real-time WebSocket updates (replace polling)
- Dark mode toggle
- Advanced filtering and search

## Technology Stack

- **HTML5**: Semantic markup
- **CSS3**: Custom properties, flexbox, grid
- **JavaScript ES6+**: Async/await, fetch API, no frameworks
- **Bootstrap 5.3**: Grid system only (minimal usage)
- **Chart.js 4.4**: Line charts for activity visualization
- **Inter Font**: Modern, clean typography

## File Structure

```
dashboard/
├── index.html              # Main HTML structure
├── README.md               # Detailed documentation
├── assets/
│   ├── custom.css          # Paper theme styles
│   └── app.js              # Dashboard logic (vanilla JS)
└── (old files - can be archived)
    ├── app.py              # Old Dash implementation
    ├── components/         # Old Dash components
    └── services/           # Old API client services
```

## Performance

- **Initial Load**: < 1 second (without backend calls)
- **Auto-Refresh**: Every 5 seconds (Overview tab only)
- **API Response**: Depends on database query performance
- **Browser Support**: Modern browsers (Chrome 90+, Firefox 88+, Safari 14+)

## Customization

### Change Theme Colors
Edit `dashboard/assets/custom.css`:
```css
:root {
  --paper-white: #fafafa;    /* Background */
  --ink-black: #1a1a1a;      /* Primary text */
  --accent-red: #d32f2f;     /* Alert color */
  /* Add your custom colors */
}
```

### Adjust Refresh Rate
Edit `dashboard/assets/app.js`:
```javascript
const REFRESH_INTERVAL = 5000;  // Change to desired milliseconds
```

### Point to Different API
Edit `dashboard/assets/app.js`:
```javascript
const API_BASE_URL = 'http://your-api-server:8000';
```

## Git Status

All changes committed to the **Perez** branch:
- Commit: `b79a003` - "Replace Dash with vanilla HTML/CSS/JS paper theme dashboard"
- Files: 6 changed, 1562 insertions, 15 deletions
- Pushed to: `origin/Perez`

---

**Questions?** Check the comprehensive `dashboard/README.md` for more details!
