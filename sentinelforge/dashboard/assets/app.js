// SentinelForge Dashboard - Vanilla JavaScript Application

// Configuration
const API_BASE_URL = 'http://localhost:8000';
const REFRESH_INTERVAL = 5000; // 5 seconds
let refreshTimer = null;
let cameraChart = null;

// Dark theme chart defaults
Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = 'rgba(99, 102, 241, 0.1)';
Chart.defaults.plugins.legend.labels.color = '#94a3b8';

// Accent palette for charts
const SF_CHART_COLORS = ['#6366f1', '#8b5cf6', '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#14b8a6'];

// Utility Functions
function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function formatDate(date) {
    return new Date(date).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

function getFlagBadge(level) {
    const badges = {
        0: '<span class="badge badge-normal">Normal</span>',
        1: '<span class="badge badge-flagged">Flagged</span>',
        2: '<span class="badge badge-flagged">Repeat</span>',
        3: '<span class="badge badge-critical">Critical</span>'
    };
    return badges[level] || badges[0];
}

// API Client
const API = {
    async get(endpoint) {
        try {
            const response = await fetch(`${API_BASE_URL}${endpoint}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return await response.json();
        } catch (error) {
            console.error(`API Error (${endpoint}):`, error);
            return null;
        }
    },

    async post(endpoint, data) {
        try {
            const response = await fetch(`${API_BASE_URL}${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return await response.json();
        } catch (error) {
            console.error(`API Error (${endpoint}):`, error);
            return null;
        }
    }
};

// Tab Navigation
function initTabs() {
    const tabs = document.querySelectorAll('.nav-tab');
    const contents = document.querySelectorAll('.tab-content');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            // Remove active states
            tabs.forEach(t => t.classList.remove('active'));
            contents.forEach(c => c.classList.remove('active'));

            // Add active state
            tab.classList.add('active');
            const tabId = tab.getAttribute('data-tab');
            document.getElementById(`${tabId}-tab`).classList.add('active');

            // Load tab data
            loadTabData(tabId);
        });
    });
}

// Load Tab-Specific Data
function loadTabData(tabName) {
    switch (tabName) {
        case 'overview':
            loadOverview();
            break;
        case 'cameras':
            loadCameras();
            break;
        case 'persons':
            loadPersons();
            break;
        case 'unknowns':
            loadUnknowns();
            break;
        case 'alerts':
            loadAlerts();
            break;
        case 'incidents':
            loadIncidents();
            break;
        case 'reports':
            setDefaultDateRange();
            break;
    }
}

// Overview Tab Functions
async function loadOverview() {
    try {
        // Load header stats
        const stats = await API.get('/api/stats/overview');
        if (stats) {
            document.getElementById('total-persons').textContent = stats.total_persons || 0;
            document.getElementById('today-sightings').textContent = stats.today_sightings || 0;
            document.getElementById('active-flags').textContent = stats.active_flags || 0;
        }

        // Load KPI cards
        const kpiData = await API.get('/api/stats/kpis');
        if (kpiData) {
            document.getElementById('kpi-total-sightings').textContent = kpiData.total_sightings?.toLocaleString() || '0';
            document.getElementById('kpi-known-persons').textContent = kpiData.known_persons || '0';
            document.getElementById('kpi-unknowns').textContent = kpiData.unknowns_90d || '0';
            document.getElementById('kpi-flagged-events').textContent = kpiData.flagged_events || '0';
        }

        // Load recent sightings
        const sightings = await API.get('/api/sightings/recent?limit=10');
        if (sightings && sightings.length > 0) {
            renderRecentSightings(sightings);
        }

        // Load camera activity chart
        const cameraData = await API.get('/api/stats/camera_activity?hours=24');
        if (cameraData) {
            renderCameraChart(cameraData);
        }
        
        // Load NEW charts (Visual Polish)
        await renderSeverityChart();
        await renderCameraVolumeChart();

        // Load alerts
        const alerts = await API.get('/api/alerts/recent?limit=20');
        if (alerts && alerts.length > 0) {
            renderAlerts(alerts);
        }
    } catch (error) {
        console.error('Error loading overview:', error);
    }
}

