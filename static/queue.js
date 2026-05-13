// Queue page JavaScript
const API_BASE = window.KaraokeURLs?.basePath || "";
const appUrl = window.KaraokeURLs?.appUrl || ((path) => path);
const appWsUrl = window.KaraokeURLs?.appWsUrl || ((path) => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}${path}`;
});
const t = window.KaraokeI18n?.t?.bind(window.KaraokeI18n) || ((key, params = {}) => key);

// Simple logger for frontend debugging
const logger = {
    log: (...args) => console.log(...args),
    warn: (...args) => console.warn(...args),
    error: (...args) => console.error(...args),
};

// Lyrics manager instance for queue modal
let lyricsManager = null;
let lyricsUIAdapter = null;

// Search functionality
const searchInput = document.getElementById('search-input');
const searchBtn = document.getElementById('search-btn');
const searchResults = document.getElementById('search-results');
const queueList = document.getElementById('queue-list');
const mainElement = document.querySelector('main[data-is-admin]');
const isAdminUser = mainElement?.dataset.isAdmin === 'true';
const queuePresenceList = document.getElementById('queue-presence-list');
const queuePresenceCount = document.getElementById('queue-presence-count');
const stageRemoteStatus = document.getElementById('stage-remote-status');
const stageRemotePlayPauseBtn = document.getElementById('stage-remote-play-pause-btn');
const stageRemotePlayPauseIcon = document.getElementById('stage-remote-play-pause-icon');
const stageRemotePlayPauseLabel = document.getElementById('stage-remote-play-pause-label');
const stageRemoteSkipBtn = document.getElementById('stage-remote-skip-btn');
const stageRemoteResyncBtn = document.getElementById('stage-remote-resync-btn');
const stageRemoteLyricsToggleBtn = document.getElementById('stage-remote-lyrics-toggle-btn');
const stageRemoteLyricsToggleIcon = document.getElementById('stage-remote-lyrics-toggle-icon');
const stageRemoteLyricsToggleLabel = document.getElementById('stage-remote-lyrics-toggle-label');
const stageRemoteVocalsToggleBtn = document.getElementById('stage-remote-vocals-toggle-btn');
const stageRemoteVocalsToggleIcon = document.getElementById('stage-remote-vocals-toggle-icon');
const stageRemoteVocalsToggleLabel = document.getElementById('stage-remote-vocals-toggle-label');
const stageRemoteVocalsVolumeSlider = document.getElementById('stage-remote-vocals-volume-slider');
const queueConfigModal = document.getElementById('queue-config-modal');
const queueConfigModalBackdrop = document.getElementById('queue-config-modal-backdrop');
const queueConfigCloseBtn = document.getElementById('queue-config-close-btn');
const queueConfigCancelBtn = document.getElementById('queue-config-cancel-btn');
const queueConfigConfirmBtn = document.getElementById('queue-config-confirm-btn');
const queueConfigQueueAsPanel = document.getElementById('queue-config-queue-as-panel');
const queueConfigQueueAsInput = document.getElementById('queue-config-queue-as-input');
const queueConfigQueueAsSuggestions = document.getElementById('queue-config-queue-as-suggestions');
const queueAsSettingsPanel = document.getElementById('queue-as-settings-panel');
const queueAsEnabledToggle = document.getElementById('queue-as-enabled-toggle');
const queueAsCurrentLabel = document.getElementById('queue-as-current-label');
const queueAsModal = document.getElementById('queue-as-modal');
const queueAsModalBackdrop = document.getElementById('queue-as-modal-backdrop');
const queueAsCloseBtn = document.getElementById('queue-as-close-btn');
const queueAsCancelBtn = document.getElementById('queue-as-cancel-btn');
const queueAsConfirmBtn = document.getElementById('queue-as-confirm-btn');
const queueAsInput = document.getElementById('queue-as-input');
const queueAsSuggestions = document.getElementById('queue-as-suggestions');
const queueConfigSongThumb = document.getElementById('queue-config-song-thumb');
const queueConfigSongTitle = document.getElementById('queue-config-song-title');
const queueConfigSongChannel = document.getElementById('queue-config-song-channel');
const queueConfigKaraokeToggle = document.getElementById('queue-config-karaoke-toggle');
const queueConfigKaraokeStatus = document.getElementById('queue-config-karaoke-status');
const queueConfigKaraokeDetail = document.getElementById('queue-config-karaoke-detail');
const queueConfigLyricsToggle = document.getElementById('queue-config-lyrics-toggle');
const queueConfigLyricsDetail = document.getElementById('queue-config-lyrics-detail');
const queueToast = document.getElementById('queue-toast');
const queueToastText = document.getElementById('queue-toast-text');
const QUEUE_AS_ENABLED_STORAGE_KEY = 'karaoke.queueAs.enabled';
const QUEUE_AS_LAST_NAME_STORAGE_KEY = 'karaoke.queueAs.lastName';
const QUEUE_CONFIRM_DEFAULT_HTML = `<span class="material-symbols-outlined text-base" style="font-variation-settings: 'FILL' 1">add_circle</span>${t('common.add_to_queue')}`;
const QUEUE_CONFIRM_LOADING_HTML = `<span class="material-symbols-outlined animate-spin text-base">sync</span>${t('lyrics.searching_providers')}`;
const KARAOKE_TITLE_HINT_RE = /\b(karaoke|ktv|sing[-\s]?along|off[-\s]?vocal|no[-\s]?vocal|instrumental|noraebang)\b/i;
const LYRICS_TITLE_HINT_RE = /\b(lyrics?|lyric\s+video|with\s+lyrics)\b/i;
let stageRemotePaused = false;
let stageRemoteLyricsEnabled = true;
let stageRemoteLyricsAvailable = false;
let stageRemoteVocalsEnabled = true;
let stageRemoteVocalsVolume = 1.0;
let stageRemoteVocalsAvailable = false;
let demucsHealth = { healthy: true, detail: t('settings.engine_unknown') };
let modalSelection = null;
let modalKaraokeEnabled = false;
let queueToastTimer = null;
let queuePresenceUsers = [];
let queueAsEnabled = false;
let queueAsModalResolver = null;

function getCookieValue(name) {
    const match = document.cookie
        .split('; ')
        .find((cookie) => cookie.startsWith(`${name}=`));
    return match ? decodeURIComponent(match.split('=').slice(1).join('=')) : '';
}

function sanitizePresenceValue(value, maxLength = 80) {
    return String(value || '').replace(/\s+/g, ' ').trim().slice(0, maxLength);
}

function sanitizeQueueAsName(value) {
    return sanitizePresenceValue(value, 40);
}

function setCookieValue(name, value, maxAge = 31536000) {
    const secure = window.location.protocol === 'https:' ? '; Secure' : '';
    document.cookie = `${name}=${encodeURIComponent(value)}; Max-Age=${maxAge}; Path=/; SameSite=Lax${secure}`;
}

function ensureGuestId() {
    const current = sanitizePresenceValue(getCookieValue('karaoke_guest_id'));
    if (current) {
        return current;
    }
    const guestId = (window.crypto?.randomUUID?.() || `guest-${Date.now()}-${Math.random().toString(16).slice(2)}`).slice(0, 80);
    setCookieValue('karaoke_guest_id', guestId);
    return guestId;
}

function ensureQueueTabId() {
    const current = sanitizePresenceValue(sessionStorage.getItem('karaoke_queue_tab_id'));
    if (current) {
        setCookieValue('karaoke_queue_tab_id', current);
        return current;
    }
    const tabId = (window.crypto?.randomUUID?.() || `tab-${Date.now()}-${Math.random().toString(16).slice(2)}`).slice(0, 80);
    sessionStorage.setItem('karaoke_queue_tab_id', tabId);
    setCookieValue('karaoke_queue_tab_id', tabId);
    return tabId;
}

function getCurrentSingerName() {
    const labelName = sanitizePresenceValue(document.getElementById('queue-singer-name')?.textContent, 40);
    const cookieName = sanitizePresenceValue(getCookieValue('karaoke_singer'), 40);
    const datasetName = sanitizePresenceValue(mainElement?.dataset.singerName, 40);
    return cookieName || datasetName || labelName || t('common.guest');
}

function setLocalStorageValue(key, value) {
    try {
        localStorage.setItem(key, value);
    } catch (_) {
        // Keep queue interactions functional when storage is unavailable.
    }
}

function getLocalStorageValue(key, fallback = null) {
    try {
        const value = localStorage.getItem(key);
        return value === null ? fallback : value;
    } catch (_) {
        return fallback;
    }
}

function getQueueAsLastName() {
    return sanitizeQueueAsName(getLocalStorageValue(QUEUE_AS_LAST_NAME_STORAGE_KEY, '') || '');
}

function setQueueAsLastName(name) {
    const normalized = sanitizeQueueAsName(name);
    if (normalized) {
        setLocalStorageValue(QUEUE_AS_LAST_NAME_STORAGE_KEY, normalized);
    }
    return normalized;
}

function updateQueueAsCurrentLabel(nameOverride = null) {
    if (!queueAsCurrentLabel) {
        return;
    }
    const name = sanitizeQueueAsName(nameOverride ?? getQueueAsLastName());
    if (name) {
        queueAsCurrentLabel.textContent = t('queue.queue_as_current', { name });
    } else {
        queueAsCurrentLabel.textContent = t('queue.queue_as_current_none');
    }
}

function updateQueueAsToggleUi() {
    if (!queueAsEnabledToggle) {
        return;
    }
    queueAsEnabledToggle.checked = queueAsEnabled;
}

function readQueueAsEnabledSetting() {
    const raw = getLocalStorageValue(QUEUE_AS_ENABLED_STORAGE_KEY, 'false');
    return raw === 'true';
}

function writeQueueAsEnabledSetting(enabled) {
    setLocalStorageValue(QUEUE_AS_ENABLED_STORAGE_KEY, enabled ? 'true' : 'false');
}

function getQueueAsSuggestions() {
    const unique = new Map();
    queuePresenceUsers.forEach((user) => {
        const normalized = sanitizeQueueAsName(user?.display_name);
        if (!normalized) {
            return;
        }
        const key = normalized.toLowerCase();
        if (!unique.has(key)) {
            unique.set(key, normalized);
        }
    });
    return Array.from(unique.values());
}

function renderQueueAsSuggestions(targetElement = queueAsSuggestions) {
    if (!targetElement) {
        return;
    }
    const suggestions = getQueueAsSuggestions();
    if (!suggestions.length) {
        targetElement.innerHTML = `<p class="text-xs text-on-surface-variant">${escapeHtml(t('queue.queue_as_no_recent'))}</p>`;
        return;
    }
    targetElement.innerHTML = suggestions.map((name) => `
        <button
            type="button"
            class="queue-as-suggestion-btn inline-flex items-center rounded-full bg-surface-container-highest px-3 py-1.5 text-xs font-semibold text-on-surface transition-colors hover:text-primary"
            data-queue-as-name="${escapeHtml(name)}"
        >
            ${escapeHtml(name)}
        </button>
    `).join('');
}

function closeQueueAsModal() {
    if (!queueAsModal) {
        return;
    }
    queueAsModal.classList.add('hidden');
    queueAsModal.classList.remove('flex');
    const queueConfigOpen = queueConfigModal && !queueConfigModal.classList.contains('hidden');
    if (!queueConfigOpen) {
        document.body.classList.remove('overflow-hidden');
    }
}

function resolveQueueAsModal(value) {
    const resolver = queueAsModalResolver;
    queueAsModalResolver = null;
    closeQueueAsModal();
    if (resolver) {
        resolver(value);
    }
}

function openQueueAsModal(defaultName = '') {
    if (!queueAsModal) {
        return Promise.resolve(sanitizeQueueAsName(defaultName) || null);
    }
    renderQueueAsSuggestions();
    if (queueAsInput) {
        queueAsInput.value = sanitizeQueueAsName(defaultName);
        window.setTimeout(() => queueAsInput.focus(), 60);
    }
    queueAsModal.classList.remove('hidden');
    queueAsModal.classList.add('flex');
    document.body.classList.add('overflow-hidden');

    return new Promise((resolve) => {
        queueAsModalResolver = resolve;
    });
}

function initializeQueueAsSettings() {
    if (!isAdminUser || !queueAsSettingsPanel) {
        return;
    }
    queueAsEnabled = readQueueAsEnabledSetting();
    updateQueueAsToggleUi();
    updateQueueAsCurrentLabel();

    queueAsEnabledToggle?.addEventListener('change', () => {
        queueAsEnabled = Boolean(queueAsEnabledToggle.checked);
        writeQueueAsEnabledSetting(queueAsEnabled);
        updateQueueAsToggleUi();
    });

    queueAsSuggestions?.addEventListener('click', (event) => {
        const button = event.target.closest('.queue-as-suggestion-btn');
        if (!button || !queueAsInput) {
            return;
        }
        queueAsInput.value = sanitizeQueueAsName(button.dataset.queueAsName);
        queueAsInput.focus();
    });

    queueAsConfirmBtn?.addEventListener('click', () => {
        const selectedName = sanitizeQueueAsName(queueAsInput?.value || '');
        if (!selectedName) {
            if (queueAsInput) {
                queueAsInput.focus();
            }
            return;
        }
        setQueueAsLastName(selectedName);
        updateQueueAsCurrentLabel(selectedName);
        resolveQueueAsModal(selectedName);
    });

    const cancelQueueAs = () => resolveQueueAsModal(null);
    queueAsCloseBtn?.addEventListener('click', cancelQueueAs);
    queueAsCancelBtn?.addEventListener('click', cancelQueueAs);
    queueAsModalBackdrop?.addEventListener('click', cancelQueueAs);
}

async function submitQueueItemWithQueueAs(selection, buttonElement, options = {}) {
    if (!isAdminUser || !queueAsEnabled) {
        return submitQueueItem(selection, buttonElement, options);
    }
    const defaultName = getQueueAsLastName() || getCurrentSingerName();
    const queueAsName = await openQueueAsModal(defaultName);
    if (!queueAsName) {
        return;
    }
    return submitQueueItem(selection, buttonElement, { ...options, queueAsName });
}

function renderPresenceList() {
    if (!queuePresenceList || !queuePresenceCount) {
        return;
    }

    if (!queuePresenceUsers.length) {
        queuePresenceCount.textContent = t('queue.no_one_here');
        queuePresenceList.innerHTML = `<p class="text-sm text-on-surface-variant">${t('queue.presence_waiting')}</p>`;
        return;
    }

    queuePresenceCount.textContent = t('queue.people_here_count', { count: queuePresenceUsers.length });
    queuePresenceList.innerHTML = queuePresenceUsers.map((user) => `
        <span class="inline-flex items-center gap-2 rounded-full border border-outline-variant/20 bg-surface-container-highest px-3 py-2 text-sm font-semibold text-on-surface">
            <span class="h-2 w-2 rounded-full bg-primary"></span>
            <span>${escapeHtml(user.display_name || t('common.guest'))}</span>
            ${user.connection_count > 1 ? `<span class="rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-primary">x${user.connection_count}</span>` : ''}
        </span>
    `).join('');
    if (queueAsModal && !queueAsModal.classList.contains('hidden')) {
        renderQueueAsSuggestions();
    }
    if (queueConfigModal && !queueConfigModal.classList.contains('hidden')) {
        renderQueueAsSuggestions(queueConfigQueueAsSuggestions);
    }
}

function upsertPresenceUser(user) {
    if (!user || !user.guest_id) {
        return;
    }
    const nextUser = {
        guest_id: user.guest_id,
        display_name: sanitizePresenceValue(user.display_name, 40) || t('common.guest'),
        joined_at: user.joined_at || null,
        connection_count: Number.isFinite(Number(user.connection_count)) ? Number(user.connection_count) : 1,
    };
    const index = queuePresenceUsers.findIndex((entry) => entry.guest_id === nextUser.guest_id);
    if (index >= 0) {
        queuePresenceUsers[index] = { ...queuePresenceUsers[index], ...nextUser };
    } else {
        queuePresenceUsers.push(nextUser);
    }
    queuePresenceUsers.sort((a, b) => {
        const joinedA = String(a.joined_at || '');
        const joinedB = String(b.joined_at || '');
        if (joinedA !== joinedB) {
            return joinedA.localeCompare(joinedB);
        }
        return String(a.display_name || '').localeCompare(String(b.display_name || ''));
    });
    renderPresenceList();
}

function removePresenceUser(guestId) {
    queuePresenceUsers = queuePresenceUsers.filter((user) => user.guest_id !== guestId);
    renderPresenceList();
}

async function refreshPresenceFallback() {
    try {
        const response = await fetch(`${API_BASE}/api/queue/presence`);
        if (!response.ok) {
            throw new Error(`Presence refresh failed: ${response.status}`);
        }
        const payload = await response.json();
        queuePresenceUsers = Array.isArray(payload.users) ? payload.users : [];
        renderPresenceList();
    } catch (error) {
        logger.warn('Presence fallback refresh failed:', error);
    }
}

function showQueueToast(message) {
    if (!queueToast || !queueToastText) {
        return;
    }

    queueToastText.textContent = message;
    queueToast.classList.remove('opacity-0', 'translate-y-3');
    queueToast.classList.add('opacity-100', 'translate-y-0');

    if (queueToastTimer) {
        clearTimeout(queueToastTimer);
    }
    queueToastTimer = setTimeout(() => {
        queueToast.classList.remove('opacity-100', 'translate-y-0');
        queueToast.classList.add('opacity-0', 'translate-y-3');
    }, 2200);
}

function getTitleHints(title) {
    const normalizedTitle = String(title || '').trim();
    return {
        karaokeLike: KARAOKE_TITLE_HINT_RE.test(normalizedTitle),
        lyricsLike: LYRICS_TITLE_HINT_RE.test(normalizedTitle),
    };
}

function getModalTitleHints() {
    return getTitleHints(modalSelection?.title || '');
}

function getModalDefaults() {
    const karaokeAvailable = demucsHealth.healthy;
    const hints = getModalTitleHints();

    if (hints.karaokeLike) {
        return { karaokeEnabled: false, lyricsEnabled: false };
    }

    if (hints.lyricsLike) {
        return { karaokeEnabled: karaokeAvailable, lyricsEnabled: false };
    }

    return { karaokeEnabled: karaokeAvailable, lyricsEnabled: karaokeAvailable };
}

/**
 * Initialize lyrics manager for the queue modal
 */
function initializeLyricsManager() {
    if (lyricsManager) return;
    
    lyricsManager = new LyricsManager({ apiBase: API_BASE });
    lyricsUIAdapter = new LyricsUIAdapter(lyricsManager, {
        titleInput: '#queue-config-lyrics-title',
        artistInput: '#queue-config-lyrics-artist',
        textarea: '#queue-config-lyrics-textarea',
        stateLabel: '#queue-config-lyrics-state',
        providerLabel: '#queue-config-lyrics-provider',
        helpText: '#queue-config-lyrics-help',
        searchBtn: '#queue-config-lyrics-search-btn',
        uploadBtn: '#queue-config-lyrics-upload-btn',
        fileInput: '#queue-config-lyrics-file',
        googleLink: '#queue-config-lyrics-google-link',
        panel: '#queue-config-lyrics-panel',
    });
    
    lyricsUIAdapter.initialize();
    lyricsManager.on(() => {
        syncQueueConfigModalUi();
    });
}

searchResults.addEventListener('click', async (event) => {
    const button = event.target.closest('.add-to-queue-btn');
    if (!button || button.disabled) return;

    const resultElement = button.closest('[data-result-source]');
    if (!resultElement) return;

    const source = resultElement.dataset.resultSource || 'youtube';
    if (source === 'local') {
        await submitQueueItemWithQueueAs(buildQueueSelection(resultElement, button), button, {
            isKaraoke: false,
            lyricsEnabled: false,
        });
        return;
    }

    openQueueConfigModal(resultElement, button);
});

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
    searchBtn.textContent = t('lyrics.searching');
    searchResults.innerHTML = `
        <div class="glass-card p-6 rounded-lg text-center">
            <div class="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full mx-auto mb-3"></div>
            <p class="text-on-surface-variant">${t('queue.searching_local')}</p>
        </div>
    `;

    try {
        // Phase 1: Fetch local results (fast)
        let localResults = [];
        try {
            const localResponse = await fetch(`${API_BASE}/api/search/?q=${encodeURIComponent(query)}&source=local`);
            if (localResponse.ok) {
                localResults = await localResponse.json();
            }
        } catch (error) {
            logger.warn('Local search failed:', error);
            // Continue to YouTube even if local search fails
        }

        // Display local results immediately
        if (localResults.length > 0) {
            displaySearchResults(localResults);
            refreshDemucsHealth().then(() => {
                if (modalSelection) {
                    syncQueueConfigModalUi();
                }
            });
            
            // Update UI to show YouTube is searching
            const loadingDiv = document.createElement('div');
            loadingDiv.className = 'glass-card p-4 rounded-lg text-center';
            loadingDiv.innerHTML = `
                <div class="flex items-center justify-center gap-2">
                    <div class="animate-spin w-4 h-4 border border-primary border-t-transparent rounded-full"></div>
                    <p class="text-xs text-on-surface-variant">${t('queue.searching_youtube_also')}</p>
                </div>
            `;
            searchResults.appendChild(loadingDiv);
        } else {
            // No local results, show YouTube loading message
            searchResults.innerHTML = `
                <div class="glass-card p-6 rounded-lg text-center">
                    <div class="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full mx-auto mb-3"></div>
                    <p class="text-on-surface-variant">${t('queue.searching_youtube')}</p>
                </div>
            `;
        }

        // Phase 2: Fetch YouTube results in background
        let youtubeResults = [];
        try {
            const youtubeResponse = await fetch(`${API_BASE}/api/search/?q=${encodeURIComponent(query)}&source=youtube`);
            if (youtubeResponse.ok) {
                youtubeResults = await youtubeResponse.json();
            }
        } catch (error) {
            logger.error('YouTube search failed:', error);
            // Show just local results if YouTube fails
            if (localResults.length > 0) {
                // Remove the loading indicator
                const loadingDiv = searchResults.querySelector('.glass-card:last-child');
                if (loadingDiv && loadingDiv.querySelector('.animate-spin')) {
                    loadingDiv.remove();
                }
                // Show error message
                const errorDiv = document.createElement('div');
                errorDiv.className = 'bg-tertiary/10 border border-tertiary/20 p-3 rounded-lg text-center';
                errorDiv.innerHTML = `
                    <p class="text-[12px] text-tertiary font-medium">${t('queue.youtube_unavailable')}</p>
                `;
                searchResults.appendChild(errorDiv);
                return;
            } else {
                // No local results and YouTube failed
                throw error;
            }
        }

        // Phase 3: Deduplicate and append YouTube results
        if (youtubeResults.length > 0) {
            // Build set of already-shown result keys
            const shownKeys = new Set();
            localResults.forEach(result => {
                const key = getResultKey(result);
                if (key) shownKeys.add(key);
            });

            // Filter out duplicates from YouTube results
            const uniqueYoutubeResults = youtubeResults.filter(result => {
                const key = getResultKey(result);
                return !key || !shownKeys.has(key);
            });

            if (uniqueYoutubeResults.length > 0) {
                // Remove the loading indicator
                const loadingDiv = searchResults.querySelector('.glass-card:last-child');
                if (loadingDiv && loadingDiv.querySelector('.animate-spin')) {
                    loadingDiv.remove();
                }

                // Append YouTube results
                const combinedResults = [...localResults, ...uniqueYoutubeResults];
                displaySearchResults(combinedResults);
            } else {
                // All YouTube results were duplicates, remove loading indicator
                const loadingDiv = searchResults.querySelector('.glass-card:last-child');
                if (loadingDiv && loadingDiv.querySelector('.animate-spin')) {
                    loadingDiv.remove();
                }
            }
        } else {
            // No YouTube results
            if (localResults.length === 0) {
                // No results from either source
                searchResults.innerHTML = `
                    <div class="text-center py-8">
                        <span class="material-symbols-outlined text-4xl text-on-surface-variant mb-3 block">search_off</span>
                        <p class="text-on-surface-variant">${t('queue.no_results')}</p>
                    </div>
                `;
            } else {
                // Just remove loading indicator for local-only display
                const loadingDiv = searchResults.querySelector('.glass-card:last-child');
                if (loadingDiv && loadingDiv.querySelector('.animate-spin')) {
                    loadingDiv.remove();
                }
            }
        }
    } catch (error) {
        searchResults.innerHTML = `
            <div class="bg-error/10 border border-error/20 p-4 rounded-lg text-center">
                <span class="material-symbols-outlined text-error text-2xl mb-2">error</span>
                <p class="text-error font-medium mb-2">${t('queue.search_failed_detail', { message: error.message })}</p>
                <button class="bg-error text-white px-4 py-2 rounded-full text-sm font-bold hover:brightness-110 active:scale-95 transition-all" onclick="performSearch()">
                    ${t('queue.retry')}
                </button>
            </div>
        `;
        console.error('Search error:', error);
    } finally {
        searchBtn.disabled = false;
        searchBtn.textContent = t('common.search');
    }
}

/**
 * Generate a unique key for deduplication based on result properties.
 * Prioritizes video_id (for YouTube links), falls back to normalized title+channel.
 */
function getResultKey(result) {
    if (result.video_id) {
        return `yt:${result.video_id}`;
    }
    if (result.media_item_id) {
        return `local:${result.media_item_id}`;
    }
    // Fallback: normalize title and channel for comparison
    const normalizedTitle = (result.title || '').toLowerCase().trim();
    const normalizedChannel = (result.channel || '').toLowerCase().trim();
    if (normalizedTitle && normalizedChannel) {
        return `title:${normalizedTitle}|${normalizedChannel}`;
    }
    return null;
}

function getYouTubeWatchUrl(videoId) {
    return videoId ? `https://www.youtube.com/watch?v=${encodeURIComponent(videoId)}` : null;
}

