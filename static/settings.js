const appUrl = window.KaraokeURLs?.appUrl || ((path) => path);
const t = window.KaraokeI18n?.t?.bind(window.KaraokeI18n) || ((key, params = {}) => key);
const SETTINGS_API = appUrl("/api/settings/");
const DEMUCS_HEALTH_API = appUrl("/api/settings/demucs-health");
const STORAGE_USAGE_API = appUrl("/api/settings/storage-usage");
const STORAGE_CLEANUP_API = appUrl("/api/settings/storage-cleanup");
const DEMUCS_GC_API = appUrl("/api/settings/demucs/gc");
const PROXY_INFO_API = appUrl("/api/settings/proxy-info");
const YTDLP_VERSION_API = appUrl("/api/settings/ytdlp/version");
const YTDLP_UPDATE_API = appUrl("/api/settings/ytdlp/update");
const WHISPERX_PRELOAD_API = appUrl("/api/settings/whisperx/preload");
const form = document.getElementById("settings-form");
const saveBtn = document.getElementById("save-settings-btn");
const reloadBtn = document.getElementById("reload-settings-btn");
const statusEl = document.getElementById("settings-status");
const saveFeedback = document.getElementById("save-feedback");
const saveFeedbackIcon = document.getElementById("save-feedback-icon");
const saveFeedbackText = document.getElementById("save-feedback-text");
const refreshYtdlpVersionBtn = document.getElementById("refresh-ytdlp-version-btn");
const updateYtdlpBtn = document.getElementById("update-ytdlp-btn");
const preloadWhisperxBtn = document.getElementById("preload-whisperx-btn");
const proxyInfoBtn = document.getElementById("check-proxy-info-btn");
const ytdlpVersionText = document.getElementById("ytdlp-version-text");
const ytdlpUpdateStatus = document.getElementById("ytdlp-update-status");
const whisperxPreloadStatus = document.getElementById("whisperx-preload-status");
const proxyInfoStatus = document.getElementById("proxy-info-status");
const proxyInfoIpText = document.getElementById("proxy-info-ip-text");
const proxyInfoOrgText = document.getElementById("proxy-info-org-text");
const proxyInfoLocationText = document.getElementById("proxy-info-location-text");
const checkStorageUsageBtn = document.getElementById("check-storage-usage-btn");
const storageUsageStatus = document.getElementById("storage-usage-status");
const storageUsageMediaText = document.getElementById("storage-usage-media-text");
const storageUsageCacheText = document.getElementById("storage-usage-cache-text");
const storageUsageDatabaseText = document.getElementById("storage-usage-database-text");
const storageUsageDatabaseNote = document.getElementById("storage-usage-database-note");
const storageUsageTotalText = document.getElementById("storage-usage-total-text");
const storageCleanupBtn = document.getElementById("cleanup-storage-btn");
const storageCleanupStatus = document.getElementById("storage-cleanup-status");
const whisperxAlignLanguageGroup = document.getElementById("whisperx-align-language-group");
const engineStatusDot = document.getElementById("engine-status-dot");
const engineStatusText = document.getElementById("engine-status-text");
const lastSyncText = document.getElementById("last-sync-text");
const demucsGcBtn = document.getElementById("demucs-gc-btn");
const demucsGcStatus = document.getElementById("demucs-gc-status");
const demucsMp3BitrateGroup = document.getElementById("demucs-mp3-bitrate-group");
const ENGINE_STATUS_STORAGE_KEY = "karaoke.engineStatus";
let saveFeedbackTimer = null;

