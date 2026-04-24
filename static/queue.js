// Queue page JavaScript
const API_BASE = window.location.origin;

// Simple logger for frontend debugging
const logger = {
    log: (...args) => console.log(...args),
    warn: (...args) => console.warn(...args),
    error: (...args) => console.error(...args),
};

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
const queueConfigSongThumb = document.getElementById('queue-config-song-thumb');
const queueConfigSongTitle = document.getElementById('queue-config-song-title');
const queueConfigSongChannel = document.getElementById('queue-config-song-channel');
const queueConfigKaraokeToggle = document.getElementById('queue-config-karaoke-toggle');
const queueConfigKaraokeStatus = document.getElementById('queue-config-karaoke-status');
const queueConfigKaraokeDetail = document.getElementById('queue-config-karaoke-detail');
const queueConfigLyricsToggle = document.getElementById('queue-config-lyrics-toggle');
const queueConfigLyricsPanel = document.getElementById('queue-config-lyrics-panel');
const queueConfigLyricsState = document.getElementById('queue-config-lyrics-state');
const queueConfigLyricsTitle = document.getElementById('queue-config-lyrics-title');
const queueConfigLyricsArtist = document.getElementById('queue-config-lyrics-artist');
const queueConfigLyricsSearchBtn = document.getElementById('queue-config-lyrics-search-btn');
const queueConfigLyricsGoogleLink = document.getElementById('queue-config-lyrics-google-link');
const queueConfigLyricsUploadBtn = document.getElementById('queue-config-lyrics-upload-btn');
const queueConfigLyricsFile = document.getElementById('queue-config-lyrics-file');
const queueConfigLyricsProvider = document.getElementById('queue-config-lyrics-provider');
const queueConfigLyricsTextarea = document.getElementById('queue-config-lyrics-textarea');
const queueConfigLyricsHelp = document.getElementById('queue-config-lyrics-help');
const QUEUE_CONFIRM_DEFAULT_HTML = '<span class="material-symbols-outlined text-base" style="font-variation-settings: \'FILL\' 1">add_circle</span>Add to Queue';
const QUEUE_CONFIRM_LOADING_HTML = '<span class="material-symbols-outlined animate-spin text-base">sync</span>Resolving lyrics...';
let stageRemotePaused = false;
let stageRemoteLyricsEnabled = true;
let stageRemoteLyricsAvailable = false;
let stageRemoteVocalsEnabled = true;
let stageRemoteVocalsVolume = 1.0;
let stageRemoteVocalsAvailable = false;
let demucsHealth = { healthy: true, detail: 'Health unknown' };
let modalSelection = null;
let modalKaraokeEnabled = false;
let modalLyricsEnabled = false;
let modalLyricsState = 'idle';
let modalLyricsProvider = '';
let modalLyricsSynced = false;
let modalLyricsFormat = 'txt';
let modalLyricsRequestId = 0;
let modalLyricsAbortController = null;

searchResults.addEventListener('click', async (event) => {
    const button = event.target.closest('.add-to-queue-btn');
    if (!button || button.disabled) return;

    const resultElement = button.closest('[data-result-source]');
    if (!resultElement) return;

    const source = resultElement.dataset.resultSource || 'youtube';
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
    searchBtn.textContent = 'Searching...';
    searchResults.innerHTML = `
        <div class="glass-card p-6 rounded-lg text-center">
            <div class="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full mx-auto mb-3"></div>
            <p class="text-on-surface-variant">Searching local library...</p>
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
            await refreshDemucsHealth();
            displaySearchResults(localResults);
            
            // Update UI to show YouTube is searching
            const loadingDiv = document.createElement('div');
            loadingDiv.className = 'glass-card p-4 rounded-lg text-center';
            loadingDiv.innerHTML = `
                <div class="flex items-center justify-center gap-2">
                    <div class="animate-spin w-4 h-4 border border-primary border-t-transparent rounded-full"></div>
                    <p class="text-xs text-on-surface-variant">Also searching YouTube...</p>
                </div>
            `;
            searchResults.appendChild(loadingDiv);
        } else {
            // No local results, show YouTube loading message
            searchResults.innerHTML = `
                <div class="glass-card p-6 rounded-lg text-center">
                    <div class="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full mx-auto mb-3"></div>
                    <p class="text-on-surface-variant">Searching YouTube...</p>
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
                    <p class="text-[12px] text-tertiary font-medium">YouTube search unavailable</p>
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
                        <p class="text-on-surface-variant">No results found</p>
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
            throw new Error('Demucs health check failed');
        }
        demucsHealth = await response.json();
    } catch (error) {
        demucsHealth = { healthy: false, detail: String(error.message || 'Demucs unavailable') };
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
        thumbnail: resultElement.dataset.thumbnail || '/static/placeholder.png',
        triggerButton,
    };
}