function renderSearchResultTitle(result, sizeClass) {
    const classes = `font-bold text-on-surface truncate ${sizeClass}`.trim();
    const previewUrl = result.source !== 'local' ? getYouTubeWatchUrl(result.video_id) : null;

    if (previewUrl) {
        return `
            <a
                href="${escapeHtml(previewUrl)}"
                target="_blank"
                rel="noopener noreferrer"
                class="block ${classes} hover:underline underline-offset-2"
            >
                ${escapeHtml(result.title)}
            </a>
        `;
    }

    return `<h4 class="${classes}">${escapeHtml(result.title)}</h4>`;
}

async function refreshDemucsHealth() {
    try {
        const response = await fetch(`${API_BASE}/api/settings/demucs-health`);
        if (!response.ok) {
            throw new Error(t('queue.demucs_health_failed'));
        }
        demucsHealth = await response.json();
    } catch (error) {
        demucsHealth = { healthy: false, detail: String(error.message || t('queue.demucs_unavailable')) };
    }
}

function updateModalToggleAppearance(toggleButton, enabled, accentClass = 'bg-primary') {
    if (!toggleButton) return;
    const knob = toggleButton.querySelector('span');
    toggleButton.setAttribute('aria-checked', enabled ? 'true' : 'false');
    toggleButton.classList.toggle(accentClass, enabled);
    toggleButton.classList.toggle('bg-surface-container-highest', !enabled);
    if (knob) {
        knob.classList.toggle('translate-x-5', enabled);
        knob.classList.toggle('bg-white', enabled);
        knob.classList.toggle('bg-on-surface-variant', !enabled);
    }
}