const fields = {
    demucs_api_url: document.getElementById("demucs_api_url"),
    demucs_api_key: document.getElementById("demucs_api_key"),
    demucs_model: document.getElementById("demucs_model"),
    demucs_device: document.getElementById("demucs_device"),
    demucs_output_format: document.getElementById("demucs_output_format"),
    demucs_mp3_bitrate: document.getElementById("demucs_mp3_bitrate"),
    demucs_direct_media_max_mb: document.getElementById("demucs_direct_media_max_mb"),
    demucs_poll_interval_seconds: document.getElementById("demucs_poll_interval_seconds"),
    whisperx_transcription_model: document.getElementById("whisperx_transcription_model"),
    whisperx_align_language: document.getElementById("whisperx_align_language"),
    whisperx_detect_language: document.getElementById("whisperx_detect_language"),
    whisperx_use_synced_lyrics: document.getElementById("whisperx_use_synced_lyrics"),
    whisperx_preload_models: document.getElementById("whisperx_preload_models"),
    media_path: document.getElementById("media_path"),
    cache_path: document.getElementById("cache_path"),
    ytdlp_path: document.getElementById("ytdlp_path"),
    ytdlp_deno_path: document.getElementById("ytdlp_deno_path"),
    ytdlp_proxy_url: document.getElementById("ytdlp_proxy_url"),
    ytdlp_video_resolution: document.getElementById("ytdlp_video_resolution"),
    ytdlp_video_codec: document.getElementById("ytdlp_video_codec"),
    concurrent_ytdlp_search_enabled: document.getElementById("concurrent_ytdlp_search_enabled"),
    lyrics_provider_netease_enabled: document.getElementById("lyrics_provider_netease_enabled"),
    lyrics_provider_lrclib_enabled: document.getElementById("lyrics_provider_lrclib_enabled"),
    ffmpeg_path: document.getElementById("ffmpeg_path"),
    ffmpeg_audio_codec: document.getElementById("ffmpeg_audio_codec"),
    stage_qr_url: document.getElementById("stage_qr_url"),
    stage_lobby_media_path: document.getElementById("stage_lobby_media_path"),
    stage_vocals_volume_default: document.getElementById("stage_vocals_volume_default"),
};

function setStatus(message, isError = false) {
    if (statusEl) {
        statusEl.textContent = message;
        statusEl.classList.toggle("text-error", isError);
        statusEl.classList.toggle("text-secondary", !isError);
    }
}

function showSaveFeedback(message, isError = false) {
    if (!saveFeedback || !saveFeedbackText || !saveFeedbackIcon) {
        return;
    }

    if (saveFeedbackTimer) {
        clearTimeout(saveFeedbackTimer);
        saveFeedbackTimer = null;
    }

    saveFeedbackText.textContent = message;
    saveFeedbackIcon.textContent = isError ? "error" : "check_circle";
    saveFeedbackIcon.classList.toggle("text-error", isError);
    saveFeedbackIcon.classList.toggle("text-primary", !isError);
    saveFeedback.classList.toggle("border-error/40", isError);
    saveFeedback.classList.toggle("border-primary/30", !isError);

    saveFeedback.classList.remove("opacity-0", "translate-y-3");
    saveFeedback.classList.add("opacity-100", "translate-y-0");

    saveFeedbackTimer = setTimeout(() => {
        saveFeedback.classList.remove("opacity-100", "translate-y-0");
        saveFeedback.classList.add("opacity-0", "translate-y-3");
    }, 2800);
}

function formatBytes(bytes) {
    const value = Number(bytes);
    if (!Number.isFinite(value) || value < 0) {
        return "0 B";
    }
    const units = ["B", "KiB", "MiB", "GiB", "TiB"];
    let amount = value;
    let unitIndex = 0;
    while (amount >= 1024 && unitIndex < units.length - 1) {
        amount /= 1024;
        unitIndex += 1;
    }
    return unitIndex === 0 ? `${Math.round(amount)} ${units[unitIndex]}` : `${amount.toFixed(1)} ${units[unitIndex]}`;
}

function persistEngineStatus(state, detail) {
    try {
        localStorage.setItem(
            ENGINE_STATUS_STORAGE_KEY,
            JSON.stringify({state, detail}),
        );
    } catch (_) {
        // Keep UX functional even when storage is unavailable.
    }
}

function readPersistedEngineStatus() {
    try {
        const raw = localStorage.getItem(ENGINE_STATUS_STORAGE_KEY);
        return raw ? JSON.parse(raw) : null;
    } catch (_) {
        return null;
    }
}

