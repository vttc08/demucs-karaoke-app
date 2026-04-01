// Queue page JavaScript
const API_BASE = window.location.origin;

// Search functionality
const searchInput = document.getElementById('search-input');
const searchBtn = document.getElementById('search-btn');
const searchResults = document.getElementById('search-results');
const queueList = document.getElementById('queue-list');
const stageRemoteStatus = document.getElementById('stage-remote-status');
const stageRemotePlayPauseBtn = document.getElementById('stage-remote-play-pause-btn');
const stageRemotePlayPauseIcon = document.getElementById('stage-remote-play-pause-icon');
const stageRemotePlayPauseLabel = document.getElementById('stage-remote-play-pause-label');
const stageRemoteSkipBtn = document.getElementById('stage-remote-skip-btn');
let stageRemotePaused = false;
let demucsHealth = { healthy: true, detail: 'Health unknown' };

searchBtn.addEventListener('click', performSearch);
searchInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        performSearch();
    }
});

// Auto-hide search button when typing
searchInput.addEventListener('input', (e) => {
    const hasText = e.target.value.trim().length > 0;
    searchBtn.style.opacity = hasText ? '1' : '0.7';
});

async function performSearch() {
    const query = searchInput.value.trim();
    if (!query) return;

    searchBtn.disabled = true;
    searchBtn.textContent = 'Searching...';
    searchResults.innerHTML = `
        <div class="glass-card p-6 rounded-lg text-center">
            <div class="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full mx-auto mb-3"></div>
            <p class="text-on-surface-variant">Searching YouTube...</p>
        </div>
    `;

    try {
        const response = await fetch(`${API_BASE}/api/search/?q=${encodeURIComponent(query)}`);
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Search failed');
        }
        
        const results = await response.json();
        await refreshDemucsHealth();
        displaySearchResults(results);
    } catch (error) {
        searchResults.innerHTML = `
            <div class="bg-error/10 border border-error/20 p-4 rounded-lg text-center">
                <span class="material-symbols-outlined text-error text-2xl mb-2">error</span>
                <p class="text-error font-medium mb-2">Search failed: ${error.message}</p>
                <button class="bg-error text-white px-4 py-2 rounded-full text-sm font-bold hover:brightness-110 active:scale-95 transition-all" onclick="performSearch()">
                    Retry
                </button>
            </div>
        `;
        console.error('Search error:', error);
    } finally {
        searchBtn.disabled = false;
        searchBtn.textContent = 'Search';
    }
}

async function refreshDemucsHealth() {
    try {
        const response = await fetch(`${API_BASE}/api/settings/demucs-health`);
        if (!response.ok) {
            throw new Error('Demucs health check failed');
        }
        demucsHealth = await response.json();
    } catch (error) {
        demucsHealth = { healthy: false, detail: String(error.message || 'Demucs unavailable') };
    }
}

