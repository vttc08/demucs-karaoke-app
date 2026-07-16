const STAGE_CONFIG = window.KaraokeStageConfig || {};
const API_BASE = window.KaraokeURLs.basePath;
const t = window.KaraokeI18n?.t?.bind(window.KaraokeI18n) || ((key, params = {}) => key);
const SERVER_STAGE_QR_URL = STAGE_CONFIG.qrUrl || "";
const STAGE_LOBBY_MEDIA_URL = STAGE_CONFIG.lobbyMediaUrl || null;
const STAGE_QR_STORAGE_KEY = "karaoke.stage.qrDisplay";
const STAGE_DISPLAY_ID_STORAGE_KEY = "karaoke.stage.displayId";
const STAGE_DISPLAY_NAME_STORAGE_KEY = "karaoke.stage.displayName";
const STAGE_IOS_VOCALS_WARNING_STORAGE_KEY = "karaoke.stage.iosVocalsWarningDismissed";
const STAGE_QR_DEFAULT_SIZE = 320;
const STAGE_QR_MIN_SIZE = 128;
const STAGE_QR_MAX_SIZE = 640;
const STAGE_QR_EDGE_PADDING = 24;
const IOS_STAGE_BROWSER = /iPhone|iPad/.test(window.navigator?.userAgent || "");
const INITIAL_CURRENT_ITEM = STAGE_CONFIG.currentItem || null;
let currentItemId = INITIAL_CURRENT_ITEM?.id ?? null;
const video = document.getElementById("stage-video-player");
const primaryAudio = document.getElementById("stage-audio-player");
const vocalsAudio = document.getElementById("stage-vocals-player");
const iosVocalsWarning = document.getElementById("stage-ios-vocals-warning");
const iosVocalsWarningClose = document.getElementById("stage-ios-vocals-warning-close");
const audioHero = document.getElementById("stage-audio-hero");
const audioCoverBg = document.getElementById("stage-audio-cover-bg");
const audioPlaceholder = document.getElementById("stage-audio-placeholder");
const audioCoverImg = document.getElementById("stage-audio-cover-img");
const audioCoverFallback = document.getElementById("stage-audio-cover-fallback");
const nowPlayingTitle = document.getElementById("now-playing-title");
const nowPlayingArtist = document.getElementById("now-playing-artist");
const nowPlayingBadge = document.getElementById("now-playing-badge");
const queuePreview = document.getElementById("queue-preview");
const upNextCount = document.getElementById("up-next-count");
const playPauseBtn = document.getElementById("play-pause-btn");
const playPauseIcon = document.getElementById("play-pause-icon");
const playPauseLabel = document.getElementById("play-pause-label");
const playbarSlider = document.getElementById("stage-playbar-slider");
const playbarElapsed = document.getElementById("stage-playbar-elapsed");
const playbarDuration = document.getElementById("stage-playbar-duration");
const vocalsToggleBtn = document.getElementById("stage-vocals-toggle-btn");
const vocalsToggleIcon = document.getElementById("stage-vocals-toggle-icon");
const vocalsToggleLabel = document.getElementById("stage-vocals-toggle-label");
const vocalsVolumeSlider = document.getElementById("stage-vocals-volume-slider");
const skipBtn = document.getElementById("skip-btn");
const forceResyncBtn = document.getElementById("force-resync-btn");
const lyricsToggleBtn = document.getElementById("lyrics-toggle-btn");
const lyricsToggleIcon = document.getElementById("lyrics-toggle-icon");
const lyricsToggleLabel = document.getElementById("lyrics-toggle-label");
const qrToggleBtn = document.getElementById("qr-toggle-btn");
const qrCloseBtn = document.getElementById("stage-qr-close-btn");
const qrSizeDecreaseBtn = document.getElementById("stage-qr-size-decrease-btn");
const qrSizeIncreaseBtn = document.getElementById("stage-qr-size-increase-btn");
const qrSizeValue = document.getElementById("stage-qr-size-value");
const shortcutsBtn = document.getElementById("stage-shortcuts-btn");
const shortcutsPanel = document.getElementById("stage-shortcuts-panel");
const lyricsSettingsBtn = document.getElementById("stage-lyrics-settings-btn");
const lyricsSettingsPanel = document.getElementById("stage-lyrics-settings-panel");
const lyricsSettingsClose = document.getElementById("stage-lyrics-settings-close");
const lyricsSettingsSave = document.getElementById("stage-lyrics-settings-save");
const lyricsPresetSelect = document.getElementById("stage-lyrics-preset-select");
const lyricsPresetName = document.getElementById("stage-lyrics-preset-name");
const lyricsPresetApply = document.getElementById("stage-lyrics-preset-apply");
const lyricsPresetCreate = document.getElementById("stage-lyrics-preset-create");
const lyricsPresetUpdate = document.getElementById("stage-lyrics-preset-update");
const lyricsPresetDelete = document.getElementById("stage-lyrics-preset-delete");
const stageDisplayNameInput = document.getElementById("stage-display-name");
const fullscreenBtn = document.getElementById("fullscreen-btn");
const fullscreenIcon = document.getElementById("fullscreen-icon");
const qrOverlay = document.getElementById("stage-qr-overlay");
const qrImage = document.getElementById("stage-qr-image");
const stageMedia = document.querySelector(".stage-media");
const stageControls = document.getElementById("stage-controls");
const lyricsOverlay = document.getElementById("stage-lyrics-overlay");
const cdgCanvas = document.getElementById("stage-cdg-canvas");
const lyricsLines = document.getElementById("stage-lyrics-lines");
const zenToggleBtn = document.getElementById("zen-toggle-btn");
const stageLyrics = new window.StageLyricsController({
    overlay: lyricsOverlay,
    lines: lyricsLines,
    button: lyricsSettingsBtn,
    panel: lyricsSettingsPanel,
    closeButton: lyricsSettingsClose,
    resetButton: document.getElementById("stage-lyrics-reset-btn"),
    exportButton: document.getElementById("stage-lyrics-export-btn"),
    applyButton: document.getElementById("stage-lyrics-apply-btn"),
    importButton: document.getElementById("stage-lyrics-import-btn"),
    importExport: document.getElementById("stage-lyrics-settings-json"),
    fileInput: document.getElementById("stage-lyrics-settings-file"),
    status: document.getElementById("stage-lyrics-settings-status"),
    backgroundLayer: document.getElementById("stage-lyrics-background"),
    backgroundImage: document.getElementById("stage-lyrics-background-image"),
    backgroundVideo: document.getElementById("stage-lyrics-background-video"),
    isFullscreenActive,
    t,
    onPanelVisibilityChange: (visible) => {
        if (visible) {
            setShortcutsPanelVisible(false);
            showStageControls();
        } else {
            scheduleHideStageControls();
        }
    },
    inputs: {
        fontPreset: document.getElementById("stage-lyrics-font-preset"),
        customFontFamily: document.getElementById("stage-lyrics-custom-font"),
        customFontWeight: document.getElementById("stage-lyrics-custom-font-weight"),
        sizeVw: document.getElementById("stage-lyrics-size"),
        sizeVwValue: document.getElementById("stage-lyrics-size-value"),
        lineWidthPct: document.getElementById("stage-lyrics-line-width-pct"),
        lineWidthPctValue: document.getElementById("stage-lyrics-line-width-pct-value"),
        lineGapVw: document.getElementById("stage-lyrics-line-gap-vw"),
        lineGapVwValue: document.getElementById("stage-lyrics-line-gap-vw-value"),
        textColor: document.getElementById("stage-lyrics-text-color"),
        activeColor: document.getElementById("stage-lyrics-active-color"),
        outlineColor: document.getElementById("stage-lyrics-outline-color"),
        outlineWidth: document.getElementById("stage-lyrics-outline-width"),
        outlineWidthValue: document.getElementById("stage-lyrics-outline-width-value"),
        previousLines: document.getElementById("stage-lyrics-previous-lines"),
        nextLines: document.getElementById("stage-lyrics-next-lines"),
        lineBehavior: document.getElementById("stage-lyrics-line-behavior"),
        neighborLineScalePct: document.getElementById("stage-lyrics-neighbor-line-scale-pct"),
        neighborLineScalePctValue: document.getElementById("stage-lyrics-neighbor-line-scale-pct-value"),
        neighborLineOpacityPct: document.getElementById("stage-lyrics-neighbor-line-opacity-pct"),
        neighborLineOpacityPctValue: document.getElementById("stage-lyrics-neighbor-line-opacity-pct-value"),
        animation: document.getElementById("stage-lyrics-animation"),
        backgroundMediaEnabled: document.getElementById("stage-lyrics-background-enabled"),
        backgroundMediaPath: document.getElementById("stage-lyrics-background-media"),
        backgroundMediaOpacityPct: document.getElementById("stage-lyrics-background-opacity-pct"),
        backgroundMediaOpacityPctValue: document.getElementById("stage-lyrics-background-opacity-pct-value"),
    },
    customFontFields: Array.from(document.querySelectorAll(".stage-lyrics-custom-font-field")),
});
const stageCdg = new window.StageCdgRenderer(cdgCanvas);

if (lyricsSettingsSave) {
    lyricsSettingsSave.addEventListener("click", () => {
        stageLyrics.persistSettings();
        stageLyrics.setSettingsPanelVisible(false);
    });
}
const LYRICS_PRESETS_API = window.KaraokeURLs.appUrl("/api/lyrics-presets/");
let lyricsPresets = [];

function getSelectedLyricsPreset() {
    return lyricsPresets.find((preset) => String(preset.id) === String(lyricsPresetSelect?.value || "")) || null;
}

function setLyricsPresetControlsState() {
    const hasSelection = Boolean(getSelectedLyricsPreset());
    const hasName = Boolean(lyricsPresetName?.value.trim());

    if (lyricsPresetApply) {
        lyricsPresetApply.disabled = !hasSelection;
    }
    if (lyricsPresetDelete) {
        lyricsPresetDelete.disabled = !hasSelection;
    }
    if (lyricsPresetUpdate) {
        lyricsPresetUpdate.disabled = !hasSelection;
    }
    if (lyricsPresetCreate) {
        lyricsPresetCreate.disabled = !hasName;
    }
}

function renderLyricsPresetOptions(selectedId = "") {
    if (!lyricsPresetSelect) {
        return;
    }

    const currentValue = selectedId || lyricsPresetSelect.value || "";
    lyricsPresetSelect.innerHTML = "";

    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = t("stage.lyrics_presets_empty");
    lyricsPresetSelect.appendChild(emptyOption);

    lyricsPresets.forEach((preset) => {
        const option = document.createElement("option");
        option.value = String(preset.id);
        option.textContent = preset.name;
        lyricsPresetSelect.appendChild(option);
    });

    lyricsPresetSelect.value = currentValue;
    if (!lyricsPresetSelect.value) {
        lyricsPresetSelect.selectedIndex = 0;
    }
    setLyricsPresetControlsState();
}

async function loadLyricsPresets(selectedId = "") {
    if (!lyricsPresetSelect) {
        return;
    }

    try {
        const response = await fetch(LYRICS_PRESETS_API, { credentials: "same-origin" });
        if (!response.ok) {
            throw new Error(`Failed to load presets (${response.status})`);
        }
        lyricsPresets = await response.json();
        renderLyricsPresetOptions(selectedId);
    } catch (error) {
        lyricsPresets = [];
        renderLyricsPresetOptions();
        stageLyrics.setStatus(t("stage.lyrics_presets_load_failed"));
    }
}

function syncPresetNameFromSelection() {
    const selected = getSelectedLyricsPreset();
    if (lyricsPresetName && selected) {
        lyricsPresetName.value = selected.name;
    }
    setLyricsPresetControlsState();
}