function setEngineStatus(state, detail, persist = true) {
    if (!engineStatusText || !lastSyncText || !engineStatusDot) {
        return;
    }

    if (state === "online") {
        engineStatusText.textContent = t("settings.engine_online");
    } else if (state === "offline") {
        engineStatusText.textContent = t("settings.engine_offline");
    } else if (state === "checking") {
        engineStatusText.textContent = t("settings.engine_checking");
    } else {
        engineStatusText.textContent = t("settings.engine_unknown");
    }

    engineStatusDot.classList.remove("bg-primary", "bg-error", "bg-warning", "bg-outline");
    if (state === "online") {
        engineStatusDot.classList.add("bg-primary");
    } else if (state === "offline") {
        engineStatusDot.classList.add("bg-error");
    } else if (state === "checking") {
        engineStatusDot.classList.add("bg-warning");
    } else {
        engineStatusDot.classList.add("bg-outline");
    }

    lastSyncText.textContent = detail;
    if (persist && (state === "online" || state === "offline" || state === "unknown")) {
        persistEngineStatus(state, detail);
    }
}

function applyDemucsHealthToUI(health, persist = true) {
    const detail = health.detail || (health.healthy ? t("settings.healthy") : t("settings.unavailable"));
    setEngineStatus(health.healthy ? "online" : "offline", detail, persist);
}

function setFormState(disabled) {
    saveBtn.disabled = disabled;
    if (preloadWhisperxBtn) {
        preloadWhisperxBtn.disabled = disabled;
    }
    if (proxyInfoBtn) {
        proxyInfoBtn.disabled = disabled;
    }
    if (checkStorageUsageBtn) {
        checkStorageUsageBtn.disabled = disabled;
    }
    if (storageCleanupBtn) {
        storageCleanupBtn.disabled = disabled;
    }
    if (demucsGcBtn) {
        demucsGcBtn.disabled = disabled;
    }
    Object.values(fields).forEach((field) => {
        field.disabled = disabled;
    });
}

function setYtdlpActionsState(disabled) {
    if (refreshYtdlpVersionBtn) {
        refreshYtdlpVersionBtn.disabled = disabled;
    }
    if (updateYtdlpBtn) {
        updateYtdlpBtn.disabled = disabled;
    }
}

function setWhisperxPreloadState(disabled) {
    if (preloadWhisperxBtn) {
        preloadWhisperxBtn.disabled = disabled;
    }
}

function setYtdlpStatus(message, isError = false) {
    if (!ytdlpUpdateStatus) {
        return;
    }
    ytdlpUpdateStatus.textContent = message;
    ytdlpUpdateStatus.classList.toggle("text-error", isError);
    ytdlpUpdateStatus.classList.toggle("text-on-surface-variant", !isError);
}

function setWhisperxPreloadStatus(message, isError = false) {
    if (!whisperxPreloadStatus) {
        return;
    }
    whisperxPreloadStatus.textContent = message;
    whisperxPreloadStatus.classList.toggle("text-error", isError);
    whisperxPreloadStatus.classList.toggle("text-on-surface-variant", !isError);
}

function setProxyInfoStatus(message, isError = false) {
    if (!proxyInfoStatus) {
        return;
    }
    proxyInfoStatus.textContent = message;
    proxyInfoStatus.classList.toggle("text-error", isError);
    proxyInfoStatus.classList.toggle("text-on-surface-variant", !isError);
}

function setStorageUsageStatus(message, isError = false) {
    if (!storageUsageStatus) {
        return;
    }
    storageUsageStatus.textContent = message;
    storageUsageStatus.classList.toggle("text-error", isError);
    storageUsageStatus.classList.toggle("text-on-surface-variant", !isError);
}

function setStorageCleanupStatus(message, isError = false) {
    if (!storageCleanupStatus) {
        return;
    }
    storageCleanupStatus.textContent = message;
    storageCleanupStatus.classList.toggle("text-error", isError);
    storageCleanupStatus.classList.toggle("text-on-surface-variant", !isError);
}