function displaySearchResults(results) {
    if (results.length === 0) {
        searchResults.innerHTML = `
            <div class="text-center py-8">
                <span class="material-symbols-outlined text-4xl text-on-surface-variant mb-3 block">search_off</span>
                <p class="text-on-surface-variant">No results found</p>
            </div>
        `;
        return;
    }

    searchResults.innerHTML = results.map(result => `
        <div class="bg-surface-container-low hover:bg-surface-container p-4 rounded-lg transition-all" data-video-id="${result.video_id}">
            <div class="flex items-center gap-4">
                <div class="relative w-20 h-14 rounded-md overflow-hidden shrink-0">
                    <img 
                        src="${result.thumbnail || '/static/placeholder.png'}" 
                        alt="${escapeHtml(result.title)}"
                        class="w-full h-full object-cover"
                        onerror="this.parentElement.innerHTML='<div class=\\'w-full h-full bg-surface-container-highest flex items-center justify-center\\'><span class=\\'material-symbols-outlined text-on-surface-variant\\'>music_note</span></div>'"
                    >
                </div>
                <div class="flex-1 min-w-0">
                    <h4 class="font-bold text-on-surface truncate text-sm">${escapeHtml(result.title)}</h4>
                    <p class="text-xs text-on-surface-variant truncate">${escapeHtml(result.channel)}</p>
                    ${result.duration ? `<p class="text-xs text-on-surface-variant/60">${result.duration}</p>` : ''}
                    
                    <div class="flex items-center gap-3 mt-2">
                        <label class="flex items-center gap-2 text-xs cursor-pointer ${demucsHealth.healthy ? '' : 'opacity-40 cursor-not-allowed'}" title="${demucsHealth.healthy ? '' : escapeHtml(demucsHealth.detail)}">
                            <input type="checkbox" class="karaoke-checkbox sr-only" ${demucsHealth.healthy ? '' : 'disabled'}>
                            <div class="karaoke-toggle w-4 h-4 rounded border border-outline-variant flex items-center justify-center transition-all ${demucsHealth.healthy ? '' : 'border-error/60'}">
                                <span class="material-symbols-outlined text-[12px] text-transparent">check</span>
                            </div>
                            <span class="text-on-surface-variant">${demucsHealth.healthy ? 'Karaoke mode' : 'Karaoke mode (Demucs offline)'}</span>
                        </label>
                        <label class="flex items-center gap-2 text-xs cursor-pointer burn-lyrics-label opacity-50">
                            <input type="checkbox" class="burn-lyrics-checkbox sr-only" checked disabled>
                            <div class="burn-lyrics-toggle w-4 h-4 rounded border border-outline-variant flex items-center justify-center transition-all">
                                <span class="material-symbols-outlined text-[12px] text-transparent">check</span>
                            </div>
                            <span class="text-on-surface-variant">Burn lyrics</span>
                        </label>
                    </div>
                </div>
                <button class="add-to-queue-btn bg-primary text-on-primary px-4 py-2 rounded-full text-sm font-bold hover:brightness-110 active:scale-95 transition-all shrink-0" 
                        onclick="addToQueue('${result.video_id}', '${escapeHtml(result.title)}', '${escapeHtml(result.channel)}')">
                    Add
                </button>
            </div>
        </div>
    `).join('');

    // Setup checkbox interactions
    document.querySelectorAll('.karaoke-checkbox').forEach(checkbox => {
        const container = checkbox.closest('[data-video-id]');
        const toggle = container.querySelector('.karaoke-toggle');
        const burnContainer = container.querySelector('.burn-lyrics-label');
        const burnCheckbox = container.querySelector('.burn-lyrics-checkbox');
        const burnToggle = container.querySelector('.burn-lyrics-toggle');
        
        function updateUI() {
            if (checkbox.checked) {
                toggle.classList.add('bg-primary', 'border-primary');
                toggle.querySelector('.material-symbols-outlined').classList.remove('text-transparent');
                toggle.querySelector('.material-symbols-outlined').classList.add('text-on-primary');
                burnContainer.classList.remove('opacity-50');
                burnCheckbox.disabled = false;
                burnCheckbox.checked = true;
                updateBurnLyricsUI();
            } else {
                toggle.classList.remove('bg-primary', 'border-primary');
                toggle.querySelector('.material-symbols-outlined').classList.add('text-transparent');
                toggle.querySelector('.material-symbols-outlined').classList.remove('text-on-primary');
                burnContainer.classList.add('opacity-50');
                burnCheckbox.disabled = true;
                burnCheckbox.checked = false;
                updateBurnLyricsUI();
            }
        }
        
        function updateBurnLyricsUI() {
            if (burnCheckbox.checked && !burnCheckbox.disabled) {
                burnToggle.classList.add('bg-secondary', 'border-secondary');
                burnToggle.querySelector('.material-symbols-outlined').classList.remove('text-transparent');
                burnToggle.querySelector('.material-symbols-outlined').classList.add('text-white');
            } else {
                burnToggle.classList.remove('bg-secondary', 'border-secondary');
                burnToggle.querySelector('.material-symbols-outlined').classList.add('text-transparent');
                burnToggle.querySelector('.material-symbols-outlined').classList.remove('text-white');
            }
        }
        
        checkbox.addEventListener('change', updateUI);
        burnCheckbox.addEventListener('change', updateBurnLyricsUI);
        toggle.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopPropagation();
            checkbox.checked = !checkbox.checked;
            checkbox.dispatchEvent(new Event('change'));
        });
        burnToggle.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopPropagation();
            if (!burnCheckbox.disabled) {
                burnCheckbox.checked = !burnCheckbox.checked;
                burnCheckbox.dispatchEvent(new Event('change'));
            }
        });
        updateUI();
    });
}