async function applySelectedLyricsPreset() {
    const selected = getSelectedLyricsPreset();
    if (!selected) {
        return;
    }

    try {
        const response = await fetch(window.KaraokeURLs.appUrl(`/api/lyrics-presets/${selected.id}`), {
            credentials: "same-origin",
        });
        if (!response.ok) {
            throw new Error(`Failed to load preset (${response.status})`);
        }
        const preset = await response.json();
        stageLyrics.applySettingsObject(preset.settings, { persist: true });
        if (lyricsPresetName) {
            lyricsPresetName.value = preset.name;
        }
        stageLyrics.setStatus(t("stage.lyrics_presets_applied", { name: preset.name }));
    } catch (error) {
        stageLyrics.setStatus(t("stage.lyrics_presets_apply_failed"));
    }
}

function sendLyricsSettingsAck(ok, payload = {}) {
    sendStageCommandRaw({
        type: "lyrics_settings_ack",
        data: {
            stage_id: getStageDisplayId(),
            ok: Boolean(ok),
            ...payload,
        },
        timestamp: Date.now(),
    });
}

async function applyRemoteLyricsSettings(payload) {
    const presetId = Number.isInteger(payload?.preset_id) ? payload.preset_id : null;
    const allowOverride = payload?.override !== false;
    const backgroundMediaEnabled = typeof payload?.background_media_enabled === "boolean"
        ? payload.background_media_enabled
        : null;
    try {
        if (typeof payload?.lyrics_enabled === "boolean") {
            setLyricsEnabled(payload.lyrics_enabled);
        }

        let nextSettings = null;
        if (presetId) {
            const response = await fetch(window.KaraokeURLs.appUrl(`/api/lyrics-presets/${presetId}`), {
                credentials: "same-origin",
            });
            if (!response.ok) {
                throw new Error(`Failed to load preset (${response.status})`);
            }
            const preset = await response.json();
            nextSettings = allowOverride
                ? {
                    ...stageLyrics.getSettingsSnapshot(),
                    ...preset.settings,
                }
                : {
                    ...preset.settings,
                };
        }

        if (allowOverride) {
            if (typeof payload?.size_vw === "number" && Number.isFinite(payload.size_vw)) {
                nextSettings = nextSettings || stageLyrics.getSettingsSnapshot();
                nextSettings.sizeVw = payload.size_vw;
            }
            if (typeof payload?.line_width_pct === "number" && Number.isFinite(payload.line_width_pct)) {
                nextSettings = nextSettings || stageLyrics.getSettingsSnapshot();
                nextSettings.lineWidthPct = payload.line_width_pct;
            }
        }
        if (backgroundMediaEnabled !== null) {
            nextSettings = nextSettings || stageLyrics.getSettingsSnapshot();
            nextSettings.backgroundMediaEnabled = backgroundMediaEnabled;
        }

        if (nextSettings) {
            stageLyrics.applySettingsObject(nextSettings, { persist: true });
        }
        sendLyricsSettingsAck(true, {
            preset_id: presetId,
            override: allowOverride,
            size_vw: nextSettings?.sizeVw,
            line_width_pct: nextSettings?.lineWidthPct,
            background_media_enabled: nextSettings?.backgroundMediaEnabled,
            applied_settings: nextSettings ? {
                sizeVw: nextSettings.sizeVw,
                lineWidthPct: nextSettings.lineWidthPct,
                backgroundMediaEnabled: nextSettings.backgroundMediaEnabled,
            } : null,
        });
        stageLyrics.setStatus(t("stage.lyrics_remote_settings_applied"));
    } catch (error) {
        console.warn("Failed to apply remote lyrics settings:", error);
        sendLyricsSettingsAck(false, {
            preset_id: presetId,
            override: allowOverride,
            error: t("stage.lyrics_remote_settings_failed"),
        });
        stageLyrics.setStatus(t("stage.lyrics_remote_settings_failed"));
    }
}

async function createLyricsPreset() {
    const name = lyricsPresetName?.value.trim();
    if (!name) {
        stageLyrics.setStatus(t("stage.lyrics_preset_name_required"));
        return;
    }

    try {
        const response = await fetch(LYRICS_PRESETS_API, {
            method: "POST",
            credentials: "same-origin",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                name,
                settings: stageLyrics.getSettingsSnapshot(),
            }),
        });
        if (!response.ok) {
            throw new Error(`Failed to create preset (${response.status})`);
        }
        const preset = await response.json();
        lyricsPresets = lyricsPresets.filter((item) => String(item.id) !== String(preset.id));
        lyricsPresets.push(preset);
        lyricsPresets.sort((a, b) => a.name.localeCompare(b.name));
        renderLyricsPresetOptions(String(preset.id));
        if (lyricsPresetName) {
            lyricsPresetName.value = preset.name;
        }
        stageLyrics.setStatus(t("stage.lyrics_preset_created", { name: preset.name }));
    } catch (error) {
        stageLyrics.setStatus(t("stage.lyrics_preset_create_failed"));
    }
}

async function updateSelectedLyricsPreset() {
    const selected = getSelectedLyricsPreset();
    if (!selected) {
        return;
    }

    const name = lyricsPresetName?.value.trim() || selected.name;
    try {
        const response = await fetch(window.KaraokeURLs.appUrl(`/api/lyrics-presets/${selected.id}`), {
            method: "PATCH",
            credentials: "same-origin",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                name,
                settings: stageLyrics.getSettingsSnapshot(),
            }),
        });
        if (!response.ok) {
            throw new Error(`Failed to update preset (${response.status})`);
        }
        const preset = await response.json();
        lyricsPresets = lyricsPresets.filter((item) => String(item.id) !== String(preset.id));
        lyricsPresets.push(preset);
        lyricsPresets.sort((a, b) => a.name.localeCompare(b.name));
        renderLyricsPresetOptions(String(preset.id));
        if (lyricsPresetName) {
            lyricsPresetName.value = preset.name;
        }
        stageLyrics.setStatus(t("stage.lyrics_preset_updated", { name: preset.name }));
    } catch (error) {
        stageLyrics.setStatus(t("stage.lyrics_preset_update_failed"));
    }
}

async function deleteSelectedLyricsPreset() {
    const selected = getSelectedLyricsPreset();
    if (!selected) {
        return;
    }
    const confirmed = window.confirm(t("stage.lyrics_preset_delete_confirm", { name: selected.name }));
    if (!confirmed) {
        return;
    }

    try {
        const response = await fetch(window.KaraokeURLs.appUrl(`/api/lyrics-presets/${selected.id}`), {
            method: "DELETE",
            credentials: "same-origin",
        });
        if (!response.ok) {
            throw new Error(`Failed to delete preset (${response.status})`);
        }
        lyricsPresets = lyricsPresets.filter((item) => String(item.id) !== String(selected.id));
        renderLyricsPresetOptions("");
        if (lyricsPresetName) {
            lyricsPresetName.value = "";
        }
        stageLyrics.setStatus(t("stage.lyrics_preset_deleted", { name: selected.name }));
    } catch (error) {
        stageLyrics.setStatus(t("stage.lyrics_preset_delete_failed"));
    }
}

lyricsPresetSelect?.addEventListener("change", syncPresetNameFromSelection);
lyricsPresetName?.addEventListener("input", setLyricsPresetControlsState);
lyricsPresetApply?.addEventListener("click", () => {
    void applySelectedLyricsPreset();
});
lyricsPresetCreate?.addEventListener("click", () => {
    void createLyricsPreset();
});
lyricsPresetUpdate?.addEventListener("click", () => {
    void updateSelectedLyricsPreset();
});
lyricsPresetDelete?.addEventListener("click", () => {
    void deleteSelectedLyricsPreset();
});
if (stageDisplayNameInput) {
    syncStageDisplayNameInput();
    stageDisplayNameInput.addEventListener("input", scheduleStageDisplayNameUpdate);
    stageDisplayNameInput.addEventListener("blur", () => {
        window.clearTimeout(stageDisplayNameUpdateTimer);
        const normalized = persistStageDisplayName(stageDisplayNameInput.value);
        stageDisplayNameInput.value = normalized;
        sendStagePresenceHello();
    });
}
void loadLyricsPresets();
const QR_CODE_ENDPOINT = window.KaraokeURLs.appUrl('/api/qr');
const STAGE_VOCALS_VOLUME_DEFAULT = Number(STAGE_CONFIG.vocalsVolumeDefault ?? 1);
const normalizedStageVocalsVolumeDefault = Number.isFinite(Number(STAGE_VOCALS_VOLUME_DEFAULT))
    ? Math.max(0, Math.min(1, Number(STAGE_VOCALS_VOLUME_DEFAULT)))
    : 1.0;
let controlsHideTimer = null;
let zenModeEnabled = false;
let isQrVisible = false;
let shortcutsPanelVisible = false;
let qrDragState = null;
let stageSocket = null;
let stageReconnectTimer = null;
let stageReconnectAttempts = 0;
let stageReconnectDelayMs = 1000;
let stageShouldReconnect = true;
let stageSocketLastMessageAt = 0;
let stageSocketLastPingAt = 0;
let mixState = {
    vocals_enabled: true,
    vocals_volume: normalizedStageVocalsVolumeDefault,
};
let lyricsState = {
    enabled: true,
    available: false,
};
let vocalsAvailable = Boolean(INITIAL_CURRENT_ITEM.vocals_path);
let vocalsPlaybackSupported = vocalsAvailable && !IOS_STAGE_BROWSER;
let audioContext = null;
let vocalsSourceNode = null;
let vocalsGainNode = null;
let syncTimer = null;
let suppressSeekBroadcast = false;
let seekBroadcastUnlockTimer = null;
let lyricsAnimationFrame = null;
let lyricsLoadRequestId = 0;
let syncOperationId = 0;
let lastHandledSyncVersion = 0;
let hardSyncInProgress = false;
let initialMultitrackResyncCompleted = !canPlayGuideVocals();
let currentPrimaryKind = null;
let currentPrimarySrc = null;
let currentLyricsKind = null;
let currentLyricsSrc = "";
let currentItem = INITIAL_CURRENT_ITEM;
let lastPlaybackStateBroadcastAt = 0;
let stageClockEnabled = false;
let isPlaybarScrubbing = false;
let playbarPreviewTime = 0;
let stageDisplayNameUpdateTimer = null;
const SOFT_DRIFT_THRESHOLD_SECONDS = 0.12;
const PLAYBACK_CLOCK_BROADCAST_INTERVAL_MS = 1000;
const MEDIA_SEEK_TIMEOUT_MS = 1200;
const MEDIA_READY_TIMEOUT_MS = 1200;
const MEDIA_METADATA_TIMEOUT_MS = 1500;
let hasCurrentQueueItem = Boolean(currentItemId);
const AUDIO_EXTENSIONS = new Set([".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus"]);

function safeReload() {
    window.location.reload();
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text || "";
    return div.innerHTML;
}

function normalizeStageDisplayName(value) {
    return String(value || "").replace(/\s+/g, " ").trim().slice(0, 80);
}

const LEGACY_STAGE_DISPLAY_DEFAULTS = new Set([
    "Stage Display",
    "舞台显示",
]);

function ensureStageDisplayId() {
    try {
        const stored = window.localStorage?.getItem(STAGE_DISPLAY_ID_STORAGE_KEY);
        if (stored && /^[a-zA-Z0-9._:-]{8,120}$/.test(stored)) {
            return stored;
        }
        const nextId = window.crypto?.randomUUID
            ? window.crypto.randomUUID()
            : `stage-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
        window.localStorage?.setItem(STAGE_DISPLAY_ID_STORAGE_KEY, nextId);
        return nextId;
    } catch (_) {
        return `stage-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
    }
}

function getStageDisplayId() {
    return ensureStageDisplayId();
}

function getStageDisplayIdSuffix() {
    const compact = String(getStageDisplayId() || "").replace(/[^a-zA-Z0-9]/g, "");
    return compact.slice(-4) || "0000";
}

function getStageScreenLabel() {
    const width = Number(window.screen?.width);
    const height = Number(window.screen?.height);
    if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
        return "";
    }
    const shortSide = Math.min(width, height);
    const longSide = Math.max(width, height);
    return `${shortSide}x${longSide}`;
}