function syncQueueConfigModalUi() {
    const karaokeAvailable = demucsHealth.healthy;
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
        queueConfigKaraokeDetail.textContent = karaokeAvailable
            ? 'Remove lead vocals using Demucs AI processing.'
            : `Demucs offline: ${demucsHealth.detail}`;
    }

    updateModalToggleAppearance(queueConfigKaraokeToggle, modalKaraokeEnabled, 'bg-tertiary');

    const lyricsEnabled = modalKaraokeEnabled;
    if (!lyricsEnabled) {
        modalLyricsEnabled = false;
    }
    if (queueConfigLyricsToggle) {
        queueConfigLyricsToggle.disabled = !lyricsEnabled;
        queueConfigLyricsToggle.classList.toggle('opacity-50', !lyricsEnabled);
        queueConfigLyricsToggle.classList.toggle('cursor-not-allowed', !lyricsEnabled);
    }
    updateModalToggleAppearance(queueConfigLyricsToggle, modalLyricsEnabled, 'bg-secondary');

    if (queueConfigLyricsPanel) {
        queueConfigLyricsPanel.classList.toggle('hidden', !modalLyricsEnabled);
    }

    if (queueConfigLyricsSearchBtn) {
        queueConfigLyricsSearchBtn.disabled = !modalLyricsEnabled;
        queueConfigLyricsSearchBtn.classList.toggle('opacity-60', !modalLyricsEnabled);
        queueConfigLyricsSearchBtn.classList.toggle('cursor-not-allowed', !modalLyricsEnabled);
        queueConfigLyricsSearchBtn.title = modalLyricsEnabled
            ? (modalLyricsState === 'loading'
                ? 'Cancel the current lookup and search again with the current title and artist'
                : 'Search with the current title and artist')
            : 'Enable lyrics first';
    }

    if (queueConfigLyricsUploadBtn) {
        queueConfigLyricsUploadBtn.disabled = !modalLyricsEnabled;
        queueConfigLyricsUploadBtn.classList.toggle('opacity-60', !modalLyricsEnabled);
        queueConfigLyricsUploadBtn.classList.toggle('cursor-not-allowed', !modalLyricsEnabled);
    }

    syncLyricsGoogleSearchLink();

    if (queueConfigLyricsTitle) {
        queueConfigLyricsTitle.disabled = !modalLyricsEnabled;
    }
    if (queueConfigLyricsArtist) {
        queueConfigLyricsArtist.disabled = !modalLyricsEnabled;
    }
    if (queueConfigLyricsTextarea) {
        queueConfigLyricsTextarea.disabled = !modalLyricsEnabled;
    }

    syncLyricsStatusUi();
    syncQueueConfirmState();
}

function getLyricsSubmissionText() {
    const manualValue = queueConfigLyricsTextarea ? queueConfigLyricsTextarea.value.trim() : '';
    return manualValue;
}

function inferLyricsFormat(text) {
    if (!text) return 'txt';
    return /^\[\d{1,2}:\d{2}(?:\.\d{1,3})?\]/m.test(text) ? 'lrc' : 'txt';
}

function buildLyricsGoogleSearchUrl() {
    const title = queueConfigLyricsTitle ? queueConfigLyricsTitle.value.trim() : '';
    const artist = queueConfigLyricsArtist ? queueConfigLyricsArtist.value.trim() : '';
    const query = [title, artist, 'lyrics'].filter(Boolean).join(' ') || 'lyrics';
    return `https://www.google.com/search?q=${encodeURIComponent(query)}`;
}

