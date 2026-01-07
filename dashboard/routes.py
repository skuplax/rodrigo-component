"""Dashboard routes for Rodrigo Component"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard():
    """Dashboard HTML page with Spotify-style player controls"""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Rodrigo Component Dashboard</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                background: #121212;
                color: #ffffff;
                min-height: 100vh;
                padding: 20px;
                position: relative;
            }
            
            .container {
                max-width: 1400px;
                margin: 0 auto;
                position: relative;
            }
            
            .status-indicator-minimal {
                position: fixed;
                top: 20px;
                right: 20px;
                display: flex;
                align-items: center;
                gap: 8px;
                font-size: 0.9rem;
                color: #b3b3b3;
                z-index: 1000;
                background: rgba(18, 18, 18, 0.9);
                padding: 6px 12px;
                border-radius: 6px;
                backdrop-filter: blur(4px);
            }
            
            .status-indicator-minimal .status-indicator {
                margin-right: 0;
            }
            
            h1 {
                color: #1db954;
                margin-bottom: 30px;
                font-size: 2.5rem;
                font-weight: 700;
            }
            
            .player-section {
                background: linear-gradient(135deg, #1e1e1e 0%, #2a2a2a 100%);
                border-radius: 16px;
                padding: 40px;
                margin-bottom: 30px;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
            }
            
            .player-controls {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 20px;
                margin-bottom: 30px;
            }
            
            .control-button {
                background: rgba(255, 255, 255, 0.1);
                border: none;
                color: #ffffff;
                cursor: pointer;
                transition: all 0.2s ease;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 50%;
            }
            
            .control-button:hover {
                background: rgba(255, 255, 255, 0.2);
                transform: scale(1.05);
            }
            
            .control-button:active {
                transform: scale(0.95);
            }
            
            .control-button:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            
            .prev-button, .next-button {
                width: 48px;
                height: 48px;
                font-size: 20px;
            }
            
            .play-pause-button {
                width: 80px;
                height: 80px;
                background: #1db954;
                font-size: 32px;
            }
            
            .play-pause-button:hover {
                background: #1ed760;
                transform: scale(1.1);
            }
            
            .cycle-source-button {
                background: #1db954;
                color: #121212;
                border: none;
                padding: 10px 20px;
                border-radius: 8px;
                cursor: pointer;
                font-weight: 600;
                font-size: 0.9rem;
                transition: all 0.2s ease;
                margin-left: auto;
            }
            
            .cycle-source-button:hover {
                background: #1ed760;
                transform: translateY(-1px);
            }
            
            .cycle-source-button:active {
                transform: translateY(0);
            }
            
            .cycle-source-button:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            
            .sources-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 16px;
            }
            
            .sources-header h2 {
                margin: 0;
            }
            
            .track-info {
                text-align: center;
                margin-top: 20px;
            }
            
            .track-name {
                font-size: 1.5rem;
                font-weight: 600;
                margin-bottom: 8px;
                color: #ffffff;
            }
            
            .source-info {
                font-size: 0.9rem;
                color: #b3b3b3;
                margin-top: 8px;
            }
            
            .source-badge {
                display: inline-block;
                background: #1db954;
                color: #121212;
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 0.85rem;
                font-weight: 600;
                margin-top: 8px;
            }
            
            .progress-container {
                margin-top: 20px;
                width: 100%;
            }
            
            .progress-bar-wrapper {
                position: relative;
                width: 100%;
                height: 6px;
                background: #404040;
                border-radius: 3px;
                cursor: pointer;
                margin-bottom: 8px;
            }
            
            .progress-bar {
                height: 100%;
                background: #1db954;
                border-radius: 3px;
                transition: width 0.3s ease;
                position: relative;
            }
            
            .progress-bar::after {
                content: '';
                position: absolute;
                right: -6px;
                top: 50%;
                transform: translateY(-50%);
                width: 12px;
                height: 12px;
                background: #ffffff;
                border-radius: 50%;
                opacity: 0;
                transition: opacity 0.2s ease;
            }
            
            .progress-bar-wrapper:hover .progress-bar::after {
                opacity: 1;
            }
            
            .time-display {
                display: flex;
                justify-content: space-between;
                font-size: 0.75rem;
                color: #b3b3b3;
                margin-top: 4px;
            }
            
            .status-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            
            .status-card {
                background: #1e1e1e;
                border-radius: 12px;
                padding: 24px;
                box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
            }
            
            .sources-list {
                list-style: none;
                padding: 0;
                margin: 12px 0 0 0;
            }
            
            .source-item {
                padding: 10px 12px;
                margin: 6px 0;
                background: #121212;
                border-radius: 6px;
                border-left: 3px solid transparent;
                display: flex;
                justify-content: space-between;
                align-items: center;
                transition: all 0.2s ease;
            }
            
            .source-item.current {
                border-left-color: #1db954;
                background: #252525;
            }
            
            .source-item-name {
                flex: 1;
                color: #ffffff;
                font-weight: 500;
            }
            
            .source-item.current .source-item-name {
                color: #1db954;
                font-weight: 600;
            }
            
            .source-item-type {
                font-size: 0.75rem;
                color: #b3b3b3;
                margin-left: 12px;
                padding: 4px 8px;
                background: #1e1e1e;
                border-radius: 4px;
                text-transform: uppercase;
            }
            
            .source-item-index {
                font-size: 0.85rem;
                color: #808080;
                margin-left: 12px;
                min-width: 30px;
                text-align: right;
            }
            
            .source-item.current .source-item-index {
                color: #1db954;
                font-weight: 600;
            }
            
            .status-card h2 {
                color: #1db954;
                font-size: 1.2rem;
                margin-bottom: 16px;
                font-weight: 600;
            }
            
            .status-indicator {
                display: inline-block;
                width: 10px;
                height: 10px;
                border-radius: 50%;
                margin-right: 8px;
            }
            
            .status-running {
                background: #1db954;
                box-shadow: 0 0 8px rgba(29, 185, 84, 0.6);
            }
            
            .status-stopped {
                background: #e22134;
            }
            
            #events {
                max-height: 300px;
                overflow-y: auto;
                background: #121212;
                padding: 12px;
                border-radius: 8px;
                margin-top: 12px;
            }
            
            .event-item {
                padding: 10px;
                margin: 6px 0;
                border-left: 3px solid #1db954;
                background: #1e1e1e;
                border-radius: 4px;
                font-size: 0.9rem;
            }
            
            .event-item:first-child {
                margin-top: 0;
            }
            
            .announcement-section {
                background: #1e1e1e;
                border-radius: 12px;
                padding: 24px;
                box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
            }
            
            .announcement-form {
                display: flex;
                gap: 12px;
                margin-top: 16px;
            }
            
            input[type="text"] {
                flex: 1;
                padding: 12px 16px;
                border: 1px solid #404040;
                border-radius: 8px;
                background: #121212;
                color: #ffffff;
                font-size: 1rem;
            }
            
            input[type="text"]:focus {
                outline: none;
                border-color: #1db954;
            }
            
            button.send-button {
                background: #1db954;
                color: #121212;
                border: none;
                padding: 12px 24px;
                border-radius: 8px;
                cursor: pointer;
                font-weight: 600;
                font-size: 1rem;
                transition: all 0.2s ease;
            }
            
            button.send-button:hover {
                background: #1ed760;
                transform: translateY(-1px);
            }
            
            .loading {
                opacity: 0.6;
                pointer-events: none;
            }
            
            .logs-section {
                background: #1e1e1e;
                border-radius: 12px;
                padding: 24px;
                box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
                margin-top: 30px;
            }
            
            .logs-filters {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 12px;
                margin-bottom: 20px;
            }
            
            .filter-group {
                display: flex;
                flex-direction: column;
                gap: 6px;
            }
            
            .filter-group label {
                font-size: 0.85rem;
                color: #b3b3b3;
                font-weight: 500;
            }
            
            .filter-group select,
            .filter-group input {
                padding: 8px 12px;
                border: 1px solid #404040;
                border-radius: 6px;
                background: #121212;
                color: #ffffff;
                font-size: 0.9rem;
            }
            
            .filter-group select:focus,
            .filter-group input:focus {
                outline: none;
                border-color: #1db954;
            }
            
            .logs-table-container {
                overflow-x: auto;
                max-height: 600px;
                overflow-y: auto;
                margin-top: 16px;
            }
            
            .logs-table {
                width: 100%;
                border-collapse: collapse;
                font-size: 0.9rem;
            }
            
            .logs-table th {
                background: #121212;
                color: #1db954;
                padding: 12px;
                text-align: left;
                font-weight: 600;
                position: sticky;
                top: 0;
                z-index: 10;
                border-bottom: 2px solid #1db954;
            }
            
            .logs-table td {
                padding: 10px 12px;
                border-bottom: 1px solid #2a2a2a;
                white-space: nowrap;
            }
            
            .logs-table tr:hover {
                background: #252525;
            }
            
            .log-level {
                display: inline-block;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 0.75rem;
                font-weight: 600;
                text-transform: uppercase;
            }
            
            .log-level-DEBUG { background: #6c757d; color: #fff; }
            .log-level-INFO { background: #1db954; color: #121212; }
            .log-level-WARNING { background: #ffc107; color: #121212; }
            .log-level-ERROR { background: #e22134; color: #fff; }
            .log-level-CRITICAL { background: #dc3545; color: #fff; }
            
            .log-message {
                max-width: 500px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                cursor: pointer;
            }
            
            .log-message:hover {
                color: #1db954;
            }
            
            .log-row {
                cursor: pointer;
            }
            
            .log-row:hover {
                background: #252525 !important;
            }
            
            /* Modal for full log view */
            .log-modal {
                display: none;
                position: fixed;
                z-index: 1000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0, 0, 0, 0.8);
                overflow: auto;
            }
            
            .log-modal-content {
                background-color: #1e1e1e;
                margin: 5% auto;
                padding: 30px;
                border: 2px solid #1db954;
                border-radius: 12px;
                width: 90%;
                max-width: 800px;
                max-height: 80vh;
                overflow-y: auto;
            }
            
            .log-modal-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
                padding-bottom: 15px;
                border-bottom: 1px solid #2a2a2a;
            }
            
            .log-modal-header h2 {
                color: #1db954;
                margin: 0;
            }
            
            .log-modal-close {
                color: #b3b3b3;
                font-size: 28px;
                font-weight: bold;
                cursor: pointer;
                background: none;
                border: none;
                padding: 0;
                width: 30px;
                height: 30px;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            
            .log-modal-close:hover {
                color: #ffffff;
            }
            
            .log-modal-detail {
                margin-bottom: 15px;
            }
            
            .log-modal-detail-label {
                color: #1db954;
                font-weight: 600;
                margin-bottom: 5px;
                font-size: 0.9rem;
            }
            
            .log-modal-detail-value {
                color: #ffffff;
                background: #121212;
                padding: 10px;
                border-radius: 6px;
                white-space: pre-wrap;
                word-wrap: break-word;
                font-family: 'Courier New', monospace;
                font-size: 0.9rem;
            }
            
            .log-modal-detail-value.json {
                max-height: 300px;
                overflow-y: auto;
            }
            
            .log-module {
                color: #b3b3b3;
                font-size: 0.85rem;
            }
            
            .log-timestamp {
                color: #808080;
                font-size: 0.85rem;
                white-space: nowrap;
            }
            
            .pagination {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-top: 16px;
                padding-top: 16px;
                border-top: 1px solid #2a2a2a;
            }
            
            .pagination-info {
                color: #b3b3b3;
                font-size: 0.9rem;
            }
            
            .pagination-buttons {
                display: flex;
                gap: 8px;
            }
            
            .pagination-button {
                padding: 8px 16px;
                background: #1db954;
                color: #121212;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                font-weight: 600;
                font-size: 0.9rem;
                transition: all 0.2s ease;
            }
            
            .pagination-button:hover:not(:disabled) {
                background: #1ed760;
            }
            
            .pagination-button:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            
            @media (max-width: 768px) {
                .player-controls {
                    flex-wrap: wrap;
                }
                
                .play-pause-button {
                    width: 64px;
                    height: 64px;
                    font-size: 24px;
                }
                
                h1 {
                    font-size: 2rem;
                    margin-top: 50px;
                }
                
                .status-indicator-minimal {
                    top: 10px;
                    right: 10px;
                    font-size: 0.8rem;
                    padding: 4px 8px;
                }
                
                .container {
                    padding-top: 10px;
                    margin-bottom: 5px;
                }
            }
        </style>
    </head>
    <body>

        <div class="container">
            <h1>🎵 Rodrigo Component Dashboard</h1>
                    <div class="status-indicator-minimal" id="status-indicator-minimal">
            <span class="status-indicator status-stopped"></span>
            <span>Monitor: Loading...</span>
        </div>
        
            <div class="player-section">
             <div class="progress-container" id="progress-container" style="display: none;">
                        <div class="progress-bar-wrapper">
                            <div class="progress-bar" id="progress-bar"></div>
                        </div>
                        <div class="time-display">
                            <span id="time-current">0:00</span>
                            <span id="time-duration">0:00</span>
                        </div>
                    </div>
                <div class="player-controls">
                    <button class="control-button prev-button" onclick="controlPlayer('previous')" title="Previous">
                        ⏮
                    </button>
                    <button class="control-button play-pause-button" id="play-pause-btn" onclick="controlPlayer('play-pause')" title="Play/Pause">
                        ▶
                    </button>
                    <button class="control-button next-button" onclick="controlPlayer('next')" title="Next">
                        ⏭
                    </button>

                </div>
                <div class="track-info">
                    <div class="track-name" id="track-name">Loading...</div>
                    <div class="source-info" id="source-info">Source: Loading...</div>
                    <div class="source-badge" id="source-badge" style="display: none;"></div>
                   
                </div>
            </div>
            
            <div class="status-card">
                <div class="sources-header">
                    <h2>Sources</h2>
                    <button class="cycle-source-button" onclick="controlPlayer('cycle-source')" title="Cycle Source">
                        Cycle Source
                    </button>
                </div>
                <ul class="sources-list" id="sources-list">Loading sources...</ul>
            </div>
            
            <div class="status-card">
                <h2>Recent Events</h2>
                <div id="events">Loading events...</div>
            </div>
            
            <div class="announcement-section">
                <h2>Announcement</h2>
                <div class="announcement-form">
                    <input type="text" id="announcement-text" placeholder="Enter text to announce" onkeypress="if(event.key==='Enter') sendAnnouncement()">
                    <button class="send-button" onclick="sendAnnouncement()">Send</button>
                </div>
            </div>
            
            <div class="logs-section">
                <h2>Logs</h2>
                <div class="logs-filters">
                    <div class="filter-group">
                        <label for="log-level">Level</label>
                        <select id="log-level" onchange="loadLogs()">
                            <option value="">All Levels</option>
                            <option value="DEBUG">DEBUG</option>
                            <option value="INFO">INFO</option>
                            <option value="WARNING">WARNING</option>
                            <option value="ERROR">ERROR</option>
                            <option value="CRITICAL">CRITICAL</option>
                        </select>
                    </div>
                    <div class="filter-group">
                        <label for="log-module">Module</label>
                        <input type="text" id="log-module" placeholder="Filter by module" onkeyup="debounceLoadLogs()">
                    </div>
                    <div class="filter-group">
                        <label for="log-search">Search</label>
                        <input type="text" id="log-search" placeholder="Search in messages" onkeyup="debounceLoadLogs()">
                    </div>
                    <div class="filter-group">
                        <label for="log-start-date">Start Date</label>
                        <input type="datetime-local" id="log-start-date" onchange="loadLogs()">
                    </div>
                    <div class="filter-group">
                        <label for="log-end-date">End Date</label>
                        <input type="datetime-local" id="log-end-date" onchange="loadLogs()">
                    </div>
                </div>
                <div class="logs-table-container">
                    <table class="logs-table">
                        <thead>
                            <tr>
                                <th>Timestamp</th>
                                <th>Level</th>
                                <th>Module</th>
                                <th>Message</th>
                            </tr>
                        </thead>
                        <tbody id="logs-table-body">
                            <tr><td colspan="4">Loading logs...</td></tr>
                        </tbody>
                    </table>
                </div>
                <div class="pagination">
                    <div class="pagination-info" id="pagination-info">Loading...</div>
                    <div class="pagination-buttons">
                        <button class="pagination-button" id="prev-page" onclick="changePage(-1)" disabled>Previous</button>
                        <button class="pagination-button" id="next-page" onclick="changePage(1)" disabled>Next</button>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Log Detail Modal -->
        <div id="log-modal" class="log-modal">
            <div class="log-modal-content">
                <div class="log-modal-header">
                    <h2>Log Details</h2>
                    <button class="log-modal-close" onclick="closeLogModal()">&times;</button>
                </div>
                <div id="log-modal-body">
                    <!-- Log details will be inserted here -->
                </div>
            </div>
        </div>
        
        <script>
            const API_BASE = window.location.origin;
            let currentState = null;
            
            function formatTime(seconds) {
                if (seconds === null || seconds === undefined || isNaN(seconds)) {
                    return '0:00';
                }
                const mins = Math.floor(seconds / 60);
                const secs = Math.floor(seconds % 60);
                return `${mins}:${secs.toString().padStart(2, '0')}`;
            }
            
            async function updateStatus() {
                try {
                    const [stateRes, gpioRes, eventsRes, sourcesRes] = await Promise.all([
                        fetch(`${API_BASE}/api/state`),
                        fetch(`${API_BASE}/api/gpio/status`),
                        fetch(`${API_BASE}/api/gpio/events?limit=20`),
                        fetch(`${API_BASE}/api/sources`)
                    ]);
                    
                    if (!stateRes.ok || !gpioRes.ok || !eventsRes.ok || !sourcesRes.ok) {
                        throw new Error('Failed to fetch status');
                    }
                    
                    const state = await stateRes.json();
                    const gpio = await gpioRes.json();
                    const events = await eventsRes.json();
                    const sources = await sourcesRes.json();
                    
                    currentState = state;
                    
                    // Update minimal status indicator in top right
                    const statusIndicatorEl = document.getElementById('status-indicator-minimal');
                    const indicatorDot = statusIndicatorEl.querySelector('.status-indicator');
                    const indicatorText = statusIndicatorEl.querySelector('span:last-child');
                    
                    if (gpio.monitor_running) {
                        indicatorDot.className = 'status-indicator status-running';
                        indicatorText.textContent = 'Monitor: Running';
                    } else {
                        indicatorDot.className = 'status-indicator status-stopped';
                        indicatorText.textContent = 'Monitor: Stopped';
                    }
                    
                    // Update play/pause button
                    const playPauseBtn = document.getElementById('play-pause-btn');
                    if (state.is_playing) {
                        playPauseBtn.textContent = '⏸';
                        playPauseBtn.title = 'Pause';
                    } else {
                        playPauseBtn.textContent = '▶';
                        playPauseBtn.title = 'Play';
                    }
                    
                    // Update track name - show actual track name
                    const trackNameEl = document.getElementById('track-name');
                    let trackDisplay = 'No track playing';
                    if (state.current_track) {
                        if (typeof state.current_track === 'string') {
                            trackDisplay = state.current_track;
                        } else if (typeof state.current_track === 'object') {
                            // Handle object - try common properties
                            trackDisplay = state.current_track.title || 
                                         state.current_track.name || 
                                         state.current_track.track || 
                                         `${state.current_track.artist || ''} - ${state.current_track.title || ''}`.trim() ||
                                         JSON.stringify(state.current_track);
                        }
                    }
                    trackNameEl.textContent = trackDisplay;
                    
                    // Update source info - show source name
                    const sourceInfoEl = document.getElementById('source-info');
                    const sourceBadgeEl = document.getElementById('source-badge');
                    if (state.current_source_name) {
                        sourceInfoEl.textContent = `Source: ${state.current_source_name}`;
                        // Show source_type badge (music or news)
                        if (state.current_source_type) {
                            sourceBadgeEl.textContent = state.current_source_type.toUpperCase();
                            sourceBadgeEl.style.display = 'inline-block';
                        } else {
                            sourceBadgeEl.style.display = 'none';
                        }
                    } else if (state.current_source) {
                        sourceInfoEl.textContent = `Source: ${state.current_source}`;
                        sourceBadgeEl.style.display = 'none';
                    } else {
                        sourceInfoEl.textContent = 'Source: Unknown';
                        sourceBadgeEl.style.display = 'none';
                    }
                    
                    // Update progress bar and time
                    const progressContainer = document.getElementById('progress-container');
                    const progressBar = document.getElementById('progress-bar');
                    const timeCurrent = document.getElementById('time-current');
                    const timeDuration = document.getElementById('time-duration');
                    
                    if (state.position !== null && state.position !== undefined && 
                        state.duration !== null && state.duration !== undefined && 
                        state.duration > 0) {
                        // Show progress bar
                        progressContainer.style.display = 'block';
                        
                        // Calculate percentage
                        const percentage = Math.min((state.position / state.duration) * 100, 100);
                        progressBar.style.width = percentage + '%';
                        
                        // Format time (MM:SS)
                        timeCurrent.textContent = formatTime(state.position);
                        timeDuration.textContent = formatTime(state.duration);
                    } else {
                        // Hide progress bar if no valid position/duration
                        progressContainer.style.display = 'none';
                    }
                    
                    // Update sources list
                    const sourcesListEl = document.getElementById('sources-list');
                    if (sources.sources && sources.sources.length > 0) {
                        const sourcesHtml = sources.sources.map((source, index) => {
                            const isCurrent = index === sources.current_index;
                            const typeLabel = source.type === 'spotify_playlist' ? 'Spotify' : 
                                            source.type === 'youtube_channel' ? 'YouTube' : 
                                            source.type;
                            return `
                                <li class="source-item ${isCurrent ? 'current' : ''}">
                                    <span class="source-item-name">${escapeHtml(source.name)}</span>
                                    <span class="source-item-type">${typeLabel}</span>
                                    <span class="source-item-index">${index + 1}</span>
                                </li>
                            `;
                        }).join('');
                        sourcesListEl.innerHTML = sourcesHtml;
                    } else {
                        sourcesListEl.innerHTML = '<li class="source-item"><span class="source-item-name">No sources available</span></li>';
                    }
                    
                    // Update events
                    const eventsEl = document.getElementById('events');
                    if (events.events && events.events.length > 0) {
                        const eventsHtml = events.events.map(e => {
                            const date = new Date(e.timestamp);
                            const timeStr = date.toLocaleTimeString();
                            return `<div class="event-item">${timeStr}: ${e.action || e.event} (Pin ${e.pin})</div>`;
                        }).join('');
                        eventsEl.innerHTML = eventsHtml;
                    } else {
                        eventsEl.innerHTML = '<div class="event-item">No events yet</div>';
                    }
                } catch (error) {
                    console.error('Error updating status:', error);
                    document.getElementById('status').innerHTML = '<span style="color: #e22134;">Error loading status</span>';
                }
            }
            
            async function controlPlayer(action) {
                const endpoint = action === 'play-pause' ? 'play-pause' : 
                                action === 'next' ? 'next' :
                                action === 'previous' ? 'previous' :
                                action === 'cycle-source' ? 'cycle-source' : null;
                
                if (!endpoint) {
                    console.error('Unknown action:', action);
                    return;
                }
                
                const btn = event.target.closest('.control-button');
                if (btn) {
                    btn.classList.add('loading');
                    btn.disabled = true;
                }
                
                try {
                    const response = await fetch(`${API_BASE}/api/player/${endpoint}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' }
                    });
                    
                    if (!response.ok) {
                        const error = await response.json();
                        throw new Error(error.detail || 'Failed to control player');
                    }
                    
                    // Update status immediately after action
                    await updateStatus();
                } catch (error) {
                    console.error('Error controlling player:', error);
                    alert('Failed to control player: ' + error.message);
                } finally {
                    if (btn) {
                        btn.classList.remove('loading');
                        btn.disabled = false;
                    }
                }
            }
            
            async function sendAnnouncement() {
                const text = document.getElementById('announcement-text').value.trim();
                if (!text) {
                    alert('Please enter some text');
                    return;
                }
                
                const btn = document.querySelector('.send-button');
                btn.disabled = true;
                btn.textContent = 'Sending...';
                
                try {
                    const response = await fetch(`${API_BASE}/api/announce`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ text })
                    });
                    
                    if (!response.ok) {
                        const error = await response.json();
                        throw new Error(error.detail || 'Failed to send announcement');
                    }
                    
                    document.getElementById('announcement-text').value = '';
                    alert('Announcement sent!');
                } catch (error) {
                    console.error('Error sending announcement:', error);
                    alert('Failed to send announcement: ' + error.message);
                } finally {
                    btn.disabled = false;
                    btn.textContent = 'Send';
                }
            }
            
            // Logs functionality
            let logsOffset = 0;
            const logsLimit = 100;
            let logsTotal = 0;
            let loadLogsTimeout = null;
            let currentLogsList = []; // Store current logs for modal access
            
            function debounceLoadLogs() {
                if (loadLogsTimeout) {
                    clearTimeout(loadLogsTimeout);
                }
                loadLogsTimeout = setTimeout(loadLogs, 500);
            }
            
            async function loadLogs() {
                const level = document.getElementById('log-level').value;
                const module = document.getElementById('log-module').value;
                const search = document.getElementById('log-search').value;
                const startDate = document.getElementById('log-start-date').value;
                const endDate = document.getElementById('log-end-date').value;
                
                const params = new URLSearchParams({
                    limit: logsLimit.toString(),
                    offset: logsOffset.toString()
                });
                
                if (level) params.append('level', level);
                if (module) params.append('module', module);
                if (search) params.append('search', search);
                if (startDate) params.append('start_date', new Date(startDate).toISOString());
                if (endDate) params.append('end_date', new Date(endDate).toISOString());
                
                try {
                    const response = await fetch(`${API_BASE}/api/logs?${params}`);
                    if (!response.ok) {
                        throw new Error('Failed to fetch logs');
                    }
                    
                    const data = await response.json();
                    logsTotal = data.total;
                    
                    // Update table
                    const tbody = document.getElementById('logs-table-body');
                    if (data.logs && data.logs.length > 0) {
                        // Store logs for modal access
                        currentLogsList = data.logs;
                        
                        tbody.innerHTML = data.logs.map((log, index) => {
                            const timestamp = new Date(log.timestamp);
                            const timeStr = timestamp.toLocaleString();
                            const moduleDisplay = log.module || log.logger_name || '-';
                            const messagePreview = log.message && log.message.length > 100 
                                ? escapeHtml(log.message.substring(0, 100)) + '...'
                                : escapeHtml(log.message || '');
                            return `
                                <tr class="log-row" onclick="showLogModal(${index})">
                                    <td class="log-timestamp">${timeStr}</td>
                                    <td><span class="log-level log-level-${log.level}">${log.level}</span></td>
                                    <td class="log-module">${moduleDisplay}</td>
                                    <td class="log-message" title="${escapeHtml(log.message || '')}">${messagePreview}</td>
                                </tr>
                            `;
                        }).join('');
                    } else {
                        tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: #b3b3b3;">No logs found</td></tr>';
                        currentLogsList = [];
                    }
                    
                    // Update pagination
                    updatePagination();
                } catch (error) {
                    console.error('Error loading logs:', error);
                    document.getElementById('logs-table-body').innerHTML = 
                        '<tr><td colspan="4" style="text-align: center; color: #e22134;">Error loading logs</td></tr>';
                }
            }
            
            function updatePagination() {
                const info = document.getElementById('pagination-info');
                const start = logsOffset + 1;
                const end = Math.min(logsOffset + logsLimit, logsTotal);
                info.textContent = `Showing ${start}-${end} of ${logsTotal} logs`;
                
                document.getElementById('prev-page').disabled = logsOffset === 0;
                document.getElementById('next-page').disabled = logsOffset + logsLimit >= logsTotal;
            }
            
            function changePage(direction) {
                const newOffset = logsOffset + (direction * logsLimit);
                if (newOffset >= 0 && newOffset < logsTotal) {
                    logsOffset = newOffset;
                    loadLogs();
                }
            }
            
            function escapeHtml(text) {
                if (text === null || text === undefined) return '';
                const div = document.createElement('div');
                div.textContent = String(text);
                return div.innerHTML;
            }
            
            function showLogModal(index) {
                if (!currentLogsList || index >= currentLogsList.length) {
                    console.error('Log not found at index:', index);
                    return;
                }
                
                const log = currentLogsList[index];
                const modal = document.getElementById('log-modal');
                const modalBody = document.getElementById('log-modal-body');
                
                const timestamp = new Date(log.timestamp);
                const timeStr = timestamp.toLocaleString();
                
                let extraDataHtml = '';
                if (log.extra_data) {
                    try {
                        const extraDataStr = JSON.stringify(log.extra_data, null, 2);
                        extraDataHtml = `<div class="log-modal-detail">
                            <div class="log-modal-detail-label">Extra Data:</div>
                            <div class="log-modal-detail-value json">${escapeHtml(extraDataStr)}</div>
                        </div>`;
                    } catch (e) {
                        extraDataHtml = `<div class="log-modal-detail">
                            <div class="log-modal-detail-label">Extra Data:</div>
                            <div class="log-modal-detail-value">${escapeHtml(String(log.extra_data))}</div>
                        </div>`;
                    }
                }
                
                modalBody.innerHTML = `
                    <div class="log-modal-detail">
                        <div class="log-modal-detail-label">Timestamp:</div>
                        <div class="log-modal-detail-value">${timeStr}</div>
                    </div>
                    <div class="log-modal-detail">
                        <div class="log-modal-detail-label">Level:</div>
                        <div class="log-modal-detail-value"><span class="log-level log-level-${log.level}">${log.level}</span></div>
                    </div>
                    <div class="log-modal-detail">
                        <div class="log-modal-detail-label">Logger Name:</div>
                        <div class="log-modal-detail-value">${escapeHtml(log.logger_name || '-')}</div>
                    </div>
                    ${log.module ? `<div class="log-modal-detail">
                        <div class="log-modal-detail-label">Module:</div>
                        <div class="log-modal-detail-value">${escapeHtml(log.module)}</div>
                    </div>` : ''}
                    ${log.function ? `<div class="log-modal-detail">
                        <div class="log-modal-detail-label">Function:</div>
                        <div class="log-modal-detail-value">${escapeHtml(log.function)}</div>
                    </div>` : ''}
                    ${log.line_number ? `<div class="log-modal-detail">
                        <div class="log-modal-detail-label">Line Number:</div>
                        <div class="log-modal-detail-value">${escapeHtml(String(log.line_number))}</div>
                    </div>` : ''}
                    <div class="log-modal-detail">
                        <div class="log-modal-detail-label">Message:</div>
                        <div class="log-modal-detail-value">${escapeHtml(log.message)}</div>
                    </div>
                    ${log.exception_info ? `<div class="log-modal-detail">
                        <div class="log-modal-detail-label">Exception Info:</div>
                        <div class="log-modal-detail-value" style="color: #e22134;">${escapeHtml(log.exception_info)}</div>
                    </div>` : ''}
                    ${extraDataHtml}
                `;
                
                modal.style.display = 'block';
            }
            
            function closeLogModal() {
                document.getElementById('log-modal').style.display = 'none';
            }
            
            // Close modal when clicking outside
            window.onclick = function(event) {
                const modal = document.getElementById('log-modal');
                if (event.target === modal) {
                    closeLogModal();
                }
            }
            
            // Update every 2 seconds
            updateStatus();
            setInterval(updateStatus, 2000);
            
            // Load logs on page load
            loadLogs();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