function getStagePlatformLabel() {
    const platformSource = String(
        window.navigator?.userAgentData?.platform
        || window.navigator?.platform
        || window.navigator?.userAgent
        || ""
    ).toLowerCase();
    const userAgent = String(window.navigator?.userAgent || "").toLowerCase();

    if (userAgent.includes("iphone")) return "iPhone";
    if (userAgent.includes("ipad")) return "iPad";
    if (userAgent.includes("android")) {
        return userAgent.includes("mobile") ? "Android Phone" : "Android Tablet";
    }
    if (platformSource.includes("mac")) return "Mac";
    if (platformSource.includes("win")) return "Windows";
    if (platformSource.includes("cros")) return "ChromeOS";
    if (platformSource.includes("linux")) return "Linux";
    if (userAgent.includes("smart-tv") || userAgent.includes("smarttv") || userAgent.includes("hbbtv")) return "TV";
    return "Stage";
}

function getDefaultStageDisplayName() {
    const parts = [getStagePlatformLabel()];
    const screenLabel = getStageScreenLabel();
    if (screenLabel) {
        parts.push(screenLabel);
    }
    parts.push(getStageDisplayIdSuffix());
    return normalizeStageDisplayName(parts.join(" "));
}

function getStoredCustomStageDisplayName() {
    try {
        const normalized = normalizeStageDisplayName(window.localStorage?.getItem(STAGE_DISPLAY_NAME_STORAGE_KEY));
        if (!normalized || LEGACY_STAGE_DISPLAY_DEFAULTS.has(normalized)) {
            return null;
        }
        return normalized;
    } catch (_) {
        return null;
    }
}

function getStageDisplayName() {
    return getStoredCustomStageDisplayName() || getDefaultStageDisplayName();
}

function persistStageDisplayName(name) {
    const normalized = normalizeStageDisplayName(name);
    try {
        if (!normalized || LEGACY_STAGE_DISPLAY_DEFAULTS.has(normalized)) {
            window.localStorage?.removeItem(STAGE_DISPLAY_NAME_STORAGE_KEY);
            return getDefaultStageDisplayName();
        }
        window.localStorage?.setItem(STAGE_DISPLAY_NAME_STORAGE_KEY, normalized);
    } catch (_) {
        // Local display names are best-effort only.
    }
    return normalized || getDefaultStageDisplayName();
}

function syncStageDisplayNameInput() {
    if (stageDisplayNameInput) {
        stageDisplayNameInput.value = getStageDisplayName();
    }
}

function sendStagePresenceHello() {
    return sendStageCommandRaw({
        type: "stage_presence_hello",
        data: {
            stage_id: getStageDisplayId(),
            stage_name: getStageDisplayName(),
        },
        timestamp: Date.now(),
    });
}

function scheduleStageDisplayNameUpdate() {
    if (!stageDisplayNameInput) {
        return;
    }
    window.clearTimeout(stageDisplayNameUpdateTimer);
    stageDisplayNameUpdateTimer = window.setTimeout(() => {
        const normalized = persistStageDisplayName(stageDisplayNameInput.value);
        stageDisplayNameInput.value = normalized;
        sendStagePresenceHello();
    }, 350);
}

function mediaExtensionFromSrc(src) {
    if (!src) {
        return "";
    }
    try {
        const url = new URL(src, window.location.href);
        const path = url.pathname.toLowerCase();
        return path.includes(".") ? `.${path.split(".").pop()}` : "";
    } catch (_) {
        const normalized = String(src).split("?")[0].toLowerCase();
        return normalized.includes(".") ? `.${normalized.split(".").pop()}` : "";
    }
}

function mediaKindFromItem(item) {
    if (!item?.media_path || !item?.id) {
        return "video";
    }
    return AUDIO_EXTENSIONS.has(mediaExtensionFromSrc(item.media_path)) ? "audio" : "video";
}

function lyricsKindFromPath(path) {
    return mediaExtensionFromSrc(path) === ".cdg" ? "cdg" : "text";
}

function hasLyricsSource(item) {
    return Boolean(item?.lyrics_path);
}

function syncLyricsRendererVisibility() {
    const isCdg = currentLyricsKind === "cdg";
    lyricsOverlay?.classList.toggle("stage-lyrics-overlay--cdg", isCdg);
    cdgCanvas?.classList.toggle("hidden", !isCdg);
    lyricsLines?.classList.toggle("hidden", isCdg);
}

function clearLyricsRenderers() {
    stageCdg.setEnabled(false);
    stageLyrics.setEnabled(false);
    stageLyrics.clearCues();
    stageCdg.clear();
    syncLyricsRendererVisibility();
    setLyricsOverlayVisible(false);
}

function setActiveLyricsRendererEnabled(enabled) {
    const shouldEnable = Boolean(enabled);
    if (currentLyricsKind === "cdg") {
        stageCdg.setEnabled(shouldEnable);
        stageLyrics.setEnabled(false);
        syncLyricsRendererVisibility();
        setLyricsOverlayVisible(shouldEnable);
        return;
    }

    stageCdg.setEnabled(false);
    stageLyrics.setEnabled(shouldEnable);
    syncLyricsRendererVisibility();
}

function getPrimaryPlayer() {
    return currentPrimaryKind === "audio" ? primaryAudio : video;
}

function getPrimaryCurrentTime() {
    const primary = getPrimaryPlayer();
    return primary ? (primary.currentTime || 0) : 0;
}

function getPrimaryDuration() {
    const primary = getPrimaryPlayer();
    const duration = primary ? primary.duration : null;
    return Number.isFinite(duration) && duration > 0 ? duration : 0;
}

function isPrimaryPaused() {
    const primary = getPrimaryPlayer();
    return primary ? primary.paused : true;
}

async function playPrimary() {
    const primary = getPrimaryPlayer();
    if (!primary) {
        return;
    }
    await primary.play();
}

function pausePrimary() {
    const primary = getPrimaryPlayer();
    if (!primary) {
        return;
    }
    primary.pause();
}

function formatPlaybackTime(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) {
        return "--:--";
    }
    const totalSeconds = Math.floor(seconds);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const secs = totalSeconds % 60;
    if (hours > 0) {
        return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
    }
    return `${minutes}:${String(secs).padStart(2, "0")}`;
}

function updatePlaybarUi(currentTime = getPrimaryCurrentTime()) {
    if (!playbarSlider || !playbarElapsed || !playbarDuration) {
        return;
    }

    const duration = getPrimaryDuration();
    const hasDuration = duration > 0;
    const effectiveTime = isPlaybarScrubbing ? playbarPreviewTime : currentTime;
    const clampedTime = hasDuration
        ? Math.max(0, Math.min(Number.isFinite(effectiveTime) ? effectiveTime : 0, duration))
        : 0;

    playbarSlider.disabled = !hasDuration || hardSyncInProgress;
    playbarSlider.max = hasDuration ? String(duration) : "0";
    playbarSlider.value = hasDuration ? String(clampedTime) : "0";
    playbarSlider.setAttribute("aria-valuetext", hasDuration
        ? `${formatPlaybackTime(clampedTime)} / ${formatPlaybackTime(duration)}`
        : formatPlaybackTime(0));

    playbarElapsed.textContent = formatPlaybackTime(clampedTime);
    playbarDuration.textContent = formatPlaybackTime(hasDuration ? duration : 0);
}

async function commitPlaybarSeek() {
    if (!playbarSlider) {
        return;
    }
    const duration = getPrimaryDuration();
    const nextTime = Number(playbarSlider.value);
    const targetTime = duration > 0 && Number.isFinite(nextTime)
        ? Math.max(0, Math.min(nextTime, duration))
        : 0;

    isPlaybarScrubbing = false;
    playbarPreviewTime = targetTime;
    updatePlaybarUi(targetTime);

    if (duration <= 0 || hardSyncInProgress) {
        return;
    }

    const shouldPausePlayback = isPrimaryPaused();
    if (!sendStageCommand("seek", { seek_time: targetTime, is_paused: shouldPausePlayback })) {
        await seekAndResyncPlayback(targetTime, shouldPausePlayback);
    }
}

async function seekByOffset(offsetSeconds) {
    const primary = getPrimaryPlayer();
    if (!primary) {
        return;
    }
    const duration = getPrimaryDuration();
    const currentTime = getPrimaryCurrentTime();
    const nextTime = Math.max(0, currentTime + offsetSeconds);
    const targetTime = duration > 0 ? Math.min(nextTime, duration) : nextTime;
    const shouldPausePlayback = isPrimaryPaused();

    updatePlaybarUi(targetTime);

    if (!sendStageCommand("seek", { seek_time: targetTime, is_paused: shouldPausePlayback })) {
        await seekAndResyncPlayback(targetTime, shouldPausePlayback);
    }
}

function updateAudioArtwork(item) {
    const thumbnail = item?.thumbnail || "";
    const hasThumbnail = Boolean(thumbnail);

    if (audioHero) {
        audioHero.classList.toggle("hidden", currentPrimaryKind !== "audio");
    }
    if (audioCoverBg) {
        audioCoverBg.style.backgroundImage = hasThumbnail ? `url("${thumbnail}")` : "";
        audioCoverBg.classList.toggle("is-visible", hasThumbnail);
    }
    if (audioPlaceholder) {
        audioPlaceholder.classList.toggle("is-visible", !hasThumbnail);
    }
    if (audioCoverImg) {
        audioCoverImg.src = hasThumbnail ? thumbnail : "";
        audioCoverImg.classList.toggle("hidden", !hasThumbnail);
    }
    if (audioCoverFallback) {
        audioCoverFallback.classList.toggle("hidden", hasThumbnail);
    }
    if (video) {
        video.classList.toggle("hidden", currentPrimaryKind === "audio");
        video.classList.toggle("block", currentPrimaryKind !== "audio");
    }
}

function loadIosVocalsWarningDismissed() {
    try {
        return window.localStorage?.getItem(STAGE_IOS_VOCALS_WARNING_STORAGE_KEY) === "1";
    } catch (_) {
        return false;
    }
}

let iosVocalsWarningDismissed = loadIosVocalsWarningDismissed();

function setIosVocalsWarningVisible(visible) {
    if (!iosVocalsWarning) {
        return;
    }
    iosVocalsWarning.classList.toggle("hidden", !visible);
}

function updateIosVocalsWarning() {
    const shouldWarn = IOS_STAGE_BROWSER && vocalsAvailable && !iosVocalsWarningDismissed;
    setIosVocalsWarningVisible(shouldWarn);
}

function dismissIosVocalsWarning() {
    iosVocalsWarningDismissed = true;
    try {
        window.localStorage?.setItem(STAGE_IOS_VOCALS_WARNING_STORAGE_KEY, "1");
    } catch (_) {
        // Local dismissal is best-effort only.
    }
    setIosVocalsWarningVisible(false);
}

function canPlayGuideVocals() {
    return vocalsAvailable && vocalsPlaybackSupported;
}

function updateLyricsUi() {
    if (!lyricsToggleBtn || !lyricsToggleLabel || !lyricsToggleIcon) return;
    const connected = !!stageSocket && stageSocket.readyState === WebSocket.OPEN;
    const label = lyricsState.available
        ? (lyricsState.enabled ? t("stage.lyrics_on") : t("stage.lyrics_off"))
        : t("stage.no_lyrics");
    lyricsToggleBtn.disabled = !lyricsState.available || !connected;
    lyricsToggleBtn.setAttribute("aria-pressed", lyricsState.available && lyricsState.enabled ? "true" : "false");
    lyricsToggleBtn.setAttribute("aria-label", label);
    lyricsToggleBtn.setAttribute("title", label);
    lyricsToggleIcon.textContent = lyricsState.available && lyricsState.enabled ? "subtitles" : "subtitles_off";
    lyricsToggleLabel.textContent = label;
}