async function addToQueue(videoId, title, channel) {
    const resultElement = document.querySelector(`[data-video-id="${videoId}"]`);
    const isKaraoke = resultElement.querySelector('.karaoke-checkbox').checked;
    const burnLyrics = isKaraoke ? resultElement.querySelector('.burn-lyrics-checkbox').checked : false;
    const button = resultElement.querySelector('.add-to-queue-btn');

        if (isKaraoke && !demucsHealth.healthy) {
            alert(`Karaoke mode is unavailable: ${demucsHealth.detail}`);
            return;
        }

        button.disabled = true;
    button.innerHTML = '<span class="material-symbols-outlined text-sm animate-spin">sync</span>';

    try {
        const response = await fetch(`${API_BASE}/api/queue/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                youtube_id: videoId,
                title: title,
                artist: channel,
                is_karaoke: isKaraoke,
                burn_lyrics: burnLyrics,
            }),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to add to queue');
        }

        const item = await response.json();

        // Trigger processing
        try {
            await fetch(`${API_BASE}/api/queue/${item.id}/process`, {
                method: 'POST',
            });
        } catch (processError) {
            console.warn('Processing trigger failed (will be retried):', processError);
        }

        button.innerHTML = '<span class="material-symbols-outlined text-sm">check</span>';
        button.classList.remove('bg-primary', 'text-on-primary');
        button.classList.add('bg-secondary', 'text-white');

        // Refresh queue
        setTimeout(() => {
            refreshQueue();
            // Clear search results after successful add
            searchInput.value = '';
            searchResults.innerHTML = '';
        }, 1000);
    } catch (error) {
        button.innerHTML = '<span class="material-symbols-outlined text-sm">error</span>';
        button.classList.remove('bg-primary', 'text-on-primary');
        button.classList.add('bg-error', 'text-white');
        console.error('Add to queue error:', error);
        
        // Show error message
        alert(`Failed to add to queue: ${error.message}`);
        
        // Reset button after 2 seconds
        setTimeout(() => {
            button.innerHTML = 'Add';
            button.disabled = false;
            button.classList.remove('bg-error', 'text-white');
            button.classList.add('bg-primary', 'text-on-primary');
        }, 2000);
    }
}

async function refreshQueue(force = false) {
    // Don't refresh if user is actively searching or typing
    if (!force && (document.activeElement === searchInput || 
        searchInput.value.trim().length > 0 || 
        searchResults.children.length > 0)) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/api/queue/`);
        const serverQueue = await response.json();
        
        // Get current queue from DOM
        const currentQueueElements = document.querySelectorAll('#queue-list .queue-item');
        const currentQueueIds = Array.from(currentQueueElements).map(el => el.dataset.id);
        const serverQueueIds = serverQueue.map(item => item.id.toString());
        
        // Only reload if queue actually changed (items added, removed, or status changed)
        const queueChanged = currentQueueIds.length !== serverQueueIds.length ||
                            !currentQueueIds.every((id, index) => id === serverQueueIds[index]);
        
        if (queueChanged) {
            // Gentle refresh - just update queue section instead of full page reload
            updateQueueDisplay(serverQueue);
        } else {
            // Check for status changes
            let statusChanged = false;
            serverQueue.forEach(item => {
                const element = document.querySelector(`[data-id="${item.id}"]`);
                if (element && element.dataset.status !== item.status) {
                    statusChanged = true;
                }
            });
            
            if (statusChanged) {
                updateQueueDisplay(serverQueue);
            }
        }
    } catch (error) {
        console.error('Refresh queue error:', error);
    }
}