function setDemucsGcStatus(message, isError = false) {
    if (!demucsGcStatus) {
        return;
    }
    demucsGcStatus.textContent = message;
    demucsGcStatus.classList.toggle("text-error", isError);
    demucsGcStatus.classList.toggle("text-on-surface-variant", !isError);
}

function setProxyInfoValues(data) {
    if (proxyInfoIpText) {
        proxyInfoIpText.textContent = data?.ip || t("common.unknown");
    }
    if (proxyInfoOrgText) {
        proxyInfoOrgText.textContent = data?.org || t("common.unknown");
    }
    if (proxyInfoLocationText) {
        const city = data?.city || "";
        const country = data?.country || "";
        proxyInfoLocationText.textContent = city && country
            ? `${city}, ${country}`
            : city || country || t("common.unknown");
    }
}

function resetProxyInfoDisplay() {
    setProxyInfoValues({});
    setProxyInfoStatus(t("settings.proxy_info_idle"));
}

function setStorageUsageValues(data) {
    if (storageUsageMediaText) {
        storageUsageMediaText.textContent = data?.media_display || t("common.unknown");
    }
    if (storageUsageCacheText) {
        storageUsageCacheText.textContent = data?.cache_display || t("common.unknown");
    }
    if (storageUsageDatabaseText) {
        storageUsageDatabaseText.textContent = data?.database_available
            ? (data.database_display || t("common.unknown"))
            : t("common.na");
    }
    if (storageUsageDatabaseNote) {
        storageUsageDatabaseNote.textContent = data?.database_available
            ? ""
            : t("settings.storage_usage_database_note");
        storageUsageDatabaseNote.classList.toggle("hidden", Boolean(data?.database_available));
    }
    if (storageUsageTotalText) {
        storageUsageTotalText.textContent = data?.total_display || t("common.unknown");
    }
}

function setWhisperxAlignLanguageState(disabled) {
    const field = fields.whisperx_align_language;
    if (!field) {
        return;
    }

    field.disabled = disabled;
    if (whisperxAlignLanguageGroup) {
        whisperxAlignLanguageGroup.classList.toggle("opacity-60", disabled);
    }
}

function updateWhisperxLanguageUi() {
    setWhisperxAlignLanguageState(Boolean(fields.whisperx_detect_language?.checked));
}

async function checkYtdlpVersion() {
    if (!ytdlpVersionText) {
        return;
    }
    setYtdlpActionsState(true);
    setYtdlpStatus(t("settings.checking_ytdlp"));
    try {
        const response = await fetch(YTDLP_VERSION_API);
        if (!response.ok) {
            const errorPayload = await response.json();
            throw new Error(errorPayload.detail || t("settings.check_ytdlp_failed"));
        }
        const data = await response.json();
        ytdlpVersionText.textContent = data.version;
        setYtdlpStatus(t("settings.current_version", { version: data.version }));
    } catch (error) {
        setYtdlpStatus(String(error.message || t("settings.check_ytdlp_failed")), true);
    } finally {
        setYtdlpActionsState(false);
    }
}

async function updateYtdlp() {
    if (!ytdlpVersionText) {
        return;
    }
    setYtdlpActionsState(true);
    setYtdlpStatus(t("settings.updating_ytdlp"));
    try {
        const response = await fetch(YTDLP_UPDATE_API, {method: "POST"});
        if (!response.ok) {
            const errorPayload = await response.json();
            throw new Error(errorPayload.detail || t("settings.update_ytdlp_failed"));
        }
        const data = await response.json();
        ytdlpVersionText.textContent = data.after_version;
        if (data.updated) {
            setYtdlpStatus(t("settings.updated_ytdlp", { before: data.before_version, after: data.after_version }));
            showSaveFeedback(t("settings.updated_ytdlp_success"), false);
        } else {
            setYtdlpStatus(t("settings.already_current_version", { version: data.after_version }));
            showSaveFeedback(t("settings.ytdlp_already_current"), false);
        }
    } catch (error) {
        setYtdlpStatus(String(error.message || t("settings.update_ytdlp_failed")), true);
        showSaveFeedback(String(error.message || t("settings.update_ytdlp_failed")), true);
    } finally {
        setYtdlpActionsState(false);
    }
}