function setLyricsOverlayVisible(visible) {
    stageLyrics.setOverlayVisible(visible);
}

function setLyricsEnabled(enabled) {
    lyricsState.enabled = Boolean(enabled);
    const shouldRenderLyrics = lyricsState.available && lyricsState.enabled;
    setActiveLyricsRendererEnabled(shouldRenderLyrics);
    updateLyricsUi();
    if (shouldRenderLyrics) {
        updateLyricsForTime(getPrimaryCurrentTime());
    } else {
        setLyricsOverlayVisible(false);
    }
}

function setBackgroundMediaEnabled(enabled) {
    stageLyrics.applySettingsObject({
        ...stageLyrics.getSettingsSnapshot(),
        backgroundMediaEnabled: Boolean(enabled),
    }, { persist: true });
}

function updateLyricsForTime(currentTime) {
    if (currentLyricsKind === "cdg") {
        stageCdg.updateForTime(currentTime);
        return;
    }
    stageLyrics.updateForTime(currentTime);
}

function startLyricsTicker() {
    const primary = getPrimaryPlayer();
    if (!primary || lyricsAnimationFrame !== null) {
        return;
    }

    const tick = () => {
        const activePrimary = getPrimaryPlayer();
        updateLyricsForTime(activePrimary ? (activePrimary.currentTime || 0) : 0);
        if (activePrimary && !activePrimary.paused) {
            lyricsAnimationFrame = window.requestAnimationFrame(tick);
        } else {
            lyricsAnimationFrame = null;
        }
    };

    lyricsAnimationFrame = window.requestAnimationFrame(tick);
}

function stopLyricsTicker() {
    if (lyricsAnimationFrame === null) {
        return;
    }
    window.cancelAnimationFrame(lyricsAnimationFrame);
    lyricsAnimationFrame = null;
}

async function loadLyricsCues() {
    if (!currentItemId) {
        lyricsLoadRequestId += 1;
        currentLyricsKind = null;
        currentLyricsSrc = "";
        clearLyricsRenderers();
        lyricsState.available = false;
        setActiveLyricsRendererEnabled(false);
        updateLyricsUi();
        syncStageBackgroundEligibility();
        return;
    }

    const requestId = ++lyricsLoadRequestId;
    const itemId = currentItemId;
    currentLyricsSrc = currentItem?.lyrics_path || currentLyricsSrc || "";
    currentLyricsKind = currentLyricsSrc ? lyricsKindFromPath(currentLyricsSrc) : null;
    syncLyricsRendererVisibility();

    try {
        if (currentLyricsKind === "cdg") {
            const loaded = await stageCdg.load(currentLyricsSrc);
            if (requestId !== lyricsLoadRequestId || currentItemId !== itemId) {
                return;
            }
            stageLyrics.clearCues();
            lyricsState.available = loaded && stageCdg.hasContent();
            setActiveLyricsRendererEnabled(lyricsState.available && lyricsState.enabled);
            updateLyricsUi();
            syncStageBackgroundEligibility();
            updateLyricsForTime(getPrimaryCurrentTime());
            return;
        }

        const response = await fetch(window.KaraokeURLs.appUrl(`/api/queue/${itemId}/lyrics-cues`));
        if (requestId !== lyricsLoadRequestId || currentItemId !== itemId) {
            return;
        }
        if (!response.ok) {
            clearLyricsRenderers();
            lyricsState.available = false;
            setActiveLyricsRendererEnabled(false);
            updateLyricsUi();
            syncStageBackgroundEligibility();
            return;
        }

        const payload = await response.json();
        if (requestId !== lyricsLoadRequestId || currentItemId !== itemId) {
            return;
        }
        const cues = Array.isArray(payload?.cues) ? payload.cues : [];
        stageLyrics.setCues(cues);
        stageCdg.clear();
        lyricsState.available = stageLyrics.hasCues();
        setActiveLyricsRendererEnabled(lyricsState.available && lyricsState.enabled);
        updateLyricsUi();
        syncStageBackgroundEligibility();
        updateLyricsForTime(getPrimaryCurrentTime());
    } catch (error) {
        if (requestId !== lyricsLoadRequestId || currentItemId !== itemId) {
            return;
        }
        console.warn("Failed to load lyrics cues:", error);
        clearLyricsRenderers();
        lyricsState.available = false;
        setActiveLyricsRendererEnabled(false);
        updateLyricsUi();
        syncStageBackgroundEligibility();
    }
}

function updateNowPlayingMeta(item) {
    if (!nowPlayingTitle || !nowPlayingArtist || !nowPlayingBadge) {
        return;
    }
    if (!item || !item.id) {
        nowPlayingTitle.textContent = t("stage.lobby_title");
        nowPlayingArtist.textContent = t("stage.lobby_artist");
        nowPlayingBadge.textContent = t("stage.lobby_badge");
        return;
    }
    nowPlayingTitle.textContent = item.title || t("stage.lobby_title");
    nowPlayingArtist.textContent = item.artist || t("stage.lobby_artist");
    nowPlayingBadge.textContent = item.is_karaoke ? t("app.karaoke") : t("app.original");
}

function syncStageBackgroundEligibility() {
    stageLyrics.setBackgroundEligible(Boolean(hasCurrentQueueItem && lyricsState.available));
}

function updatePlaybackModeFlags(item) {
    hasCurrentQueueItem = Boolean(item && item.id);
    syncStageBackgroundEligibility();
    if (video) {
        video.loop = !hasCurrentQueueItem;
    }
    if (primaryAudio) {
        primaryAudio.loop = !hasCurrentQueueItem;
    }
    if (skipBtn) {
        skipBtn.disabled = !hasCurrentQueueItem;
    }
}

function setAudioSource(mediaElement, src) {
    if (!mediaElement) return;
    const source = mediaElement.querySelector("source");
    if (source) {
        source.setAttribute("src", src || "");
    } else {
        mediaElement.src = src || "";
    }
}

function resetSyncStateForSourceSwap() {
    syncOperationId += 1;
    hardSyncInProgress = false;
    stopSyncTimer();
    stopLyricsTicker();
    suppressSeekBroadcast = false;
    if (seekBroadcastUnlockTimer) {
        window.clearTimeout(seekBroadcastUnlockTimer);
        seekBroadcastUnlockTimer = null;
    }
}

async function applyCurrentPlaybackItem(item) {
    if (!video && !primaryAudio) return;
    const nextMediaSrc = item?.media_path || STAGE_LOBBY_MEDIA_URL;
    if (!nextMediaSrc) return;
    const nextVocalsSrc = item?.vocals_path || "";
    const nextItemId = item?.id ?? null;
    const nextMediaKind = mediaKindFromItem(item);
    const sourceChanged = currentItemId !== nextItemId || currentPrimaryKind !== nextMediaKind || currentPrimarySrc !== nextMediaSrc;
    currentItem = item || null;
    currentItemId = nextItemId;
    currentPrimaryKind = nextMediaKind;
    currentPrimarySrc = nextMediaSrc;
    lyricsState.available = false;
    updatePlaybackModeFlags(item);
    updateNowPlayingMeta(item);
    updateAudioArtwork(item);
    updatePlaybarUi(0);
    vocalsAvailable = Boolean(nextVocalsSrc);
    vocalsPlaybackSupported = vocalsAvailable && !IOS_STAGE_BROWSER;
    currentLyricsKind = item?.lyrics_path ? lyricsKindFromPath(item.lyrics_path) : null;
    currentLyricsSrc = item?.lyrics_path || "";
    syncLyricsRendererVisibility();
    if (!sourceChanged) {
        updateIosVocalsWarning();
        updateVocalsUi();
        await loadLyricsCues();
        updatePlaybarUi();
        return;
    }
    resetSyncStateForSourceSwap();
    clearLyricsRenderers();
    if (vocalsAudio) {
        vocalsAudio.pause();
        vocalsAudio.currentTime = 0;
        setAudioSource(vocalsAudio, vocalsPlaybackSupported ? nextVocalsSrc : "");
    }
    video.pause();
    if (primaryAudio) {
        primaryAudio.pause();
        primaryAudio.currentTime = 0;
    }
    if (nextMediaKind === "audio") {
        setAudioSource(video, "");
        if (primaryAudio) {
            setAudioSource(primaryAudio, nextMediaSrc);
            primaryAudio.load();
        }
    } else {
        setAudioSource(video, nextMediaSrc);
        if (primaryAudio) {
            setAudioSource(primaryAudio, "");
            primaryAudio.load();
        }
    }
    video.load();
    if (vocalsAudio) {
        vocalsAudio.load();
    }
    initialMultitrackResyncCompleted = !canPlayGuideVocals();
    updateIosVocalsWarning();
    updateVocalsUi();
    await loadLyricsCues();
    try {
        await ensureAudioGraph();
        await playPrimary();
        if (canPlayGuideVocals()) {
            syncVocalsToVideo(true);
            startSyncTimer();
        } else if (vocalsAudio) {
            vocalsAudio.pause();
            vocalsAudio.currentTime = 0;
        }
        startLyricsTicker();
    } catch (error) {
        console.warn("Failed to start switched playback source:", error);
    } finally {
        updatePlayPauseUi();
        updatePlaybarUi();
        showStageControls();
    }
}

async function refreshStageState() {
    const [currentResponse, queueResponse] = await Promise.all([
        fetch(window.KaraokeURLs.appUrl("/api/queue/current")),
        fetch(window.KaraokeURLs.appUrl("/api/queue/")),
    ]);
    const currentItem = currentResponse.ok ? await currentResponse.json() : null;
    if (queueResponse.ok) {
        const queue = await queueResponse.json();
        renderQueuePreview(queue);
    }
    await applyCurrentPlaybackItem(currentItem);
}

function updatePlayPauseUi() {
    if (!playPauseIcon || !playPauseLabel) return;
    const isPaused = isPrimaryPaused();
    const label = isPaused ? t("common.play") : t("stage.pause");
    playPauseIcon.textContent = isPaused ? "play_arrow" : "pause";
    playPauseLabel.textContent = label;
    if (playPauseBtn) {
        playPauseBtn.setAttribute("aria-label", label);
        playPauseBtn.setAttribute("title", label);
    }
}

function updateVocalsUi() {
    if (!vocalsToggleBtn || !vocalsToggleLabel || !vocalsVolumeSlider) return;
    const hasVocalsTrack = vocalsAvailable;
    const supported = canPlayGuideVocals();
    const label = !hasVocalsTrack
        ? t("stage.vocals_off")
        : supported
        ? (mixState.vocals_enabled ? t("stage.vocals_on") : t("stage.vocals_off"))
        : t("stage.vocals_unsupported");
    vocalsToggleBtn.disabled = !hasVocalsTrack || !supported;
    vocalsToggleBtn.setAttribute("aria-pressed", supported && mixState.vocals_enabled ? "true" : "false");
    vocalsToggleBtn.setAttribute("aria-label", label);
    vocalsToggleBtn.setAttribute("title", label);
    vocalsVolumeSlider.disabled = !hasVocalsTrack || !supported;
    if (vocalsToggleIcon) {
        vocalsToggleIcon.textContent = supported && mixState.vocals_enabled ? "mic" : "mic_off";
    }
    vocalsToggleLabel.textContent = supported && mixState.vocals_enabled ? t("stage.vocals_on") : t("stage.vocals_off");
    vocalsVolumeSlider.value = String(Math.round(mixState.vocals_volume * 100));
    vocalsVolumeSlider.setAttribute("aria-label", label);
}

async function ensureAudioGraph() {
    if (!canPlayGuideVocals() || !vocalsAudio) {
        return;
    }
    if (!audioContext) {
        audioContext = new AudioContext();
    }
    if (!vocalsSourceNode) {
        vocalsSourceNode = audioContext.createMediaElementSource(vocalsAudio);
        vocalsGainNode = audioContext.createGain();
        vocalsSourceNode.connect(vocalsGainNode);
        vocalsGainNode.connect(audioContext.destination);
    }
    if (audioContext.state === "suspended") {
        await audioContext.resume();
    }
    applyVocalsMix();
}