function updateQueueDisplay(queue) {
    const queueList = document.getElementById('queue-list');
    if (!queueList) return;
    
    if (queue.length === 0) {
        queueList.innerHTML = `
            <div class="text-center py-12">
                <div class="w-20 h-20 mx-auto mb-4 rounded-full bg-surface-container flex items-center justify-center">
                    <span class="material-symbols-outlined text-4xl text-on-surface-variant">queue_music</span>
                </div>
                <p class="text-on-surface-variant text-lg font-medium">Queue is empty</p>
                <p class="text-on-surface-variant/60 text-sm">Search and add songs to get started!</p>
            </div>
        `;
        return;
    }
    
    queueList.innerHTML = queue.map(item => {
        const statusInfo = getStatusInfo(item.status);
        return `
            <div class="queue-item ${item.status === 'playing' ? 'glass-card border border-outline-variant/15 shadow-[0_0_20px_rgba(0,242,255,0.05)]' : 'bg-surface-container-low hover:bg-surface-container'} p-4 rounded-lg flex items-center gap-4 transition-all" data-id="${item.id}" data-status="${item.status}">
                <div class="relative w-16 h-16 rounded-md overflow-hidden shrink-0 ${item.status !== 'playing' ? 'grayscale-[50%]' : ''}">
                    <div class="w-full h-full bg-surface-container-highest flex items-center justify-center">
                        <span class="material-symbols-outlined text-2xl text-on-surface-variant">music_note</span>
                    </div>
                </div>
                <div class="flex-1 min-w-0">
                    <h3 class="font-bold ${item.status === 'playing' ? 'text-on-surface' : 'text-on-surface/80'} truncate">${escapeHtml(item.title)}</h3>
                    ${item.artist ? `<p class="text-xs text-on-surface-variant truncate">${escapeHtml(item.artist)}</p>` : ''}
                    <div class="mt-2 inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full ${statusInfo.bgClass}">
                        ${statusInfo.icon}
                        <span class="text-[10px] font-black uppercase tracking-tighter ${statusInfo.textClass}">${statusInfo.label}</span>
                    </div>
                    ${item.is_karaoke ? `
                    <div class="mt-1 inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-secondary/10 border border-secondary/20">
                        <span class="material-symbols-outlined text-[10px] text-secondary">mic</span>
                        <span class="text-[8px] font-bold uppercase tracking-tighter text-secondary">Karaoke</span>
                    </div>
                    ` : ''}
                </div>
                <div class="flex flex-col gap-2">
                    ${item.status === 'ready' ? `
                    <button class="w-10 h-10 rounded-full bg-primary text-on-primary flex items-center justify-center shadow-[0_0_15px_rgba(0,242,255,0.3)] active:scale-90 transition-all neon-glow" 
                            onclick="skipToSong('${item.id}')">
                        <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 1">play_arrow</span>
                    </button>
                    ` : item.status === 'playing' ? `
                    <button class="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center cursor-default" disabled title="Currently playing">
                        <span class="material-symbols-outlined">equalizer</span>
                    </button>
                    ` : `
                    <button class="w-10 h-10 rounded-full bg-surface-container-highest text-on-surface-variant flex items-center justify-center hover:text-error transition-colors" 
                            onclick="removeSong('${item.id}')">
                        <span class="material-symbols-outlined">remove</span>
                    </button>
                    `}
                </div>
            </div>
        `;
    }).join('');
}

