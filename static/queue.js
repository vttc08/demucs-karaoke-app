// Queue page JavaScript
const API_BASE = window.KaraokeURLs?.basePath || "";
const appUrl = window.KaraokeURLs?.appUrl || ((path) => path);
const appWsUrl = window.KaraokeURLs?.appWsUrl || ((path) => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}${path}`;
});
const t = window.KaraokeI18n?.t?.bind(window.KaraokeI18n) || ((key, params = {}) => key);
const WS_DEBUG = window.KARAOKE_WS_DEBUG === true;

// Simple logger for frontend debugging
const logger = {
    log: (...args) => {
        if (WS_DEBUG) {
            console.log(...args);
        }
    },
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
const stageRemoteSeekForwardBtn = document.getElementById('stage-remote-seek-forward-btn');
const stageRemoteLyricsSettingsBtn = document.getElementById('stage-remote-lyrics-settings-btn');
const stageRemoteLyricsToggleIcon = document.getElementById('stage-remote-lyrics-toggle-icon');
const stageRemoteLyricsToggleLabel = document.getElementById('stage-remote-lyrics-toggle-label');
const stageRemoteLyricsSettingsPanel = document.getElementById('stage-remote-lyrics-settings-panel');
const stageRemoteLyricsSettingsStatus = document.getElementById('stage-remote-lyrics-settings-status');
const stageRemoteStageRefreshBtn = document.getElementById('stage-remote-stage-refresh-btn');
const stageRemoteStageSelect = document.getElementById('stage-remote-stage-select');
const stageRemoteLyricsPresetSelect = document.getElementById('stage-remote-lyrics-preset-select');
const stageRemoteLyricsSizeSlider = document.getElementById('stage-remote-lyrics-size-slider');
const stageRemoteLyricsSizeValue = document.getElementById('stage-remote-lyrics-size-value');
const stageRemoteLyricsWidthSlider = document.getElementById('stage-remote-lyrics-width-slider');
const stageRemoteLyricsWidthValue = document.getElementById('stage-remote-lyrics-width-value');
const stageRemoteLyricsEnabledToggle = document.getElementById('stage-remote-lyrics-enabled-toggle');
const stageRemoteLyricsBackgroundEnabledToggle = document.getElementById('stage-remote-lyrics-background-enabled-toggle');
const stageRemoteLyricsApplyBtn = document.getElementById('stage-remote-lyrics-apply-btn');
const stageRemoteLyricsOverrideBtn = document.getElementById('stage-remote-lyrics-override-btn');
const stageRemoteVocalsControl = document.getElementById('stage-remote-vocals-control');
const stageRemoteVocalsToggleBtn = document.getElementById('stage-remote-vocals-toggle-btn');
const stageRemoteVocalsToggleIcon = document.getElementById('stage-remote-vocals-toggle-icon');
const stageRemoteVocalsVolumeSlider = document.getElementById('stage-remote-vocals-volume-slider');
const stageRemoteVocalsVolumeLabel = document.getElementById('stage-remote-vocals-volume-label');
const queueConfigModal = document.getElementById('queue-config-modal');
const queueConfigModalBackdrop = document.getElementById('queue-config-modal-backdrop');
const queueConfigCloseBtn = document.getElementById('queue-config-close-btn');
const queueConfigCancelBtn = document.getElementById('queue-config-cancel-btn');
const queueConfigConfirmBtn = document.getElementById('queue-config-confirm-btn');
const queueConfigQueueAsPanel = document.getElementById('queue-config-queue-as-panel');
const queueConfigQueueAsCheckbox = document.getElementById('queue-config-queue-as-checkbox');
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
const queueConfigAlignToggle = document.getElementById('queue-config-align-toggle');
const queueConfigAlignDetail = document.getElementById('queue-config-align-detail');
const queueConfigLineProcessingToggle = document.getElementById('queue-config-line-processing-toggle');
const queueConfigLineProcessingDetail = document.getElementById('queue-config-line-processing-detail');
const queueConfigMaxLineLengthInput = document.getElementById('queue-config-max-line-length');
const queueConfigMaxLineLengthCjkInput = document.getElementById('queue-config-max-line-length-cjk');
const queueConfigLyricsLanguageInput = document.getElementById('queue-config-lyrics-language-code');
const queueToast = document.getElementById('queue-toast');
const queueToastText = document.getElementById('queue-toast-text');
const QUEUE_AS_ENABLED_STORAGE_KEY = 'karaoke.queueAs.enabled';
const QUEUE_AS_LAST_NAME_STORAGE_KEY = 'karaoke.queueAs.lastName';
const QUEUE_AS_LAST_GUEST_ID_STORAGE_KEY = 'karaoke.queueAs.lastGuestId';
const QUEUE_LYRICS_PRESETS_API = appUrl('/api/lyrics-presets/');
const QUEUE_CONFIRM_DEFAULT_HTML = `<span class="material-symbols-outlined text-base" style="font-variation-settings: 'FILL' 1">add_circle</span>${t('common.add_to_queue')}`;
const QUEUE_CONFIRM_LOADING_HTML = `<span class="material-symbols-outlined animate-spin text-base">sync</span>${t('lyrics.searching_providers')}`;
const KARAOKE_TITLE_HINT_RE = /\b(karaoke|ktv|sing[-\s]?along|off[-\s]?vocal|no[-\s]?vocal|instrumental|noraebang)\b/i;
const LYRICS_TITLE_HINT_RE = /\b(lyrics?|lyric\s+video|with\s+lyrics)\b/i;
let stageRemotePaused = false;
let stageRemoteLyricsEnabled = true;
let stageRemoteLyricsBackgroundEnabled = true;
let stageRemoteLyricsAvailable = false;
let stageRemoteCanControl = isAdminUser;
let stageRemoteVocalsEnabled = true;
let stageRemoteVocalsVolume = Number(window.KARAOKE_STAGE_VOCALS_VOLUME_DEFAULT);
stageRemoteVocalsVolume = Number.isFinite(stageRemoteVocalsVolume)
    ? Math.max(0, Math.min(1, stageRemoteVocalsVolume))
    : 1.0;
let stageRemoteVocalsLastVolume = stageRemoteVocalsVolume > 0 ? stageRemoteVocalsVolume : 1.0;
let stageRemoteVocalsAvailable = false;
let stageRemoteCurrentTime = null;
let stageRemoteStageDisplays = [];
let stageRemoteLyricsPresets = [];
let stageRemoteLyricsSettingsOpen = false;
let stageRemoteLyricsApplyPending = false;
let stageRemoteLyricsAckTimer = null;
let stageRemoteLyricsPendingStageId = null;
let demucsHealth = { healthy: true, detail: t('settings.engine_unknown') };
let modalSelection = null;
let modalKaraokeEnabled = false;
let modalAlignLyricsEnabled = false;
let modalAlignLyricsAutoEnabled = false;
let modalProcessLyricsLinesEnabled = false;
let modalConfigInitializing = false;
let queueToastTimer = null;
let queuePresenceUsers = [];
let queueAsEnabled = false;
let queueAsModalResolver = null;
let queueConfigSelectedQueueAsGuestId = null;
let currentQueueState = [];
let refreshInterval = null;
let queueRecoveryTimeout = null;
let queueRefreshPromise = null;
let queueRefreshPending = false;

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

function getQueueAsLastGuestId() {
    return sanitizePresenceValue(getLocalStorageValue(QUEUE_AS_LAST_GUEST_ID_STORAGE_KEY, '') || '');
}

function setQueueAsSelection(name, guestId = null) {
    const normalized = sanitizeQueueAsName(name);
    if (normalized) {
        setLocalStorageValue(QUEUE_AS_LAST_NAME_STORAGE_KEY, normalized);
    }
    const normalizedGuestId = sanitizePresenceValue(guestId);
    if (normalizedGuestId) {
        setLocalStorageValue(QUEUE_AS_LAST_GUEST_ID_STORAGE_KEY, normalizedGuestId);
    } else {
        try {
            localStorage.removeItem(QUEUE_AS_LAST_GUEST_ID_STORAGE_KEY);
        } catch (_) {
            // Storage is optional for queue interactions.
        }
    }
    return {
        name: normalized,
        guestId: normalizedGuestId || null,
    };
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
        const guestId = sanitizePresenceValue(user?.guest_id);
        if (!guestId) {
            return;
        }
        const key = guestId.toLowerCase();
        if (!unique.has(key)) {
            unique.set(key, {
                name: normalized,
                guestId,
            });
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
    targetElement.innerHTML = suggestions.map(({ name, guestId }) => `
        <button
            type="button"
            class="queue-as-suggestion-btn inline-flex items-center rounded-full bg-surface-container-highest px-3 py-1.5 text-xs font-semibold text-on-surface transition-colors hover:text-primary"
            data-queue-as-name="${escapeHtml(name)}"
            data-queue-as-guest-id="${escapeHtml(guestId)}"
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