function applyVocalsMix() {
    if (!vocalsGainNode || !canPlayGuideVocals()) return;
    const targetGain = mixState.vocals_enabled ? mixState.vocals_volume : 0.0;
    vocalsGainNode.gain.value = targetGain;
}

function syncVocalsToVideo(forceSeek = false) {
    const primary = getPrimaryPlayer();
    if (!canPlayGuideVocals() || !primary || !vocalsAudio) return;
    if (primary.paused) {
        if (!vocalsAudio.paused) {
            vocalsAudio.pause();
        }
        return;
    }
    const primaryTime = primary.currentTime || 0;
    const drift = Math.abs((vocalsAudio.currentTime || 0) - primaryTime);
    if (forceSeek || drift > SOFT_DRIFT_THRESHOLD_SECONDS) {
        vocalsAudio.currentTime = primaryTime;
    }
    vocalsAudio.play().catch((error) => {
        console.warn("Vocals playback start blocked:", error);
    });
}

function sendPlaybackTimeUpdate(force = false) {
    const primary = getPrimaryPlayer();
    if (!primary) {
        return;
    }
    updatePlaybarUi(primary.currentTime || 0);
    if (!force && !stageClockEnabled) {
        return;
    }
    const now = performance.now();
    if (!force && now - lastPlaybackStateBroadcastAt < PLAYBACK_CLOCK_BROADCAST_INTERVAL_MS) {
        return;
    }
    lastPlaybackStateBroadcastAt = now;
    const currentTime = primary.currentTime || 0;
    sendStageCommandRaw({
        type: "stage_time_update",
        data: {
            current_time: force ? currentTime : Math.round(currentTime * 10) / 10,
            is_paused: primary.paused,
            source: "stage",
        },
        timestamp: Date.now(),
    });
}

function startSyncTimer() {
    if (syncTimer || !canPlayGuideVocals()) return;
    syncTimer = window.setInterval(() => syncVocalsToVideo(false), 250);
}

function stopSyncTimer() {
    if (!syncTimer) return;
    window.clearInterval(syncTimer);
    syncTimer = null;
}

function suppressSeekBroadcastTemporarily() {
    suppressSeekBroadcast = true;
    if (seekBroadcastUnlockTimer) {
        window.clearTimeout(seekBroadcastUnlockTimer);
    }
    seekBroadcastUnlockTimer = window.setTimeout(() => {
        suppressSeekBroadcast = false;
        seekBroadcastUnlockTimer = null;
    }, 500);
}

function seekMediaElement(mediaElement, seekTime) {
    return new Promise((resolve) => {
        if (!mediaElement) {
            resolve();
            return;
        }
        const targetTime = Math.max(0, Number.isFinite(seekTime) ? seekTime : 0);
        const currentTime = Number.isFinite(mediaElement.currentTime) ? mediaElement.currentTime : 0;
        if (Math.abs(currentTime - targetTime) < 0.01) {
            resolve();
            return;
        }
        let settled = false;
        const settle = () => {
            if (settled) return;
            settled = true;
            mediaElement.removeEventListener("seeked", settle);
            mediaElement.removeEventListener("error", settle);
            resolve();
        };
        mediaElement.addEventListener("seeked", settle, { once: true });
        mediaElement.addEventListener("error", settle, { once: true });
        window.setTimeout(settle, MEDIA_SEEK_TIMEOUT_MS);
        try {
            mediaElement.currentTime = targetTime;
        } catch (_) {
            settle();
        }
    });
}

function waitForMediaReady(mediaElement, timeoutMs = MEDIA_READY_TIMEOUT_MS) {
    return new Promise((resolve) => {
        if (!mediaElement || mediaElement.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
            resolve();
            return;
        }
        let settled = false;
        const settle = () => {
            if (settled) return;
            settled = true;
            mediaElement.removeEventListener("canplay", settle);
            mediaElement.removeEventListener("loadeddata", settle);
            mediaElement.removeEventListener("error", settle);
            resolve();
        };
        mediaElement.addEventListener("canplay", settle, { once: true });
        mediaElement.addEventListener("loadeddata", settle, { once: true });
        mediaElement.addEventListener("error", settle, { once: true });
        window.setTimeout(settle, timeoutMs);
    });
}

function waitForMediaMetadata(mediaElement, timeoutMs = MEDIA_METADATA_TIMEOUT_MS) {
    return new Promise((resolve) => {
        if (!mediaElement || mediaElement.readyState >= HTMLMediaElement.HAVE_METADATA) {
            resolve();
            return;
        }
        let settled = false;
        const settle = () => {
            if (settled) return;
            settled = true;
            mediaElement.removeEventListener("loadedmetadata", settle);
            mediaElement.removeEventListener("loadeddata", settle);
            mediaElement.removeEventListener("error", settle);
            resolve();
        };
        mediaElement.addEventListener("loadedmetadata", settle, { once: true });
        mediaElement.addEventListener("loadeddata", settle, { once: true });
        mediaElement.addEventListener("error", settle, { once: true });
        window.setTimeout(settle, timeoutMs);
    });
}

async function reloadMediaElement(mediaElement, targetTime) {
    if (!mediaElement) return;
    const source = mediaElement.querySelector("source");
    const sourceUrl = source?.getAttribute("src") || mediaElement.currentSrc || mediaElement.src;
    if (!sourceUrl) return;
    mediaElement.pause();
    const bustedUrl = new URL(sourceUrl, window.location.href);
    bustedUrl.searchParams.set("_sync", String(Date.now()));
    if (source) {
        source.setAttribute("src", bustedUrl.toString());
    } else {
        mediaElement.src = bustedUrl.toString();
    }
    mediaElement.load();
    await waitForMediaMetadata(mediaElement);
    await seekMediaElement(mediaElement, targetTime);
    await waitForMediaReady(mediaElement);
}

async function seekAndResyncPlayback(targetTime, shouldPausePlayback) {
    const primary = getPrimaryPlayer();
    if (!primary) return;
    const seekTime = Math.max(0, Number.isFinite(targetTime) ? targetTime : 0);
    suppressSeekBroadcastTemporarily();
    primary.pause();
    stopSyncTimer();
    if (canPlayGuideVocals() && vocalsAudio && !vocalsAudio.paused) {
        vocalsAudio.pause();
    }
    const seeks = [seekMediaElement(primary, seekTime)];
    if (canPlayGuideVocals() && vocalsAudio) {
        seeks.push(seekMediaElement(vocalsAudio, seekTime));
    }
    await Promise.all(seeks);
    updateLyricsForTime(seekTime);
    updatePlaybarUi(seekTime);
    if (shouldPausePlayback) {
        updatePlayPauseUi();
        return;
    }
    try {
        await ensureAudioGraph();
        await playPrimary();
        syncVocalsToVideo(true);
        startSyncTimer();
        startLyricsTicker();
    } catch (error) {
        console.error("Seek/resync playback failed:", error);
    } finally {
        updatePlayPauseUi();
    }
}

async function hardResyncPlayback({
    targetTime = null,
    shouldPausePlayback = null,
    broadcast = false,
    syncVersion = null,
    reloadMedia = true,
    fallbackReload = true,
    reason = "manual",
    attempt = 0,
} = {}) {
    const primary = getPrimaryPlayer();
    if (!primary) return;
    if (typeof syncVersion === "number" && syncVersion <= lastHandledSyncVersion) {
        return;
    }
    if (typeof syncVersion === "number") {
        lastHandledSyncVersion = syncVersion;
    }

    const operationId = ++syncOperationId;
    const pauseAfterRelock = typeof shouldPausePlayback === "boolean" ? shouldPausePlayback : primary.paused;
    const seekTime = Math.max(0, Number.isFinite(targetTime) ? targetTime : (primary.currentTime || 0));

    suppressSeekBroadcastTemporarily();
    stopSyncTimer();
    stopLyricsTicker();
    primary.pause();
    if (canPlayGuideVocals() && vocalsAudio && !vocalsAudio.paused) {
        vocalsAudio.pause();
    }

    try {
        hardSyncInProgress = true;
        if (reloadMedia) {
            const reloads = [reloadMediaElement(primary, seekTime)];
            if (canPlayGuideVocals() && vocalsAudio) {
                reloads.push(reloadMediaElement(vocalsAudio, seekTime));
            }
            await Promise.all(reloads);
        } else {
            const seeks = [seekMediaElement(primary, seekTime)];
            if (canPlayGuideVocals() && vocalsAudio) {
                seeks.push(seekMediaElement(vocalsAudio, seekTime));
            }
            await Promise.all(seeks);
            const readiness = [waitForMediaReady(primary)];
            if (canPlayGuideVocals() && vocalsAudio) {
                readiness.push(waitForMediaReady(vocalsAudio));
            }
            await Promise.all(readiness);
        }
        if (operationId !== syncOperationId) return;

        updateLyricsForTime(seekTime);
        updatePlaybarUi(seekTime);
        if (pauseAfterRelock) {
            updatePlayPauseUi();
            return;
        }

        await ensureAudioGraph();
        await playPrimary();
        if (canPlayGuideVocals() && vocalsAudio) {
            vocalsAudio.currentTime = getPrimaryCurrentTime() || seekTime;
            await vocalsAudio.play();
        }
        startSyncTimer();
        startLyricsTicker();
        await new Promise((resolve) => window.setTimeout(resolve, 140));
        if (operationId !== syncOperationId) return;

    } catch (error) {
        console.warn("Hard playback resync failed:", { reason, attempt, error });
        if (attempt === 0) {
            await hardResyncPlayback({
                targetTime: getPrimaryCurrentTime() || seekTime,
                shouldPausePlayback: pauseAfterRelock,
                broadcast: false,
                reloadMedia: true,
                fallbackReload,
                reason: `${reason}:retry`,
                attempt: attempt + 1,
            });
            return;
        }
        if (fallbackReload) {
            safeReload();
            return;
        }
    } finally {
        hardSyncInProgress = false;
        updatePlayPauseUi();
    }

}

async function forceResyncPlayback(broadcast = true, syncVersion = null) {
    const primary = getPrimaryPlayer();
    if (!primary) return;
    if (broadcast) {
        const sent = sendStageCommand("resync", {
            seek_time: primary.currentTime || 0,
            is_paused: primary.paused,
        });
        if (sent) {
            return;
        }
    }
    await hardResyncPlayback({
        targetTime: primary.currentTime || 0,
        shouldPausePlayback: primary.paused,
        broadcast: false,
        syncVersion,
        reloadMedia: true,
        reason: "manual",
    });
}

async function runInitialMultitrackResync() {
    const primary = getPrimaryPlayer();
    if (!primary || !canPlayGuideVocals() || initialMultitrackResyncCompleted || hardSyncInProgress) {
        return false;
    }
    initialMultitrackResyncCompleted = true;
    await hardResyncPlayback({
        targetTime: primary.currentTime || 0,
        shouldPausePlayback: false,
        broadcast: false,
        reloadMedia: true,
        reason: "initial-multitrack-start",
    });
    return true;
}

function applyStageStateFromServer(data) {
    if (!data || typeof data !== "object") return;
    if (typeof data.sync_version === "number" && Number.isFinite(data.sync_version)) {
        lastHandledSyncVersion = Math.max(lastHandledSyncVersion, data.sync_version);
    }
    if (typeof data.vocals_enabled === "boolean") {
        mixState.vocals_enabled = data.vocals_enabled;
    }
    if (typeof data.vocals_volume === "number" && Number.isFinite(data.vocals_volume)) {
        mixState.vocals_volume = Math.max(0, Math.min(1, data.vocals_volume));
    }
    if (typeof data.current_time === "number" && Number.isFinite(data.current_time)) {
        updatePlaybarUi(data.current_time);
    } else {
        updatePlaybarUi();
    }
    if (typeof data.lyrics_enabled === "boolean") {
        setLyricsEnabled(data.lyrics_enabled);
    } else {
        updateLyricsUi();
    }
    if (typeof data.background_media_enabled === "boolean") {
        setBackgroundMediaEnabled(data.background_media_enabled);
    }
    updateVocalsUi();
    applyVocalsMix();
    if (canPlayGuideVocals() && !isPrimaryPaused()) {
        ensureAudioGraph()
            .then(() => syncVocalsToVideo(false))
            .catch((error) => {
                console.warn("Failed applying remote vocals state:", error);
            });
    }
}

