const SETTINGS_API = `${window.location.origin}/api/settings/`;
const DEMUCS_HEALTH_API = `${window.location.origin}/api/settings/demucs-health`;

const form = document.getElementById("settings-form");
const saveBtn = document.getElementById("save-settings-btn");
const reloadBtn = document.getElementById("reload-settings-btn");
const statusEl = document.getElementById("settings-status");
const engineStatusText = document.getElementById("engine-status-text");
const lastSyncText = document.getElementById("last-sync-text");

const fields = {
    demucs_api_url: document.getElementById("demucs_api_url"),
    ffmpeg_preset: document.getElementById("ffmpeg_preset"),
    ffmpeg_crf: document.getElementById("ffmpeg_crf"),
    ytdlp_path: document.getElementById("ytdlp_path"),
    ffmpeg_path: document.getElementById("ffmpeg_path"),
};

function setStatus(message, isError = false) {
    if (statusEl) {
        statusEl.textContent = message;
        statusEl.classList.toggle("text-error", isError);
        statusEl.classList.toggle("text-secondary", !isError);
    }
    if (engineStatusText) {
        engineStatusText.textContent = isError ? "AI Engine: Warning" : "AI Engine: Online";
    }
    if (lastSyncText) {
        const now = new Date();
        lastSyncText.textContent = `Last Sync: ${now.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"})}`;
    }
}

function applyDemucsHealthToUI(health) {
    if (!engineStatusText || !lastSyncText) {
        return;
    }
    engineStatusText.textContent = health.healthy ? "AI Engine: Online" : "AI Engine: Offline";
    const detail = health.detail || (health.healthy ? "Healthy" : "Unavailable");
    lastSyncText.textContent = detail;
}

function setFormState(disabled) {
    saveBtn.disabled = disabled;
    Object.values(fields).forEach((field) => {
        field.disabled = disabled;
    });
}

function applySettingsToForm(data) {
    fields.demucs_api_url.value = data.demucs_api_url || "";
    fields.ffmpeg_preset.value = data.ffmpeg_preset || "veryfast";
    fields.ffmpeg_crf.value = String(data.ffmpeg_crf ?? 23);
    fields.ytdlp_path.value = data.ytdlp_path || "";
    fields.ffmpeg_path.value = data.ffmpeg_path || "";
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
        applyDemucsHealthToUI({
            healthy: Boolean(data.demucs_healthy),
            detail: data.demucs_health_detail,
        });
        setStatus("Settings loaded");
    } catch (error) {
        setStatus(error.message || "Unable to load settings", true);
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

    const payload = {
        demucs_api_url: fields.demucs_api_url.value.trim(),
        ffmpeg_preset: fields.ffmpeg_preset.value,
        ffmpeg_crf: Number(fields.ffmpeg_crf.value),
        ytdlp_path: fields.ytdlp_path.value.trim(),
        ffmpeg_path: fields.ffmpeg_path.value.trim(),
    };

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
    } catch (error) {
        setStatus(error.message || "Unable to save settings", true);
    } finally {
        setFormState(false);
    }
}

async function refreshDemucsHealth() {
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

if (saveBtn) {
    saveBtn.addEventListener("click", saveSettings);
}
if (reloadBtn) {
    reloadBtn.addEventListener("click", loadSettings);
}

loadSettings();
refreshDemucsHealth();