function getStatusInfo(status) {
    switch(status) {
        case 'playing':
            return {
                icon: '<span class="w-1.5 h-1.5 rounded-full bg-primary animate-pulse"></span>',
                label: 'Playing',
                bgClass: 'bg-primary/10 border border-primary/20',
                textClass: 'text-primary'
            };
        case 'processing':
            return {
                icon: '<span class="material-symbols-outlined text-[12px] text-tertiary animate-spin">auto_fix_high</span>',
                label: 'Processing AI',
                bgClass: 'bg-tertiary/10 border border-tertiary/20',
                textClass: 'text-tertiary'
            };
        case 'downloading':
            return {
                icon: '<span class="material-symbols-outlined text-[12px] text-tertiary animate-pulse">download</span>',
                label: 'Downloading',
                bgClass: 'bg-tertiary/10 border border-tertiary/20',
                textClass: 'text-tertiary'
            };
        case 'failed':
            return {
                icon: '<span class="material-symbols-outlined text-[12px] text-error">error</span>',
                label: 'Failed',
                bgClass: 'bg-error/10 border border-error/20',
                textClass: 'text-error'
            };
        case 'ready':
            return {
                icon: '<span class="w-1.5 h-1.5 rounded-full bg-secondary"></span>',
                label: 'Ready',
                bgClass: 'bg-secondary/10 border border-secondary/20',
                textClass: 'text-secondary'
            };
        default:
            return {
                icon: '',
                label: 'In Queue',
                bgClass: 'bg-on-surface/5 border border-on-surface/10',
                textClass: 'text-on-surface-variant'
            };
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// WebSocket connection for real-time queue updates
class QueueWebSocket {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000; // Start with 1 second
        this.maxReconnectDelay = 8000; // Max 8 seconds
        this.isConnected = false;
        this.isReconnecting = false;
        this.heartbeatTimeout = null;
        this.statusIndicator = null;
        
        this.createStatusIndicator();
        this.connect();
    }
    
    createStatusIndicator() {
        // Reuse header status chip so indicator never overlaps controls
        this.statusIndicator = document.getElementById('ws-status');
    }
    
    updateStatus(status, message) {
        if (!this.statusIndicator) return;
        
        this.statusIndicator.textContent = message;
        
        switch (status) {
            case 'connected':
                this.statusIndicator.className = 'inline-flex items-center gap-1.5 rounded-full border border-primary/35 bg-primary/10 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary';
                this.statusIndicator.innerHTML = '<span class="h-1.5 w-1.5 rounded-full bg-primary animate-pulse"></span><span>Live</span>';
                this.statusIndicator.style.display = 'inline-flex';
                setTimeout(() => {
                    this.statusIndicator.style.display = 'none';
                }, 3000);
                break;
            case 'reconnecting':
                this.statusIndicator.className = 'inline-flex items-center gap-1.5 rounded-full border border-tertiary/35 bg-tertiary/10 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-tertiary';
                this.statusIndicator.innerHTML = `<span class="material-symbols-outlined text-[12px] animate-spin">sync</span><span>${message}</span>`;
                this.statusIndicator.style.display = 'inline-flex';
                break;
            case 'disconnected':
                this.statusIndicator.className = 'inline-flex items-center gap-1.5 rounded-full border border-error/35 bg-error/10 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-error';
                this.statusIndicator.innerHTML = '<span class="material-symbols-outlined text-[12px]">portable_wifi_off</span><span>Offline</span>';
                this.statusIndicator.style.display = 'inline-flex';
                break;
            case 'fallback':
                this.statusIndicator.className = 'inline-flex items-center gap-1.5 rounded-full border border-outline-variant/40 bg-surface-container-high px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-on-surface-variant';
                this.statusIndicator.innerHTML = '<span class="material-symbols-outlined text-[12px]">schedule</span><span>Polling</span>';
                this.statusIndicator.style.display = 'inline-flex';
                break;
        }
        this.updateRemoteControlsState();
    }

    updateRemoteControlsState() {
        const connected = this.ws && this.ws.readyState === WebSocket.OPEN;
        if (stageRemotePlayPauseBtn) stageRemotePlayPauseBtn.disabled = !connected;
        if (stageRemoteSkipBtn) stageRemoteSkipBtn.disabled = !connected;
        if (stageRemoteStatus) {
            stageRemoteStatus.textContent = connected ? 'Connected' : 'Offline';
        }
    }
    
    connect() {
        if (this.ws && (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)) {
            return;
        }
        
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/queue/ws`;
        
        console.log('[WebSocket] Connecting to', wsUrl);
        this.updateStatus('reconnecting', 'Connecting...');
        
        try {
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                console.log('[WebSocket] Connected');
                this.isConnected = true;
                this.isReconnecting = false;
                this.reconnectAttempts = 0;
                this.reconnectDelay = 1000;
                this.updateStatus('connected', '● Live');
                
                // Stop polling when WebSocket is connected
                if (refreshInterval) {
                    clearInterval(refreshInterval);
                    refreshInterval = null;
                }
            };
            
            this.ws.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    this.handleMessage(message);
                } catch (error) {
                    console.error('[WebSocket] Error parsing message:', error);
                }
            };
            
            this.ws.onerror = (error) => {
                console.error('[WebSocket] Error:', error);
            };
            
            this.ws.onclose = () => {
                console.log('[WebSocket] Disconnected');
                this.isConnected = false;
                
                if (this.heartbeatTimeout) {
                    clearTimeout(this.heartbeatTimeout);
                    this.heartbeatTimeout = null;
                }
                
                // Attempt reconnection
                if (this.reconnectAttempts < this.maxReconnectAttempts) {
                    this.reconnect();
                } else {
                    console.log('[WebSocket] Max reconnection attempts reached, falling back to polling');
                    this.updateStatus('fallback', 'Using polling');
                    this.fallbackToPolling();
                }
            };
        } catch (error) {
            console.error('[WebSocket] Connection error:', error);
            this.reconnect();
        }
    }
    
    reconnect() {
        if (this.isReconnecting) return;
        
        this.isReconnecting = true;
        this.reconnectAttempts++;
        
        const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1), this.maxReconnectDelay);
        
        console.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
        this.updateStatus('reconnecting', `Reconnecting... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
        
        setTimeout(() => {
            this.isReconnecting = false;
            this.connect();
        }, delay);
    }
    
    fallbackToPolling() {
        console.log('[WebSocket] Falling back to polling mode');
        // Start the traditional polling interval
        if (!refreshInterval) {
            refreshInterval = setInterval(() => {
                if (document.visibilityState === 'visible') {
                    refreshQueue();
                }
            }, 15000); // 15 seconds in fallback mode
        }
    }
    
    handleMessage(message) {
        console.log('[WebSocket] Received:', message.type, message.data);
        
        switch (message.type) {
            case 'connected':
                console.log('[WebSocket] Connection confirmed, active connections:', message.data.connection_count);
                break;
            case 'ping':
                // Respond to server ping
                this.send({ type: 'pong', timestamp: Date.now() });
                break;
            case 'queue_item_added':
                window.dispatchEvent(new CustomEvent('queue_item_added', { detail: message.data }));
                break;
            case 'queue_item_updated':
                window.dispatchEvent(new CustomEvent('queue_item_updated', { detail: message.data }));
                break;
            case 'queue_item_removed':
                window.dispatchEvent(new CustomEvent('queue_item_removed', { detail: message.data }));
                break;
            case 'queue_cleared':
                window.dispatchEvent(new CustomEvent('queue_cleared', { detail: message.data }));
                break;
            case 'current_item_changed':
                window.dispatchEvent(new CustomEvent('current_item_changed', { detail: message.data }));
                break;
            case 'queue_item_failed':
                window.dispatchEvent(new CustomEvent('queue_item_failed', { detail: message.data }));
                break;
            case 'stage_state_update':
                window.dispatchEvent(new CustomEvent('stage_state_update', { detail: message.data }));
                break;
            default:
                console.log('[WebSocket] Unknown message type:', message.type);
        }
    }
    
    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
            return true;
        }
        return false;
    }
    
    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        if (this.heartbeatTimeout) {
            clearTimeout(this.heartbeatTimeout);
            this.heartbeatTimeout = null;
        }
    }
}