function updateFullscreenUi() {
    if (!fullscreenIcon) return;
    const inFullscreen = !!document.fullscreenElement;
    const label = inFullscreen ? t("stage.exit_fullscreen") : t("stage.fullscreen");
    fullscreenIcon.textContent = inFullscreen ? "fullscreen_exit" : "fullscreen";
    if (fullscreenBtn) {
        fullscreenBtn.setAttribute("aria-label", label);
        fullscreenBtn.setAttribute("title", label);
    }
}

function resolveStageQrUrl() {
    const configured = (SERVER_STAGE_QR_URL || "").trim();
    if (configured) {
        return configured;
    }
    return window.location.hostname;
}

function clampNumber(value, min, max, fallback) {
    const number = Number(value);
    if (!Number.isFinite(number)) {
        return fallback;
    }
    return Math.max(min, Math.min(max, number));
}

function clampQrSize(value) {
    return Math.round(clampNumber(value, STAGE_QR_MIN_SIZE, STAGE_QR_MAX_SIZE, STAGE_QR_DEFAULT_SIZE));
}

function createDefaultQrDisplayState() {
    return {
        sizePx: STAGE_QR_DEFAULT_SIZE,
        xRatio: 1,
        yRatio: 1,
    };
}

function normalizeQrDisplayState(state) {
    const source = state && typeof state === "object" ? state : {};
    return {
        sizePx: clampQrSize(source.sizePx),
        xRatio: clampNumber(source.xRatio, 0, 1, 1),
        yRatio: clampNumber(source.yRatio, 0, 1, 1),
    };
}

function loadQrDisplayState() {
    try {
        const stored = window.localStorage?.getItem(STAGE_QR_STORAGE_KEY);
        if (!stored) {
            return createDefaultQrDisplayState();
        }
        return normalizeQrDisplayState(JSON.parse(stored));
    } catch (_) {
        return createDefaultQrDisplayState();
    }
}

function saveQrDisplayState() {
    try {
        window.localStorage?.setItem(STAGE_QR_STORAGE_KEY, JSON.stringify(qrDisplayState));
    } catch (_) {
        stageLyrics.setStatus(t("stage.qr_customize_save_failed"));
    }
}

function getQrViewportBounds() {
    const containerWidth = qrOverlay?.offsetWidth || qrDisplayState.sizePx + 24;
    const containerHeight = qrOverlay?.offsetHeight || qrDisplayState.sizePx + 48;
    return {
        minX: STAGE_QR_EDGE_PADDING,
        minY: STAGE_QR_EDGE_PADDING,
        maxX: Math.max(STAGE_QR_EDGE_PADDING, window.innerWidth - containerWidth - STAGE_QR_EDGE_PADDING),
        maxY: Math.max(STAGE_QR_EDGE_PADDING, window.innerHeight - containerHeight - STAGE_QR_EDGE_PADDING),
    };
}

function ratioToCoordinate(ratio, min, max) {
    if (max <= min) {
        return min;
    }
    return min + (max - min) * clampNumber(ratio, 0, 1, 1);
}

function coordinateToRatio(value, min, max) {
    if (max <= min) {
        return 1;
    }
    return clampNumber((value - min) / (max - min), 0, 1, 1);
}

function getQrCoordinatesFromState() {
    const bounds = getQrViewportBounds();
    return {
        x: ratioToCoordinate(qrDisplayState.xRatio, bounds.minX, bounds.maxX),
        y: ratioToCoordinate(qrDisplayState.yRatio, bounds.minY, bounds.maxY),
    };
}

function setQrCoordinates(x, y, persist = true) {
    const bounds = getQrViewportBounds();
    const clampedX = clampNumber(x, bounds.minX, bounds.maxX, bounds.maxX);
    const clampedY = clampNumber(y, bounds.minY, bounds.maxY, bounds.maxY);
    qrDisplayState.xRatio = coordinateToRatio(clampedX, bounds.minX, bounds.maxX);
    qrDisplayState.yRatio = coordinateToRatio(clampedY, bounds.minY, bounds.maxY);
    if (persist) {
        saveQrDisplayState();
    }
    return { x: clampedX, y: clampedY };
}

function applyQrOverlayPlacement() {
    if (!qrOverlay) return;
    const coords = getQrCoordinatesFromState();
    const { x, y } = setQrCoordinates(coords.x, coords.y, false);
    qrOverlay.style.setProperty("--stage-qr-size", `${qrDisplayState.sizePx}px`);
    qrOverlay.style.left = `${x}px`;
    qrOverlay.style.top = `${y}px`;
    qrOverlay.style.transform = isQrVisible
        ? "translate3d(0, 0, 0) scale(1)"
        : "translate3d(0, 8px, 0) scale(0.97)";
}

function updateQrOverlayContent() {
    if (!qrImage) return;
    applyQrOverlayPlacement();
    const target = resolveStageQrUrl();
    const params = new URLSearchParams({
        data: target,
        size: String(qrDisplayState.sizePx),
    });
    qrImage.src = `${QR_CODE_ENDPOINT}?${params.toString()}`;
}

function syncQrSettingsUi() {
    if (qrSizeValue) {
        qrSizeValue.textContent = `${qrDisplayState.sizePx}px`;
    }
}

function changeQrSize(delta) {
    qrDisplayState.sizePx = clampQrSize(qrDisplayState.sizePx + delta);
    syncQrSettingsUi();
    saveQrDisplayState();
    updateQrOverlayContent();
}

function beginQrDrag(event) {
    const target = event.target;
    if (
        !qrOverlay ||
        !isQrVisible ||
        event.button === 2 ||
        (target instanceof HTMLElement && target.closest("button, input, label"))
    ) {
        return;
    }
    const rect = qrOverlay.getBoundingClientRect();
    qrDragState = {
        pointerId: event.pointerId,
        offsetX: event.clientX - rect.left,
        offsetY: event.clientY - rect.top,
    };
    qrOverlay.setPointerCapture?.(event.pointerId);
    qrOverlay.classList.add("is-dragging");
    showStageControls();
    event.preventDefault();
}

function updateQrDrag(event) {
    if (!qrDragState || qrDragState.pointerId !== event.pointerId) {
        return;
    }
    const nextX = event.clientX - qrDragState.offsetX;
    const nextY = event.clientY - qrDragState.offsetY;
    const { x, y } = setQrCoordinates(nextX, nextY, false);
    qrOverlay.style.left = `${x}px`;
    qrOverlay.style.top = `${y}px`;
    qrOverlay.style.transform = "translate3d(0, 0, 0) scale(1)";
    event.preventDefault();
}

function endQrDrag(event) {
    if (!qrDragState || qrDragState.pointerId !== event.pointerId) {
        return;
    }
    qrOverlay.releasePointerCapture?.(event.pointerId);
    qrOverlay.classList.remove("is-dragging");
    saveQrDisplayState();
    qrDragState = null;
    scheduleHideStageControls();
}

const qrDisplayState = loadQrDisplayState();
syncQrSettingsUi();
applyQrOverlayPlacement();

function setQrOverlayVisible(visible) {
    if (!qrOverlay || !qrToggleBtn) return;
    isQrVisible = visible;
    qrOverlay.classList.toggle("is-visible", visible);
    applyQrOverlayPlacement();
    qrToggleBtn.setAttribute("aria-pressed", visible ? "true" : "false");
    qrToggleBtn.classList.toggle("bg-primary/85", visible);
    qrToggleBtn.classList.toggle("text-on-primary", visible);
    qrToggleBtn.classList.toggle("bg-surface-container-high/75", !visible);
    qrToggleBtn.classList.toggle("text-on-surface", !visible);
}

function updateShortcutsUi() {
    if (!shortcutsBtn || !shortcutsPanel) return;
    shortcutsBtn.setAttribute("aria-expanded", shortcutsPanelVisible ? "true" : "false");
    shortcutsPanel.classList.toggle("hidden", !shortcutsPanelVisible);
}

function setShortcutsPanelVisible(visible) {
    shortcutsPanelVisible = Boolean(visible);
    updateShortcutsUi();
}

function toggleShortcutsPanel() {
    const nextVisible = !shortcutsPanelVisible;
    setShortcutsPanelVisible(nextVisible);
    if (nextVisible) {
        stageLyrics.setSettingsPanelVisible(false);
        showStageControls();
    } else {
        scheduleHideStageControls();
    }
}

function isFullscreenActive() {
    return !!document.fullscreenElement;
}

function setZenModeEnabled(enabled) {
    zenModeEnabled = Boolean(enabled) && isFullscreenActive();

    if (!stageMedia) {
        return;
    }

    stageMedia.classList.toggle("is-zen", zenModeEnabled);

    if (zenModeEnabled) {
        stageControls?.classList.add("hidden");
        stageMedia.classList.remove("is-controls-visible");
        if (controlsHideTimer) {
            window.clearTimeout(controlsHideTimer);
            controlsHideTimer = null;
        }
        return;
    }

    stageControls?.classList.remove("hidden");
    if (isFullscreenActive()) {
        showStageControls();
    }
}

function showStageControls() {
    if (!stageMedia) return;

    if (zenModeEnabled) {
        stageMedia.classList.remove("is-controls-visible");
        if (controlsHideTimer) {
            window.clearTimeout(controlsHideTimer);
            controlsHideTimer = null;
        }
        return;
    }

    stageMedia.classList.add("is-controls-visible");

    if (controlsHideTimer) {
        window.clearTimeout(controlsHideTimer);
        controlsHideTimer = null;
    }

    if (shortcutsPanelVisible || stageLyrics.settingsPanelVisible || qrDragState) {
        return;
    }

    if (isFullscreenActive() && !isPrimaryPaused()) {
        controlsHideTimer = window.setTimeout(() => {
            stageMedia.classList.remove("is-controls-visible");
        }, 1000);
    }
}

function scheduleHideStageControls() {
    if (!stageMedia || zenModeEnabled || !isFullscreenActive() || isPrimaryPaused()) {
        return;
    }

    showStageControls();
}

function syncFullscreenState() {
    if (!stageMedia) return;

    const active = isFullscreenActive();
    stageMedia.classList.toggle("is-fullscreen", active);

    if (active) {
        stageLyrics.applyBackgroundSettings();
        if (zenModeEnabled) {
            setZenModeEnabled(true);
        } else {
            showStageControls();
        }
    } else {
        setZenModeEnabled(false);
        if (controlsHideTimer) {
            window.clearTimeout(controlsHideTimer);
            controlsHideTimer = null;
        }
        stageMedia.classList.remove("is-controls-visible", "is-fullscreen");
    }
}

function renderQueuePreview(queue) {
    if (!queuePreview || !upNextCount) return;

    const upcoming = queue.filter((item) => item.status !== "playing").slice(0, 5);
    upNextCount.textContent = upcoming.length ? t("stage.queue_count", { count: upcoming.length }) : "";

    if (upcoming.length === 0) {
        queuePreview.innerHTML = `<p class="text-sm text-on-surface-variant">${t("stage.no_upcoming")}</p>`;
        return;
    }

    queuePreview.innerHTML = upcoming
        .map((item) => `
            <div class="min-w-0 grow rounded-full bg-surface-container-high px-3 py-2 sm:grow-0">
                <p class="truncate text-sm font-medium text-on-surface">${escapeHtml(item.title)}</p>
            </div>
        `)
        .join("");
}