function buildQueueSelection(resultElement, triggerButton) {
    return {
        source: resultElement.dataset.resultSource || 'youtube',
        videoId: resultElement.dataset.videoId || null,
        mediaItemId: resultElement.dataset.mediaItemId || null,
        title: resultElement.dataset.title || '',
        channel: resultElement.dataset.channel || '',
        thumbnail: resultElement.dataset.thumbnail || appUrl('/static/placeholder.png'),
        triggerButton,
    };
}

function syncQueueSongTitleLink() {
    if (!queueConfigSongTitle || !modalSelection) return;

    const previewUrl = getYouTubeWatchUrl(modalSelection.videoId);
    queueConfigSongTitle.textContent = modalSelection.title || t('queue.selected_song');
    queueConfigSongTitle.title = previewUrl ? t('queue.open_youtube') : '';

    if (previewUrl) {
        queueConfigSongTitle.href = previewUrl;
        queueConfigSongTitle.classList.remove('cursor-default', 'pointer-events-none');
        queueConfigSongTitle.classList.add('cursor-pointer');
    } else {
        queueConfigSongTitle.removeAttribute('href');
        queueConfigSongTitle.removeAttribute('title');
        queueConfigSongTitle.classList.remove('cursor-pointer');
        queueConfigSongTitle.classList.add('cursor-default', 'pointer-events-none');
    }
}