function syncLyricsGoogleSearchLink() {
    if (!queueConfigLyricsGoogleLink) return;
    queueConfigLyricsGoogleLink.href = buildLyricsGoogleSearchUrl();
}

function syncQueueSongTitleLink() {
    if (!queueConfigSongTitle || !modalSelection) return;

    const previewUrl = getYouTubeWatchUrl(modalSelection.videoId);
    queueConfigSongTitle.textContent = modalSelection.title || 'Selected song';
    queueConfigSongTitle.title = previewUrl ? 'Open in YouTube' : '';

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

function cancelInFlightLyricsResolve() {
    if (modalLyricsAbortController) {
        modalLyricsAbortController.abort();
        modalLyricsAbortController = null;
    }
    if (modalLyricsState === 'loading') {
        modalLyricsRequestId += 1;
    }
}

function syncLyricsStatusUi(detail = '') {
    if (!queueConfigLyricsState) return;

    const states = {
        idle: { label: 'Idle', className: 'bg-on-surface/5 text-on-surface-variant' },
        loading: { label: 'Searching', className: 'bg-primary/10 text-primary' },
        resolved: { label: 'Resolved', className: 'bg-secondary/10 text-secondary' },
        not_found: { label: 'Not found', className: 'bg-error/10 text-error' },
        error: { label: 'Error', className: 'bg-error/10 text-error' },
        manual: { label: 'Manual', className: 'bg-secondary/10 text-secondary' },
    };
    const state = states[modalLyricsState] || states.idle;
    queueConfigLyricsState.textContent = state.label;
    queueConfigLyricsState.className = `rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${state.className}`;

    if (queueConfigLyricsProvider) {
        if (modalLyricsProvider) {
            queueConfigLyricsProvider.textContent = `${modalLyricsProvider}${modalLyricsSynced ? ' • synced' : ' • plain'}`;
        } else {
            queueConfigLyricsProvider.textContent = '';
        }
    }

    if (queueConfigLyricsHelp && detail) {
        queueConfigLyricsHelp.textContent = detail;
    } else if (queueConfigLyricsHelp && modalLyricsState === 'not_found') {
        queueConfigLyricsHelp.textContent = 'No lyrics were found. Use the editor below or upload an LRC file.';
    } else if (queueConfigLyricsHelp && modalLyricsState === 'error') {
        queueConfigLyricsHelp.textContent = 'Lyrics search failed. Use the editor below or upload an LRC file.';
    } else if (queueConfigLyricsHelp && modalLyricsState === 'resolved') {
        queueConfigLyricsHelp.textContent = modalLyricsSynced
            ? 'Resolved synced lyrics are ready. Edit the box below before adding to the queue.'
            : 'Resolved plain lyrics are ready. Edit the box below before adding to the queue.';
    } else if (queueConfigLyricsHelp && modalLyricsState === 'manual') {
        queueConfigLyricsHelp.textContent = 'Your editor content is ready to be queued.';
    }
}

function syncQueueConfirmState() {
    if (!queueConfigConfirmBtn) return;

    const lyricsRequired = modalLyricsEnabled;
    const ready = !lyricsRequired || modalLyricsState === 'resolved' || modalLyricsState === 'not_found' || modalLyricsState === 'error' || Boolean(getLyricsSubmissionText());
    const waiting = lyricsRequired && modalLyricsState === 'loading';
    const disabled = waiting || (lyricsRequired && !ready);

    queueConfigConfirmBtn.disabled = disabled;
    queueConfigConfirmBtn.setAttribute('aria-disabled', disabled ? 'true' : 'false');
    queueConfigConfirmBtn.setAttribute('aria-busy', waiting ? 'true' : 'false');
    queueConfigConfirmBtn.title = waiting
        ? 'Lyrics are still resolving'
        : lyricsRequired && !ready
            ? 'Resolve lyrics or add your own synced lyrics before continuing'
            : 'Add the song to the queue';

    queueConfigConfirmBtn.classList.toggle('bg-primary', !disabled);
    queueConfigConfirmBtn.classList.toggle('text-on-primary', !disabled);
    queueConfigConfirmBtn.classList.toggle('bg-surface-container-highest', disabled);
    queueConfigConfirmBtn.classList.toggle('text-on-surface-variant', disabled);

    if (waiting) {
        queueConfigConfirmBtn.innerHTML = QUEUE_CONFIRM_LOADING_HTML;
    } else {
        queueConfigConfirmBtn.innerHTML = QUEUE_CONFIRM_DEFAULT_HTML;
    }
}

async function openQueueConfigModal(resultElement, triggerButton) {
    if (!queueConfigModal || !queueConfigConfirmBtn) {
        await submitQueueItem(buildQueueSelection(resultElement, triggerButton), triggerButton, {
            isKaraoke: false,
            lyricsEnabled: false,
        });
        return;
    }

    modalSelection = buildQueueSelection(resultElement, triggerButton);

    modalKaraokeEnabled = false;
    modalLyricsEnabled = false;
    modalLyricsState = 'idle';
    modalLyricsProvider = '';
    modalLyricsSynced = false;
    modalLyricsFormat = 'txt';
    modalLyricsRequestId = 0;
    modalLyricsAbortController = null;

    syncQueueSongTitleLink();
    if (queueConfigSongChannel) queueConfigSongChannel.textContent = modalSelection.channel || '';
    if (queueConfigSongThumb) {
        queueConfigSongThumb.src = modalSelection.thumbnail;
        queueConfigSongThumb.onerror = () => {
            queueConfigSongThumb.src = '/static/placeholder.png';
        };
    }

    queueConfigConfirmBtn.disabled = false;
    queueConfigConfirmBtn.setAttribute('aria-disabled', 'false');
    queueConfigConfirmBtn.setAttribute('aria-busy', 'false');
    queueConfigConfirmBtn.title = 'Add the song to the queue';
    queueConfigConfirmBtn.classList.remove('bg-secondary', 'text-white', 'bg-error', 'bg-surface-container-highest', 'text-on-surface-variant');
    queueConfigConfirmBtn.classList.add('bg-primary', 'text-on-primary');
    queueConfigConfirmBtn.innerHTML = QUEUE_CONFIRM_DEFAULT_HTML;
    queueConfigModal.classList.remove('hidden');
    queueConfigModal.classList.add('flex');
    document.body.classList.add('overflow-hidden');

    if (queueConfigLyricsTitle) queueConfigLyricsTitle.value = modalSelection.title || '';
    if (queueConfigLyricsArtist) queueConfigLyricsArtist.value = modalSelection.channel || '';
    if (queueConfigLyricsTextarea) queueConfigLyricsTextarea.value = '';
    syncLyricsGoogleSearchLink();
    syncQueueConfigModalUi();
    refreshDemucsHealth().then(() => {
        if (modalSelection) {
            syncQueueConfigModalUi();
        }
    });
}

function closeQueueConfigModal() {
    if (!queueConfigModal) return;
    cancelInFlightLyricsResolve();
    queueConfigModal.classList.add('hidden');
    queueConfigModal.classList.remove('flex');
    document.body.classList.remove('overflow-hidden');
    modalSelection = null;
    modalKaraokeEnabled = false;
    modalLyricsEnabled = false;
    modalLyricsState = 'idle';
    modalLyricsProvider = '';
    modalLyricsSynced = false;
    modalLyricsFormat = 'txt';
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

    searchResults.innerHTML = results.map(result => {
        const isDownloaded = result.source === 'local' || result.downloaded;
        
        // Compact layout for downloaded items
        if (isDownloaded) {
            return `
                <div
                    class="bg-surface-container-lowest hover:bg-surface-container-low p-3 rounded-lg transition-all border border-outline-variant/10"
                    data-result-source="${escapeHtml(result.source || 'youtube')}"
                    data-video-id="${escapeHtml(result.video_id || '')}"
                    data-media-item-id="${result.media_item_id ?? ''}"
                    data-title="${escapeHtml(result.title)}"
                    data-channel="${escapeHtml(result.channel || '')}"
                    data-thumbnail="${escapeHtml(result.thumbnail || '/static/placeholder.png')}"
                >
                    <div class="flex items-center gap-3">
                        <div class="relative w-12 h-12 rounded-md overflow-hidden shrink-0">
                            <img 
                                src="${result.thumbnail || '/static/placeholder.png'}" 
                                alt="${escapeHtml(result.title)}"
                                class="w-full h-full object-cover"
                                onerror="this.parentElement.innerHTML='<div class=\\'w-full h-full bg-surface-container-highest flex items-center justify-center\\'><span class=\\'material-symbols-outlined text-on-surface-variant\\'>music_note</span></div>'"
                            >
                        </div>
                        <div class="flex-1 min-w-0">
                            ${renderSearchResultTitle(result, 'text-xs')}
                            <p class="text-[11px] text-on-surface-variant truncate">${escapeHtml(result.channel)}</p>
                            <div class="mt-1 flex items-center gap-1.5">
                                ${result.source === 'local' ? `
                                    <div class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-primary/10 border border-primary/20">
                                        <span class="material-symbols-outlined text-[9px] text-primary">library_music</span>
                                        <span class="text-[7px] font-bold uppercase tracking-tighter text-primary">Local</span>
                                    </div>
                                ` : ''}
                                <div class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-secondary/10 border border-secondary/20">
                                    <span class="material-symbols-outlined text-[9px] text-secondary">download_done</span>
                                    <span class="text-[7px] font-bold uppercase tracking-tighter text-secondary">Ready</span>
                                </div>
                            </div>
                        </div>
                        <button class="add-to-queue-btn bg-primary text-on-primary px-3 py-1.5 rounded-full text-xs font-bold hover:brightness-110 active:scale-95 transition-all shrink-0" 
                                type="button">
                            Add
                        </button>
                    </div>
                </div>
            `;
        }
        
        // Full layout for YouTube results
        return `
            <div
                class="bg-surface-container-low hover:bg-surface-container p-4 rounded-lg transition-all"
                data-result-source="${escapeHtml(result.source || 'youtube')}"
                data-video-id="${escapeHtml(result.video_id || '')}"
                data-media-item-id="${result.media_item_id ?? ''}"
                data-title="${escapeHtml(result.title)}"
                data-channel="${escapeHtml(result.channel || '')}"
                data-thumbnail="${escapeHtml(result.thumbnail || '/static/placeholder.png')}"
            >
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
                        ${renderSearchResultTitle(result, 'text-sm')}
                        <p class="text-xs text-on-surface-variant truncate">${escapeHtml(result.channel)}</p>
                        ${result.duration ? `<p class="text-xs text-on-surface-variant/60">${result.duration}</p>` : ''}
                        ${result.source === 'local' ? `
                            <div class="mt-2 inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-primary/10 border border-primary/20">
                                <span class="material-symbols-outlined text-[10px] text-primary">library_music</span>
                                <span class="text-[8px] font-bold uppercase tracking-tighter text-primary">Local</span>
                            </div>
                        ` : ''}
                    </div>
                    <button class="add-to-queue-btn bg-primary text-on-primary px-4 py-2 rounded-full text-sm font-bold hover:brightness-110 active:scale-95 transition-all shrink-0" 
                            type="button">
                        Add
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

async function addToQueueFromModal(selection, buttonElement) {
    return submitQueueItem(selection, buttonElement, {
        isKaraoke: modalKaraokeEnabled,
        lyricsEnabled: modalLyricsEnabled,
    });
}

async function addToQueueDirect(resultElement, buttonElement) {
    return submitQueueItem(buildQueueSelection(resultElement, buttonElement), buttonElement, {
        isKaraoke: false,
        lyricsEnabled: false,
    });
}

async function resolveLyricsFromModal(trigger = 'manual') {
    if (!modalSelection || !modalLyricsEnabled) return;
    const title = queueConfigLyricsTitle ? queueConfigLyricsTitle.value.trim() : '';
    const artist = queueConfigLyricsArtist ? queueConfigLyricsArtist.value.trim() : '';
    if (!title) {
        modalLyricsState = 'error';
        syncLyricsStatusUi('Title is required before searching for lyrics.');
        syncQueueConfirmState();
        return;
    }

    cancelInFlightLyricsResolve();
    const requestId = ++modalLyricsRequestId;
    const abortController = new AbortController();
    modalLyricsAbortController = abortController;
    modalLyricsState = 'loading';
    modalLyricsProvider = '';
    modalLyricsSynced = false;
    syncLyricsStatusUi('Searching lyrics providers...');
    syncQueueConfirmState();

    const payload = {
        title,
    };
    if (artist) {
        payload.artist = artist;
    }
    if (trigger === 'auto' && modalSelection.title) {
        payload.youtube_title = modalSelection.title;
    }

    try {
        const response = await fetch(`${API_BASE}/api/lyrics/resolve`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload),
            signal: abortController.signal,
        });

        if (!response.ok) {
            throw new Error((await response.json()).detail || 'Lyrics search failed');
        }

        const result = await response.json();
        if (requestId !== modalLyricsRequestId) return;

        modalLyricsState = result.status;
        modalLyricsProvider = result.provider || '';
        modalLyricsSynced = Boolean(result.is_synced);
        modalLyricsFormat = modalLyricsSynced ? 'lrc' : 'txt';

        if (queueConfigLyricsTitle && result.title) {
            queueConfigLyricsTitle.value = result.title;
        }
        if (queueConfigLyricsArtist && result.artist) {
            queueConfigLyricsArtist.value = result.artist;
        }
        syncLyricsGoogleSearchLink();
        if (result.status === 'resolved' && queueConfigLyricsTextarea) {
            queueConfigLyricsTextarea.value = result.lyrics || '';
        }

        if (result.status === 'resolved') {
            syncLyricsStatusUi(result.is_synced ? 'Synced lyrics resolved.' : 'Plain lyrics resolved.');
        } else {
            syncLyricsStatusUi(result.detail || 'Lyrics not found.');
        }
        syncQueueConfirmState();
    } catch (error) {
        if (requestId !== modalLyricsRequestId) return;
        if (error?.name === 'AbortError') return;
        modalLyricsState = 'error';
        modalLyricsProvider = '';
        modalLyricsSynced = false;
        syncLyricsStatusUi(error.message || 'Lyrics search failed.');
        syncQueueConfirmState();
    } finally {
        if (requestId === modalLyricsRequestId) {
            modalLyricsAbortController = null;
        }
    }
}

function handleLyricsTextChange() {
    if (!modalLyricsEnabled) return;
    cancelInFlightLyricsResolve();
    const hasText = Boolean(getLyricsSubmissionText());
    if (hasText) {
        modalLyricsState = 'manual';
        syncLyricsStatusUi('Manual lyrics ready.');
    } else if (modalLyricsState === 'manual') {
        modalLyricsState = 'idle';
        syncLyricsStatusUi('Search or upload lyrics to continue.');
    }
    syncQueueConfirmState();
}

function triggerLyricsUpload() {
    if (queueConfigLyricsFile && !queueConfigLyricsFile.disabled) {
        queueConfigLyricsFile.click();
    }
}

async function loadLyricsUpload(file) {
    if (!file) return;
    cancelInFlightLyricsResolve();
    const text = await file.text();
    if (queueConfigLyricsTextarea) {
        queueConfigLyricsTextarea.value = text.trim();
    }
    modalLyricsFormat = file.name.toLowerCase().endsWith('.lrc') ? 'lrc' : 'txt';
    modalLyricsState = 'manual';
    modalLyricsProvider = `upload:${file.name}`;
    modalLyricsSynced = modalLyricsFormat === 'lrc';
    syncLyricsStatusUi('Uploaded lyrics ready.');
    syncQueueConfirmState();
}

async function submitQueueItem(selection, buttonElement, options = {}) {
    const source = selection?.source || 'youtube';
    const videoId = selection?.videoId || null;
    const mediaItemId = selection?.mediaItemId || null;
    const title = selection?.title || '';
    const channel = selection?.channel || '';
    const isKaraoke = Boolean(options.isKaraoke);
    const lyricsEnabled = Boolean(options.lyricsEnabled && isKaraoke);
    const lyricsText = getLyricsSubmissionText();
    const lyricsFormat = lyricsText ? inferLyricsFormat(lyricsText) : null;
    const button = buttonElement || queueConfigConfirmBtn;
    if (!button) {
        throw new Error('Missing add-to-queue trigger button');
    }

    if (isKaraoke && !demucsHealth.healthy) {
        alert(`Karaoke mode is unavailable: ${demucsHealth.detail}`);
        return;
    }

    button.disabled = true;
    button.innerHTML = '<span class="material-symbols-outlined text-sm animate-spin">sync</span>';

    try {
        const payload = {
            title: title,
            artist: channel,
            is_karaoke: isKaraoke,
        };
        if (isKaraoke && lyricsEnabled && lyricsText) {
            payload.lyrics_text = lyricsText;
            payload.lyrics_format = lyricsFormat || modalLyricsFormat || inferLyricsFormat(lyricsText);
        }
        if (source === 'local' && mediaItemId) {
            payload.media_item_id = Number(mediaItemId);
        } else if (videoId) {
            payload.youtube_id = videoId;
        } else {
            throw new Error('Missing media source identifier');
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
            closeQueueConfigModal();
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
            button.innerHTML = '<span class="material-symbols-outlined text-base" style="font-variation-settings: \'FILL\' 1">add_circle</span>Add to Queue';
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
        syncQueueConfigModalUi();
    });
}

if (queueConfigLyricsToggle) {
    queueConfigLyricsToggle.addEventListener('click', () => {
        if (queueConfigLyricsToggle.disabled) return;
        modalLyricsEnabled = !modalLyricsEnabled;
        if (!modalLyricsEnabled) {
            cancelInFlightLyricsResolve();
            modalLyricsState = 'idle';
            modalLyricsProvider = '';
            modalLyricsSynced = false;
        } else if (modalSelection) {
            resolveLyricsFromModal('auto');
        }
        syncQueueConfigModalUi();
    });
}

if (queueConfigLyricsSearchBtn) {
    queueConfigLyricsSearchBtn.addEventListener('click', async () => {
        await resolveLyricsFromModal('manual');
    });
}

if (queueConfigLyricsUploadBtn) {
    queueConfigLyricsUploadBtn.addEventListener('click', triggerLyricsUpload);
}

if (queueConfigLyricsFile) {
    queueConfigLyricsFile.addEventListener('change', async () => {
        const file = queueConfigLyricsFile.files && queueConfigLyricsFile.files[0];
        if (file) {
            await loadLyricsUpload(file);
        }
        queueConfigLyricsFile.value = '';
    });
}

if (queueConfigLyricsTextarea) {
    queueConfigLyricsTextarea.addEventListener('input', handleLyricsTextChange);
}

if (queueConfigLyricsTitle) {
    queueConfigLyricsTitle.addEventListener('input', () => {
        syncLyricsGoogleSearchLink();
        syncQueueConfirmState();
    });
}

if (queueConfigLyricsArtist) {
    queueConfigLyricsArtist.addEventListener('input', () => {
        syncLyricsGoogleSearchLink();
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
        if (stageRemoteResyncBtn) stageRemoteResyncBtn.disabled = !connected;
        updateStageRemoteLyricsUi();
        updateStageRemoteVocalsUi();
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
                if (message.data && message.data.stage_state) {
                    window.dispatchEvent(new CustomEvent('stage_state_update', { detail: message.data.stage_state }));
                }
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
        stageRemoteVocalsToggleLabel.textContent = stageRemoteVocalsEnabled ? 'Vocals On' : 'Vocals Off';
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
        stageRemoteLyricsToggleLabel.textContent = stageRemoteLyricsAvailable ? (stageRemoteLyricsEnabled ? 'Lyrics On' : 'Lyrics Off') : 'No Lyrics';
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
            alert('Stage control is offline');
        }
    });
}

if (stageRemoteLyricsToggleBtn) {
    stageRemoteLyricsToggleBtn.addEventListener('click', () => {
        if (!queueWebSocket) return;
        if (!stageRemoteLyricsAvailable) {
            alert('Current song has no lyrics track');
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
            alert('Stage control is offline');
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
            alert('Current song has no vocals sidecar track');
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
            alert('Stage control is offline');
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