function renderRecentSightings(sightings) {
    const container = document.getElementById('recent-sightings-list');
    
    if (!sightings || sightings.length === 0) {
        container.innerHTML = '<p class="text-mini text-muted text-center" style="padding:1rem;">No recent sightings</p>';
        return;
    }

    const html = sightings.map(s => `
        <div class="sighting-row">
            <div class="sighting-info">
                <strong>${s.person_name || 'Unknown'}</strong>
                <span class="sighting-meta">${s.camera_id}</span>
            </div>
            <div style="text-align: right;">
                ${getFlagBadge(s.flag_level)}
                <div class="sighting-meta">${formatTimestamp(s.timestamp).split(',')[1]}</div>
            </div>
        </div>
    `).join('');

    container.innerHTML = html;
}

function renderAlerts(alerts) {
    const container = document.getElementById('alert-ticker');
    
    if (!alerts || alerts.length === 0) {
        container.innerHTML = '<p class="text-mini text-muted text-center">No recent alerts</p>';
        return;
    }

    const html = alerts.map(alert => `
        <div class="alert-item-compact">
            <span style="font-weight:700">${formatTimestamp(alert.timestamp).split(',')[1]}</span> 
            ${alert.message}
        </div>
    `).join('');

    container.innerHTML = html;
}

// === NEW CHART FUNCTIONS ===

async function renderSeverityChart() {
    const ctx = document.getElementById('severity-chart');
    if (!ctx) return;
    
    // Fetch real data
    const data = await API.get('/api/stats/severity_distribution');
    const chartData = data ? data.data : [100, 0, 0, 0]; // Fallback
    
    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Normal', 'Flagged', 'Repeat', 'Crit'],
            datasets: [{
                data: chartData,
                backgroundColor: ['#334155', '#f59e0b', '#f97316', '#ef4444'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'right', labels: { boxWidth: 8, font: { size: 9 }, color: '#94a3b8' } }
            },
            cutout: '70%'
        }
    });
}

async function renderCameraVolumeChart() {
    const ctx = document.getElementById('camera-volume-chart');
    if (!ctx) return;
    
    // Fetch real data
    const data = await API.get('/api/stats/camera_volume');
    const labels = data ? data.labels.map(l => l.substring(0,6)) : ['None'];
    const values = data ? data.data : [0];
    
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Sightings',
                data: values,
                backgroundColor: 'rgba(99, 102, 241, 0.6)',
                hoverBackgroundColor: 'rgba(99, 102, 241, 0.9)',
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { font: { size: 8 }, color: '#64748b' }, grid: { display: false } },
                y: { display: false, grid: { display: false } }
            }
        }
    });
}

function renderCameraChart(data) {
    const ctx = document.getElementById('camera-activity-chart');
    if (!ctx) return;

    // Destroy existing chart
    if (cameraChart) {
        cameraChart.destroy();
    }

    // Prepare data
    const labels = data.labels || [];
    const datasets = data.datasets || [];

    cameraChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: datasets.map((ds, idx) => ({
                label: ds.camera_id,
                data: ds.data,
                borderColor: SF_CHART_COLORS[idx % SF_CHART_COLORS.length],
                backgroundColor: 'transparent',
                borderWidth: 2,
                tension: 0.4,
                pointRadius: 2,
                pointHoverRadius: 5,
                pointBackgroundColor: SF_CHART_COLORS[idx % SF_CHART_COLORS.length]
            }))
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: true,
                    position: 'bottom'
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        precision: 0
                    }
                }
            }
        }
    });
}

// Persons Tab Functions
async function loadPersons() {
    const filter = document.getElementById('person-filter').value;
    const persons = await API.get(`/api/persons?filter=${filter}`);
    
    const gallery = document.getElementById('persons-gallery');
    
    if (!persons || persons.length === 0) {
        gallery.innerHTML = '<div class="loading">No persons found</div>';
        return;
    }

    const html = persons.map(person => `
        <div class="gallery-item" onclick="viewPerson('${person.id}')">
            <div class="gallery-img" style="background: var(--sf-bg-primary); display: flex; align-items: center; justify-content: center;">
                <span style="font-size: 3rem; color: var(--sf-text-muted);">👤</span>
            </div>
            <div class="gallery-info">
                <div class="gallery-title">${person.name || 'Unknown'}</div>
                <div class="gallery-meta">
                    Last seen: ${formatDate(person.last_sighting)}<br>
                    Sightings: ${person.sighting_count || 0}
                    ${person.flag_level > 0 ? `<br>${getFlagBadge(person.flag_level)}` : ''}
                </div>
            </div>
        </div>
    `).join('');

    gallery.innerHTML = html;
}