function syncQueueConfirmState() {
    if (!queueConfigConfirmBtn) return;

    const lyricsState = lyricsManager?.state.lyricsState || 'idle';
    const lyricsRequired = Boolean(lyricsManager?.state.lyricsEnabled);
    const ready = !lyricsRequired
        || ['resolved', 'not_found', 'error', 'manual'].includes(lyricsState)
        || Boolean(lyricsManager?.getSubmissionText());
    const waiting = lyricsRequired && lyricsState === 'loading';
    const queueAsRequired = isAdminUser
        && queueAsEnabled
        && modalSelection?.source !== 'local'
        && Boolean(queueConfigQueueAsPanel)
        && !sanitizeQueueAsName(queueConfigQueueAsInput?.value || '');
    const disabled = waiting || (lyricsRequired && !ready) || queueAsRequired;

    queueConfigConfirmBtn.disabled = disabled;
    queueConfigConfirmBtn.setAttribute('aria-disabled', disabled ? 'true' : 'false');
    queueConfigConfirmBtn.setAttribute('aria-busy', waiting ? 'true' : 'false');
    queueConfigConfirmBtn.title = waiting
        ? t('queue.lyrics_resolving')
        : lyricsRequired && !ready
            ? t('queue.resolve_before_continue')
            : queueAsRequired
                ? t('queue.queue_as_required')
                : t('queue.add_song_to_queue');

    queueConfigConfirmBtn.classList.toggle('bg-primary', !disabled);
    queueConfigConfirmBtn.classList.toggle('text-on-primary', !disabled);
    queueConfigConfirmBtn.classList.toggle('bg-surface-container-highest', disabled);
    queueConfigConfirmBtn.classList.toggle('text-on-surface-variant', disabled);

    queueConfigConfirmBtn.innerHTML = waiting ? QUEUE_CONFIRM_LOADING_HTML : QUEUE_CONFIRM_DEFAULT_HTML;
}

function syncQueueAsInQueueConfig() {
    const inlineQueueAsEnabled = isAdminUser
        && queueAsEnabled
        && modalSelection?.source !== 'local'
        && Boolean(queueConfigQueueAsPanel);
    if (!queueConfigQueueAsPanel) {
        return;
    }
    queueConfigQueueAsPanel.classList.toggle('hidden', !inlineQueueAsEnabled);
    if (!inlineQueueAsEnabled) {
        return;
    }
    renderQueueAsSuggestions(queueConfigQueueAsSuggestions);
    if (queueConfigQueueAsInput) {
        const current = sanitizeQueueAsName(queueConfigQueueAsInput.value);
        if (!current) {
            queueConfigQueueAsInput.value = getQueueAsLastName() || getCurrentSingerName();
        }
    }
}