function updateStageRemotePlayPauseUi() {
    if (!stageRemotePlayPauseIcon || !stageRemotePlayPauseLabel) return;
    stageRemotePlayPauseIcon.textContent = stageRemotePaused ? 'play_arrow' : 'pause';
    stageRemotePlayPauseLabel.textContent = stageRemotePaused ? 'Play' : 'Pause';
}

// Initialize WebSocket connection
let queueWebSocket = null;
if (window.location.pathname === '/queue' || window.location.pathname === '/') {
    queueWebSocket = new QueueWebSocket();
}

if (stageRemotePlayPauseBtn) {
    stageRemotePlayPauseBtn.addEventListener('click', () => {
        if (!queueWebSocket) return;
        const command = stageRemotePaused ? 'play' : 'pause';
        const sent = queueWebSocket.send({
            type: 'stage_command',
            data: {
                command,
                source: 'queue',
            },
            timestamp: Date.now(),
        });
        if (!sent) {
            alert('Stage control is offline');
            return;
        }
        stageRemotePaused = !stageRemotePaused;
        updateStageRemotePlayPauseUi();
    });
}

if (stageRemoteSkipBtn) {
    stageRemoteSkipBtn.addEventListener('click', () => {
        if (!queueWebSocket) return;
        const sent = queueWebSocket.send({
            type: 'stage_command',
            data: {
                command: 'skip',
                source: 'queue',
            },
            timestamp: Date.now(),
        });
        if (!sent) {
            alert('Stage control is offline');
        }
    });
}