async function preloadWhisperxModels() {
    if (!fields.whisperx_preload_models) {
        return;
    }

    setWhisperxPreloadState(true);
    setWhisperxPreloadStatus(t("settings.preloading_whisperx_models"));
    try {
        const response = await fetch(WHISPERX_PRELOAD_API, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                whisperx_preload_models: fields.whisperx_preload_models.value.trim(),
            }),
        });
        if (!response.ok) {
            const errorPayload = await response.json();
            throw new Error(errorPayload.detail || t("settings.preload_whisperx_models_failed"));
        }
        const data = await response.json();
        const loadedCount = Array.isArray(data.loaded_entries) ? data.loaded_entries.length : 0;
        setWhisperxPreloadStatus(
            t("settings.preloaded_whisperx_models", {
                count: loadedCount,
                detail: data.detail || t("settings.preloaded_whisperx_models_default_detail"),
            }),
        );
        showSaveFeedback(
            t("settings.preloaded_whisperx_models_feedback", { count: loadedCount }),
            false,
        );
    } catch (error) {
        const message = String(error.message || t("settings.preload_whisperx_models_failed"));
        setWhisperxPreloadStatus(message, true);
        showSaveFeedback(message, true);
    } finally {
        setWhisperxPreloadState(false);
    }
}

async function triggerDemucsGarbageCollection() {
    if (!demucsGcBtn) {
        return;
    }

    demucsGcBtn.disabled = true;
    setDemucsGcStatus(t("settings.demucs_gc_running"));
    try {
        const response = await fetch(DEMUCS_GC_API, {
            method: "POST",
        });
        if (!response.ok) {
            const errorPayload = await response.json();
            throw new Error(errorPayload.detail || t("settings.demucs_gc_failed"));
        }
        const data = await response.json();
        setDemucsGcStatus(
            t("settings.demucs_gc_done", {
                mode: data.executed_mode || t("settings.demucs_gc_mode_unknown"),
                detail: data.detail || t("settings.demucs_gc_done_default"),
            }),
        );
        showSaveFeedback(
            t("settings.demucs_gc_feedback", {
                mode: data.executed_mode || t("settings.demucs_gc_mode_unknown"),
            }),
            false,
        );
    } catch (error) {
        const message = String(error.message || t("settings.demucs_gc_failed"));
        setDemucsGcStatus(message, true);
        showSaveFeedback(message, true);
    } finally {
        demucsGcBtn.disabled = false;
    }
}

async function checkProxyInfo() {
    if (!proxyInfoBtn || !fields.ytdlp_proxy_url) {
        return;
    }

    const proxyUrl = fields.ytdlp_proxy_url.value.trim();
    if (!proxyUrl) {
        setProxyInfoStatus(t("settings.proxy_info_requires_proxy"), true);
        return;
    }

    proxyInfoBtn.disabled = true;
    setProxyInfoStatus(t("settings.proxy_info_loading"));
    try {
        const response = await fetch(PROXY_INFO_API, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({proxy_url: proxyUrl}),
        });
        if (!response.ok) {
            const errorPayload = await response.json();
            throw new Error(errorPayload.detail || t("settings.proxy_info_failed"));
        }
        const data = await response.json();
        setProxyInfoValues(data);
        setProxyInfoStatus(data.detail || t("settings.proxy_info_loaded"));
    } catch (error) {
        setProxyInfoStatus(String(error.message || t("settings.proxy_info_failed")), true);
    } finally {
        proxyInfoBtn.disabled = false;
    }
}