async function openQueueConfigModal(resultElement, triggerButton) {
    if (!queueConfigModal || !queueConfigConfirmBtn) {
        await submitQueueItemWithQueueAs(buildQueueSelection(resultElement, triggerButton), triggerButton, {
            isKaraoke: false,
            lyricsEnabled: false,
        });
        return;
    }

    initializeLyricsManager();
    modalSelection = buildQueueSelection(resultElement, triggerButton);

    const defaults = getModalDefaults();
    modalKaraokeEnabled = defaults.karaokeEnabled;
    lyricsManager.reset();
    lyricsManager.setMetadata(modalSelection.title || '', modalSelection.channel || '', modalSelection.title || '');
    lyricsManager.setEnabled(defaults.lyricsEnabled);

    syncQueueSongTitleLink();
    if (queueConfigSongChannel) queueConfigSongChannel.textContent = modalSelection.channel || '';
    if (queueConfigSongThumb) {
        queueConfigSongThumb.src = modalSelection.thumbnail;
        queueConfigSongThumb.onerror = () => {
            queueConfigSongThumb.src = appUrl('/static/placeholder.png');
        };
    }

    queueConfigConfirmBtn.disabled = false;
    queueConfigConfirmBtn.setAttribute('aria-disabled', 'false');
    queueConfigConfirmBtn.setAttribute('aria-busy', 'false');
    queueConfigConfirmBtn.title = t('queue.add_song_to_queue');
    queueConfigConfirmBtn.classList.remove('bg-secondary', 'text-white', 'bg-error', 'bg-surface-container-highest', 'text-on-surface-variant');
    queueConfigConfirmBtn.classList.add('bg-primary', 'text-on-primary');
    queueConfigConfirmBtn.innerHTML = QUEUE_CONFIRM_DEFAULT_HTML;
    queueConfigModal.classList.remove('hidden');
    queueConfigModal.classList.add('flex');
    document.body.classList.add('overflow-hidden');

    if (queueConfigQueueAsInput) {
        queueConfigQueueAsInput.value = getQueueAsLastName() || getCurrentSingerName();
    }
    syncQueueConfigModalUi();

    if (lyricsManager.state.lyricsEnabled && modalKaraokeEnabled && lyricsManager.shouldAutoResolve()) {
        lyricsManager.resolve('auto').catch((error) => {
            console.error('Lyrics auto-resolve failed:', error);
        });
    }

    refreshDemucsHealth().then(() => {
        if (modalSelection) {
            syncQueueConfigModalUi();
        }
    });
}

function closeQueueConfigModal() {
    if (!queueConfigModal) return;
    if (lyricsManager) {
        lyricsManager.reset();
    }
    queueConfigModal.classList.add('hidden');
    queueConfigModal.classList.remove('flex');
    document.body.classList.remove('overflow-hidden');
    modalSelection = null;
    modalKaraokeEnabled = false;
}

function displaySearchResults(results) {
    if (results.length === 0) {
        searchResults.innerHTML = `
            <div class="text-center py-8">
                <span class="material-symbols-outlined text-4xl text-on-surface-variant mb-3 block">search_off</span>
                <p class="text-on-surface-variant">${t('queue.no_results')}</p>
            </div>
        `;
        return;
    }

    searchResults.innerHTML = results.map(result => {
        const isDownloaded = result.source === 'local' || result.downloaded;
        const source = escapeHtml(result.source || 'youtube');
        const videoId = escapeHtml(result.video_id || '');
        const mediaItemId = result.media_item_id ?? '';
        const title = escapeHtml(result.title || '');
        const channel = escapeHtml(result.channel || '');
        const thumbnail = escapeHtml(appUrl(result.thumbnail || '/static/placeholder.png'));

        if (isDownloaded) {
            return `
                <div
                    class="bg-surface-container-lowest hover:bg-surface-container-low p-3 rounded-lg transition-all border border-outline-variant/10"
                    data-result-source="${source}"
                    data-video-id="${videoId}"
                    data-media-item-id="${mediaItemId}"
                    data-title="${title}"
                    data-channel="${channel}"
                    data-thumbnail="${thumbnail}"
                >
                    <div class="flex items-center gap-3">
                        <div class="relative w-12 h-12 rounded-md overflow-hidden shrink-0">
                            <img src="${thumbnail}" alt="${title}" class="w-full h-full object-cover" onerror="this.parentElement.innerHTML='<div class=\\'w-full h-full bg-surface-container-highest flex items-center justify-center\\'><span class=\\'material-symbols-outlined text-on-surface-variant\\'>music_note</span></div>'">
                        </div>
                        <div class="flex-1 min-w-0">
                            ${renderSearchResultTitle(result, 'text-xs')}
                            <p class="text-[11px] text-on-surface-variant truncate">${channel}</p>
                            <div class="mt-1 flex items-center gap-1.5">
                                ${result.source === 'local' ? `
                                    <div class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-primary/10 border border-primary/20">
                                        <span class="material-symbols-outlined text-[9px] text-primary">library_music</span>
                                        <span class="text-[7px] font-bold uppercase tracking-tighter text-primary">Local</span>
                                    </div>
                                ` : ''}
                                <div class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-secondary/10 border border-secondary/20">
                                    <span class="material-symbols-outlined text-[9px] text-secondary">download_done</span>
                                    <span class="text-[7px] font-bold uppercase tracking-tighter text-secondary">${t('common.ready')}</span>
                                </div>
                            </div>
                        </div>
                        <button class="add-to-queue-btn bg-primary text-on-primary px-3 py-1.5 rounded-full text-xs font-bold hover:brightness-110 active:scale-95 transition-all shrink-0" type="button">Add</button>
                    </div>
                </div>
            `;
        }

        return `
            <div
                class="bg-surface-container-low hover:bg-surface-container p-4 rounded-lg transition-all"
                data-result-source="${source}"
                data-video-id="${videoId}"
                data-media-item-id="${mediaItemId}"
                data-title="${title}"
                data-channel="${channel}"
                data-thumbnail="${thumbnail}"
            >
                <div class="flex items-center gap-4">
                    <div class="relative w-20 h-14 rounded-md overflow-hidden shrink-0">
                        <img src="${thumbnail}" alt="${title}" class="w-full h-full object-cover" onerror="this.parentElement.innerHTML='<div class=\\'w-full h-full bg-surface-container-highest flex items-center justify-center\\'><span class=\\'material-symbols-outlined text-on-surface-variant\\'>music_note</span></div>'">
                    </div>
                    <div class="flex-1 min-w-0">
                        ${renderSearchResultTitle(result, 'text-sm')}
                        <p class="text-xs text-on-surface-variant truncate">${channel}</p>
                        ${result.duration ? `<p class="text-xs text-on-surface-variant/60">${escapeHtml(result.duration)}</p>` : ''}
                    </div>
                    <button class="add-to-queue-btn bg-primary text-on-primary px-4 py-2 rounded-full text-sm font-bold hover:brightness-110 active:scale-95 transition-all shrink-0" type="button">Add</button>
                </div>
            </div>
        `;
    }).join('');
}

async function addToQueueFromModal(selection, buttonElement) {
    const queueAsName = isAdminUser && queueAsEnabled && selection?.source !== 'local'
        ? sanitizeQueueAsName(queueConfigQueueAsInput?.value || '')
        : null;
    if (queueAsName) {
        setQueueAsLastName(queueAsName);
        updateQueueAsCurrentLabel(queueAsName);
    }
    return submitQueueItem(selection, buttonElement, {
        isKaraoke: modalKaraokeEnabled,
        lyricsEnabled: Boolean(lyricsManager?.state.lyricsEnabled),
        queueAsName,
    });
}

function syncQueueConfigModalUi() {
    const karaokeAvailable = demucsHealth.healthy;
    const titleHints = getModalTitleHints();
    if (!karaokeAvailable) {
        modalKaraokeEnabled = false;
    }

    if (queueConfigKaraokeToggle) {
        queueConfigKaraokeToggle.disabled = !karaokeAvailable;
        queueConfigKaraokeToggle.classList.toggle('opacity-50', !karaokeAvailable);
        queueConfigKaraokeToggle.classList.toggle('cursor-not-allowed', !karaokeAvailable);
    }
    if (queueConfigKaraokeStatus) {
        queueConfigKaraokeStatus.classList.toggle('hidden', karaokeAvailable);
    }
    if (queueConfigKaraokeDetail) {
        if (!karaokeAvailable) {
            queueConfigKaraokeDetail.textContent = t('queue.demucs_offline', { detail: demucsHealth.detail });
        } else if (titleHints.karaokeLike) {
            queueConfigKaraokeDetail.textContent = t('queue.karaoke_already_detail');
        } else {
            queueConfigKaraokeDetail.textContent = t('queue.remove_vocals_ai');
        }
    }

    updateModalToggleAppearance(queueConfigKaraokeToggle, modalKaraokeEnabled, 'bg-tertiary');

    const lyricsEnabled = modalKaraokeEnabled;
    if (!lyricsEnabled && lyricsManager?.state.lyricsEnabled) {
        lyricsManager.setEnabled(false);
    }
    
    if (queueConfigLyricsToggle) {
        queueConfigLyricsToggle.disabled = !lyricsEnabled;
        queueConfigLyricsToggle.classList.toggle('opacity-50', !lyricsEnabled);
        queueConfigLyricsToggle.classList.toggle('cursor-not-allowed', !lyricsEnabled);
    }
    
    if (lyricsManager) {
        updateModalToggleAppearance(queueConfigLyricsToggle, lyricsManager.state.lyricsEnabled, 'bg-secondary');
    }

    if (queueConfigLyricsDetail) {
        if (titleHints.lyricsLike) {
            queueConfigLyricsDetail.textContent = t('queue.lyrics_already_detail');
        } else {
            queueConfigLyricsDetail.textContent = t('queue.lyrics_detail');
        }
    }
    syncQueueAsInQueueConfig();

    syncQueueConfirmState();
}