// WebSocket event handlers
window.addEventListener('queue_item_added', (event) => {
    console.log('[Event] Queue item added:', event.detail);
    // Refresh the entire queue to maintain order
    refreshQueue(true);
});

window.addEventListener('queue_item_updated', (event) => {
    console.log('[Event] Queue item updated:', event.detail);
    const item = event.detail;
    const element = document.querySelector(`[data-id="${item.id}"]`);
    
    if (element) {
        // Update the status without full refresh
        const oldStatus = element.dataset.status;
        if (oldStatus !== item.status) {
            console.log(`[Event] Status changed for item ${item.id}: ${oldStatus} → ${item.status}`);
            // Smooth refresh - update just this item's display
            refreshQueue(true);
        }
    } else {
        // Item not in DOM yet, refresh to add it
        refreshQueue(true);
    }
});

window.addEventListener('queue_item_removed', (event) => {
    console.log('[Event] Queue item removed:', event.detail);
    const itemId = event.detail.id;
    const element = document.querySelector(`[data-id="${itemId}"]`);
    
    if (element) {
        // Animate removal
        element.style.transition = 'all 0.3s ease-out';
        element.style.opacity = '0';
        element.style.transform = 'translateX(100%)';
        
        setTimeout(() => {
            element.remove();
            
            // Check if queue is now empty
            const queueList = document.getElementById('queue-list');
            if (queueList && queueList.children.length === 0) {
                queueList.innerHTML = `
                    <div class="text-center py-12">
                        <div class="w-20 h-20 mx-auto mb-4 rounded-full bg-surface-container flex items-center justify-center">
                            <span class="material-symbols-outlined text-4xl text-on-surface-variant">queue_music</span>
                        </div>
                        <p class="text-on-surface-variant text-lg font-medium">Queue is empty</p>
                        <p class="text-on-surface-variant/60 text-sm">Search and add songs to get started!</p>
                    </div>
                `;
            }
        }, 300);
    }
});