async function completeCurrentSong() {
    const response = await fetch(window.KaraokeURLs.appUrl('/api/queue/complete-current'), { method: "POST" });
    if (!response.ok) {
        throw new Error(t("stage.complete_failed"));
    }
}

async function skipCurrentSong() {
    const response = await fetch(window.KaraokeURLs.appUrl('/api/queue/skip'), { method: "POST" });
    if (!response.ok) {
        throw new Error(t("stage.skip_failed"));
    }
}

function clearStageReconnectTimer() {
    if (stageReconnectTimer) {
        window.clearTimeout(stageReconnectTimer);
        stageReconnectTimer = null;
    }
}

function resetStageReconnectState() {
    clearStageReconnectTimer();
    stageReconnectAttempts = 0;
    stageReconnectDelayMs = 1000;
}

function isStageSocketStale() {
    return window.KaraokeWebSocketLifecycle?.isSocketStale({
        socket: stageSocket,
        lastActivityAt: Math.max(stageSocketLastMessageAt || 0, stageSocketLastPingAt || 0),
        graceMs: 5000,
    }) || false;
}

function scheduleStageReconnect() {
    if (!stageShouldReconnect) {
        return;
    }
    stageReconnectAttempts += 1;
    const rawDelay = Math.min(stageReconnectDelayMs * Math.pow(2, stageReconnectAttempts - 1), 8000);
    const delay = window.KaraokeWebSocketLifecycle?.withJitter(rawDelay) ?? rawDelay;
    clearStageReconnectTimer();
    stageReconnectTimer = window.setTimeout(() => {
        stageReconnectTimer = null;
        connectStageWebSocket(true);
    }, delay);
}

function reconnectStageSocketNow(reason = "manual") {
    stageShouldReconnect = true;
    clearStageReconnectTimer();
    if (stageSocket && stageSocket.readyState !== WebSocket.CLOSED) {
        try {
            stageSocket.close(4000, reason);
        } catch (_) {
            // Best-effort only.
        }
    }
    stageSocket = null;
    resetStageReconnectState();
    connectStageWebSocket(true);
}

function handleStageVisibleResume(event) {
    stageShouldReconnect = true;
    if (!window.KaraokeWebSocketLifecycle?.isVisible()) {
        return;
    }
    if (stageSocket && stageSocket.readyState === WebSocket.CONNECTING) {
        return;
    }
    if (!stageSocket || stageSocket.readyState === WebSocket.CLOSED || isStageSocketStale() || event?.persisted) {
        reconnectStageSocketNow(event?.persisted ? "pageshow" : "foreground");
        return;
    }
    refreshStageState().catch((error) => {
        console.warn("Failed to refresh stage state on resume:", error);
    });
}

function handleStagePageHide() {
    stageShouldReconnect = false;
    clearStageReconnectTimer();
    if (!stageSocket) {
        return;
    }
    try {
        stageSocket.close(1000, "page hide");
    } catch (_) {
        // Best-effort only.
    }
}

function connectStageWebSocket(force = false) {
    const wsUrl = window.KaraokeURLs.appWsUrl('/api/queue/ws');
    if (stageSocket && (stageSocket.readyState === WebSocket.OPEN || stageSocket.readyState === WebSocket.CONNECTING)) {
        if (!force) {
            return;
        }
        try {
            stageSocket.close(4000, "force reconnect");
        } catch (_) {
            // Best-effort only.
        }
        stageSocket = null;
    }
    if (!stageShouldReconnect) {
        return;
    }
    try {
        stageSocket = new WebSocket(wsUrl);
    } catch (error) {
        console.warn("Failed to open stage websocket:", error);
        if (stageShouldReconnect) {
            scheduleStageReconnect();
        }
        return;
    }
    const socket = stageSocket;

    stageSocket.onopen = () => {
        if (stageSocket !== socket) {
            return;
        }
        resetStageReconnectState();
        stageSocketLastMessageAt = Date.now();
        stageSocketLastPingAt = 0;
        sendStageCommandRaw({
            type: "client_subscribe",
            data: { page: "stage" },
            timestamp: Date.now(),
        });
        sendStagePresenceHello();
        refreshStageState().catch((error) => {
            console.warn("Failed to refresh stage state after reconnect:", error);
        });
    };

    stageSocket.onmessage = async (event) => {
        if (stageSocket !== socket) {
            return;
        }
        try {
            const message = JSON.parse(event.data);
            const messageType = message?.type;
            stageSocketLastMessageAt = Date.now();
            if (messageType === "ping") {
                stageSocketLastPingAt = Date.now();
                sendStageCommandRaw({ type: "pong", timestamp: Date.now() });
                return;
            }
            if (messageType === "connected") {
                const initialStageState = message?.data?.stage_state;
                applyStageStateFromServer(initialStageState);
                return;
            }
            if (messageType === "stage_clock_subscribers_update") {
                stageClockEnabled = Boolean(message?.data?.clock_enabled);
                return;
            }
            if (messageType === "current_item_changed") {
                await refreshStageState();
                return;
            }
            if (messageType === "queue_item_added" || messageType === "queue_item_removed" || messageType === "queue_cleared") {
                const queueResponse = await fetch(window.KaraokeURLs.appUrl('/api/queue/'));
                if (queueResponse.ok) {
                    const queue = await queueResponse.json();
                    renderQueuePreview(queue);
                }
                return;
            }
            if (messageType === "queue_item_updated" || messageType === "queue_item_failed") {
                const queueResponse = await fetch(window.KaraokeURLs.appUrl('/api/queue/'));
                if (queueResponse.ok) {
                    const queue = await queueResponse.json();
                    renderQueuePreview(queue);
                }
                return;
            }
            if (messageType === "stage_control_command") {
                const command = message?.data?.command;
                if (command === "apply_lyrics_settings") {
                    await applyRemoteLyricsSettings(message?.data || {});
                    return;
                } else if (command === "set_background_media_enabled") {
                    const nextEnabled = message?.data?.background_media_enabled;
                    if (typeof nextEnabled === "boolean") {
                        setBackgroundMediaEnabled(nextEnabled);
                        sendLyricsSettingsAck(true, {
                            background_media_enabled: nextEnabled,
                            applied_settings: {
                                ...stageLyrics.getSettingsSnapshot(),
                            },
                        });
                    }
                    return;
                }
                const primary = getPrimaryPlayer();
                if (!primary) return;
                if (command === "resync") {
                    const seekTime = message?.data?.seek_time;
                    const remotePaused = message?.data?.is_paused;
                    const syncVersion = message?.data?.sync_version;
                    await hardResyncPlayback({
                        targetTime: (typeof seekTime === "number" && Number.isFinite(seekTime)) ? seekTime : (primary.currentTime || 0),
                        shouldPausePlayback: typeof remotePaused === "boolean" ? remotePaused : primary.paused,
                        broadcast: false,
                        syncVersion: (typeof syncVersion === "number" && Number.isFinite(syncVersion)) ? syncVersion : null,
                        reason: "remote-resync",
                    });
                } else if (command === "seek") {
                    const seekTime = message?.data?.seek_time;
                    const remotePaused = message?.data?.is_paused;
                    if (typeof seekTime === "number" && Number.isFinite(seekTime)) {
                        const shouldPausePlayback = typeof remotePaused === "boolean" ? remotePaused : primary.paused;
                        await seekAndResyncPlayback(seekTime, shouldPausePlayback);
                    }
                } else if (command === "seek_relative") {
                    const offsetSeconds = Number(message?.data?.offset_seconds);
                    if (Number.isFinite(offsetSeconds)) {
                        const duration = getPrimaryDuration();
                        const currentTime = getPrimaryCurrentTime();
                        const unclampedTime = Math.max(0, currentTime + offsetSeconds);
                        const targetTime = duration > 0 ? Math.min(unclampedTime, duration) : unclampedTime;
                        const remotePaused = message?.data?.is_paused;
                        const shouldPausePlayback = typeof remotePaused === "boolean" ? remotePaused : primary.paused;
                        await seekAndResyncPlayback(targetTime, shouldPausePlayback);
                    }
                } else if (command === "play" && primary.paused) {
                    await ensureAudioGraph();
                    await playPrimary();
                    syncVocalsToVideo(true);
                } else if (command === "pause" && !primary.paused) {
                    pausePrimary();
                }
                updatePlayPauseUi();
                return;
            }
            if (messageType === "stage_state_update") {
                const isPaused = message?.data?.is_paused;
                applyStageStateFromServer(message?.data);
                const primary = getPrimaryPlayer();
                if (!primary || typeof isPaused !== "boolean") return;
                if (isPaused && !primary.paused) {
                    pausePrimary();
                }
                if (!isPaused && primary.paused) {
                    await ensureAudioGraph();
                    await playPrimary();
                    syncVocalsToVideo(true);
                }
                updatePlayPauseUi();
            }
        } catch (error) {
            console.error("Failed to process stage websocket message:", error);
        }
    };

    stageSocket.onerror = () => {
        if (stageSocket !== socket) {
            return;
        }
    };

    stageSocket.onclose = () => {
        if (stageSocket !== socket) {
            return;
        }
        stageSocket = null;
        if (stageShouldReconnect) {
            scheduleStageReconnect();
        }
    };
}

function sendStageCommandRaw(payload) {
    if (!stageSocket || stageSocket.readyState !== WebSocket.OPEN) {
        return false;
    }
    stageSocket.send(JSON.stringify(payload));
    return true;
}

function sendStageCommand(command, extraData = {}) {
    const sent = sendStageCommandRaw({
        type: "stage_command",
        data: {
            command,
            source: "stage",
            ...extraData,
        },
        timestamp: Date.now(),
    });
    return sent;
}

function bindPrimaryMediaEvents(mediaElement) {
    if (!mediaElement) {
        return;
    }
    mediaElement.addEventListener("ended", async () => {
        if (mediaElement !== getPrimaryPlayer() || !hasCurrentQueueItem) {
            return;
        }
        stopSyncTimer();
        stopLyricsTicker();
        if (canPlayGuideVocals() && vocalsAudio) {
            vocalsAudio.pause();
            vocalsAudio.currentTime = 0;
        }
        try {
            await completeCurrentSong();
        } catch (error) {
            console.error("Failed to advance after playback ended:", error);
        } finally {
            await refreshStageState();
        }
    });

    mediaElement.addEventListener("play", updatePlayPauseUi);
    mediaElement.addEventListener("pause", updatePlayPauseUi);
    mediaElement.addEventListener("loadedmetadata", () => {
        if (mediaElement !== getPrimaryPlayer()) {
            return;
        }
        updatePlaybarUi(mediaElement.currentTime || 0);
    });
    mediaElement.addEventListener("durationchange", () => {
        if (mediaElement !== getPrimaryPlayer()) {
            return;
        }
        updatePlaybarUi(mediaElement.currentTime || 0);
    });
    mediaElement.addEventListener("play", async () => {
        if (mediaElement !== getPrimaryPlayer()) {
            return;
        }
        sendPlaybackTimeUpdate(true);
        if (await runInitialMultitrackResync()) {
            return;
        }
        if (hardSyncInProgress) {
            return;
        }
        await ensureAudioGraph();
        syncVocalsToVideo(true);
        startSyncTimer();
        startLyricsTicker();
    });
    mediaElement.addEventListener("pause", () => {
        if (mediaElement !== getPrimaryPlayer()) {
            return;
        }
        sendPlaybackTimeUpdate(true);
        updatePlaybarUi(mediaElement.currentTime || 0);
        stopSyncTimer();
        stopLyricsTicker();
        if (canPlayGuideVocals() && vocalsAudio && !vocalsAudio.paused) {
            vocalsAudio.pause();
        }
    });
    mediaElement.addEventListener("timeupdate", () => {
        if (mediaElement !== getPrimaryPlayer()) {
            return;
        }
        updatePlaybarUi(mediaElement.currentTime || 0);
        sendPlaybackTimeUpdate(false);
        updateLyricsForTime(mediaElement.currentTime || 0);
    });
    mediaElement.addEventListener("seeking", () => {
        if (mediaElement !== getPrimaryPlayer()) {
            return;
        }
        updatePlaybarUi(mediaElement.currentTime || 0);
        sendPlaybackTimeUpdate(true);
        if (canPlayGuideVocals() && vocalsAudio) {
            vocalsAudio.currentTime = mediaElement.currentTime || 0;
            if (mediaElement.paused && !vocalsAudio.paused) {
                vocalsAudio.pause();
            }
        }
        updateLyricsForTime(mediaElement.currentTime || 0);
        if (!mediaElement.paused) {
            syncVocalsToVideo(true);
        }
        if (!suppressSeekBroadcast && !hardSyncInProgress) {
            sendStageCommand("seek", {
                seek_time: mediaElement.currentTime || 0,
                is_paused: mediaElement.paused,
            });
        }
    });
}