function openQueueAsModal(defaultSelection = {}) {
    if (!queueAsModal) {
        const fallbackName = sanitizeQueueAsName(defaultSelection?.name || '');
        return Promise.resolve(fallbackName ? { name: fallbackName, guestId: null } : null);
    }
    renderQueueAsSuggestions();
    if (queueAsInput) {
        queueAsInput.value = sanitizeQueueAsName(defaultSelection?.name || '');
        queueAsInput.dataset.selectedGuestId = sanitizePresenceValue(defaultSelection?.guestId || '');
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
        queueAsInput.dataset.selectedGuestId = sanitizePresenceValue(button.dataset.queueAsGuestId);
        queueAsInput.focus();
    });

    queueAsInput?.addEventListener('input', () => {
        const selectedGuestId = sanitizePresenceValue(queueAsInput.dataset.selectedGuestId || '');
        const selectedName = sanitizeQueueAsName(queueAsInput.value);
        const matchingUser = queuePresenceUsers.find((user) => (
            sanitizeQueueAsName(user?.display_name) === selectedName
            && sanitizePresenceValue(user?.guest_id) === selectedGuestId
        ));
        if (!matchingUser) {
            queueAsInput.dataset.selectedGuestId = '';
        }
    });

    queueAsConfirmBtn?.addEventListener('click', () => {
        const selectedName = sanitizeQueueAsName(queueAsInput?.value || '');
        if (!selectedName) {
            if (queueAsInput) {
                queueAsInput.focus();
            }
            return;
        }
        const selection = setQueueAsSelection(
            selectedName,
            sanitizePresenceValue(queueAsInput?.dataset.selectedGuestId || '') || null,
        );
        updateQueueAsCurrentLabel(selection.name);
        resolveQueueAsModal(selection.name ? selection : null);
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
    const queueAsSelection = await openQueueAsModal({
        name: getQueueAsLastName() || getCurrentSingerName(),
        guestId: getQueueAsLastGuestId() || null,
    });
    if (!queueAsSelection) {
        return;
    }
    return submitQueueItem(selection, buttonElement, {
        ...options,
        queueAsName: queueAsSelection.name,
        queueAsGuestId: queueAsSelection.guestId,
    });
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

function normalizeWhisperxLanguageCode(value) {
    const normalized = String(value || '').trim().toLowerCase();
    return normalized === 'auto' || normalized === 'default' ? '' : normalized;
}

function inferQueueConfigLyricsFormat() {
    const lyricsText = lyricsManager?.getSubmissionText() || '';
    return lyricsText ? LyricsManager.inferFormat(lyricsText) : null;
}

function parseQueueConfigLineLength(input, fallback, maxValue) {
    const rawValue = String(input?.value ?? '').trim();
    const parsed = Number.parseInt(rawValue, 10);
    if (!Number.isFinite(parsed)) {
        return fallback;
    }
    return Math.max(1, Math.min(maxValue, parsed));
}

function queueConfigLyricsCanAlign() {
    const lyricsEnabled = Boolean(modalKaraokeEnabled && lyricsManager?.state.lyricsEnabled);
    if (!lyricsEnabled || !demucsHealth.healthy) {
        return false;
    }
    const format = inferQueueConfigLyricsFormat();
    return format !== 'json' && format !== 'ttml';
}

function syncQueueConfigAlignControls() {
    const lyricsEnabled = Boolean(modalKaraokeEnabled && lyricsManager?.state.lyricsEnabled);
    const lyricsText = lyricsManager?.getSubmissionText() || '';
    const lyricsFormat = inferQueueConfigLyricsFormat();
    const lyricsState = lyricsManager?.state.lyricsState || 'idle';
    const canAlign = queueConfigLyricsCanAlign();

    if (!lyricsEnabled || !demucsHealth.healthy || lyricsFormat === 'json' || lyricsFormat === 'ttml') {
        if (!modalConfigInitializing) {
            modalAlignLyricsEnabled = false;
            modalAlignLyricsAutoEnabled = false;
            modalProcessLyricsLinesEnabled = false;
        }
    } else if (modalAlignLyricsAutoEnabled && lyricsEnabled) {
        modalAlignLyricsEnabled = true;
    }

    if (queueConfigAlignToggle) {
        queueConfigAlignToggle.disabled = !canAlign;
        queueConfigAlignToggle.classList.toggle('opacity-50', !canAlign);
        queueConfigAlignToggle.classList.toggle('cursor-not-allowed', !canAlign);
        updateModalToggleAppearance(queueConfigAlignToggle, modalAlignLyricsEnabled, 'bg-primary');
    }

    if (queueConfigAlignDetail) {
        if (!lyricsEnabled) {
            queueConfigAlignDetail.textContent = t('lyrics.enable_first');
        } else if (!demucsHealth.healthy) {
            queueConfigAlignDetail.textContent = t('lyrics.align_demucs_unavailable');
        } else if (lyricsFormat === 'json') {
            queueConfigAlignDetail.textContent = t('lyrics.align_json_unsupported');
        } else if (lyricsFormat === 'ttml') {
            queueConfigAlignDetail.textContent = t('lyrics.align_xml_skipped');
        } else if (!lyricsText) {
            queueConfigAlignDetail.textContent = t('lyrics.align_requires_text');
        } else {
            queueConfigAlignDetail.textContent = t('queue.whisperx_align_detail');
        }
    }

    if (queueConfigLyricsLanguageInput) {
        queueConfigLyricsLanguageInput.disabled = !canAlign || !modalAlignLyricsEnabled;
        queueConfigLyricsLanguageInput.classList.toggle('opacity-60', queueConfigLyricsLanguageInput.disabled);
    }

    const canProcessLines = Boolean(canAlign && modalAlignLyricsEnabled);
    if (!canProcessLines && !modalConfigInitializing) {
        modalProcessLyricsLinesEnabled = false;
    }

    if (queueConfigLineProcessingToggle) {
        queueConfigLineProcessingToggle.disabled = !canProcessLines;
        queueConfigLineProcessingToggle.classList.toggle('opacity-50', !canProcessLines);
        queueConfigLineProcessingToggle.classList.toggle('cursor-not-allowed', !canProcessLines);
        updateModalToggleAppearance(queueConfigLineProcessingToggle, modalProcessLyricsLinesEnabled, 'bg-secondary');
    }

    if (queueConfigLineProcessingDetail) {
        if (!lyricsEnabled) {
            queueConfigLineProcessingDetail.textContent = t('lyrics.enable_first');
        } else if (!demucsHealth.healthy) {
            queueConfigLineProcessingDetail.textContent = t('lyrics.align_demucs_unavailable');
        } else if (lyricsFormat === 'json') {
            queueConfigLineProcessingDetail.textContent = t('queue.process_lyrics_lines_json_unsupported');
        } else if (lyricsFormat === 'ttml') {
            queueConfigLineProcessingDetail.textContent = t('lyrics.align_xml_skipped');
        } else if (!lyricsText) {
            queueConfigLineProcessingDetail.textContent = t('lyrics.align_requires_text');
        } else {
            queueConfigLineProcessingDetail.textContent = t('queue.process_lyrics_lines_detail');
        }
    }

    if (queueConfigMaxLineLengthInput) {
        queueConfigMaxLineLengthInput.disabled = !canProcessLines || !modalProcessLyricsLinesEnabled;
    }
    if (queueConfigMaxLineLengthCjkInput) {
        queueConfigMaxLineLengthCjkInput.disabled = !canProcessLines || !modalProcessLyricsLinesEnabled;
    }
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
        downgradeBtn: '#queue-config-lyrics-downgrade-btn',
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
        && Boolean(queueConfigQueueAsCheckbox?.checked)
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
    if (queueConfigQueueAsCheckbox) {
        queueConfigQueueAsCheckbox.checked = true;
    }
    if (queueConfigQueueAsInput) {
        const current = sanitizeQueueAsName(queueConfigQueueAsInput.value);
        if (!current) {
            queueConfigQueueAsInput.value = getQueueAsLastName() || getCurrentSingerName();
        }
        if (!sanitizePresenceValue(queueConfigQueueAsInput.dataset.selectedGuestId || '')) {
            queueConfigQueueAsInput.dataset.selectedGuestId = getQueueAsLastGuestId() || '';
        }
    }
    queueConfigSelectedQueueAsGuestId = sanitizePresenceValue(queueConfigQueueAsInput?.dataset.selectedGuestId || '') || null;
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
    modalAlignLyricsAutoEnabled = Boolean(defaults.karaokeEnabled && defaults.lyricsEnabled);
    modalAlignLyricsEnabled = modalAlignLyricsAutoEnabled;
    modalProcessLyricsLinesEnabled = false;
    modalConfigInitializing = true;
    lyricsManager.reset();
    lyricsManager.setMetadata(modalSelection.title || '', modalSelection.channel || '', modalSelection.title || '');
    lyricsManager.setEnabled(defaults.lyricsEnabled);
    if (queueConfigLyricsLanguageInput) {
        queueConfigLyricsLanguageInput.value = '';
    }
    if (queueConfigMaxLineLengthInput) {
        queueConfigMaxLineLengthInput.value = '36';
    }
    if (queueConfigMaxLineLengthCjkInput) {
        queueConfigMaxLineLengthCjkInput.value = '12';
    }

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
        queueConfigQueueAsInput.dataset.selectedGuestId = getQueueAsLastGuestId() || '';
    }
    queueConfigSelectedQueueAsGuestId = getQueueAsLastGuestId() || null;
    syncQueueConfigModalUi();
    modalConfigInitializing = false;
    window.setTimeout(() => {
        if (!modalSelection || !modalKaraokeEnabled || !lyricsManager?.state.lyricsEnabled) {
            return;
        }
        if (modalAlignLyricsAutoEnabled) {
            modalAlignLyricsEnabled = true;
            syncQueueConfigAlignControls();
        }
    }, 0);

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
    if (queueConfigLyricsLanguageInput) {
        queueConfigLyricsLanguageInput.value = '';
        queueConfigLyricsLanguageInput.disabled = false;
    }
    if (queueConfigMaxLineLengthInput) {
        queueConfigMaxLineLengthInput.value = '36';
        queueConfigMaxLineLengthInput.disabled = false;
    }
    if (queueConfigMaxLineLengthCjkInput) {
        queueConfigMaxLineLengthCjkInput.value = '12';
        queueConfigMaxLineLengthCjkInput.disabled = false;
    }
    queueConfigModal.classList.add('hidden');
    queueConfigModal.classList.remove('flex');
    document.body.classList.remove('overflow-hidden');
    modalSelection = null;
    modalKaraokeEnabled = false;
    modalAlignLyricsEnabled = false;
    modalAlignLyricsAutoEnabled = false;
    modalProcessLyricsLinesEnabled = false;
    modalConfigInitializing = false;
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
    const queueAsName = isAdminUser && queueAsEnabled && selection?.source !== 'local' && queueConfigQueueAsCheckbox?.checked
        ? sanitizeQueueAsName(queueConfigQueueAsInput?.value || '')
        : null;
    const queueAsGuestId = queueAsName
        ? sanitizePresenceValue(queueConfigQueueAsInput?.dataset.selectedGuestId || queueConfigSelectedQueueAsGuestId || '')
        : '';
    if (queueAsName) {
        const queueAsSelection = setQueueAsSelection(queueAsName, queueAsGuestId || null);
        updateQueueAsCurrentLabel(queueAsSelection.name);
    }
    return submitQueueItem(selection, buttonElement, {
        isKaraoke: modalKaraokeEnabled,
        lyricsEnabled: Boolean(lyricsManager?.state.lyricsEnabled),
        queueAsName,
        queueAsGuestId,
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
    syncQueueConfigAlignControls();
    syncQueueAsInQueueConfig();

    syncQueueConfirmState();
    if (modalAlignLyricsAutoEnabled && modalKaraokeEnabled && lyricsManager?.state.lyricsEnabled) {
        window.requestAnimationFrame(() => {
            if (!modalSelection || !modalAlignLyricsAutoEnabled || !modalKaraokeEnabled || !lyricsManager?.state.lyricsEnabled) {
                return;
            }
            modalAlignLyricsEnabled = true;
            syncQueueConfigAlignControls();
            syncQueueConfirmState();
        });
    }
}

async function submitQueueItem(selection, buttonElement, options = {}) {
    const source = selection?.source || 'youtube';
    const videoId = selection?.videoId || null;
    const mediaItemId = selection?.mediaItemId || null;
    const isKaraoke = Boolean(options.isKaraoke);
    const lyricsEnabled = Boolean(options.lyricsEnabled && isKaraoke && lyricsManager);
    const queueAsName = sanitizeQueueAsName(options.queueAsName);
    const queueAsGuestId = sanitizePresenceValue(options.queueAsGuestId);
    
    // Get title/artist from manager if available, otherwise fall back to selection
    const title = lyricsEnabled && lyricsManager.state.title 
        ? lyricsManager.state.title 
        : (selection?.title || '');
    const artist = lyricsEnabled && lyricsManager.state.artist 
        ? lyricsManager.state.artist 
        : (selection?.channel || '');
    
    const lyricsText = lyricsEnabled ? lyricsManager.getSubmissionText() : '';
    const lyricsFormat = lyricsText ? LyricsManager.inferFormat(lyricsText) : null;
    const alignLyrics = Boolean(lyricsEnabled && modalAlignLyricsEnabled && lyricsText && lyricsFormat !== 'json' && lyricsFormat !== 'ttml');
    const processLyricsLines = Boolean(alignLyrics && modalProcessLyricsLinesEnabled);
    const whisperxAlignLanguageOverride = alignLyrics
        ? normalizeWhisperxLanguageCode(queueConfigLyricsLanguageInput?.value)
        : '';
    const maxLineLength = processLyricsLines
        ? parseQueueConfigLineLength(queueConfigMaxLineLengthInput, 36, 200)
        : null;
    const maxLineLengthCjk = processLyricsLines
        ? parseQueueConfigLineLength(queueConfigMaxLineLengthCjkInput, 12, 100)
        : null;
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
            payload.align_lyrics = alignLyrics;
            payload.process_lyrics_lines = processLyricsLines;
            if (processLyricsLines) {
                payload.max_line_length = maxLineLength;
                payload.max_line_length_cjk = maxLineLengthCjk;
            }
            if (whisperxAlignLanguageOverride) {
                payload.whisperx_align_language_override = whisperxAlignLanguageOverride;
            }
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
            if (queueAsGuestId) {
                payload.queue_as_guest_id = queueAsGuestId;
            }
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

        setTimeout(() => {
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
        if (!modalKaraokeEnabled) {
            modalAlignLyricsEnabled = false;
            modalAlignLyricsAutoEnabled = false;
        } else if (lyricsManager?.state.lyricsEnabled) {
            modalAlignLyricsEnabled = true;
            modalAlignLyricsAutoEnabled = true;
        }
        if (modalKaraokeEnabled && getModalTitleHints().karaokeLike) {
            showQueueToast(t('queue.karaoke_already'));
        }
        syncQueueConfigModalUi();
    });
}

if (queueConfigAlignToggle) {
    queueConfigAlignToggle.addEventListener('click', () => {
        if (queueConfigAlignToggle.disabled || !lyricsManager) return;
        modalAlignLyricsEnabled = !modalAlignLyricsEnabled;
        modalAlignLyricsAutoEnabled = modalAlignLyricsEnabled;
        if (!modalAlignLyricsEnabled) {
            modalProcessLyricsLinesEnabled = false;
        }
        syncQueueConfigModalUi();
    });
}

if (queueConfigLineProcessingToggle) {
    queueConfigLineProcessingToggle.addEventListener('click', () => {
        if (queueConfigLineProcessingToggle.disabled || !lyricsManager) return;
        modalProcessLyricsLinesEnabled = !modalProcessLyricsLinesEnabled;
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
        modalAlignLyricsEnabled = Boolean(newEnabled);
        modalAlignLyricsAutoEnabled = Boolean(newEnabled);
        modalProcessLyricsLinesEnabled = false;

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
            queueConfigQueueAsInput.dataset.selectedGuestId = sanitizePresenceValue(button.dataset.queueAsGuestId);
            queueConfigSelectedQueueAsGuestId = sanitizePresenceValue(button.dataset.queueAsGuestId) || null;
            queueConfigQueueAsInput.focus();
            if (queueConfigQueueAsCheckbox) {
                queueConfigQueueAsCheckbox.checked = true;
            }
            syncQueueConfirmState();
        });
    }

    if (queueConfigQueueAsInput) {
        queueConfigQueueAsInput.addEventListener('input', () => {
            const selectedGuestId = sanitizePresenceValue(queueConfigQueueAsInput.dataset.selectedGuestId || '');
            const selectedName = sanitizeQueueAsName(queueConfigQueueAsInput.value);
            const matchingUser = queuePresenceUsers.find((user) => (
                sanitizeQueueAsName(user?.display_name) === selectedName
                && sanitizePresenceValue(user?.guest_id) === selectedGuestId
            ));
            if (!matchingUser) {
                queueConfigQueueAsInput.dataset.selectedGuestId = '';
                queueConfigSelectedQueueAsGuestId = null;
            }
            syncQueueConfirmState();
        });
    }

    if (queueConfigQueueAsCheckbox) {
        queueConfigQueueAsCheckbox.addEventListener('change', () => {
            if (!queueConfigQueueAsCheckbox.checked && queueConfigQueueAsInput) {
                queueConfigQueueAsInput.dataset.selectedGuestId = '';
                queueConfigSelectedQueueAsGuestId = null;
            }
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

queueList?.addEventListener('click', handleQueueItemCardClick);

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

    if (queueRefreshPromise) {
        queueRefreshPending = queueRefreshPending || force;
        return queueRefreshPromise;
    }

    queueRefreshPromise = (async () => {
        try {
            const response = await fetch(`${API_BASE}/api/queue/`);
            if (!response.ok) {
                throw new Error(`Queue refresh failed: ${response.status}`);
            }
            const serverQueue = await response.json();
            applyQueueState(serverQueue);
        } catch (error) {
            console.error('Refresh queue error:', error);
        } finally {
            queueRefreshPromise = null;
            if (queueRefreshPending) {
                queueRefreshPending = false;
                window.setTimeout(() => {
                    refreshQueue(true);
                }, 0);
            }
        }
    })();

    return queueRefreshPromise;
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
        const canOpenTaskDetails = ['downloading', 'processing'].includes(item.status) && Number.isFinite(Number(item.task_id));
        const canOpenMediaDetails = ['ready', 'completed'].includes(item.status) && Number.isFinite(Number(item.media_id));
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
    const rightActionHtml = item.can_cancel_task ? `
                    <button class="w-10 h-10 rounded-full bg-error/10 text-error flex items-center justify-center hover:bg-error/15 transition-colors disabled:cursor-not-allowed disabled:opacity-60"
                            onclick="cancelTask('${item.task_id}', this)"
                            title="${escapeHtml(t('queue.cancel_task'))}"
                            aria-label="${escapeHtml(t('queue.cancel_task'))}">
                        <span class="material-symbols-outlined">close</span>
                    </button>
                    ` : item.can_remove ? `
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
        const progressHtml = renderQueueProgressBlock(item);
        const statusBadgeHtml = progressHtml ? '' : `
                    <div class="mt-2 inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full ${statusInfo.bgClass}">
                        ${statusInfo.icon}
                        <span class="text-[10px] font-black uppercase tracking-tighter ${statusInfo.textClass}">${statusInfo.label}</span>
                    </div>
                    `;
        return `
            <div class="queue-item ${item.status === 'playing' ? 'glass-card border border-outline-variant/15 shadow-[0_0_20px_rgba(0,242,255,0.05)]' : 'bg-surface-container-low hover:bg-surface-container'} ${canOpenTaskDetails || canOpenMediaDetails ? 'cursor-pointer hover:border-primary/30' : ''} p-4 rounded-lg flex items-center gap-4 transition-all" data-id="${item.id}" data-media-id="${item.media_id ?? ''}" data-task-id="${item.task_id ?? ''}" data-status="${item.status}" data-processing-progress="${item.processing_progress ?? ''}" data-processing-label="${escapeHtml(item.processing_label || '')}">
                ${leftColumnHtml}
                <div class="relative w-16 h-16 rounded-md overflow-hidden shrink-0 ${item.status !== 'playing' ? 'grayscale-[50%]' : ''}">
                    <img src="${thumbnail}" alt="${escapeHtml(item.title)}" class="w-full h-full object-cover" onerror="this.parentElement.innerHTML='<div class=\\'w-full h-full bg-surface-container-highest flex items-center justify-center\\'><span class=\\'material-symbols-outlined text-on-surface-variant\\'>music_note</span></div>'">
                </div>
                <div class="flex-1 min-w-0">
                    <h3 class="font-bold ${item.status === 'playing' ? 'text-on-surface' : 'text-on-surface/80'} truncate">${escapeHtml(item.title)}</h3>
                    ${item.artist ? `<p class="text-xs text-on-surface-variant truncate">${escapeHtml(item.artist)}</p>` : ''}
                    ${item.requested_by_name ? `<p class="mt-1 text-[11px] font-medium uppercase tracking-wide text-on-surface-variant">${escapeHtml(t('queue.requested_by', { name: item.requested_by_name }))}</p>` : ''}
                    ${statusBadgeHtml}
                    ${progressHtml}
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
    window.KaraokeTaskProgress?.sync(queueList);
}

function openQueueTaskInMedia(taskId) {
    const numericTaskId = Number(taskId);
    if (!Number.isFinite(numericTaskId) || numericTaskId <= 0) {
        return;
    }
    const targetUrl = new URL(appUrl('/media'), window.location.origin);
    targetUrl.searchParams.set('task_id', String(numericTaskId));
    targetUrl.hash = 'media-task-panel';
    window.location.assign(targetUrl.toString());
}

function openQueueMediaItem(mediaId) {
    const numericMediaId = Number(mediaId);
    if (!Number.isFinite(numericMediaId) || numericMediaId <= 0) {
        return;
    }
    const targetUrl = new URL(appUrl('/media'), window.location.origin);
    targetUrl.searchParams.set('media_id', String(numericMediaId));
    window.location.assign(targetUrl.toString());
}

function handleQueueItemCardClick(event) {
    if (!queueList) {
        return;
    }
    const queueItem = event.target.closest('.queue-item');
    if (!queueItem || !queueList.contains(queueItem)) {
        return;
    }
    if (event.target.closest('button, a, input, select, textarea, label, [role="button"]')) {
        return;
    }
    const status = queueItem.dataset.status;
    const mediaId = Number(queueItem.dataset.mediaId);
    const taskId = Number(queueItem.dataset.taskId);
    if (['ready', 'completed'].includes(status) && Number.isFinite(mediaId) && mediaId > 0) {
        openQueueMediaItem(mediaId);
        return;
    }
    if (!['downloading', 'processing'].includes(status) || !Number.isFinite(taskId) || taskId <= 0) {
        return;
    }
    openQueueTaskInMedia(taskId);
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

function getQueueProgressLabel(item) {
    const label = item?.processing_label_key
        ? t(item.processing_label_key, item.processing_label_args || {})
        : (item?.processing_label || item?.processing_stage || t('queue.processing_ai'));
    const stepIndex = Number(item?.processing_step_index);
    const stepTotal = Number(item?.processing_step_total);
    if (Number.isFinite(stepIndex) && Number.isFinite(stepTotal) && stepIndex > 0 && stepTotal > 0) {
        return t('task.progress_step', {
            label,
            current: stepIndex,
            total: stepTotal,
        });
    }
    return label;
}

function renderQueueProgressBlock(item) {
    const isActive = ['downloading', 'processing'].includes(item.status);
    if (!isActive) {
        return '';
    }
    const progressValue = item.processing_progress;
    const percent = Number.isFinite(Number(progressValue)) ? Number(progressValue) : 0;
    const label = getQueueProgressLabel(item);
    const mode = item.processing_mode || '';
    const separator = mode === 'indeterminate' ? '' : ' • ';
    return `
        <div class="mt-2 max-w-xs" data-task-progress-key="queue-${item.id}" data-task-progress-status="${escapeHtml(item.status)}" data-task-progress-stage="${escapeHtml(item.processing_stage || '')}" data-task-progress-mode="${escapeHtml(mode)}" data-task-progress-reported-percent="${Math.max(0, Math.min(100, percent))}" data-task-progress-label="${escapeHtml(label)}">
            <div class="h-1.5 overflow-hidden rounded-full bg-surface-container-highest" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.max(0, Math.min(100, percent))}">
                <div class="h-full rounded-full bg-tertiary transition-all duration-300 ease-out" data-task-progress-fill style="width: ${Math.max(0, Math.min(100, percent))}%"></div>
            </div>
            <p class="mt-1 text-[10px] text-on-surface-variant">${escapeHtml(label)}${separator}<span data-task-progress-percent-text class="${mode === 'indeterminate' ? 'hidden' : ''}">${escapeHtml(String(percent))}%</span></p>
        </div>
    `;
}

function normalizeQueueItem(item) {
    if (!item || typeof item !== 'object') {
        return null;
    }
    return {
        ...item,
        id: Number(item.id),
        position: Number.isFinite(Number(item.position)) ? Number(item.position) : 0,
    };
}

function sortQueueItems(queue) {
    return [...queue].sort((a, b) => {
        const positionDelta = Number(a?.position || 0) - Number(b?.position || 0);
        if (positionDelta !== 0) {
            return positionDelta;
        }
        return Number(a?.id || 0) - Number(b?.id || 0);
    });
}

function applyQueueState(queue, { render = true } = {}) {
    const normalized = Array.isArray(queue)
        ? sortQueueItems(queue.map(normalizeQueueItem).filter(Boolean))
        : [];
    currentQueueState = normalized;
    syncStageControlAvailability(currentQueueState);
    syncStageVocalsAvailability(currentQueueState);
    syncStageLyricsAvailability(currentQueueState);
    if (render) {
        updateQueueDisplay(currentQueueState);
    }
}

function updateQueueState(mutator, options = {}) {
    const snapshot = sortQueueItems(currentQueueState.map((item) => ({ ...item })));
    const nextQueue = mutator(snapshot);
    applyQueueState(Array.isArray(nextQueue) ? nextQueue : snapshot, options);
}

function upsertQueueItemState(item) {
    const normalized = normalizeQueueItem(item);
    if (!normalized) {
        return false;
    }
    updateQueueState((queue) => {
        const index = queue.findIndex((entry) => entry.id === normalized.id);
        if (index >= 0) {
            queue[index] = { ...queue[index], ...normalized };
        } else {
            queue.push(normalized);
        }
        return queue;
    });
    return true;
}

function patchQueueItemProgressState(item) {
    if (!item || typeof item !== 'object') {
        return false;
    }
    const normalizedId = Number(item.id);
    if (!Number.isFinite(normalizedId)) {
        return false;
    }
    const index = currentQueueState.findIndex((entry) => entry.id === normalizedId);
    if (index < 0) {
        return false;
    }
    updateQueueState((queue) => {
        const targetIndex = queue.findIndex((entry) => entry.id === normalizedId);
        if (targetIndex < 0) {
            return queue;
        }
        queue[targetIndex] = {
            ...queue[targetIndex],
            ...item,
            id: normalizedId,
        };
        return queue;
    });
    return true;
}

function removeQueueItemState(itemId) {
    const normalizedId = Number(itemId);
    if (!Number.isFinite(normalizedId)) {
        return false;
    }
    updateQueueState((queue) => queue.filter((item) => item.id !== normalizedId));
    return true;
}

function handleCurrentItemChanged(eventDetail) {
    const currentId = Number(eventDetail?.id);
    const previousId = Number(eventDetail?.previous_id);
    const hasCurrentId = Number.isFinite(currentId) && currentId > 0;
    const hasPreviousId = Number.isFinite(previousId) && previousId > 0;

    if (hasCurrentId && !currentQueueState.some((item) => item.id === currentId)) {
        refreshQueue(true);
        return;
    }

    updateQueueState((queue) => queue
        .filter((item) => !(hasPreviousId && item.id === previousId && item.id !== currentId))
        .map((item) => {
            if (hasCurrentId && item.id === currentId) {
                return { ...item, status: 'playing' };
            }
            if (item.status === 'playing' && item.id !== currentId) {
                return { ...item, status: 'ready' };
            }
            return item;
        }));
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

async function cancelTask(taskId, button) {
    const numericTaskId = Number(taskId);
    if (!Number.isFinite(numericTaskId) || numericTaskId <= 0) {
        return;
    }

    const actionButton = button || null;
    const originalHtml = actionButton?.innerHTML || "";
    if (actionButton) {
        actionButton.disabled = true;
        actionButton.setAttribute("aria-busy", "true");
        actionButton.title = t('queue.canceling');
        actionButton.setAttribute("aria-label", t('queue.canceling'));
        actionButton.innerHTML = '<span class="material-symbols-outlined animate-spin text-[18px]">sync</span>';
    }

    try {
        const response = await fetch(window.KaraokeURLs.appUrl(`/api/tasks/${numericTaskId}/cancel`), {
            method: "POST",
        });
        if (!response.ok) {
            let detail = t('queue.cancel_task_failed');
            try {
                const payload = await response.json();
                if (payload?.detail) {
                    detail = payload.detail;
                }
            } catch (_) {
                // Keep fallback text.
            }
            throw new Error(detail);
        }

        refreshQueue(true);
    } catch (error) {
        console.error('Error canceling task:', error);
        alert(error instanceof Error ? error.message : t('queue.cancel_task_failed'));
        if (actionButton) {
            actionButton.disabled = false;
            actionButton.removeAttribute("aria-busy");
            actionButton.title = t('queue.cancel_task');
            actionButton.setAttribute("aria-label", t('queue.cancel_task'));
            actionButton.innerHTML = originalHtml || `<span class="material-symbols-outlined">close</span>`;
        }
    }
}

window.moveSong = moveSong;
window.cancelTask = cancelTask;

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
        this.shouldReconnect = true;
        this.lastMessageAt = 0;
        this.lastPingAt = 0;
        this.reconnectTimer = null;
        this.statusIndicator = null;
        this.guestId = ensureGuestId();
        this.tabId = ensureQueueTabId();
        this.heartbeatIntervalMs = window.KaraokeWebSocketLifecycle?.heartbeatIntervalMs || 30000;
        
        this.createStatusIndicator();
        this.lifecycleCleanup = window.KaraokeWebSocketLifecycle?.installPageLifecycle({
            onVisible: () => this.handleVisibleResume(),
            onOnline: () => this.handleVisibleResume(),
            onPageShow: () => this.handlePageShow(),
            onPageHide: () => this.handlePageHide(),
            onOffline: () => {
                if (!this.isConnected) {
                    this.updateStatus('disconnected');
                }
            },
        }) || null;
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
        const canControl = connected && stageRemoteCanControl;
        if (stageRemotePlayPauseBtn) stageRemotePlayPauseBtn.disabled = !canControl;
        if (stageRemoteSkipBtn) stageRemoteSkipBtn.disabled = !canControl;
        if (stageRemoteResyncBtn) stageRemoteResyncBtn.disabled = !canControl;
        updateStageRemoteSeekForwardUi();
        updateStageRemoteLyricsUi();
        updateStageRemoteVocalsUi();
        if (stageRemoteStatus) {
            stageRemoteStatus.textContent = connected
                ? (stageRemoteCanControl ? t('queue.connected') : t('queue.stage_controls_limited'))
                : t('queue.offline');
        }
    }

    clearReconnectTimer() {
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
    }

    clearPollingTimers() {
        if (queueRecoveryTimeout) {
            clearTimeout(queueRecoveryTimeout);
            queueRecoveryTimeout = null;
        }
    }

    isSocketStale() {
        return window.KaraokeWebSocketLifecycle?.isSocketStale({
            socket: this.ws,
            lastActivityAt: Math.max(this.lastMessageAt || 0, this.lastPingAt || 0),
            graceMs: 5000,
        }) || false;
    }

    resetReconnectState() {
        this.clearReconnectTimer();
        this.isReconnecting = false;
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
    }

    handlePageShow(event) {
        this.shouldReconnect = true;
        if (!event?.persisted && this.ws && this.ws.readyState === WebSocket.CONNECTING) {
            return;
        }
        if (event?.persisted || !this.ws || this.ws.readyState === WebSocket.CLOSED || this.isSocketStale()) {
            this.reconnectNow('pageshow');
        }
    }

    handlePageHide() {
        this.disconnect({ allowReconnect: false });
    }

    handleVisibleResume() {
        this.shouldReconnect = true;
        if (!document || document.visibilityState !== 'visible') {
            return;
        }
        if (this.ws && this.ws.readyState === WebSocket.CONNECTING) {
            return;
        }
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN || this.isSocketStale()) {
            this.reconnectNow('foreground');
        }
    }

    reconnectNow(reason = 'manual') {
        this.shouldReconnect = true;
        logger.log(`[WebSocket] Forcing reconnect due to ${reason}`);
        this.clearReconnectTimer();
        if (this.ws && this.ws.readyState !== WebSocket.CLOSED) {
            try {
                this.ws.close(4000, reason);
            } catch (_) {
                // Best-effort close only.
            }
        }
        this.ws = null;
        this.resetReconnectState();
        this.connect(true);
        if (document.visibilityState === 'visible') {
            startQueueRefresh({ fast: true });
        }
    }

    connect(force = false) {
        if (this.ws && (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)) {
            if (!force) {
                return;
            }
            try {
                this.ws.close(4000, 'force reconnect');
            } catch (_) {
                // Ignore close failures and create a fresh socket below.
            }
            this.ws = null;
        }

        if (!this.shouldReconnect) {
            return;
        }

        const wsUrl = appWsUrl('/api/queue/ws');
        
        logger.log('[WebSocket] Connecting to', wsUrl);
        this.updateStatus('reconnecting', 'Connecting...');
        
        try {
            this.ws = new WebSocket(wsUrl);
            const socket = this.ws;
            
            this.ws.onopen = () => {
                if (this.ws !== socket) {
                    return;
                }
                logger.log('[WebSocket] Connected');
                this.isConnected = true;
                this.isReconnecting = false;
                this.lastMessageAt = Date.now();
                this.lastPingAt = 0;
                this.resetReconnectState();
                this.updateStatus('connected', `● ${t('queue.live')}`);
                
                // Stop polling when WebSocket is connected
                this.clearPollingTimers();
                if (refreshInterval) {
                    clearInterval(refreshInterval);
                    refreshInterval = null;
                }
                this.send({
                    type: 'client_subscribe',
                    data: { page: 'queue' },
                    timestamp: Date.now(),
                });
                this.sendPresenceHello();
                requestStagePresenceSnapshot();
                void loadRemoteLyricsPresets();
                refreshQueue(true);
            };
            
            this.ws.onmessage = (event) => {
                if (this.ws !== socket) {
                    return;
                }
                try {
                    const message = JSON.parse(event.data);
                    this.lastMessageAt = Date.now();
                    this.handleMessage(message);
                } catch (error) {
                    console.error('[WebSocket] Error parsing message:', error);
                }
            };
            
            this.ws.onerror = (error) => {
                if (this.ws !== socket) {
                    return;
                }
                logger.error('[WebSocket] Error:', error);
            };

            this.ws.onclose = () => {
                if (this.ws !== socket) {
                    return;
                }
                logger.log('[WebSocket] Disconnected');
                this.isConnected = false;
                this.ws = null;
                clearRemoteLyricsApplyPending(t('queue.stage_offline'));
                
                // Attempt reconnection
                if (this.shouldReconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
                    this.reconnect();
                } else if (this.shouldReconnect) {
                    logger.warn('[WebSocket] Max reconnection attempts reached, falling back to polling');
                    this.updateStatus('fallback', 'Using polling');
                    this.fallbackToPolling();
                } else {
                    this.updateStatus('disconnected');
                }
            };
        } catch (error) {
            logger.error('[WebSocket] Connection error:', error);
            if (this.shouldReconnect) {
                this.reconnect();
            }
        }
    }
    
    reconnect() {
        if (!this.shouldReconnect || this.isReconnecting) return;
        
        this.isReconnecting = true;
        this.reconnectAttempts++;
        
        const rawDelay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1), this.maxReconnectDelay);
        const delay = window.KaraokeWebSocketLifecycle?.withJitter(rawDelay) ?? rawDelay;
        
        logger.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
        this.updateStatus('reconnecting', `Reconnecting... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
        
        this.clearReconnectTimer();
        this.reconnectTimer = setTimeout(() => {
            this.isReconnecting = false;
            this.connect();
        }, delay);
    }
    
    fallbackToPolling() {
        logger.warn('[WebSocket] Falling back to polling mode');
        refreshPresenceFallback();
        startQueueRefresh({ fast: true });
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
        this.lastMessageAt = Date.now();
        switch (message.type) {
            case 'connected':
                logger.log('[WebSocket] Connection confirmed, active connections:', message.data.connection_count);
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
                this.lastPingAt = Date.now();
                this.send({ type: 'pong', timestamp: Date.now() });
                break;
            case 'queue_item_added':
                window.dispatchEvent(new CustomEvent('queue_item_added', { detail: message.data }));
                break;
            case 'queue_item_updated':
                window.dispatchEvent(new CustomEvent('queue_item_updated', { detail: message.data }));
                break;
            case 'queue_item_progress':
                window.dispatchEvent(new CustomEvent('queue_item_progress', { detail: message.data }));
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
            case 'stage_time_update':
                window.dispatchEvent(new CustomEvent('stage_time_update', { detail: message.data }));
                break;
            case 'stage_presence_snapshot':
                stageRemoteStageDisplays = Array.isArray(message.data?.stages) ? message.data.stages : [];
                renderRemoteStageOptions();
                updateStageRemoteSeekForwardUi();
                break;
            case 'lyrics_settings_ack':
                window.dispatchEvent(new CustomEvent('lyrics_settings_ack', { detail: message.data }));
                break;
            case 'error':
                if (message.data?.detail) {
                    const detail = message.data.detail === 'Not allowed to control this stage item'
                        ? t('queue.stage_control_denied')
                        : message.data.detail;
                    showQueueToast(detail);
                }
                break;
            default:
                logger.log('[WebSocket] Unknown message type:', message.type);
        }
    }
    
    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
            return true;
        }
        return false;
    }
    
    disconnect({ allowReconnect = false } = {}) {
        this.shouldReconnect = Boolean(allowReconnect);
        this.clearReconnectTimer();
        this.clearPollingTimers();
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.isConnected = false;
        this.isReconnecting = false;
    }
}

function updateStageRemotePlayPauseUi() {
    if (!stageRemotePlayPauseIcon || !stageRemotePlayPauseLabel) return;
    stageRemotePlayPauseIcon.textContent = stageRemotePaused ? 'play_arrow' : 'pause';
    stageRemotePlayPauseLabel.textContent = stageRemotePaused ? t('common.play') : t('stage.pause');
}

function updateStageRemoteSeekForwardUi() {
    if (!stageRemoteSeekForwardBtn) return;
    const connected = !!(queueWebSocket && queueWebSocket.isConnected);
    const hasConnectedStage = stageRemoteStageDisplays.length > 0;
    stageRemoteSeekForwardBtn.disabled = !connected || !stageRemoteCanControl || !hasConnectedStage;
}

function updateStageRemoteVocalsUi() {
    const isDisabled = !stageRemoteCanControl || !stageRemoteVocalsAvailable || !(queueWebSocket && queueWebSocket.isConnected);
    const volume = Math.round(stageRemoteVocalsVolume * 100);

    if (stageRemoteVocalsControl) {
        stageRemoteVocalsControl.classList.toggle('opacity-70', isDisabled);
    }

    if (stageRemoteVocalsToggleBtn) {
        stageRemoteVocalsToggleBtn.disabled = isDisabled;
        stageRemoteVocalsToggleBtn.setAttribute('aria-pressed', stageRemoteVocalsEnabled ? 'true' : 'false');
        stageRemoteVocalsToggleBtn.classList.toggle('bg-secondary/15', stageRemoteVocalsEnabled);
        stageRemoteVocalsToggleBtn.classList.toggle('text-secondary', stageRemoteVocalsEnabled);
        stageRemoteVocalsToggleBtn.classList.toggle('bg-surface-container-highest', !stageRemoteVocalsEnabled);
        stageRemoteVocalsToggleBtn.classList.toggle('text-on-surface-variant', !stageRemoteVocalsEnabled);
    }

    if (stageRemoteVocalsToggleIcon) {
        stageRemoteVocalsToggleIcon.textContent = stageRemoteVocalsEnabled ? 'mic' : 'mic_off';
    }

    if (stageRemoteVocalsVolumeSlider) {
        stageRemoteVocalsVolumeSlider.disabled = isDisabled;
        stageRemoteVocalsVolumeSlider.value = String(volume);
        stageRemoteVocalsVolumeSlider.setAttribute('aria-valuetext', `${volume}%`);
    }

    if (stageRemoteVocalsVolumeLabel) {
        stageRemoteVocalsVolumeLabel.textContent = `${volume}%`;
        stageRemoteVocalsVolumeLabel.classList.toggle('text-secondary', stageRemoteVocalsEnabled && volume > 0);
        stageRemoteVocalsVolumeLabel.classList.toggle('text-on-surface-variant', !stageRemoteVocalsEnabled || volume === 0);
    }
}

function setStageRemoteLyricsStatus(message) {
    if (stageRemoteLyricsSettingsStatus) {
        stageRemoteLyricsSettingsStatus.textContent = message;
    }
}

function getSelectedRemoteStage() {
    const selectedId = stageRemoteStageSelect?.value || '';
    return stageRemoteStageDisplays.find((stage) => String(stage.stage_id) === selectedId) || null;
}

function getRemoteStageDisplayLabel(stage) {
    return stage?.stage_name || stage?.stage_id || t('stage.display_name_default');
}

function renderRemoteStageOptions() {
    if (!stageRemoteStageSelect) return;
    const previousValue = stageRemoteStageSelect.value;
    stageRemoteStageSelect.innerHTML = '';

    if (!stageRemoteStageDisplays.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = t('queue.stage_no_displays');
        stageRemoteStageSelect.appendChild(option);
        setStageRemoteLyricsStatus(t('queue.stage_no_displays'));
        updateStageRemoteLyricsUi();
        return;
    }

    const requireSelection = stageRemoteStageDisplays.length > 1;
    if (requireSelection) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = t('queue.stage_choose_display');
        stageRemoteStageSelect.appendChild(option);
    }

    stageRemoteStageDisplays.forEach((stage) => {
        const option = document.createElement('option');
        option.value = stage.stage_id;
        option.textContent = stage.connection_count > 1
            ? t('queue.stage_display_with_tabs', {
                name: getRemoteStageDisplayLabel(stage),
                count: stage.connection_count,
            })
            : getRemoteStageDisplayLabel(stage);
        stageRemoteStageSelect.appendChild(option);
    });

    const hasPrevious = stageRemoteStageDisplays.some((stage) => stage.stage_id === previousValue);
    if (hasPrevious) {
        stageRemoteStageSelect.value = previousValue;
    } else if (!requireSelection) {
        stageRemoteStageSelect.value = stageRemoteStageDisplays[0].stage_id;
    } else {
        stageRemoteStageSelect.value = '';
    }

    setStageRemoteLyricsStatus(
        requireSelection ? t('queue.stage_lyrics_choose_target') : t('queue.stage_lyrics_ready')
    );
    updateStageRemoteLyricsUi();
}

function renderRemoteLyricsPresetOptions() {
    if (!stageRemoteLyricsPresetSelect) return;
    const previousValue = stageRemoteLyricsPresetSelect.value;
    stageRemoteLyricsPresetSelect.innerHTML = '';

    const emptyOption = document.createElement('option');
    emptyOption.value = '';
    emptyOption.textContent = t('queue.stage_lyrics_no_preset');
    stageRemoteLyricsPresetSelect.appendChild(emptyOption);

    stageRemoteLyricsPresets.forEach((preset) => {
        const option = document.createElement('option');
        option.value = String(preset.id);
        option.textContent = preset.name;
        stageRemoteLyricsPresetSelect.appendChild(option);
    });

    if (Array.from(stageRemoteLyricsPresetSelect.options).some((option) => option.value === previousValue)) {
        stageRemoteLyricsPresetSelect.value = previousValue;
    }
    syncRemoteLyricsControls(getSelectedRemoteLyricsPreset()?.settings || {});
}

function getSelectedRemoteLyricsPreset() {
    const presetId = Number(stageRemoteLyricsPresetSelect?.value || 0);
    if (presetId <= 0) {
        return null;
    }
    return stageRemoteLyricsPresets.find((preset) => Number(preset.id) === presetId) || null;
}

async function loadRemoteLyricsPresets() {
    if (!isAdminUser || !stageRemoteLyricsPresetSelect) return;
    try {
        const response = await fetch(QUEUE_LYRICS_PRESETS_API, { credentials: 'same-origin' });
        if (!response.ok) {
            throw new Error(`Failed to load presets (${response.status})`);
        }
        stageRemoteLyricsPresets = await response.json();
    } catch (error) {
        stageRemoteLyricsPresets = [];
        setStageRemoteLyricsStatus(t('queue.stage_lyrics_presets_failed'));
    }
    renderRemoteLyricsPresetOptions();
}

function updateRemoteLyricsSliderLabels() {
    if (stageRemoteLyricsSizeValue && stageRemoteLyricsSizeSlider) {
        stageRemoteLyricsSizeValue.textContent = `${Number(stageRemoteLyricsSizeSlider.value).toFixed(1)}vw`;
    }
    if (stageRemoteLyricsWidthValue && stageRemoteLyricsWidthSlider) {
        stageRemoteLyricsWidthValue.textContent = `${Math.round(Number(stageRemoteLyricsWidthSlider.value))}%`;
    }
}

function syncRemoteLyricsControls(settings = {}) {
    if (stageRemoteLyricsSizeSlider && typeof settings.sizeVw === 'number' && Number.isFinite(settings.sizeVw)) {
        stageRemoteLyricsSizeSlider.value = String(settings.sizeVw);
    }
    if (stageRemoteLyricsWidthSlider && typeof settings.lineWidthPct === 'number' && Number.isFinite(settings.lineWidthPct)) {
        stageRemoteLyricsWidthSlider.value = String(Math.round(settings.lineWidthPct));
    }
    if (stageRemoteLyricsBackgroundEnabledToggle && typeof settings.backgroundMediaEnabled === 'boolean') {
        stageRemoteLyricsBackgroundEnabled = settings.backgroundMediaEnabled;
        stageRemoteLyricsBackgroundEnabledToggle.checked = settings.backgroundMediaEnabled;
    }
    updateRemoteLyricsSliderLabels();
}

function requestStagePresenceSnapshot() {
    if (!queueWebSocket) return false;
    return queueWebSocket.send({
        type: 'stage_presence_request',
        data: {},
        timestamp: Date.now(),
    });
}

function setRemoteLyricsSettingsPanelOpen(open) {
    stageRemoteLyricsSettingsOpen = Boolean(open);
    if (stageRemoteLyricsSettingsPanel) {
        stageRemoteLyricsSettingsPanel.classList.toggle('hidden', !stageRemoteLyricsSettingsOpen);
    }
    if (stageRemoteLyricsSettingsBtn) {
        stageRemoteLyricsSettingsBtn.setAttribute('aria-expanded', stageRemoteLyricsSettingsOpen ? 'true' : 'false');
    }
    if (stageRemoteLyricsSettingsOpen) {
        updateRemoteLyricsSliderLabels();
        requestStagePresenceSnapshot();
        void loadRemoteLyricsPresets();
    }
    updateStageRemoteLyricsUi();
}

function clearRemoteLyricsApplyPending(message = '') {
    window.clearTimeout(stageRemoteLyricsAckTimer);
    stageRemoteLyricsApplyPending = false;
    stageRemoteLyricsPendingStageId = null;
    if (message) {
        setStageRemoteLyricsStatus(message);
    }
    updateStageRemoteLyricsUi();
}

function updateStageRemoteLyricsUi() {
    const connected = !!(queueWebSocket && queueWebSocket.isConnected);
    const canUseLyricsControl = connected && stageRemoteCanControl;
    const canOpenSettings = canUseLyricsControl && isAdminUser;
    const selectedStage = getSelectedRemoteStage();
    const selectedPreset = Number(stageRemoteLyricsPresetSelect?.value || 0);
    const canApplySettings = canOpenSettings
        && stageRemoteStageDisplays.length > 0
        && Boolean(selectedStage)
        && selectedPreset > 0
        && !stageRemoteLyricsApplyPending;

    if (stageRemoteLyricsSettingsBtn) {
        stageRemoteLyricsSettingsBtn.disabled = isAdminUser
            ? !canOpenSettings
            : (!canUseLyricsControl || !stageRemoteLyricsAvailable);
    }
    if (stageRemoteLyricsToggleIcon) {
        stageRemoteLyricsToggleIcon.textContent = isAdminUser
            ? (stageRemoteLyricsSettingsOpen ? 'close' : 'tune')
            : (stageRemoteLyricsEnabled ? 'subtitles' : 'subtitles_off');
    }
    if (stageRemoteLyricsToggleLabel) {
        stageRemoteLyricsToggleLabel.textContent = isAdminUser
            ? t('stage.lyrics_settings')
            : (stageRemoteLyricsAvailable ? (stageRemoteLyricsEnabled ? t('stage.lyrics_on') : t('stage.lyrics_off')) : t('stage.no_lyrics'));
    }
    if (stageRemoteStageRefreshBtn) {
        stageRemoteStageRefreshBtn.disabled = !connected;
    }
    if (stageRemoteStageSelect) {
        stageRemoteStageSelect.disabled = !canOpenSettings || stageRemoteStageDisplays.length === 0 || stageRemoteLyricsApplyPending;
    }
    if (stageRemoteLyricsPresetSelect) {
        stageRemoteLyricsPresetSelect.disabled = !canOpenSettings || stageRemoteLyricsApplyPending;
    }
    if (stageRemoteLyricsEnabledToggle) {
        stageRemoteLyricsEnabledToggle.disabled = !canOpenSettings || stageRemoteLyricsApplyPending;
        stageRemoteLyricsEnabledToggle.checked = stageRemoteLyricsEnabled;
    }
    if (stageRemoteLyricsBackgroundEnabledToggle) {
        stageRemoteLyricsBackgroundEnabledToggle.disabled = !canOpenSettings
            || stageRemoteLyricsApplyPending
            || !selectedStage;
        stageRemoteLyricsBackgroundEnabledToggle.checked = stageRemoteLyricsBackgroundEnabled;
    }
    if (stageRemoteLyricsSizeSlider) {
        stageRemoteLyricsSizeSlider.disabled = !canOpenSettings || stageRemoteLyricsApplyPending;
    }
    if (stageRemoteLyricsWidthSlider) {
        stageRemoteLyricsWidthSlider.disabled = !canOpenSettings || stageRemoteLyricsApplyPending;
    }
    if (stageRemoteLyricsApplyBtn) {
        stageRemoteLyricsApplyBtn.disabled = !canApplySettings;
    }
    if (stageRemoteLyricsOverrideBtn) {
        stageRemoteLyricsOverrideBtn.disabled = !canApplySettings;
    }
}

function syncStageControlAvailability(queue) {
    if (isAdminUser) {
        stageRemoteCanControl = true;
    } else {
        const playingItem = Array.isArray(queue) ? queue.find((item) => item.status === 'playing') : null;
        stageRemoteCanControl = Boolean(playingItem && playingItem.can_control_stage);
    }
    queueWebSocket?.updateRemoteControlsState();
}

function syncStageVocalsAvailability(queue) {
    const playingItem = Array.isArray(queue) ? queue.find((item) => item.status === 'playing') : null;
    stageRemoteVocalsAvailable = Boolean(playingItem && playingItem.vocals_path);
    if (!stageRemoteVocalsAvailable) {
        stageRemoteVocalsEnabled = false;
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

function canSendStageControl() {
    if (stageRemoteCanControl) {
        return true;
    }
    alert(t('queue.stage_control_denied'));
    return false;
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
        if (!canSendStageControl()) return;
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
        if (!canSendStageControl()) return;
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
        if (!canSendStageControl()) return;
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

if (stageRemoteSeekForwardBtn) {
    stageRemoteSeekForwardBtn.addEventListener('click', () => {
        if (!queueWebSocket) return;
        if (!canSendStageControl()) return;
        const sent = queueWebSocket.send({
            type: 'stage_command',
            data: {
                command: 'seek_relative',
                source: 'queue',
                offset_seconds: 5,
                is_paused: stageRemotePaused,
            },
            timestamp: Date.now(),
        });
        if (!sent) {
            alert(t('queue.stage_offline'));
        }
    });
}

function sendStageLyricsEnabled(nextEnabled, { requireLyricsTrack = false } = {}) {
    if (!queueWebSocket) return false;
    if (!canSendStageControl()) return false;
    if (requireLyricsTrack && !stageRemoteLyricsAvailable) {
        alert(t('queue.no_lyrics_track'));
        return false;
    }
    const sent = queueWebSocket.send({
        type: 'stage_command',
        data: {
            command: 'set_lyrics_enabled',
            source: 'queue',
            lyrics_enabled: Boolean(nextEnabled),
        },
        timestamp: Date.now(),
    });
    if (!sent) {
        alert(t('queue.stage_offline'));
        return false;
    }
    stageRemoteLyricsEnabled = Boolean(nextEnabled);
    updateStageRemoteLyricsUi();
    return true;
}

function sendStageBackgroundEnabled(nextEnabled) {
    if (!queueWebSocket) return false;
    if (!canSendStageControl()) return false;

    const selectedStage = getSelectedRemoteStage();
    if (!selectedStage) {
        setStageRemoteLyricsStatus(t('queue.stage_lyrics_choose_target'));
        updateStageRemoteLyricsUi();
        return false;
    }

    const sent = queueWebSocket.send({
        type: 'stage_command',
        data: {
            command: 'set_background_media_enabled',
            source: 'queue',
            target_stage_id: selectedStage.stage_id,
            background_media_enabled: Boolean(nextEnabled),
        },
        timestamp: Date.now(),
    });
    if (!sent) {
        alert(t('queue.stage_offline'));
        return false;
    }

    stageRemoteLyricsBackgroundEnabled = Boolean(nextEnabled);
    stageRemoteLyricsApplyPending = true;
    stageRemoteLyricsPendingStageId = selectedStage.stage_id;
    setStageRemoteLyricsStatus(t('queue.stage_lyrics_applying', { name: getRemoteStageDisplayLabel(selectedStage) }));
    updateStageRemoteLyricsUi();
    window.clearTimeout(stageRemoteLyricsAckTimer);
    stageRemoteLyricsAckTimer = window.setTimeout(() => {
        clearRemoteLyricsApplyPending(t('queue.stage_lyrics_apply_timeout'));
    }, 7000);
    return true;
}

function sendRemoteLyricsApply({ override = false } = {}) {
    if (!queueWebSocket) return false;
    if (!canSendStageControl()) return false;

    const selectedStage = getSelectedRemoteStage();
    if (!selectedStage) {
        setStageRemoteLyricsStatus(t('queue.stage_lyrics_choose_target'));
        updateStageRemoteLyricsUi();
        return false;
    }

    const presetId = Number(stageRemoteLyricsPresetSelect?.value || 0);
    if (presetId <= 0) {
        setStageRemoteLyricsStatus(t('queue.stage_lyrics_choose_preset'));
        updateStageRemoteLyricsUi();
        return false;
    }

    const lyricsEnabled = Boolean(stageRemoteLyricsEnabledToggle?.checked);
    const backgroundMediaEnabled = Boolean(stageRemoteLyricsBackgroundEnabledToggle?.checked);
    const payload = {
        command: 'apply_lyrics_settings',
        source: 'queue',
        target_stage_id: selectedStage.stage_id,
        lyrics_enabled: lyricsEnabled,
        background_media_enabled: backgroundMediaEnabled,
        preset_id: presetId,
        override: Boolean(override),
    };

    if (override) {
        const sizeVw = Number(stageRemoteLyricsSizeSlider?.value || 4.5);
        const lineWidthPct = Number(stageRemoteLyricsWidthSlider?.value || 85);
        payload.size_vw = Number.isFinite(sizeVw) ? sizeVw : 4.5;
        payload.line_width_pct = Number.isFinite(lineWidthPct) ? Math.round(lineWidthPct) : 85;
    }

    const sent = queueWebSocket.send({
        type: 'stage_command',
        data: payload,
        timestamp: Date.now(),
    });
    if (!sent) {
        setStageRemoteLyricsStatus(t('queue.stage_offline'));
        return false;
    }

    stageRemoteLyricsApplyPending = true;
    stageRemoteLyricsPendingStageId = selectedStage.stage_id;
    setStageRemoteLyricsStatus(t('queue.stage_lyrics_applying', { name: getRemoteStageDisplayLabel(selectedStage) }));
    updateStageRemoteLyricsUi();
    window.clearTimeout(stageRemoteLyricsAckTimer);
    stageRemoteLyricsAckTimer = window.setTimeout(() => {
        clearRemoteLyricsApplyPending(t('queue.stage_lyrics_apply_timeout'));
    }, 7000);
    return true;
}

if (stageRemoteLyricsSettingsBtn) {
    stageRemoteLyricsSettingsBtn.addEventListener('click', () => {
        if (!isAdminUser) {
            sendStageLyricsEnabled(!stageRemoteLyricsEnabled, { requireLyricsTrack: true });
            return;
        }
        if (!queueWebSocket) return;
        if (!canSendStageControl()) return;
        setRemoteLyricsSettingsPanelOpen(!stageRemoteLyricsSettingsOpen);
    });
}

stageRemoteStageRefreshBtn?.addEventListener('click', () => {
    if (!requestStagePresenceSnapshot()) {
        setStageRemoteLyricsStatus(t('queue.stage_offline'));
    } else {
        setStageRemoteLyricsStatus(t('queue.stage_lyrics_refreshing'));
    }
});

stageRemoteStageSelect?.addEventListener('change', updateStageRemoteLyricsUi);
stageRemoteLyricsPresetSelect?.addEventListener('change', () => {
    syncRemoteLyricsControls(getSelectedRemoteLyricsPreset()?.settings || {});
    updateStageRemoteLyricsUi();
});
stageRemoteLyricsEnabledToggle?.addEventListener('change', () => {
    const nextEnabled = Boolean(stageRemoteLyricsEnabledToggle.checked);
    if (!sendStageLyricsEnabled(nextEnabled)) {
        stageRemoteLyricsEnabledToggle.checked = stageRemoteLyricsEnabled;
    }
});
stageRemoteLyricsBackgroundEnabledToggle?.addEventListener('change', () => {
    const nextEnabled = Boolean(stageRemoteLyricsBackgroundEnabledToggle.checked);
    if (!sendStageBackgroundEnabled(nextEnabled)) {
        stageRemoteLyricsBackgroundEnabledToggle.checked = stageRemoteLyricsBackgroundEnabled;
    }
});
stageRemoteLyricsSizeSlider?.addEventListener('input', updateRemoteLyricsSliderLabels);
stageRemoteLyricsWidthSlider?.addEventListener('input', updateRemoteLyricsSliderLabels);

stageRemoteLyricsApplyBtn?.addEventListener('click', () => {
    sendRemoteLyricsApply({ override: false });
});

stageRemoteLyricsOverrideBtn?.addEventListener('click', () => {
    sendRemoteLyricsApply({ override: true });
});

function sendStageVocalsVolume(nextVolume) {
    if (!queueWebSocket || !stageRemoteCanControl || !stageRemoteVocalsAvailable) {
        return false;
    }

    const clampedVolume = Math.max(0, Math.min(1, nextVolume));
    const commands = [];

    if (clampedVolume > 0 && !stageRemoteVocalsEnabled) {
        commands.push({
            command: 'set_vocals_enabled',
            payload: { vocals_enabled: true },
        });
    }

    commands.push({
        command: 'set_vocals_volume',
        payload: { vocals_volume: clampedVolume },
    });

    if (clampedVolume === 0 && stageRemoteVocalsEnabled) {
        commands.push({
            command: 'set_vocals_enabled',
            payload: { vocals_enabled: false },
        });
    }

    let sent = false;
    commands.forEach(({ command, payload }) => {
        sent = queueWebSocket.send({
            type: 'stage_command',
            data: {
                command,
                source: 'queue',
                ...payload,
            },
            timestamp: Date.now(),
        }) || sent;
    });

    if (sent) {
        stageRemoteVocalsVolume = clampedVolume;
        if (clampedVolume > 0) {
            stageRemoteVocalsLastVolume = clampedVolume;
            stageRemoteVocalsEnabled = true;
        } else {
            stageRemoteVocalsEnabled = false;
        }
        updateStageRemoteVocalsUi();
    }

    return sent;
}

function toggleStageVocalsEnabled() {
    if (!queueWebSocket) return false;
    if (!canSendStageControl()) return false;
    if (!stageRemoteVocalsAvailable) {
        alert(t('queue.no_vocals_track'));
        return false;
    }

    const nextEnabled = !stageRemoteVocalsEnabled;
    const fallbackVolume = stageRemoteVocalsLastVolume > 0 ? stageRemoteVocalsLastVolume : 1.0;
    const nextVolume = nextEnabled && stageRemoteVocalsVolume <= 0 ? fallbackVolume : stageRemoteVocalsVolume;

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
        return false;
    }

    stageRemoteVocalsEnabled = nextEnabled;
    if (nextEnabled && nextVolume !== stageRemoteVocalsVolume) {
        stageRemoteVocalsVolume = nextVolume;
        if (nextVolume > 0) {
            stageRemoteVocalsLastVolume = nextVolume;
        }
        queueWebSocket.send({
            type: 'stage_command',
            data: {
                command: 'set_vocals_volume',
                source: 'queue',
                vocals_volume: nextVolume,
            },
            timestamp: Date.now(),
        });
    }
    updateStageRemoteVocalsUi();
    return true;
}

if (stageRemoteVocalsToggleBtn) {
    stageRemoteVocalsToggleBtn.addEventListener('click', () => {
        toggleStageVocalsEnabled();
    });
}

if (stageRemoteVocalsVolumeSlider) {
    stageRemoteVocalsVolumeSlider.addEventListener('input', () => {
        const nextVolume = Number(stageRemoteVocalsVolumeSlider.value) / 100;
        const sent = sendStageVocalsVolume(Number.isFinite(nextVolume) ? nextVolume : stageRemoteVocalsVolume);
        if (!sent) {
            updateStageRemoteVocalsUi();
        }
    });
}

// WebSocket event handlers
window.addEventListener('queue_item_added', (event) => {
    if (!upsertQueueItemState(event.detail)) {
        refreshQueue(true);
    }
});

window.addEventListener('queue_item_updated', (event) => {
    if (!upsertQueueItemState(event.detail)) {
        refreshQueue(true);
    }
});

window.addEventListener('queue_item_progress', (event) => {
    if (!patchQueueItemProgressState(event.detail)) {
        refreshQueue(true);
    }
});

window.addEventListener('queue_item_removed', (event) => {
    if (!removeQueueItemState(event.detail?.id)) {
        refreshQueue(true);
    }
});

window.addEventListener('queue_cleared', () => {
    updateQueueState((queue) => queue.filter((item) => item.status === 'playing'));
});

window.addEventListener('current_item_changed', (event) => {
    handleCurrentItemChanged(event.detail);
});

window.addEventListener('queue_item_failed', (event) => {
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
    
    updateQueueState((queue) => queue.map((item) => {
        if (item.id !== Number(id)) {
            return item;
        }
        return {
            ...item,
            status: 'failed',
            error,
            processing_progress: null,
            processing_label: null,
        };
    }));
});

window.addEventListener('stage_state_update', (event) => {
    const isPaused = event.detail?.is_paused;
    if (typeof isPaused === 'boolean') {
        stageRemotePaused = isPaused;
        updateStageRemotePlayPauseUi();
    }
    const currentTime = event.detail?.current_time;
    if (typeof currentTime === 'number' && Number.isFinite(currentTime)) {
        stageRemoteCurrentTime = Math.max(0, currentTime);
    }
    const vocalsEnabled = event.detail?.vocals_enabled;
    if (typeof vocalsEnabled === 'boolean') {
        stageRemoteVocalsEnabled = vocalsEnabled;
    }
    const vocalsVolume = event.detail?.vocals_volume;
    if (typeof vocalsVolume === 'number' && Number.isFinite(vocalsVolume)) {
        stageRemoteVocalsVolume = Math.max(0, Math.min(1, vocalsVolume));
        if (stageRemoteVocalsVolume > 0) {
            stageRemoteVocalsLastVolume = stageRemoteVocalsVolume;
        }
    }
    const lyricsEnabled = event.detail?.lyrics_enabled;
    if (typeof lyricsEnabled === 'boolean') {
        stageRemoteLyricsEnabled = lyricsEnabled;
    }
    updateStageRemoteVocalsUi();
    updateStageRemoteLyricsUi();
    updateStageRemoteSeekForwardUi();
});

window.addEventListener('stage_time_update', (event) => {
    const currentTime = event.detail?.current_time;
    if (typeof currentTime === 'number' && Number.isFinite(currentTime)) {
        stageRemoteCurrentTime = Math.max(0, currentTime);
    }
    const isPaused = event.detail?.is_paused;
    if (typeof isPaused === 'boolean') {
        stageRemotePaused = isPaused;
        updateStageRemotePlayPauseUi();
    }
    updateStageRemoteSeekForwardUi();
});

window.addEventListener('lyrics_settings_ack', (event) => {
    const detail = event.detail || {};
    if (!stageRemoteLyricsApplyPending) {
        return;
    }
    if (detail.stage_id !== stageRemoteLyricsPendingStageId) {
        return;
    }
    if (detail.applied_settings) {
        syncRemoteLyricsControls(detail.applied_settings);
    } else if (detail.size_vw !== undefined || detail.line_width_pct !== undefined || detail.background_media_enabled !== undefined) {
        syncRemoteLyricsControls({
            sizeVw: detail.size_vw,
            lineWidthPct: detail.line_width_pct,
            backgroundMediaEnabled: detail.background_media_enabled,
        });
    }
    const stageName = getRemoteStageDisplayLabel(getSelectedRemoteStage());
    clearRemoteLyricsApplyPending(
        detail.ok
            ? t('queue.stage_lyrics_applied', { name: stageName })
            : (detail.error || t('queue.stage_lyrics_apply_failed'))
    );
});

function startQueueRefresh({ fast = false } = {}) {
    const intervalMs = fast ? 5000 : 15000;
    if (refreshInterval) clearInterval(refreshInterval);
    refreshInterval = setInterval(() => {
        if (document.visibilityState === 'visible') {
            refreshQueue();
            refreshPresenceFallback();
        }
    }, intervalMs);

    if (queueRecoveryTimeout) {
        clearTimeout(queueRecoveryTimeout);
        queueRecoveryTimeout = null;
    }

    if (fast) {
        queueRecoveryTimeout = setTimeout(() => {
            if (!queueWebSocket || !queueWebSocket.isConnected) {
                startQueueRefresh({ fast: false });
            }
        }, 30000);
    }
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
