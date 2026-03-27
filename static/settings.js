const SETTINGS_API = `${window.location.origin}/api/settings/`;
const DEMUCS_HEALTH_API = `${window.location.origin}/api/settings/demucs-health`;

const form = document.getElementById("settings-form");
const saveBtn = document.getElementById("save-settings-btn");
const reloadBtn = document.getElementById("reload-settings-btn");
const statusEl = document.getElementById("settings-status");
const saveFeedback = document.getElementById("save-feedback");
const saveFeedbackIcon = document.getElementById("save-feedback-icon");
const saveFeedbackText = document.getElementById("save-feedback-text");
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
    ffmpeg_path: document.getElementById("ffmpeg_path"),
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
        engineStatusText.textContent = "AI Engine: Online";
    } else if (state === "offline") {
        engineStatusText.textContent = "AI Engine: Offline";
    } else if (state === "checking") {
        engineStatusText.textContent = "AI Engine: Checking";
    } else {
        engineStatusText.textContent = "AI Engine: Unknown";
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
    const detail = health.detail || (health.healthy ? "Healthy" : "Unavailable");
    setEngineStatus(health.healthy ? "online" : "offline", detail, persist);
}

function setFormState(disabled) {
    saveBtn.disabled = disabled;
    Object.values(fields).forEach((field) => {
        field.disabled = disabled;
    });
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
    fields.ffmpeg_path.value = data.ffmpeg_path || "";
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
    setStatus("Loading settings...");
    try {
        const response = await fetch(SETTINGS_API);
        if (!response.ok) {
            throw new Error("Failed to load settings");
        }
        const data = await response.json();
        applySettingsToForm(data);
        setStatus("Settings loaded");
        return true;
    } catch (error) {
        setStatus(error.message || "Unable to load settings", true);
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
    setStatus("Saving settings...");
    showSaveFeedback("Saving settings...", false);
    setEngineStatus("checking", "Checking Demucs health...", false);

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
        ffmpeg_path: fields.ffmpeg_path.value.trim(),
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
            throw new Error(errorPayload.detail || "Failed to save settings");
        }
        const updated = await response.json();
        applySettingsToForm(updated);
        applyDemucsHealthToUI({
            healthy: Boolean(updated.demucs_healthy),
            detail: updated.demucs_health_detail,
        });
        setStatus(updated.demucs_healthy ? "Settings saved" : "Settings saved (Demucs offline)", !updated.demucs_healthy);
        showSaveFeedback(
            updated.demucs_healthy
                ? "Settings saved successfully."
                : "Settings saved. Demucs is currently offline.",
            !updated.demucs_healthy,
        );
    } catch (error) {
        setStatus(error.message || "Unable to save settings", true);
        showSaveFeedback(String(error.message || "Unable to save settings"), true);
        setEngineStatus("offline", String(error.message || "Save failed"));
    } finally {
        setFormState(false);
    }
}

async function refreshDemucsHealth() {
    setEngineStatus("checking", "Checking Demucs health...", false);
    try {
        const response = await fetch(DEMUCS_HEALTH_API);
        if (!response.ok) {
            throw new Error("Unable to fetch Demucs health");
        }
        const health = await response.json();
        applyDemucsHealthToUI(health);
    } catch (error) {
        applyDemucsHealthToUI({
            healthy: false,
            detail: String(error.message || "Health check failed"),
        });
    }
}

async function reloadEngineStatus() {
    setStatus("Reloading engine status...");
    const loaded = await loadSettings();
    if (!loaded) {
        return;
    }
    await refreshDemucsHealth();
    setStatus("Engine status refreshed");
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

const persistedState = readPersistedEngineStatus();
if (persistedState?.state && persistedState?.detail) {
    setEngineStatus(persistedState.state, persistedState.detail, false);
}

loadSettings();