bindPrimaryMediaEvents(video);
bindPrimaryMediaEvents(primaryAudio);
updatePlayPauseUi();
updateVocalsUi();
updateIosVocalsWarning();

if (playPauseBtn) {
    playPauseBtn.addEventListener("click", async () => {
        const primary = getPrimaryPlayer();
        if (!primary) {
            return;
        }
        const command = primary.paused ? "play" : "pause";
        if (!sendStageCommand(command)) {
            if (primary.paused) {
                try {
                    await ensureAudioGraph();
                    await playPrimary();
                    syncVocalsToVideo(true);
                } catch (error) {
                    console.error("Play failed:", error);
                }
            } else {
                pausePrimary();
            }
        }
        updatePlayPauseUi();
    });
}

if (vocalsToggleBtn) {
    vocalsToggleBtn.addEventListener("click", async () => {
        if (!canPlayGuideVocals()) return;
        const nextEnabled = !mixState.vocals_enabled;
        const sent = sendStageCommand("set_vocals_enabled", { vocals_enabled: nextEnabled });
        if (!sent) {
            mixState.vocals_enabled = nextEnabled;
            await ensureAudioGraph();
            updateVocalsUi();
            applyVocalsMix();
        }
    });
}

if (vocalsVolumeSlider) {
    vocalsVolumeSlider.addEventListener("input", async () => {
        if (!canPlayGuideVocals()) return;
        const nextVolume = Number(vocalsVolumeSlider.value) / 100;
        const sent = sendStageCommand("set_vocals_volume", { vocals_volume: nextVolume });
        if (!sent) {
            mixState.vocals_volume = Math.max(0, Math.min(1, nextVolume));
            await ensureAudioGraph();
            updateVocalsUi();
            applyVocalsMix();
        }
    });
}

if (playbarSlider) {
    playbarSlider.addEventListener("pointerdown", () => {
        isPlaybarScrubbing = true;
        showStageControls();
    });
    playbarSlider.addEventListener("input", () => {
        isPlaybarScrubbing = true;
        playbarPreviewTime = Number(playbarSlider.value) || 0;
        updatePlaybarUi(playbarPreviewTime);
        showStageControls();
    });
    playbarSlider.addEventListener("change", async () => {
        await commitPlaybarSeek();
    });
    playbarSlider.addEventListener("blur", () => {
        if (!isPlaybarScrubbing) {
            return;
        }
        isPlaybarScrubbing = false;
        updatePlaybarUi();
    });
}

if (skipBtn) {
    skipBtn.addEventListener("click", async () => {
        skipBtn.disabled = true;
        try {
            if (!sendStageCommand("skip")) {
                await skipCurrentSong();
                await refreshStageState();
            }
        } catch (error) {
            console.error("Skip failed:", error);
        } finally {
            skipBtn.disabled = false;
        }
    });
}

if (forceResyncBtn) {
    forceResyncBtn.addEventListener("click", async () => {
        forceResyncBtn.disabled = true;
        try {
            await forceResyncPlayback();
        } finally {
            forceResyncBtn.disabled = false;
        }
    });
}

if (lyricsToggleBtn) {
    lyricsToggleBtn.addEventListener("click", () => {
        if (!lyricsState.available) {
            return;
        }
        const nextEnabled = !lyricsState.enabled;
        const sent = sendStageCommand("set_lyrics_enabled", { lyrics_enabled: nextEnabled });
        if (!sent) {
            setLyricsEnabled(nextEnabled);
        }
    });
}

if (qrToggleBtn) {
    qrToggleBtn.addEventListener("click", () => {
        if (!isQrVisible) {
            updateQrOverlayContent();
        }
        setQrOverlayVisible(!isQrVisible);
    });
}

if (qrCloseBtn) {
    qrCloseBtn.addEventListener("click", (event) => {
        event.stopPropagation();
        setQrOverlayVisible(false);
        scheduleHideStageControls();
    });
}

if (qrSizeDecreaseBtn) {
    qrSizeDecreaseBtn.addEventListener("click", () => {
        changeQrSize(-16);
    });
}

if (qrSizeIncreaseBtn) {
    qrSizeIncreaseBtn.addEventListener("click", () => {
        changeQrSize(16);
    });
}

if (qrOverlay) {
    qrOverlay.addEventListener("pointerdown", beginQrDrag);
    qrOverlay.addEventListener("pointermove", updateQrDrag);
    qrOverlay.addEventListener("pointerup", endQrDrag);
    qrOverlay.addEventListener("pointercancel", endQrDrag);
}

if (zenToggleBtn) {
    zenToggleBtn.addEventListener("click", () => {
        if (!stageControls || !isFullscreenActive()) return;
        setZenModeEnabled(!zenModeEnabled);
    });
}

if (shortcutsBtn) {
    shortcutsBtn.addEventListener("click", () => {
        toggleShortcutsPanel();
    });
}

if (fullscreenBtn) {
    fullscreenBtn.addEventListener("click", async () => {
        try {
            if (document.fullscreenElement) {
                await document.exitFullscreen();
            } else {
                if (stageMedia && stageMedia.requestFullscreen) {
                    await stageMedia.requestFullscreen({
                        navigationUI: "hide",
                    });
                }
            }
        } catch (error) {
            console.error("Fullscreen toggle failed:", error);
        } finally {
            updateFullscreenUi();
        }
    });
}

if (stageMedia) {
    stageMedia.addEventListener("mousemove", showStageControls);
    stageMedia.addEventListener("mouseenter", showStageControls);
    stageMedia.addEventListener("touchstart", showStageControls, { passive: true });
    stageMedia.addEventListener("focusin", showStageControls);
    stageMedia.addEventListener("mouseleave", scheduleHideStageControls);
}

window.addEventListener("resize", () => {
    applyQrOverlayPlacement();
});

document.addEventListener("fullscreenchange", () => {
    window.setTimeout(() => {
        applyQrOverlayPlacement();
    }, 0);
});

if (vocalsAudio) {
    vocalsAudio.addEventListener("error", () => {
        vocalsAvailable = false;
        vocalsPlaybackSupported = false;
        updateIosVocalsWarning();
        updateVocalsUi();
        stopSyncTimer();
    });
    vocalsAudio.addEventListener("ended", () => {
        syncVocalsToVideo(true);
    });
}

if (iosVocalsWarningClose) {
    iosVocalsWarningClose.addEventListener("click", dismissIosVocalsWarning);
}

window.addEventListener("keydown", async (event) => {
    const target = event.target;
    const isTypingTarget = target instanceof HTMLElement && (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.tagName === "SELECT" ||
        target.isContentEditable
    );

    if (isTypingTarget || event.metaKey || event.ctrlKey || event.altKey) {
        return;
    }

    if (event.key === "Escape" && shortcutsPanelVisible) {
        event.preventDefault();
        setShortcutsPanelVisible(false);
        scheduleHideStageControls();
        return;
    }

    if (event.key === "Escape" && stageLyrics.settingsPanelVisible) {
        event.preventDefault();
        stageLyrics.setSettingsPanelVisible(false);
        scheduleHideStageControls();
        return;
    }

    if (event.key === "Escape" && isQrVisible) {
        event.preventDefault();
        setQrOverlayVisible(false);
        scheduleHideStageControls();
        return;
    }

    if (event.code === "ArrowLeft") {
        event.preventDefault();
        await seekByOffset(-5);
        return;
    }

    if (event.code === "ArrowRight") {
        event.preventDefault();
        await seekByOffset(5);
        return;
    }

    if (event.key.toLowerCase() === "r") {
        event.preventDefault();
        if (forceResyncBtn) {
            forceResyncBtn.click();
        }
        return;
    }

    if (event.key.toLowerCase() === "v") {
        event.preventDefault();
        if (vocalsToggleBtn) {
            vocalsToggleBtn.click();
        }
        return;
    }

    if (event.key.toLowerCase() === "l") {
        event.preventDefault();
        if (lyricsToggleBtn) {
            lyricsToggleBtn.click();
        }
        return;
    }

    if (event.key.toLowerCase() === "s") {
        event.preventDefault();
        if (lyricsSettingsBtn) {
            lyricsSettingsBtn.click();
        }
        return;
    }

    if (event.key.toLowerCase() === "q") {
        event.preventDefault();
        if (qrToggleBtn) {
            qrToggleBtn.click();
        }
        return;
    }

    if (event.key === "?" || (event.shiftKey && event.code === "Slash")) {
        event.preventDefault();
        toggleShortcutsPanel();
        return;
    }

    if (event.code === "Space") {
        event.preventDefault();
        const primary = getPrimaryPlayer();
        if (primary) {
            if (primary.paused) {
                await playPrimary();
            } else {
                pausePrimary();
            }
        }
        return;
    }

    if (event.key.toLowerCase() === "f") {
        event.preventDefault();
        if (document.fullscreenElement) {
            await document.exitFullscreen();
        } else if (stageMedia && stageMedia.requestFullscreen) {
            await stageMedia.requestFullscreen({ navigationUI: "hide" });
        }
        return;
    }

    if (event.key === "Escape" && document.fullscreenElement) {
        event.preventDefault();
        await document.exitFullscreen();
    }

    if (event.key.toLowerCase() === "z") {
        event.preventDefault();
        if (isFullscreenActive()) {
            setZenModeEnabled(!zenModeEnabled);
        }
    }
});

document.addEventListener("fullscreenchange", () => {
    syncFullscreenState();
    updateFullscreenUi();
    if (lyricsState.enabled) {
        stageLyrics.resetActiveState();
        updateLyricsForTime(getPrimaryCurrentTime());
    } else {
        setLyricsOverlayVisible(false);
    }
    if (!isFullscreenActive()) {
        stageControls?.classList.remove("hidden");
    }
});
syncFullscreenState();
updateFullscreenUi();
currentPrimaryKind = mediaKindFromItem(INITIAL_CURRENT_ITEM);
currentPrimarySrc = INITIAL_CURRENT_ITEM?.media_path || STAGE_LOBBY_MEDIA_URL;
currentItem = INITIAL_CURRENT_ITEM;
currentLyricsKind = INITIAL_CURRENT_ITEM?.lyrics_path ? lyricsKindFromPath(INITIAL_CURRENT_ITEM.lyrics_path) : null;
currentLyricsSrc = INITIAL_CURRENT_ITEM?.lyrics_path || "";
syncLyricsRendererVisibility();
updateAudioArtwork(INITIAL_CURRENT_ITEM);
updateVocalsUi();
updateLyricsUi();
updatePlaybarUi();
updateQrOverlayContent();
updateShortcutsUi();
connectStageWebSocket();
window.KaraokeWebSocketLifecycle?.installPageLifecycle({
    onVisible: () => handleStageVisibleResume(),
    onOnline: () => handleStageVisibleResume(),
    onPageShow: (event) => handleStageVisibleResume(event),
    onPageHide: () => handleStagePageHide(),
});
updateNowPlayingMeta(INITIAL_CURRENT_ITEM);
updatePlaybackModeFlags(INITIAL_CURRENT_ITEM);
refreshStageState().catch((error) => {
    console.warn("Failed to refresh initial stage state:", error);
});
