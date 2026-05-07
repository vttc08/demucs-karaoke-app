const appUrl = window.KaraokeURLs?.appUrl || ((path) => path);
const t = window.KaraokeI18n?.t?.bind(window.KaraokeI18n) || ((key, params = {}) => key);
const SETTINGS_API = appUrl("/api/settings/");
const DEMUCS_HEALTH_API = appUrl("/api/settings/demucs-health");
const YTDLP_VERSION_API = appUrl("/api/settings/ytdlp/version");
const YTDLP_UPDATE_API = appUrl("/api/settings/ytdlp/update");
const form = document.getElementById("settings-form");
const saveBtn = document.getElementById("save-settings-btn");
const reloadBtn = document.getElementById("reload-settings-btn");
const statusEl = document.getElementById("settings-status");
const saveFeedback = document.getElementById("save-feedback");
const saveFeedbackIcon = document.getElementById("save-feedback-icon");
const saveFeedbackText = document.getElementById("save-feedback-text");
const refreshYtdlpVersionBtn = document.getElementById("refresh-ytdlp-version-btn");
const updateYtdlpBtn = document.getElementById("update-ytdlp-btn");
const ytdlpVersionText = document.getElementById("ytdlp-version-text");
const ytdlpUpdateStatus = document.getElementById("ytdlp-update-status");
const engineStatusDot = document.getElementById("engine-status-dot");
const engineStatusText = document.getElementById("engine-status-text");
const lastSyncText = document.getElementById("last-sync-text");
const demucsMp3BitrateGroup = document.getElementById("demucs-mp3-bitrate-group");
const ENGINE_STATUS_STORAGE_KEY = "karaoke.engineStatus";
let saveFeedbackTimer = null;

const fields = {
    demucs_api_url: document.getElementById("demucs_api_url"),
    demucs_model: document.getElementById("demucs_model"),
    demucs_device: document.getElementById("demucs_device"),
    demucs_output_format: document.getElementById("demucs_output_format"),
    demucs_mp3_bitrate: document.getElementById("demucs_mp3_bitrate"),
    ffmpeg_preset: document.getElementById("ffmpeg_preset"),
    ffmpeg_crf: document.getElementById("ffmpeg_crf"),
    media_path: document.getElementById("media_path"),
    cache_path: document.getElementById("cache_path"),
    ytdlp_path: document.getElementById("ytdlp_path"),
    ytdlp_proxy_url: document.getElementById("ytdlp_proxy_url"),
    concurrent_ytdlp_search_enabled: document.getElementById("concurrent_ytdlp_search_enabled"),
    lyrics_provider_netease_enabled: document.getElementById("lyrics_provider_netease_enabled"),
    lyrics_provider_lrclib_enabled: document.getElementById("lyrics_provider_lrclib_enabled"),
    ffmpeg_path: document.getElementById("ffmpeg_path"),
    stage_qr_url: document.getElementById("stage_qr_url"),
    stage_lobby_media_path: document.getElementById("stage_lobby_media_path"),
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

function setYtdlpStatus(message, isError = false) {
    if (!ytdlpUpdateStatus) {
        return;
    }
    ytdlpUpdateStatus.textContent = message;
    ytdlpUpdateStatus.classList.toggle("text-error", isError);
    ytdlpUpdateStatus.classList.toggle("text-on-surface-variant", !isError);
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

function applySettingsToForm(data) {
    fields.demucs_api_url.value = data.demucs_api_url || "";
    fields.demucs_model.value = data.demucs_model || "htdemucs";
    fields.demucs_device.value = data.demucs_device || "cuda";
    fields.demucs_output_format.value = data.demucs_output_format || "wav";
    fields.demucs_mp3_bitrate.value = String(data.demucs_mp3_bitrate ?? 320);
    fields.ffmpeg_preset.value = data.ffmpeg_preset || "veryfast";
    fields.ffmpeg_crf.value = String(data.ffmpeg_crf ?? 23);
    fields.media_path.value = data.media_path || "";
    fields.cache_path.value = data.cache_path || "";
    fields.ytdlp_path.value = data.ytdlp_path || "";
    fields.ytdlp_proxy_url.value = data.ytdlp_proxy_url || "";
    fields.concurrent_ytdlp_search_enabled.checked = Boolean(data.concurrent_ytdlp_search_enabled);
    fields.lyrics_provider_netease_enabled.checked = Boolean(data.lyrics_provider_netease_enabled ?? true);
    fields.lyrics_provider_lrclib_enabled.checked = Boolean(data.lyrics_provider_lrclib_enabled ?? true);
    fields.ffmpeg_path.value = data.ffmpeg_path || "";
    if (fields.stage_qr_url) {
        fields.stage_qr_url.value = data.stage_qr_url || "";
    }
    if (fields.stage_lobby_media_path) {
        fields.stage_lobby_media_path.value = data.stage_lobby_media_path || "";
    }
    updateDemucsOutputUi();
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
        demucs_model: fields.demucs_model.value,
        demucs_device: fields.demucs_device.value,
        demucs_output_format: fields.demucs_output_format.value,
        ffmpeg_preset: fields.ffmpeg_preset.value,
        ffmpeg_crf: Number(fields.ffmpeg_crf.value),
        media_path: fields.media_path.value.trim(),
        cache_path: fields.cache_path.value.trim(),
        ytdlp_path: fields.ytdlp_path.value.trim(),
        ytdlp_proxy_url: fields.ytdlp_proxy_url.value.trim(),
        concurrent_ytdlp_search_enabled: fields.concurrent_ytdlp_search_enabled.checked,
        lyrics_provider_netease_enabled: fields.lyrics_provider_netease_enabled.checked,
        lyrics_provider_lrclib_enabled: fields.lyrics_provider_lrclib_enabled.checked,
        ffmpeg_path: fields.ffmpeg_path.value.trim(),
        stage_qr_url: fields.stage_qr_url ? fields.stage_qr_url.value.trim() : "",
        stage_lobby_media_path: fields.stage_lobby_media_path ? fields.stage_lobby_media_path.value.trim() : "",
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
if (refreshYtdlpVersionBtn) {
    refreshYtdlpVersionBtn.addEventListener("click", checkYtdlpVersion);
}
if (updateYtdlpBtn) {
    updateYtdlpBtn.addEventListener("click", updateYtdlp);
}

const persistedState = readPersistedEngineStatus();
if (persistedState?.state && persistedState?.detail) {
    setEngineStatus(persistedState.state, persistedState.detail, false);
}

loadSettings();
checkYtdlpVersion();
