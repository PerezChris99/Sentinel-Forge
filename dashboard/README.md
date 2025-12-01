# SentinelForge Dashboard

Minimalist HTML/CSS/JavaScript dashboard for the SentinelForge CCTV Security System.

## Design Philosophy

**Paper Theme**: Clean, elegant, and professional interface inspired by paper and ink:
- White background (#fafafa) with subtle shadows
- Black ink (#1a1a1a) for primary text
- Minimal borders and clean typography
- Focus on content and readability

## Features

### Overview Tab
- **KPI Cards**: Total sightings, known persons, unknowns, flagged events
- **Recent Sightings**: Live feed of latest detections
- **Alert Ticker**: Real-time flagged events
- **Camera Activity Chart**: 24-hour activity visualization with Chart.js

### Persons Tab
- **Gallery View**: Grid layout of all known persons
- **Filtering**: All persons, flagged only, recent activity
- **Person Details**: Click to view detailed sighting history (coming soon)

### Unknowns Tab
- **90-Day Window**: Unknown individuals detected within retention period
- **Auto-Purge Info**: Clear indication of data lifecycle
- **Gallery Format**: Consistent visual presentation

### Reports Tab
- **Date Range Selection**: Custom report generation
- **Summary Metrics**: Total events, unique persons, average confidence
- **Detailed Event Log**: Sortable table with all event data
- **Export Options**: (coming soon)

## Technology Stack

- **HTML5**: Semantic markup
- **Bootstrap 5.3**: Responsive grid and utilities (minimal usage)
- **Vanilla JavaScript**: No frameworks, pure ES6+
- **Chart.js 4.4**: Data visualization
- **Inter Font**: Clean, modern typography

## Setup

### Prerequisites
- FastAPI backend running on `http://localhost:8000`
- PostgreSQL database with TimescaleDB and pgvector
- Redis for caching

### Quick Start

1. **Start the backend**:
   ```bash
   cd sentinelforge
   uvicorn api.main:app --reload
   ```

2. **Open the dashboard**:
   - Simply open `dashboard/index.html` in a modern browser
   - Or serve with a simple HTTP server:
     ```bash
     cd dashboard
     python -m http.server 8080
     ```
   - Navigate to `http://localhost:8080`

### Configuration

Edit `assets/app.js` to change API endpoint:

```javascript
const API_BASE_URL = 'http://localhost:8000';  // Change if needed
const REFRESH_INTERVAL = 5000;  // Auto-refresh interval (ms)
```

## API Endpoints Used

The dashboard consumes the following FastAPI endpoints:

| Endpoint | Purpose |
|----------|---------|
| `GET /api/stats/overview` | Header statistics |
| `GET /api/stats/kpis` | KPI card data |
| `GET /api/sightings/recent` | Recent sightings list |
| `GET /api/alerts/recent` | Flagged events |
| `GET /api/stats/camera_activity` | Chart data |
| `GET /api/persons` | Person gallery |
| `GET /api/unknowns` | Unknown sightings |
| `GET /api/reports/events` | Event reports |

## Development Mode

To use mock data without a running backend, uncomment the mock data section at the bottom of `assets/app.js`:

```javascript
// Uncomment this section to use mock data when backend is unavailable
const MOCK_API = {
    '/api/stats/overview': {
        total_persons: 127,
        today_sightings: 45,
        active_flags: 3
    },
    // ... more mock data
};
```

## Auto-Refresh

The overview tab automatically refreshes every 5 seconds to show live data. Other tabs load data when activated.

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+

## File Structure

```
dashboard/
├── index.html          # Main HTML structure
├── assets/
│   ├── custom.css      # Paper theme styles
│   └── app.js          # Dashboard logic
└── README.md           # This file
```

## Customization

### Colors

Edit CSS variables in `assets/custom.css`:

```css
:root {
  --paper-white: #fafafa;
  --ink-black: #1a1a1a;
  --accent-red: #d32f2f;
  /* ... more variables */
}
```

### Refresh Interval

Change in `assets/app.js`:

```javascript
const REFRESH_INTERVAL = 5000;  // Milliseconds
```

## Future Enhancements

- [ ] Person detail modal with sighting timeline
- [ ] Event detail modal with footage preview
- [ ] Report export (CSV/PDF)
- [ ] Real-time WebSocket updates
- [ ] Dark mode toggle
- [ ] Advanced filtering options
- [ ] Heatmap visualization
- [ ] User authentication UI

## License

Part of the SentinelForge project.