async function checkStorageUsage() {
    if (!checkStorageUsageBtn) {
        return;
    }

    checkStorageUsageBtn.disabled = true;
    setStorageUsageStatus(t("settings.storage_usage_loading"));
    try {
        const response = await fetch(STORAGE_USAGE_API);
        if (!response.ok) {
            const errorPayload = await response.json();
            throw new Error(errorPayload.detail || t("settings.storage_usage_failed"));
        }
        const data = await response.json();
        setStorageUsageValues(data);
        setStorageUsageStatus(t("settings.storage_usage_loaded"));
    } catch (error) {
        setStorageUsageStatus(String(error.message || t("settings.storage_usage_failed")), true);
    } finally {
        checkStorageUsageBtn.disabled = false;
    }
}

async function cleanupStorage() {
    if (!storageCleanupBtn) {
        return;
    }

    storageCleanupBtn.disabled = true;
    setStorageCleanupStatus(t("settings.storage_cleanup_running"));
    try {
        const response = await fetch(STORAGE_CLEANUP_API, {
            method: "POST",
        });
        if (!response.ok) {
            const errorPayload = await response.json();
            throw new Error(errorPayload.detail || t("settings.storage_cleanup_failed"));
        }
        const data = await response.json();
        setStorageCleanupStatus(
            t("settings.storage_cleanup_done", {
                cache_files: data.cache_deleted_files ?? 0,
                cache_bytes: formatBytes(data.cache_deleted_bytes ?? 0),
                tasks: data.db_deleted_done_tasks ?? 0,
                missing_media: data.db_deleted_missing_media_items ?? 0,
            }),
        );
        showSaveFeedback(
            t("settings.storage_cleanup_feedback", {
                cache_files: data.cache_deleted_files ?? 0,
                missing_media: data.db_deleted_missing_media_items ?? 0,
            }),
            false,
        );
        await checkStorageUsage();
    } catch (error) {
        setStorageCleanupStatus(String(error.message || t("settings.storage_cleanup_failed")), true);
        showSaveFeedback(String(error.message || t("settings.storage_cleanup_failed")), true);
    } finally {
        storageCleanupBtn.disabled = false;
    }
}

function applySettingsToForm(data) {
    fields.demucs_api_url.value = data.demucs_api_url || "";
    fields.demucs_api_key.value = data.demucs_api_key || "";
    fields.demucs_model.value = data.demucs_model || "htdemucs";
    fields.demucs_device.value = data.demucs_device || "cuda";
    fields.demucs_output_format.value = data.demucs_output_format || "wav";
    fields.demucs_mp3_bitrate.value = String(data.demucs_mp3_bitrate ?? 320);
    fields.demucs_direct_media_max_mb.value = String(data.demucs_direct_media_max_mb ?? 500);
    fields.demucs_poll_interval_seconds.value = String(data.demucs_poll_interval_seconds ?? 1.0);
    fields.whisperx_transcription_model.value = data.whisperx_transcription_model || "tiny";
    fields.whisperx_align_language.value = data.whisperx_align_language || "en";
    fields.whisperx_detect_language.checked = Boolean(data.whisperx_detect_language);
    fields.whisperx_use_synced_lyrics.checked = Boolean(data.whisperx_use_synced_lyrics);
    fields.whisperx_preload_models.value = data.whisperx_preload_models || "transcription=tiny,align=en";
    fields.media_path.value = data.media_path || "";
    fields.cache_path.value = data.cache_path || "";
    fields.ytdlp_path.value = data.ytdlp_path || "";
    fields.ytdlp_deno_path.value = data.ytdlp_deno_path || "";
    fields.ytdlp_proxy_url.value = data.ytdlp_proxy_url || "";
    fields.ytdlp_video_resolution.value = data.ytdlp_video_resolution || "default";
    fields.ytdlp_video_codec.value = data.ytdlp_video_codec || "";
    fields.concurrent_ytdlp_search_enabled.checked = Boolean(data.concurrent_ytdlp_search_enabled);
    fields.lyrics_provider_netease_enabled.checked = Boolean(data.lyrics_provider_netease_enabled ?? true);
    fields.lyrics_provider_lrclib_enabled.checked = Boolean(data.lyrics_provider_lrclib_enabled ?? true);
    fields.ffmpeg_path.value = data.ffmpeg_path || "";
    fields.ffmpeg_audio_codec.value = data.ffmpeg_audio_codec || "";
    if (fields.stage_qr_url) {
        fields.stage_qr_url.value = data.stage_qr_url || "";
    }
    if (fields.stage_lobby_media_path) {
        fields.stage_lobby_media_path.value = data.stage_lobby_media_path || "";
    }
    if (fields.stage_vocals_volume_default) {
        const defaultVolume = Number(data.stage_vocals_volume_default);
        const normalizedVolume = Number.isFinite(defaultVolume) ? Math.max(0, Math.min(1, defaultVolume)) : 1.0;
        fields.stage_vocals_volume_default.value = String(Math.round(normalizedVolume * 100));
    }
    updateWhisperxLanguageUi();
    updateDemucsOutputUi();
    resetProxyInfoDisplay();
}