async function submitQueueItem(selection, buttonElement, options = {}) {
    const source = selection?.source || 'youtube';
    const videoId = selection?.videoId || null;
    const mediaItemId = selection?.mediaItemId || null;
    const isKaraoke = Boolean(options.isKaraoke);
    const lyricsEnabled = Boolean(options.lyricsEnabled && isKaraoke && lyricsManager);
    const queueAsName = sanitizeQueueAsName(options.queueAsName);
    
    // Get title/artist from manager if available, otherwise fall back to selection
    const title = lyricsEnabled && lyricsManager.state.title 
        ? lyricsManager.state.title 
        : (selection?.title || '');
    const artist = lyricsEnabled && lyricsManager.state.artist 
        ? lyricsManager.state.artist 
        : (selection?.channel || '');
    
    const lyricsText = lyricsEnabled ? lyricsManager.getSubmissionText() : '';
    const lyricsFormat = lyricsText ? LyricsManager.inferFormat(lyricsText) : null;
    const button = buttonElement || queueConfigConfirmBtn;
    if (!button) {
        throw new Error('Missing add-to-queue trigger button');
    }

    if (isKaraoke && !demucsHealth.healthy) {
        alert(t('queue.karaoke_unavailable', { detail: demucsHealth.detail }));
        return;
    }

    button.disabled = true;
    button.innerHTML = '<span class="material-symbols-outlined text-sm animate-spin">sync</span>';

    try {
        const payload = {
            title: title,
            artist: artist,
            is_karaoke: isKaraoke,
        };
        if (isKaraoke && lyricsEnabled && lyricsText) {
            payload.lyrics_text = lyricsText;
            payload.lyrics_format = lyricsFormat;
        }
        if (source === 'local' && mediaItemId) {
            payload.media_item_id = Number(mediaItemId);
        } else if (videoId) {
            payload.youtube_id = videoId;
        } else {
            throw new Error('Missing media source identifier');
        }
        if (queueAsName) {
            payload.queue_as_name = queueAsName;
        }

        const response = await fetch(`${API_BASE}/api/queue/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || t('media.queue_failed'));
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
            closeQueueConfigModal();
        }, 1000);
    } catch (error) {
        button.innerHTML = '<span class="material-symbols-outlined text-sm">error</span>';
        button.classList.remove('bg-primary', 'text-on-primary');
        button.classList.add('bg-error', 'text-white');
        console.error('Add to queue error:', error);
        
        // Show error message
        alert(t('queue.add_failed_detail', { message: error.message }));
        
        // Reset button after 2 seconds
        setTimeout(() => {
            button.innerHTML = QUEUE_CONFIRM_DEFAULT_HTML;
            button.disabled = false;
            button.classList.remove('bg-error', 'text-white');
            button.classList.add('bg-primary', 'text-on-primary');
        }, 2000);
    }
}

if (queueConfigKaraokeToggle) {
    queueConfigKaraokeToggle.addEventListener('click', () => {
        if (queueConfigKaraokeToggle.disabled) return;
        modalKaraokeEnabled = !modalKaraokeEnabled;
        if (modalKaraokeEnabled && getModalTitleHints().karaokeLike) {
            showQueueToast(t('queue.karaoke_already'));
        }
        syncQueueConfigModalUi();
    });
}

if (queueConfigLyricsToggle) {
    queueConfigLyricsToggle.addEventListener('click', () => {
        if (queueConfigLyricsToggle.disabled || !lyricsManager) return;
        const newEnabled = !lyricsManager.state.lyricsEnabled;
        if (newEnabled && modalSelection) {
            lyricsManager.setMetadata(modalSelection.title || '', modalSelection.channel || '', modalSelection.title || '');
        }
        lyricsManager.setEnabled(newEnabled);

        if (newEnabled) {
            if (getModalTitleHints().lyricsLike) {
                showQueueToast(t('queue.lyrics_already'));
            }
            if (lyricsManager.shouldAutoResolve()) {
                lyricsManager.resolve('auto');
            }
        }

        syncQueueConfigModalUi();
    });
}

if (queueConfigQueueAsSuggestions) {
    queueConfigQueueAsSuggestions.addEventListener('click', (event) => {
        const button = event.target.closest('.queue-as-suggestion-btn');
        if (!button || !queueConfigQueueAsInput) {
            return;
        }
        queueConfigQueueAsInput.value = sanitizeQueueAsName(button.dataset.queueAsName);
        queueConfigQueueAsInput.focus();
        syncQueueConfirmState();
    });
}

if (queueConfigQueueAsInput) {
    queueConfigQueueAsInput.addEventListener('input', () => {
        syncQueueConfirmState();
    });
}

if (queueConfigConfirmBtn) {
    queueConfigConfirmBtn.addEventListener('click', async () => {
        if (!modalSelection) return;
        await addToQueueFromModal(modalSelection, queueConfigConfirmBtn);
    });
}

if (queueConfigCloseBtn) {
    queueConfigCloseBtn.addEventListener('click', closeQueueConfigModal);
}

if (queueConfigCancelBtn) {
    queueConfigCancelBtn.addEventListener('click', closeQueueConfigModal);
}

if (queueConfigModalBackdrop) {
    queueConfigModalBackdrop.addEventListener('click', closeQueueConfigModal);
}

window.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && queueConfigModal && !queueConfigModal.classList.contains('hidden')) {
        closeQueueConfigModal();
    }
    if (event.key === 'Escape' && queueAsModal && !queueAsModal.classList.contains('hidden')) {
        resolveQueueAsModal(null);
    }
});

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
        syncStageVocalsAvailability(serverQueue);
        syncStageLyricsAvailability(serverQueue);
        
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
                <p class="text-on-surface-variant text-lg font-medium">${t('queue.empty')}</p>
                <p class="text-on-surface-variant/60 text-sm">${t('queue.add_started')}</p>
            </div>
        `;
        return;
    }

    const movableItems = queue.filter((item) => item.status !== 'playing');
    const movableIndexById = new Map(movableItems.map((item, index) => [String(item.id), index]));
    const movableCount = movableItems.length;

    queueList.innerHTML = queue.map(item => {
        const statusInfo = getStatusInfo(item.status);
        const thumbnail = escapeHtml(appUrl(item.thumbnail || '/static/placeholder.png'));
        const leftActionHtml = item.status === 'playing' ? `
                    <button class="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center cursor-default" disabled title="${t('queue.playing')}">
                        <span class="material-symbols-outlined">equalizer</span>
                    </button>
                    ` : isAdminUser ? `
                    <div class="flex flex-col items-center gap-1">
                        <button
                            id="queue-move-up-${item.id}"
                            class="w-9 h-9 rounded-full bg-surface-container-highest text-on-surface-variant flex items-center justify-center transition-colors hover:text-primary disabled:cursor-not-allowed disabled:opacity-40"
                            onclick="moveSong('${item.id}', 'up')"
                            ${movableIndexById.get(String(item.id)) === 0 ? 'disabled' : ''}
                            title="${escapeHtml(t('queue.move_up'))}"
                            aria-label="${escapeHtml(t('queue.move_up'))}"
                        >
                            <span class="material-symbols-outlined text-[18px]">keyboard_arrow_up</span>
                        </button>
                        <button
                            id="queue-move-down-${item.id}"
                            class="w-9 h-9 rounded-full bg-surface-container-highest text-on-surface-variant flex items-center justify-center transition-colors hover:text-primary disabled:cursor-not-allowed disabled:opacity-40"
                            onclick="moveSong('${item.id}', 'down')"
                            ${movableIndexById.get(String(item.id)) === movableCount - 1 ? 'disabled' : ''}
                            title="${escapeHtml(t('queue.move_down'))}"
                            aria-label="${escapeHtml(t('queue.move_down'))}"
                        >
                            <span class="material-symbols-outlined text-[18px]">keyboard_arrow_down</span>
                        </button>
                    </div>
                    ` : '<span class="w-10 h-10" aria-hidden="true"></span>';
    const rightActionHtml = item.can_remove ? `
                    <button class="w-10 h-10 rounded-full bg-surface-container-highest text-on-surface-variant flex items-center justify-center hover:text-error transition-colors"
                            onclick="removeSong('${item.id}')">
                        <span class="material-symbols-outlined">remove</span>
                    </button>
                    ` : '<span class="w-10 h-10" aria-hidden="true"></span>';
        const leftColumnHtml = isAdminUser ? `
                <div class="flex shrink-0 flex-col items-center gap-1">
                    ${leftActionHtml}
                </div>
                ` : '';
        return `
            <div class="queue-item ${item.status === 'playing' ? 'glass-card border border-outline-variant/15 shadow-[0_0_20px_rgba(0,242,255,0.05)]' : 'bg-surface-container-low hover:bg-surface-container'} p-4 rounded-lg flex items-center gap-4 transition-all" data-id="${item.id}" data-status="${item.status}">
                ${leftColumnHtml}
                <div class="relative w-16 h-16 rounded-md overflow-hidden shrink-0 ${item.status !== 'playing' ? 'grayscale-[50%]' : ''}">
                    <img src="${thumbnail}" alt="${escapeHtml(item.title)}" class="w-full h-full object-cover" onerror="this.parentElement.innerHTML='<div class=\\'w-full h-full bg-surface-container-highest flex items-center justify-center\\'><span class=\\'material-symbols-outlined text-on-surface-variant\\'>music_note</span></div>'">
                </div>
                <div class="flex-1 min-w-0">
                    <h3 class="font-bold ${item.status === 'playing' ? 'text-on-surface' : 'text-on-surface/80'} truncate">${escapeHtml(item.title)}</h3>
                    ${item.artist ? `<p class="text-xs text-on-surface-variant truncate">${escapeHtml(item.artist)}</p>` : ''}
                    ${item.requested_by_name ? `<p class="mt-1 text-[11px] font-medium uppercase tracking-wide text-on-surface-variant">${escapeHtml(t('queue.requested_by', { name: item.requested_by_name }))}</p>` : ''}
                    <div class="mt-2 inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full ${statusInfo.bgClass}">
                        ${statusInfo.icon}
                        <span class="text-[10px] font-black uppercase tracking-tighter ${statusInfo.textClass}">${statusInfo.label}</span>
                    </div>
                    ${item.is_karaoke ? `
                    <div class="mt-1 inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-secondary/10 border border-secondary/20">
                        <span class="material-symbols-outlined text-[10px] text-secondary">mic</span>
                        <span class="text-[8px] font-bold uppercase tracking-tighter text-secondary">${t('app.karaoke')}</span>
                    </div>
                    ` : ''}
                </div>
                <div class="flex shrink-0 items-center">
                    ${rightActionHtml}
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
                label: t('queue.playing'),
                bgClass: 'bg-primary/10 border border-primary/20',
                textClass: 'text-primary'
            };
        case 'processing':
            return {
                icon: '<span class="material-symbols-outlined text-[12px] text-tertiary animate-spin">auto_fix_high</span>',
                label: t('queue.processing_ai'),
                bgClass: 'bg-tertiary/10 border border-tertiary/20',
                textClass: 'text-tertiary'
            };
        case 'downloading':
            return {
                icon: '<span class="material-symbols-outlined text-[12px] text-tertiary animate-pulse">download</span>',
                label: t('queue.downloading'),
                bgClass: 'bg-tertiary/10 border border-tertiary/20',
                textClass: 'text-tertiary'
            };
        case 'failed':
            return {
                icon: '<span class="material-symbols-outlined text-[12px] text-error">error</span>',
                label: t('common.failed'),
                bgClass: 'bg-error/10 border border-error/20',
                textClass: 'text-error'
            };
        case 'ready':
            return {
                icon: '<span class="w-1.5 h-1.5 rounded-full bg-secondary"></span>',
                label: t('common.ready'),
                bgClass: 'bg-secondary/10 border border-secondary/20',
                textClass: 'text-secondary'
            };
        default:
            return {
                icon: '',
                label: t('queue.in_queue'),
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

async function moveSong(songId, direction) {
    try {
        const response = await fetch(window.KaraokeURLs.appUrl(`/api/queue/${songId}/move`), {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ direction }),
        });

        if (response.ok) {
            await refreshQueue(true);
            return;
        }

        let detail = t('queue.move_failed');
        try {
            const payload = await response.json();
            if (payload?.detail) {
                detail = payload.detail;
            }
        } catch (_) {
            // Keep fallback text.
        }
        alert(detail);
    } catch (error) {
        console.error('Error moving queue item:', error);
        alert(t('queue.move_failed'));
    }
}

window.moveSong = moveSong;

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
        this.guestId = ensureGuestId();
        this.tabId = ensureQueueTabId();
        
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
                this.statusIndicator.innerHTML = `<span class="h-1.5 w-1.5 rounded-full bg-primary animate-pulse"></span><span>${t('queue.live')}</span>`;
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
                this.statusIndicator.innerHTML = `<span class="material-symbols-outlined text-[12px]">portable_wifi_off</span><span>${t('queue.offline')}</span>`;
                this.statusIndicator.style.display = 'inline-flex';
                break;
            case 'fallback':
                this.statusIndicator.className = 'inline-flex items-center gap-1.5 rounded-full border border-outline-variant/40 bg-surface-container-high px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-on-surface-variant';
                this.statusIndicator.innerHTML = `<span class="material-symbols-outlined text-[12px]">schedule</span><span>${t('queue.polling')}</span>`;
                this.statusIndicator.style.display = 'inline-flex';
                break;
        }
        this.updateRemoteControlsState();
    }

    updateRemoteControlsState() {
        const connected = this.ws && this.ws.readyState === WebSocket.OPEN;
        if (stageRemotePlayPauseBtn) stageRemotePlayPauseBtn.disabled = !connected;
        if (stageRemoteSkipBtn) stageRemoteSkipBtn.disabled = !connected;
        if (stageRemoteResyncBtn) stageRemoteResyncBtn.disabled = !connected;
        updateStageRemoteLyricsUi();
        updateStageRemoteVocalsUi();
        if (stageRemoteStatus) {
            stageRemoteStatus.textContent = connected ? t('queue.connected') : t('queue.offline');
        }
    }
    
    connect() {
        if (this.ws && (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)) {
            return;
        }
        
        const wsUrl = appWsUrl('/api/queue/ws');
        
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
                this.updateStatus('connected', `● ${t('queue.live')}`);
                
                // Stop polling when WebSocket is connected
                if (refreshInterval) {
                    clearInterval(refreshInterval);
                    refreshInterval = null;
                }
                this.sendPresenceHello();
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
        refreshPresenceFallback();
        // Start the traditional polling interval
        if (!refreshInterval) {
            refreshInterval = setInterval(() => {
                if (document.visibilityState === 'visible') {
                    refreshQueue();
                    refreshPresenceFallback();
                }
            }, 15000); // 15 seconds in fallback mode
        }
    }

    buildPresencePayload() {
        this.guestId = ensureGuestId();
        this.tabId = ensureQueueTabId();
        return {
            guest_id: this.guestId,
            display_name: getCurrentSingerName(),
            tab_id: this.tabId,
            page: 'queue',
        };
    }

    sendPresenceHello() {
        return this.send({
            type: 'presence_hello',
            data: this.buildPresencePayload(),
            timestamp: Date.now(),
        });
    }

    sendPresenceUpdate() {
        return this.send({
            type: 'presence_update',
            data: this.buildPresencePayload(),
            timestamp: Date.now(),
        });
    }
    
    handleMessage(message) {
        console.log('[WebSocket] Received:', message.type, message.data);
        
        switch (message.type) {
            case 'connected':
                console.log('[WebSocket] Connection confirmed, active connections:', message.data.connection_count);
                if (message.data && message.data.stage_state) {
                    window.dispatchEvent(new CustomEvent('stage_state_update', { detail: message.data.stage_state }));
                }
                break;
            case 'presence_snapshot':
                queuePresenceUsers = Array.isArray(message.data?.users) ? message.data.users : [];
                renderPresenceList();
                break;
            case 'user_joined':
                upsertPresenceUser(message.data);
                if (message.data?.guest_id && message.data.guest_id !== this.guestId) {
                    showQueueToast(t('queue.user_joined', { name: message.data.display_name || t('common.guest') }));
                }
                break;
            case 'user_updated':
                upsertPresenceUser(message.data);
                break;
            case 'user_left':
                removePresenceUser(message.data?.guest_id);
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
    stageRemotePlayPauseLabel.textContent = stageRemotePaused ? t('common.play') : t('stage.pause');
}

function updateStageRemoteVocalsUi() {
    if (stageRemoteVocalsToggleBtn) {
        stageRemoteVocalsToggleBtn.disabled = !stageRemoteVocalsAvailable || !(queueWebSocket && queueWebSocket.isConnected);
    }
    if (stageRemoteVocalsVolumeSlider) {
        stageRemoteVocalsVolumeSlider.disabled = !stageRemoteVocalsAvailable || !(queueWebSocket && queueWebSocket.isConnected);
        stageRemoteVocalsVolumeSlider.value = String(Math.round(stageRemoteVocalsVolume * 100));
    }
    if (stageRemoteVocalsToggleIcon) {
        stageRemoteVocalsToggleIcon.textContent = stageRemoteVocalsEnabled ? 'mic' : 'mic_off';
    }
    if (stageRemoteVocalsToggleLabel) {
        stageRemoteVocalsToggleLabel.textContent = stageRemoteVocalsEnabled ? t('stage.vocals_on') : t('stage.vocals_off');
    }
}

function updateStageRemoteLyricsUi() {
    if (stageRemoteLyricsToggleBtn) {
        stageRemoteLyricsToggleBtn.disabled = !stageRemoteLyricsAvailable || !(queueWebSocket && queueWebSocket.isConnected);
    }
    if (stageRemoteLyricsToggleIcon) {
        stageRemoteLyricsToggleIcon.textContent = stageRemoteLyricsEnabled ? 'subtitles' : 'subtitles_off';
    }
    if (stageRemoteLyricsToggleLabel) {
        stageRemoteLyricsToggleLabel.textContent = stageRemoteLyricsAvailable ? (stageRemoteLyricsEnabled ? t('stage.lyrics_on') : t('stage.lyrics_off')) : t('stage.no_lyrics');
    }
}

function syncStageVocalsAvailability(queue) {
    const playingItem = Array.isArray(queue) ? queue.find((item) => item.status === 'playing') : null;
    stageRemoteVocalsAvailable = Boolean(playingItem && playingItem.vocals_path);
    if (!stageRemoteVocalsAvailable) {
        stageRemoteVocalsEnabled = false;
        stageRemoteVocalsVolume = 0;
    } else if (stageRemoteVocalsVolume <= 0) {
        stageRemoteVocalsEnabled = true;
        stageRemoteVocalsVolume = 1.0;
    }
    updateStageRemoteVocalsUi();
}

function syncStageLyricsAvailability(queue) {
    const playingItem = Array.isArray(queue) ? queue.find((item) => item.status === 'playing') : null;
    stageRemoteLyricsAvailable = Boolean(playingItem && playingItem.lyrics_path);
    if (!stageRemoteLyricsAvailable) {
        stageRemoteLyricsEnabled = false;
    }
    updateStageRemoteLyricsUi();
}

// Initialize WebSocket connection
let queueWebSocket = null;
initializeQueueAsSettings();
if (window.location.pathname === appUrl('/queue') || window.location.pathname === appUrl('/')) {
    queueWebSocket = new QueueWebSocket();
    window.queueWebSocket = queueWebSocket;
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
            alert(t('queue.stage_offline'));
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
            alert(t('queue.stage_offline'));
        }
    });
}

if (stageRemoteResyncBtn) {
    stageRemoteResyncBtn.addEventListener('click', () => {
        if (!queueWebSocket) return;
        const sent = queueWebSocket.send({
            type: 'stage_command',
            data: {
                command: 'resync',
                source: 'queue',
            },
            timestamp: Date.now(),
        });
        if (!sent) {
            alert(t('queue.stage_offline'));
        }
    });
}

if (stageRemoteLyricsToggleBtn) {
    stageRemoteLyricsToggleBtn.addEventListener('click', () => {
        if (!queueWebSocket) return;
        if (!stageRemoteLyricsAvailable) {
            alert(t('queue.no_lyrics_track'));
            return;
        }
        const nextEnabled = !stageRemoteLyricsEnabled;
        const sent = queueWebSocket.send({
            type: 'stage_command',
            data: {
                command: 'set_lyrics_enabled',
                source: 'queue',
                lyrics_enabled: nextEnabled,
            },
            timestamp: Date.now(),
        });
        if (!sent) {
            alert(t('queue.stage_offline'));
            return;
        }
        stageRemoteLyricsEnabled = nextEnabled;
        updateStageRemoteLyricsUi();
    });
}

if (stageRemoteVocalsToggleBtn) {
    stageRemoteVocalsToggleBtn.addEventListener('click', () => {
        if (!queueWebSocket) return;
        if (!stageRemoteVocalsAvailable) {
            alert(t('queue.no_vocals_track'));
            return;
        }
        const nextEnabled = !stageRemoteVocalsEnabled;
        const sent = queueWebSocket.send({
            type: 'stage_command',
            data: {
                command: 'set_vocals_enabled',
                source: 'queue',
                vocals_enabled: nextEnabled,
            },
            timestamp: Date.now(),
        });
        if (!sent) {
            alert(t('queue.stage_offline'));
            return;
        }
        stageRemoteVocalsEnabled = nextEnabled;
        updateStageRemoteVocalsUi();
    });
}

if (stageRemoteVocalsVolumeSlider) {
    stageRemoteVocalsVolumeSlider.addEventListener('input', () => {
        if (!queueWebSocket) return;
        if (!stageRemoteVocalsAvailable) {
            return;
        }
        const nextVolume = Number(stageRemoteVocalsVolumeSlider.value) / 100;
        const sent = queueWebSocket.send({
            type: 'stage_command',
            data: {
                command: 'set_vocals_volume',
                source: 'queue',
                vocals_volume: nextVolume,
            },
            timestamp: Date.now(),
        });
        if (!sent) {
            return;
        }
        stageRemoteVocalsVolume = Math.max(0, Math.min(1, nextVolume));
        updateStageRemoteVocalsUi();
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
    refreshQueue(true);
});

window.addEventListener('queue_item_removed', (event) => {
    console.log('[Event] Queue item removed:', event.detail);
    refreshQueue(true);
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
                                    <p class="text-on-surface-variant text-lg font-medium">${t('queue.empty')}</p>
                                    <p class="text-on-surface-variant/60 text-sm">${t('queue.add_started')}</p>
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
                <p class="font-medium">${t('queue.processing_failed')}</p>
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
    const vocalsEnabled = event.detail?.vocals_enabled;
    if (typeof vocalsEnabled === 'boolean') {
        stageRemoteVocalsEnabled = vocalsEnabled;
    }
    const vocalsVolume = event.detail?.vocals_volume;
    if (typeof vocalsVolume === 'number' && Number.isFinite(vocalsVolume)) {
        stageRemoteVocalsVolume = Math.max(0, Math.min(1, vocalsVolume));
    }
    const lyricsEnabled = event.detail?.lyrics_enabled;
    if (typeof lyricsEnabled === 'boolean') {
        stageRemoteLyricsEnabled = lyricsEnabled;
    }
    updateStageRemoteVocalsUi();
    updateStageRemoteLyricsUi();
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
updateStageRemoteVocalsUi();
refreshQueue(true);

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