function refreshPersons() {
    loadPersons();
}

function viewPerson(personId) {
    // TODO: Implement person detail modal
    console.log('View person:', personId);
    alert(`Person detail view coming soon\nPerson ID: ${personId}`);
}

// Unknowns Tab Functions
async function loadUnknowns() {
    const unknowns = await API.get('/api/unknowns?days=90');
    
    const gallery = document.getElementById('unknowns-gallery');
    
    if (!unknowns || unknowns.length === 0) {
        gallery.innerHTML = '<div class="loading">No unknown sightings in past 90 days</div>';
        return;
    }

    const html = unknowns.map(unknown => `
        <div class="gallery-item">
            <div class="gallery-img" style="background: var(--sf-bg-primary); display: flex; align-items: center; justify-content: center;">
                <span style="font-size: 3rem; color: var(--sf-text-muted);">❓</span>
            </div>
            <div class="gallery-info">
                <div class="gallery-title">Unknown</div>
                <div class="gallery-meta">
                    ${formatTimestamp(unknown.timestamp)}<br>
                    Camera: ${unknown.camera_id}<br>
                    Confidence: ${(unknown.confidence * 100).toFixed(1)}%
                </div>
            </div>
        </div>
    `).join('');

    gallery.innerHTML = html;
}

// Reports Tab Functions
function setDefaultDateRange() {
    const today = new Date();
    const weekAgo = new Date(today);
    weekAgo.setDate(weekAgo.getDate() - 7);

    document.getElementById('report-end-date').valueAsDate = today;
    document.getElementById('report-start-date').valueAsDate = weekAgo;
}