function updateDemucsOutputUi() {
    const isMp3 = fields.demucs_output_format.value === "mp3";
    if (demucsMp3BitrateGroup) {
        demucsMp3BitrateGroup.classList.toggle("opacity-60", !isMp3);
    }
    fields.demucs_mp3_bitrate.disabled = !isMp3;
    fields.demucs_mp3_bitrate.required = isMp3;
}

async function loadSettings() {
    setFormState(true);
    setStatus(t("settings.loading"));
    try {
        const response = await fetch(SETTINGS_API);
        if (!response.ok) {
            throw new Error(t("settings.load_failed"));
        }
        const data = await response.json();
        applySettingsToForm(data);
        setStatus(t("settings.loaded"));
        return true;
    } catch (error) {
        setStatus(error.message || t("settings.load_unable"), true);
        return false;
    } finally {
        setFormState(false);
    }
}

async function saveSettings() {
    if (!form.reportValidity()) {
        return;
    }

    setFormState(true);
    setStatus(t("settings.saving"));
    showSaveFeedback(t("settings.saving"), false);
    setEngineStatus("checking", t("settings.checking_demucs"), false);

    const payload = {
        demucs_api_url: fields.demucs_api_url.value.trim(),
        demucs_api_key: fields.demucs_api_key.value.trim(),
        demucs_model: fields.demucs_model.value,
        demucs_device: fields.demucs_device.value,
        demucs_output_format: fields.demucs_output_format.value,
        demucs_direct_media_max_mb: Number(fields.demucs_direct_media_max_mb.value),
        demucs_poll_interval_seconds: Number(fields.demucs_poll_interval_seconds.value),
        whisperx_transcription_model: fields.whisperx_transcription_model.value.trim(),
        whisperx_align_language: fields.whisperx_align_language.value.trim(),
        whisperx_detect_language: fields.whisperx_detect_language.checked,
        whisperx_use_synced_lyrics: fields.whisperx_use_synced_lyrics.checked,
        whisperx_preload_models: fields.whisperx_preload_models.value.trim(),
        media_path: fields.media_path.value.trim(),
        cache_path: fields.cache_path.value.trim(),
        ytdlp_path: fields.ytdlp_path.value.trim(),
        ytdlp_deno_path: fields.ytdlp_deno_path.value.trim(),
        ytdlp_proxy_url: fields.ytdlp_proxy_url.value.trim(),
        ytdlp_video_resolution: fields.ytdlp_video_resolution.value,
        ytdlp_video_codec: fields.ytdlp_video_codec.value.trim(),
        concurrent_ytdlp_search_enabled: fields.concurrent_ytdlp_search_enabled.checked,
        lyrics_provider_netease_enabled: fields.lyrics_provider_netease_enabled.checked,
        lyrics_provider_lrclib_enabled: fields.lyrics_provider_lrclib_enabled.checked,
        ffmpeg_path: fields.ffmpeg_path.value.trim(),
        ffmpeg_audio_codec: fields.ffmpeg_audio_codec.value.trim(),
        stage_qr_url: fields.stage_qr_url ? fields.stage_qr_url.value.trim() : "",
        stage_lobby_media_path: fields.stage_lobby_media_path ? fields.stage_lobby_media_path.value.trim() : "",
        stage_vocals_volume_default: fields.stage_vocals_volume_default
            ? Number(fields.stage_vocals_volume_default.value) / 100
            : 1.0,
    };
    if (fields.demucs_output_format.value === "mp3") {
        payload.demucs_mp3_bitrate = Number(fields.demucs_mp3_bitrate.value);
    }

    try {
        const response = await fetch(SETTINGS_API, {
            method: "PATCH",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            const errorPayload = await response.json();
            throw new Error(errorPayload.detail || t("settings.save_failed"));
        }
        const updated = await response.json();
        applySettingsToForm(updated);
        applyDemucsHealthToUI({
            healthy: Boolean(updated.demucs_healthy),
            detail: updated.demucs_health_detail,
        });
        setStatus(updated.demucs_healthy ? t("settings.saved") : t("settings.saved_demucs_offline"), !updated.demucs_healthy);
        showSaveFeedback(
            updated.demucs_healthy
                ? t("settings.saved_success")
                : t("settings.saved_offline_detail"),
            !updated.demucs_healthy,
        );
    } catch (error) {
        setStatus(error.message || t("settings.save_unable"), true);
        showSaveFeedback(String(error.message || t("settings.save_unable")), true);
        setEngineStatus("offline", String(error.message || t("settings.save_failed_short")));
    } finally {
        setFormState(false);
    }
}

async function refreshDemucsHealth() {
    setEngineStatus("checking", t("settings.checking_demucs"), false);
    try {
        const response = await fetch(DEMUCS_HEALTH_API);
        if (!response.ok) {
            throw new Error(t("settings.demucs_health_fetch_failed"));
        }
        const health = await response.json();
        applyDemucsHealthToUI(health);
    } catch (error) {
        applyDemucsHealthToUI({
            healthy: false,
            detail: String(error.message || t("settings.health_check_failed")),
        });
    }
}

async function reloadEngineStatus() {
    setStatus(t("settings.refreshing_status"));
    const loaded = await loadSettings();
    if (!loaded) {
        return;
    }
    await refreshDemucsHealth();
    setStatus(t("settings.status_refreshed"));
}

if (saveBtn) {
    saveBtn.addEventListener("click", saveSettings);
}
if (reloadBtn) {
    reloadBtn.addEventListener("click", reloadEngineStatus);
}
if (fields.demucs_output_format) {
    fields.demucs_output_format.addEventListener("change", updateDemucsOutputUi);
}
if (fields.whisperx_detect_language) {
    fields.whisperx_detect_language.addEventListener("change", updateWhisperxLanguageUi);
}
if (refreshYtdlpVersionBtn) {
    refreshYtdlpVersionBtn.addEventListener("click", checkYtdlpVersion);
}
if (updateYtdlpBtn) {
    updateYtdlpBtn.addEventListener("click", updateYtdlp);
}
if (preloadWhisperxBtn) {
    preloadWhisperxBtn.addEventListener("click", preloadWhisperxModels);
}
if (proxyInfoBtn) {
    proxyInfoBtn.addEventListener("click", checkProxyInfo);
}
if (checkStorageUsageBtn) {
    checkStorageUsageBtn.addEventListener("click", checkStorageUsage);
}
if (storageCleanupBtn) {
    storageCleanupBtn.addEventListener("click", cleanupStorage);
}
if (demucsGcBtn) {
    demucsGcBtn.addEventListener("click", triggerDemucsGarbageCollection);
}

const persistedState = readPersistedEngineStatus();
if (persistedState?.state && persistedState?.detail) {
    setEngineStatus(persistedState.state, persistedState.detail, false);
}

updateWhisperxLanguageUi();
loadSettings();
checkYtdlpVersion();