window.addEventListener('queue_cleared', (event) => {
    console.log('[Event] Queue cleared');
    const queueList = document.getElementById('queue-list');
    
    if (queueList) {
        // Remove all non-playing items with animation
        const items = queueList.querySelectorAll('.queue-item');
        items.forEach((item, index) => {
            if (item.dataset.status !== 'playing') {
                setTimeout(() => {
                    item.style.transition = 'all 0.3s ease-out';
                    item.style.opacity = '0';
                    item.style.transform = 'translateX(100%)';
                    
                    setTimeout(() => {
                        item.remove();
                        
                        // Check if only playing item or empty
                        const remainingItems = queueList.querySelectorAll('.queue-item');
                        if (remainingItems.length === 0) {
                            queueList.innerHTML = `
                                <div class="text-center py-12">
                                    <div class="w-20 h-20 mx-auto mb-4 rounded-full bg-surface-container flex items-center justify-center">
                                        <span class="material-symbols-outlined text-4xl text-on-surface-variant">queue_music</span>
                                    </div>
                                    <p class="text-on-surface-variant text-lg font-medium">Queue is empty</p>
                                    <p class="text-on-surface-variant/60 text-sm">Search and add songs to get started!</p>
                                </div>
                            `;
                        }
                    }, 300);
                }, index * 50); // Stagger the animations
            }
        });
    }
});

window.addEventListener('current_item_changed', (event) => {
    console.log('[Event] Current item changed:', event.detail);
    // Refresh to update playing state visuals
    refreshQueue(true);
});

window.addEventListener('queue_item_failed', (event) => {
    console.log('[Event] Queue item failed:', event.detail);
    const { id, error } = event.detail;
    
    // Show error notification
    const notification = document.createElement('div');
    notification.className = 'fixed bottom-4 right-4 bg-error/90 text-on-error px-4 py-3 rounded-lg shadow-lg max-w-md z-50 animate-slide-in';
    notification.innerHTML = `
        <div class="flex items-start gap-3">
            <span class="material-symbols-outlined">error</span>
            <div>
                <p class="font-medium">Processing Failed</p>
                <p class="text-sm opacity-90">${escapeHtml(error)}</p>
            </div>
        </div>
    `;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.transition = 'all 0.3s ease-out';
        notification.style.opacity = '0';
        notification.style.transform = 'translateX(100%)';
        setTimeout(() => notification.remove(), 300);
    }, 5000);
    
    // Refresh queue to show failed status
    refreshQueue(true);
});

window.addEventListener('stage_state_update', (event) => {
    const isPaused = event.detail?.is_paused;
    if (typeof isPaused === 'boolean') {
        stageRemotePaused = isPaused;
        updateStageRemotePlayPauseUi();
    }
});

// Much gentler auto-refresh - only when user is not actively using search
// Note: This is primarily for fallback mode when WebSocket is unavailable
let refreshInterval;
function startQueueRefresh() {
    if (refreshInterval) clearInterval(refreshInterval);
    refreshInterval = setInterval(() => {
        if (document.visibilityState === 'visible') {
            refreshQueue();
        }
    }, 8000); // 8 seconds for initial load, 15 seconds in fallback mode
}

// Don't start polling automatically - let WebSocket handle it
// Only start if WebSocket initialization fails
if (!queueWebSocket) {
    startQueueRefresh();
}
refreshDemucsHealth();
updateStageRemotePlayPauseUi();

// Pause refresh during search interactions
searchInput.addEventListener('focus', () => {
    if (refreshInterval) clearInterval(refreshInterval);
});

searchInput.addEventListener('blur', () => {
    // Only resume if not connected via WebSocket
    if (!queueWebSocket || !queueWebSocket.isConnected) {
        setTimeout(startQueueRefresh, 2000);
    }
});

// Clear search results when input is cleared
searchInput.addEventListener('input', (e) => {
    if (e.target.value.trim() === '') {
        searchResults.innerHTML = '';
    }
});
