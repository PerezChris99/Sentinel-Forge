// SentinelForge Dashboard - Vanilla JavaScript Application

// Configuration
const API_BASE_URL = 'http://localhost:8000';
const REFRESH_INTERVAL = 5000; // 5 seconds
let refreshTimer = null;
let cameraChart = null;

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
        case 'persons':
            loadPersons();
            break;
        case 'unknowns':
            loadUnknowns();
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
        container.innerHTML = '<p class="text-center" style="color: var(--ink-gray);">No recent sightings</p>';
        return;
    }

    const html = sightings.map(s => `
        <div style="padding: 0.75rem 0; border-bottom: 1px solid var(--border-subtle);">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <strong>${s.person_name || 'Unknown'}</strong>
                    <span style="color: var(--ink-gray); font-size: 0.85rem; margin-left: 0.5rem;">
                        ${s.camera_id}
                    </span>
                </div>
                <div style="text-align: right;">
                    ${getFlagBadge(s.flag_level)}
                    <div style="font-size: 0.8rem; color: var(--ink-gray); margin-top: 0.25rem;">
                        ${formatTimestamp(s.timestamp)}
                    </div>
                </div>
            </div>
        </div>
    `).join('');

    container.innerHTML = html;
}

function renderAlerts(alerts) {
    const container = document.getElementById('alert-ticker');
    
    if (!alerts || alerts.length === 0) {
        container.innerHTML = '<p class="text-center" style="color: var(--ink-gray); font-size: 0.85rem;">No recent alerts</p>';
        return;
    }

    const html = alerts.map(alert => `
        <div class="alert-item">
            <span class="alert-time">${formatTimestamp(alert.timestamp)}</span> — 
            ${alert.message}
        </div>
    `).join('');

    container.innerHTML = html;
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
                borderColor: idx === 0 ? '#1a1a1a' : '#4a4a4a',
                backgroundColor: 'transparent',
                borderWidth: 2,
                tension: 0.3,
                pointRadius: 3,
                pointHoverRadius: 5
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
            <div class="gallery-img" style="background: var(--paper-cream); display: flex; align-items: center; justify-content: center;">
                <span style="font-size: 3rem; color: var(--ink-gray);">👤</span>
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
            <div class="gallery-img" style="background: var(--paper-cream); display: flex; align-items: center; justify-content: center;">
                <span style="font-size: 3rem; color: var(--ink-gray);">❓</span>
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
                <td colspan="6" class="text-center" style="padding: 2rem; color: var(--ink-gray);">
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
    
    // Start auto-refresh
    startAutoRefresh();
    
    // Set up filter change handler
    document.getElementById('person-filter').addEventListener('change', loadPersons);
    
    // Cleanup on page unload
    window.addEventListener('beforeunload', stopAutoRefresh);
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