async function generateReport() {
    const startDate = document.getElementById('report-start-date').value;
    const endDate = document.getElementById('report-end-date').value;

    if (!startDate || !endDate) {
        alert('Please select both start and end dates');
        return;
    }

    const reportData = await API.get(`/api/reports/events?start=${startDate}&end=${endDate}`);
    
    if (!reportData) {
        alert('Failed to generate report');
        return;
    }

    // Update summary cards
    document.getElementById('report-total-events').textContent = reportData.summary.total_events || 0;
    document.getElementById('report-unique-persons').textContent = reportData.summary.unique_persons || 0;
    document.getElementById('report-avg-confidence').textContent = 
        reportData.summary.avg_confidence ? `${(reportData.summary.avg_confidence * 100).toFixed(1)}%` : 'N/A';

    // Update table
    const tbody = document.getElementById('report-table-body');
    
    if (!reportData.events || reportData.events.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center" style="padding: 2rem; color: var(--sf-text-muted);">
                    No events found in selected date range
                </td>
            </tr>
        `;
        return;
    }

    const html = reportData.events.map(event => `
        <tr>
            <td>${formatTimestamp(event.timestamp)}</td>
            <td class="font-mono">${event.person_id ? event.person_id.substring(0, 8) + '...' : 'Unknown'}</td>
            <td>${event.camera_id}</td>
            <td>${(event.confidence * 100).toFixed(1)}%</td>
            <td>${getFlagBadge(event.flag_level)}</td>
            <td>
                <button class="btn" style="padding: 0.25rem 0.75rem; font-size: 0.75rem;" 
                        onclick="viewEventDetail('${event.id}')">
                    View
                </button>
            </td>
        </tr>
    `).join('');

    tbody.innerHTML = html;
}

function viewEventDetail(eventId) {
    // TODO: Implement event detail modal
    console.log('View event:', eventId);
    alert(`Event detail view coming soon\nEvent ID: ${eventId}`);
}

// Auto-refresh Logic
function startAutoRefresh() {
    // Clear existing timer
    if (refreshTimer) {
        clearInterval(refreshTimer);
    }

    // Set up new timer
    refreshTimer = setInterval(() => {
        const activeTab = document.querySelector('.nav-tab.active');
        if (activeTab) {
            const tabName = activeTab.getAttribute('data-tab');
            if (tabName === 'overview') {
                loadOverview();
            }
        }
    }, REFRESH_INTERVAL);
}

function stopAutoRefresh() {
    if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
    }
}

// Initialize Dashboard
document.addEventListener('DOMContentLoaded', () => {
    console.log('SentinelForge Dashboard Initialized');
    
    // Initialize navigation
    initTabs();
    
    // Load initial data
    loadOverview();
    
    // Initialize WebSocket
    initWebSocket();
    
    // Start auto-refresh
    startAutoRefresh();
    
    // Set up filter change handlers
    document.getElementById('person-filter')?.addEventListener('change', loadPersons);
    document.getElementById('alert-severity-filter')?.addEventListener('change', loadAlerts);
    document.getElementById('alert-status-filter')?.addEventListener('change', loadAlerts);
    
    // Cleanup on page unload
    window.addEventListener('beforeunload', () => {
        stopAutoRefresh();
        if (socket) socket.disconnect();
    });
});

// Mock Data Fallback (for development without backend)
// Uncomment this section to use mock data when backend is unavailable

/*
const MOCK_API = {
    '/api/stats/overview': {
        total_persons: 127,
        today_sightings: 45,
        active_flags: 3
    },
    '/api/stats/kpis': {
        total_sightings: 15847,
        known_persons: 127,
        unknowns_90d: 89,
        flagged_events: 12
    },
    '/api/sightings/recent': [
        { person_name: 'John Doe', camera_id: 'CAM-01', flag_level: 0, timestamp: new Date().toISOString() },
        { person_name: 'Jane Smith', camera_id: 'CAM-02', flag_level: 1, timestamp: new Date(Date.now() - 300000).toISOString() }
    ]
};

// Override API.get for mock mode
const originalGet = API.get;
API.get = async function(endpoint) {
    const mockData = MOCK_API[endpoint.split('?')[0]];
    if (mockData) {
        return Promise.resolve(mockData);
    }
    return originalGet.call(this, endpoint);
};
*/

// WebSocket Connection
let socket = null;

function initWebSocket() {
    socket = io(API_BASE_URL, {
        path: '/ws/socket.io',
        transports: ['websocket', 'polling']
    });

    socket.on('connect', () => {
        console.log('WebSocket connected');
        socket.emit('subscribe', { rooms: ['alerts', 'sightings'] });
    });

    socket.on('new_alert', (alert) => {
        console.log('New alert received:', alert);
        showToast(`New Alert: ${alert.message}`, 'warning');
        loadAlerts(); // Refresh alerts table
    });

    socket.on('new_sighting', (sighting) => {
        console.log('New sighting:', sighting);
        updateRecentSightings(); // Refresh sightings
    });

    socket.on('camera_status', (status) => {
        console.log('Camera status update:', status);
        updateCameraStatus(status);
    });

    socket.on('disconnect', () => {
        console.log('WebSocket disconnected');
    });
}

// Camera Management

// Camera type display labels
const CAMERA_TYPE_LABELS = {
    ip_webcam: 'IP Webcam',
    rtsp: 'RTSP',
    usb: 'USB',
    file: 'File',
    http: 'HTTP'
};

const CAMERA_TYPE_ICONS = {
    ip_webcam: 'bi-phone',
    rtsp: 'bi-camera-video',
    usb: 'bi-usb-drive',
    file: 'bi-file-play',
    http: 'bi-globe'
};

let _currentViewCameraId = null;

async function loadCameras() {
    const grid = document.getElementById('cameras-grid');
    const cameras = await API.get('/api/cameras');

    if (!cameras || cameras.length === 0) {
        grid.innerHTML = '<div class="text-center p-4">No cameras configured. Click "Add Camera" to get started.</div>';
        return;
    }

    grid.innerHTML = cameras.map(camera => {
        const typeLabel = CAMERA_TYPE_LABELS[camera.camera_type] || camera.camera_type || 'Unknown';
        const typeIcon = CAMERA_TYPE_ICONS[camera.camera_type] || 'bi-camera-video';
        return `
        <div class="card">
            <div class="d-flex justify-content-between align-items-center mb-2">
                <h4>${camera.name}</h4>
                <span class="badge ${camera.status === 'online' ? 'bg-success' : camera.status === 'error' ? 'bg-danger' : 'bg-secondary'}">
                    ${camera.status.toUpperCase()}
                </span>
            </div>
            <p class="text-muted mb-1">${camera.camera_id}</p>
            <p class="small mb-2">
                <span class="badge bg-dark"><i class="bi ${typeIcon}"></i> ${typeLabel}</span><br>
                <strong>Location:</strong> ${camera.location || 'N/A'}<br>
                <strong>Zone:</strong> ${camera.zone || 'N/A'}
            </p>
            <div class="btn-group btn-group-sm w-100">
                <button class="btn btn-outline-primary" onclick="viewCameraStream('${camera.camera_id}', '${camera.stream_url}', '${camera.name}', '${camera.location || ''}', '${camera.camera_type || 'ip_webcam'}')">
                    <i class="bi bi-eye"></i> View
                </button>
                <button class="btn btn-outline-info" onclick="testCameraConnection('${camera.camera_id}', this)">
                    <i class="bi bi-wifi"></i> Test
                </button>
                <button class="btn btn-outline-secondary" onclick="editCamera('${camera.camera_id}')">
                    <i class="bi bi-pencil"></i> Edit
                </button>
            </div>
        </div>`;
    }).join('');
}

function showAddCameraModal() {
    const modal = new bootstrap.Modal(document.getElementById('addCameraModal'));
    document.getElementById('addCameraForm').reset();
    modal.show();
}

async function saveCamera() {
    const form = document.getElementById('addCameraForm');
    if (!form.checkValidity()) {
        form.reportValidity();
        return;
    }

    const cameraType = document.getElementById('cameraType').value || null;

    const cameraData = {
        name: document.getElementById('cameraName').value,
        camera_id: document.getElementById('cameraId').value,
        stream_url: document.getElementById('streamUrl').value,
        camera_type: cameraType,
        location: document.getElementById('cameraLocation').value,
        zone: document.getElementById('cameraZone').value,
        extra_metadata: {}
    };

    const result = await API.post('/api/cameras', cameraData);
    
    if (result) {
        showToast('Camera added successfully!', 'success');
        bootstrap.Modal.getInstance(document.getElementById('addCameraModal')).hide();
        loadCameras();
    } else {
        showToast('Failed to add camera', 'error');
    }
}

// Camera type change handler — show/hide IP Webcam helper
function onCameraTypeChange() {
    const type = document.getElementById('cameraType').value;
    const helper = document.getElementById('ipWebcamHelper');
    const urlField = document.getElementById('streamUrl');
    const helpText = document.getElementById('streamUrlHelp');

    if (type === 'ip_webcam' || type === '') {
        helper.style.display = 'block';
        urlField.placeholder = 'http://192.168.1.100:8080/video';
        helpText.innerHTML = 'IP Webcam Pro: <code>http://[IP]:8080/video</code> (MJPEG) or <code>http://[IP]:8080/videofeed</code>';
    } else if (type === 'rtsp') {
        helper.style.display = 'none';
        urlField.placeholder = 'rtsp://192.168.1.100:554/stream';
        helpText.textContent = 'RTSP stream URL from your IP camera / NVR';
    } else if (type === 'usb') {
        helper.style.display = 'none';
        urlField.placeholder = '0';
        helpText.textContent = 'Device index (0 = default webcam, 1 = second camera, etc.)';
    } else if (type === 'file') {
        helper.style.display = 'none';
        urlField.placeholder = 'C:\\Videos\\test_footage.mp4';
        helpText.textContent = 'Path to a video file for testing';
    } else {
        helper.style.display = 'none';
        urlField.placeholder = 'http://camera-host/stream';
        helpText.textContent = 'Generic HTTP MJPEG stream URL';
    }
}

// IP Webcam quick setup
function fillIPWebcamUrl() {
    const ip = document.getElementById('ipWebcamIP').value.trim();
    if (!ip) {
        showToast('Enter the IP address first', 'warning');
        return;
    }
    document.getElementById('streamUrl').value = `http://${ip}:8080/video`;
}

// Test camera connection
async function testCameraConnection(cameraId, btn) {
    const origHtml = btn.innerHTML;
    btn.innerHTML = '<i class="bi bi-hourglass-split"></i> Testing...';
    btn.disabled = true;

    const result = await API.post(`/api/cameras/${cameraId}/test`, {});

    btn.disabled = false;
    if (result && result.status === 'online') {
        btn.innerHTML = '<i class="bi bi-check-circle"></i> Online';
        btn.classList.remove('btn-outline-info');
        btn.classList.add('btn-outline-success');
        showToast(`${cameraId}: Online (${result.latency_ms}ms, ${result.resolution})`, 'success');
    } else {
        btn.innerHTML = '<i class="bi bi-x-circle"></i> Failed';
        btn.classList.remove('btn-outline-info');
        btn.classList.add('btn-outline-danger');
        showToast(`${cameraId}: ${result ? result.detail : 'Connection failed'}`, 'error');
    }

    setTimeout(() => {
        btn.innerHTML = origHtml;
        btn.className = btn.className.replace('btn-outline-success', 'btn-outline-info').replace('btn-outline-danger', 'btn-outline-info');
    }, 3000);
}

// Test from view modal
async function testCameraFromModal() {
    if (!_currentViewCameraId) return;
    const btn = document.getElementById('testConnectionBtn');
    const container = document.getElementById('testResultContainer');
    const alert = document.getElementById('testResultAlert');

    btn.disabled = true;
    btn.innerHTML = '<i class="bi bi-hourglass-split"></i> Testing...';

    const result = await API.post(`/api/cameras/${_currentViewCameraId}/test`, {});

    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-wifi"></i> Test Connection';
    container.style.display = 'block';

    if (result && result.status === 'online') {
        alert.className = 'alert alert-success py-2 small';
        alert.innerHTML = `<i class="bi bi-check-circle"></i> <strong>Online</strong> — ${result.resolution}, ${result.latency_ms}ms latency`;
        document.getElementById('cameraStreamStatus').textContent = 'Online';
    } else {
        alert.className = 'alert alert-danger py-2 small';
        alert.innerHTML = `<i class="bi bi-x-circle"></i> <strong>Failed</strong> — ${result ? result.detail : 'No response'}`;
        document.getElementById('cameraStreamStatus').textContent = 'Error';
    }
}

function viewCameraStream(cameraId, streamUrl, name, location, cameraType) {
    _currentViewCameraId = cameraId;
    const modal = new bootstrap.Modal(document.getElementById('viewCameraModal'));
    document.getElementById('viewCameraTitle').textContent = name;
    document.getElementById('cameraStreamLocation').textContent = location || 'N/A';
    document.getElementById('cameraStreamType').textContent = CAMERA_TYPE_LABELS[cameraType] || cameraType || 'Unknown';

    // Hide previous test results
    document.getElementById('testResultContainer').style.display = 'none';

    const img = document.getElementById('cameraStreamImg');

    // For USB and file-based sources, use the snapshot API endpoint instead
    if (cameraType === 'usb' || cameraType === 'file') {
        img.src = `${API_BASE_URL}/api/cameras/${cameraId}/snapshot?t=${Date.now()}`;
    } else {
        // Direct MJPEG stream (browser-native for IP Webcam, HTTP)
        img.src = streamUrl;
    }

    img.onerror = () => {
        img.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480"><rect fill="%231e293b" width="640" height="480" rx="8"/><text x="50%" y="45%" text-anchor="middle" fill="%2364748b" font-family="Inter,sans-serif" font-size="18">Stream Unavailable</text><text x="50%" y="55%" text-anchor="middle" fill="%23475569" font-family="Inter,sans-serif" font-size="13">Click "Test Connection" to diagnose</text></svg>';
        document.getElementById('cameraStreamStatus').textContent = 'Offline';
    };
    img.onload = () => {
        document.getElementById('cameraStreamStatus').textContent = 'Online';
    };
    
    modal.show();
}

function updateCameraStatus(status) {
    // Update camera card if on cameras tab
    const grid = document.getElementById('cameras-grid');
    if (grid) {
        loadCameras(); // Refresh to show updated status
    }
}

// Alert Management
async function loadAlerts() {
    const tbody = document.getElementById('alerts-table-body');
    const severity = document.getElementById('alert-severity-filter')?.value;
    const status = document.getElementById('alert-status-filter')?.value;
    
    let url = '/api/alerts?limit=100';
    if (severity) url += `&severity=${severity}`;
    if (status) url += `&status=${status}`;
    
    const alerts = await API.get(url);
    
    if (!alerts || alerts.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center">No alerts found</td></tr>';
        return;
    }
    
    tbody.innerHTML = alerts.map(alert => `
        <tr>
            <td>${formatTimestamp(alert.created_at)}</td>
            <td>${alert.alert_type}</td>
            <td><span class="badge ${getSeverityBadge(alert.severity)}">${alert.severity}</span></td>
            <td>${alert.message}</td>
            <td><span class="badge ${getStatusBadge(alert.status)}">${alert.status}</span></td>
            <td>
                ${alert.status === 'NEW' ? `
                    <button class="btn btn-sm btn-success" onclick="acknowledgeAlert('${alert.id}')">Acknowledge</button>
                    <button class="btn btn-sm btn-warning" onclick="dismissAlert('${alert.id}')">Dismiss</button>
                ` : '—'}
            </td>
        </tr>
    `).join('');
}

async function acknowledgeAlert(alertId) {
    const result = await API.post(`/api/alerts/${alertId}/acknowledge`, {});
    if (result) {
        showToast('Alert acknowledged', 'success');
        loadAlerts();
    }
}

async function dismissAlert(alertId) {
    const result = await API.post(`/api/alerts/${alertId}/dismiss`, {});
    if (result) {
        showToast('Alert dismissed', 'success');
        loadAlerts();
    }
}

function getSeverityBadge(severity) {
    const badges = {
        1: 'bg-info',
        2: 'bg-warning',
        3: 'bg-danger',
        4: 'bg-dark'
    };
    return badges[severity] || 'bg-secondary';
}

function getStatusBadge(status) {
    const badges = {
        'NEW': 'bg-danger',
        'ACKNOWLEDGED': 'bg-warning',
        'DISMISSED': 'bg-secondary',
        'ESCALATED': 'bg-dark'
    };
    return badges[status] || 'bg-secondary';
}

// Incident Management
async function loadIncidents() {
    const tbody = document.getElementById('incidents-table-body');
    const incidents = await API.get('/api/incidents?limit=50');
    
    if (!incidents || incidents.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center">No incidents found</td></tr>';
        return;
    }
    
    tbody.innerHTML = incidents.map(incident => `
        <tr>
            <td>${incident.id.substring(0, 8)}...</td>
            <td>${incident.title}</td>
            <td><span class="badge ${getIncidentStatusBadge(incident.status)}">${incident.status}</span></td>
            <td><span class="badge ${getSeverityBadge(incident.severity)}">${incident.severity}</span></td>
            <td>${formatTimestamp(incident.created_at)}</td>
            <td>${incident.assigned_to ? incident.assigned_to.substring(0, 8) + '...' : 'Unassigned'}</td>
            <td>
                <button class="btn btn-sm btn-primary" onclick="viewIncident('${incident.id}')">View</button>
            </td>
        </tr>
    `).join('');
}

function getIncidentStatusBadge(status) {
    const badges = {
        'OPEN': 'bg-danger',
        'INVESTIGATING': 'bg-warning',
        'RESOLVED': 'bg-success',
        'CLOSED': 'bg-secondary'
    };
    return badges[status] || 'bg-secondary';
}

function showCreateIncidentModal() {
    const modal = new bootstrap.Modal(document.getElementById('createIncidentModal'));
    document.getElementById('createIncidentForm').reset();
    modal.show();
}

async function createIncident() {
    const form = document.getElementById('createIncidentForm');
    if (!form.checkValidity()) {
        form.reportValidity();
        return;
    }

    const incidentData = {
        title: document.getElementById('incidentTitle').value,
        description: document.getElementById('incidentDescription').value,
        severity: parseInt(document.getElementById('incidentSeverity').value)
    };

    const result = await API.post('/api/incidents', incidentData);
    
    if (result) {
        showToast('Incident created successfully!', 'success');
        bootstrap.Modal.getInstance(document.getElementById('createIncidentModal')).hide();
        loadIncidents();
    } else {
        showToast('Failed to create incident', 'error');
    }
}

async function viewIncident(incidentId) {
    // Fetch incident details and show in a modal or navigate to detail view
    const incident = await API.get(`/api/incidents/${incidentId}`);
    if (incident) {
        // For now, just log it - you can create a detail modal later
        console.log('Incident details:', incident);
        alert(`Incident: ${incident.title}\nStatus: ${incident.status}\nEvents: ${incident.events.length}`);
    }
}

// Toast Notifications
function showToast(message, type = 'info') {
    // Simple toast implementation
    const toastContainer = document.createElement('div');
    toastContainer.className = `toast-notification toast-${type}`;
    toastContainer.textContent = message;
    toastContainer.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 12px 20px;
        background: ${type === 'success' ? '#28a745' : type === 'error' ? '#dc3545' : type === 'warning' ? '#ffc107' : '#17a2b8'};
        color: white;
        border-radius: 8px;
        z-index: 9999;
        animation: slideIn 0.3s ease-out;
    `;
    
    document.body.appendChild(toastContainer);
    
    setTimeout(() => {
        toastContainer.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => toastContainer.remove(), 300);
    }, 3000);
}
