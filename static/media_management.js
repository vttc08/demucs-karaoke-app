const searchInput = document.getElementById("media-search-input");
const appUrl = window.KaraokeURLs?.appUrl || ((path) => path);
const apiBase = window.KaraokeURLs?.basePath || "";
const t = window.KaraokeI18n?.t?.bind(window.KaraokeI18n) || ((key, params = {}) => key);
const filterButtons = document.querySelectorAll(".media-cap-filter");
const mediaRows = document.querySelectorAll(".media-item-row, .media-item-card");
const emptyState = document.getElementById("media-empty-state");
const toast = document.getElementById("media-toast");
const toastText = document.getElementById("media-toast-text");
const editModal = document.getElementById("media-edit-modal");
const editForm = document.getElementById("media-edit-form");
const editItemIdInput = document.getElementById("media-edit-item-id");
const editTitleInput = document.getElementById("media-edit-title");
const editArtistInput = document.getElementById("media-edit-artist");
const editRenameDiskCheckbox = document.getElementById("media-edit-rename-disk");
const editAiToggle = document.getElementById("media-edit-ai-toggle");
const editAiStatus = document.getElementById("media-edit-ai-status");
const editLyricsToggle = document.getElementById("media-edit-lyrics-toggle");
const editLyricsStatus = document.getElementById("media-edit-lyrics-status");
const editLyricsProvider = document.getElementById("media-edit-lyrics-provider");
const editLyricsTextarea = document.getElementById("media-edit-lyrics-textarea");
const editLyricsSearchBtn = document.getElementById("media-edit-lyrics-search-btn");
const editLyricsGoogleBtn = document.getElementById("media-edit-lyrics-google-btn");
const editLyricsUploadBtn = document.getElementById("media-edit-lyrics-upload-btn");
const editLyricsFileInput = document.getElementById("media-edit-lyrics-file");
const editLyricsAlignToggle = document.getElementById("media-edit-lyrics-align-toggle");
const editLyricsAlignStatus = document.getElementById("media-edit-lyrics-align-status");
const editFilenamePreview = document.getElementById("media-edit-filename-preview");
const editFilesList = document.getElementById("media-edit-files-list");
const editDownloadPackageButton = document.getElementById("media-download-package-button");
const editModalCloseButtons = document.querySelectorAll("[data-edit-modal-close]");
const isAdmin = document.querySelector('main[data-is-admin]')?.dataset.isAdmin === "true";
const taskPanel = document.getElementById("media-task-panel");
const taskList = document.getElementById("media-task-list");
const taskLogShell = document.getElementById("media-task-log-shell");
const taskLogTitle = document.getElementById("media-task-log-title");
const taskLogOutput = document.getElementById("media-task-log-output");
const AUTO_RENAME_DEFAULT_HTML = `<span class="material-symbols-outlined text-[16px]">auto_fix_high</span><span>${t('common.auto')}</span>`;
const AUTO_RENAME_LOADING_HTML = `<span class="material-symbols-outlined animate-spin text-[16px]">sync</span><span>${t('media.inferring')}</span>`;

// Lyrics Manager Setup
let lyricsManager = null;
let lyricsUIAdapter = null;
const editLyricsFormSection = document.getElementById("media-edit-lyrics-form-section");

function initializeMediaEditLyricsManager() {
    if (lyricsManager) return;
    
    lyricsManager = new LyricsManager({ apiBase });
    lyricsUIAdapter = new LyricsUIAdapter(lyricsManager, {
        titleInput: '#media-edit-lyrics-title',
        artistInput: '#media-edit-lyrics-artist',
        textarea: '#media-edit-lyrics-textarea',
        providerLabel: '#media-edit-lyrics-provider',
        searchBtn: '#media-edit-lyrics-search-btn',
        googleLink: '#media-edit-lyrics-google-btn',
        uploadBtn: '#media-edit-lyrics-upload-btn',
        fileInput: '#media-edit-lyrics-file',
        whisperxLanguageInput: '#media-edit-lyrics-whisperx-language-code',
        processLinesToggle: '#lyrics-process-lines-toggle',
        processLinesDetail: '#lyrics-process-lines-detail',
        maxLineLengthInput: '#lyrics-max-line-length',
        maxLineLengthCjkInput: '#lyrics-max-line-length-cjk',
        panel: '#media-edit-lyrics-form-section'
    });
    lyricsUIAdapter.initialize();
    lyricsManager.on(() => updateMediaEditLyricsControls());
}

function setSwitchToggleState(toggle, checked, disabled) {
    if (!toggle) return;
    toggle.disabled = Boolean(disabled);
    toggle.setAttribute("aria-disabled", String(Boolean(disabled)));
    if (toggle.getAttribute("aria-checked") !== String(Boolean(checked))) {
        toggle.setAttribute("aria-checked", String(Boolean(checked)));
    }
    toggle.classList.toggle("opacity-60", Boolean(disabled));
    toggle.classList.toggle("cursor-not-allowed", Boolean(disabled));
    toggle.classList.toggle("bg-primary", Boolean(checked) && !disabled);
    toggle.classList.toggle("bg-surface-container-highest", !Boolean(checked) || Boolean(disabled));
    const knob = toggle.querySelector("span");
    if (knob) {
        knob.classList.toggle("translate-x-5", Boolean(checked));
        knob.classList.toggle("translate-x-0", !Boolean(checked));
    }
}

function syncMediaEditLyricsMetadata() {
    if (!lyricsManager) return;
    lyricsManager.setMetadata(editTitleInput?.value || "", editArtistInput?.value || "", editTitleInput?.value || "");
}

function applyEditAiAvailability() {
    if (!editAiToggle) return;
    if (activeEditHasMulti) {
        editAiToggle.checked = true;
        editAiToggle.disabled = true;
        if (editAiStatus) {
            editAiStatus.textContent = t("karaoke.already_multi_track");
        }
        updateMediaEditLyricsControls();
        return;
    }

    editAiToggle.disabled = !demucsHealth.healthy;
    if (!demucsHealth.healthy) {
        editAiToggle.checked = false;
    }
    if (editAiStatus) {
        editAiStatus.textContent = demucsHealth.healthy
            ? t("karaoke.available")
            : t("karaoke.unavailable_detail", { detail: demucsHealth.detail });
    }
    updateMediaEditLyricsControls();
}

function isSyncedJsonLyrics(lyricsPath, lyricsKind = "") {
    if (String(lyricsKind || "").trim().toLowerCase() === "json") {
        return true;
    }
    return String(lyricsPath || "").trim().toLowerCase().endsWith(".json");
}

function isCdgLyricsPath(lyricsPath, lyricsKind = "") {
    if (String(lyricsKind || "").trim().toLowerCase() === "cdg") {
        return true;
    }
    return String(lyricsPath || "").trim().toLowerCase().endsWith(".cdg");
}

async function refreshEditDemucsHealth() {
    if (editAiToggle) {
        editAiToggle.disabled = true;
    }
    if (editAiStatus) {
        editAiStatus.textContent = t("karaoke.checking_availability");
    }
    try {
        const response = await fetch(appUrl("/api/settings/demucs-health"));
        if (!response.ok) {
            throw new Error(t("queue.demucs_health_failed"));
        }
        demucsHealth = await response.json();
    } catch (error) {
        demucsHealth = {
            healthy: false,
            detail: error instanceof Error ? error.message : t("queue.demucs_unavailable"),
        };
    }
    applyEditAiAvailability();
}

// Preview elements
const previewImg = document.getElementById("media-edit-preview-img");
const previewPlaceholder = document.getElementById("media-edit-preview-placeholder");
const previewTitle = document.getElementById("media-edit-preview-title");
const previewArtist = document.getElementById("media-edit-preview-artist");
const previewImgMobile = document.getElementById("media-edit-preview-img-mobile");
const previewPlaceholderMobile = document.getElementById("media-edit-preview-placeholder-mobile");
const previewTitleMobile = document.getElementById("media-edit-preview-title-mobile");
const previewArtistMobile = document.getElementById("media-edit-preview-artist-mobile");

const activeCapabilityFilters = new Set();
let toastTimer = null;
let activeEditItemId = null;
let activeEditMediaPath = "";
const mediaLyricsCache = new Map();
let activeEditLyricsPath = "";
let activeEditLyricsBaselineHash = "";
let activeEditLyricsBaselineFormat = "";
let activeEditLyricsBaselineProvider = "";
let activeEditLyricsIsCdg = false;
let activeEditLyricsLoadToken = 0;
let activeEditLyricsLoadPromise = null;
let activeEditInitialTitle = "";
let activeEditInitialArtist = "";
let activeEditInitialRenameOnDisk = true;
let activeEditInitialAiChecked = false;
let activeEditHasMulti = false;
let activeEditFileManifest = null;
let activeEditFilesLoadToken = 0;
let demucsHealth = { healthy: false, detail: t("karaoke.checking_availability") };
let activeTaskId = null;
let activeTaskLogSequence = 0;
let taskSummarySource = null;
let taskDetailSource = null;
let currentTasks = [];
let taskRefreshTimer = null;
let taskRefreshPromise = null;
let taskRefreshPending = false;
let lastTaskRefreshAt = 0;
let shouldScrollToTaskPanel = false;
const mediaModalQueryParam = "media_id";
const initialTaskId = (() => {
    const rawTaskId = new URLSearchParams(window.location.search).get("task_id");
    const parsedTaskId = Number(rawTaskId);
    return Number.isFinite(parsedTaskId) && parsedTaskId > 0 ? parsedTaskId : null;
})();
const initialMediaId = (() => {
    const rawMediaId = new URLSearchParams(window.location.search).get(mediaModalQueryParam);
    const parsedMediaId = Number(rawMediaId);
    return Number.isFinite(parsedMediaId) && parsedMediaId > 0 ? parsedMediaId : null;
})();

function isMobile() {
    return window.innerWidth < 640;
}

function getMediaIdFromUrl(search = window.location.search) {
    const rawMediaId = new URLSearchParams(search).get(mediaModalQueryParam);
    const parsedMediaId = Number(rawMediaId);
    return Number.isFinite(parsedMediaId) && parsedMediaId > 0 ? parsedMediaId : null;
}

function getMediaManagementUrl(mediaId = null) {
    const url = new URL(window.location.href);
    if (mediaId) {
        url.searchParams.set(mediaModalQueryParam, String(mediaId));
    } else {
        url.searchParams.delete(mediaModalQueryParam);
    }
    return `${url.pathname}${url.search}${url.hash}`;
}

function findMediaItemNodeById(mediaId) {
    if (!mediaId) {
        return null;
    }
    return document.querySelector(`[data-item-id="${mediaId}"]`);
}

function updateMediaModalHistory(mediaId, { replace = false } = {}) {
    const nextUrl = getMediaManagementUrl(mediaId);
    const nextState = mediaId
        ? { mediaModal: true, mediaId }
        : { mediaModal: false, mediaId: null };
    if (replace) {
        history.replaceState(nextState, "", nextUrl);
    } else {
        history.pushState(nextState, "", nextUrl);
    }
}

function openMediaModalFromUrl(mediaId) {
    const itemNode = findMediaItemNodeById(mediaId);
    if (!itemNode || !isAdmin) {
        return false;
    }

    openEditModal(itemNode, { syncHistory: false });
    return true;
}

function syncMediaModalStateFromUrl() {
    const mediaId = getMediaIdFromUrl();
    if (mediaId && openMediaModalFromUrl(mediaId)) {
        return;
    }
    closeEditModal({ syncHistory: false });
}

function getFilenameFromPath(mediaPath) {
    const cleanPath = String(mediaPath || "").split("?")[0];
    const parts = cleanPath.split("/").filter(Boolean);
    return parts.length > 0 ? decodeURIComponent(parts[parts.length - 1]) : "";
}

function inferLyricsFormatFromPath(lyricsPath) {
    const suffix = getFilenameFromPath(lyricsPath).toLowerCase().split(".").pop();
    if (lyricsPath && String(lyricsPath).toLowerCase().endsWith(".json")) {
        return "json";
    }
    if (lyricsPath && String(lyricsPath).toLowerCase().endsWith(".lrc")) {
        return "lrc";
    }
    if (lyricsPath && String(lyricsPath).toLowerCase().endsWith(".cdg")) {
        return "cdg";
    }
    if (suffix === "txt") {
        return "txt";
    }
    return "";
}

function hashLyricsText(text) {
    let hash = 0x811c9dc5;
    const normalized = String(text || "").replace(/\r\n/g, "\n");
    for (let index = 0; index < normalized.length; index += 1) {
        hash ^= normalized.charCodeAt(index);
        hash = Math.imul(hash, 0x01000193);
    }
    return (`0000000${(hash >>> 0).toString(16)}`).slice(-8);
}

function resetMediaEditLyricsState() {
    activeEditLyricsPath = "";
    activeEditLyricsBaselineHash = "";
    activeEditLyricsBaselineFormat = "";
    activeEditLyricsBaselineProvider = "";
    activeEditLyricsIsCdg = false;
    activeEditLyricsLoadToken += 1;
    activeEditLyricsLoadPromise = null;
}

function resetMediaEditInitialState() {
    activeEditInitialTitle = "";
    activeEditInitialArtist = "";
    activeEditInitialRenameOnDisk = true;
    activeEditInitialAiChecked = false;
}

function updateMediaEditLyricsControls() {
    if (!lyricsManager) return;
    const state = lyricsManager.getState();
    const isCdg = Boolean(activeEditLyricsIsCdg);
    const isEnabled = Boolean(state.lyricsEnabled);
    const isSynced = Boolean(isEnabled && state.format === "json");
    const isLocked = Boolean(isSynced || isCdg);
    const hasText = Boolean((state.text || "").trim());
    const ttmlLyrics = state.format === "ttml";
    const canAlign = Boolean(isEnabled && hasText && !isLocked && !ttmlLyrics && demucsHealth.healthy);
    if (!canAlign && state.processLyricsLines) {
        lyricsManager.setLineProcessingSettings(false);
    }

    if (editLyricsToggle) {
        editLyricsToggle.checked = Boolean(isEnabled && !isCdg);
        editLyricsToggle.disabled = isLocked;
    }

    if (editLyricsFormSection) {
        editLyricsFormSection.classList.toggle("hidden", isLocked);
    }

    if (editLyricsTextarea) {
        editLyricsTextarea.readOnly = isLocked;
        editLyricsTextarea.classList.toggle("cursor-not-allowed", isLocked);
    }

    [editLyricsSearchBtn, editLyricsUploadBtn, editLyricsFileInput].forEach((control) => {
        if (!control) return;
        control.disabled = !isEnabled || isLocked;
        control.classList.toggle("opacity-50", control.disabled);
        control.classList.toggle("cursor-not-allowed", control.disabled);
    });

    if (editLyricsGoogleBtn) {
        editLyricsGoogleBtn.setAttribute("aria-disabled", String(!isEnabled || isLocked));
        editLyricsGoogleBtn.tabIndex = !isEnabled || isLocked ? -1 : 0;
        editLyricsGoogleBtn.classList.toggle("pointer-events-none", !isEnabled || isLocked);
        editLyricsGoogleBtn.classList.toggle("opacity-50", !isEnabled || isLocked);
    }

    if (editLyricsStatus) {
        if (isCdg) {
            editLyricsStatus.textContent = t("media.cdg_lyrics_disabled");
            editLyricsStatus.className = "text-[10px] leading-tight text-warning";
        } else if (isLocked) {
            editLyricsStatus.textContent = t("media.already_synced_lyrics");
            editLyricsStatus.className = "text-[10px] leading-tight text-on-surface-variant";
        } else {
            editLyricsStatus.textContent = "";
            editLyricsStatus.className = "text-[10px] leading-tight text-on-surface-variant";
        }
    }

    if (editLyricsAlignToggle) {
        const alignRequested = Boolean(state.alignLyricsRequested);
        if (!canAlign && alignRequested) {
            lyricsManager.setAlignLyricsRequested(false);
        }
        setSwitchToggleState(editLyricsAlignToggle, Boolean(canAlign && alignRequested), !canAlign);
    }
    if (editLyricsAlignStatus) {
        if (isCdg) {
            editLyricsAlignStatus.textContent = t("media.cdg_lyrics_disabled");
        } else if (isLocked) {
            editLyricsAlignStatus.textContent = t("lyrics.align_json_unsupported");
        } else if (ttmlLyrics) {
            editLyricsAlignStatus.textContent = t("lyrics.align_xml_skipped");
        } else if (!demucsHealth.healthy) {
            editLyricsAlignStatus.textContent = t("lyrics.align_demucs_unavailable");
        } else if (!hasText) {
            editLyricsAlignStatus.textContent = t("lyrics.align_requires_text");
        } else {
            editLyricsAlignStatus.textContent = t("lyrics.align_available");
        }
    }
}

function updateMediaEditToolAvailability() {
    const isCdg = Boolean(activeEditLyricsIsCdg);
    const trimButtons = editModal?.querySelectorAll('button[data-action="open-trim-editor"]') || [];
    const subtitleButtons = editModal?.querySelectorAll('button[data-action="open-subtitle-editor"]') || [];
    trimButtons.forEach((button) => {
        const toolSpans = button.querySelectorAll("span");
        const iconSpan = toolSpans[0];
        const labelSpan = toolSpans[1];
        button.disabled = false;
        button.classList.toggle("opacity-50", false);
        button.classList.toggle("cursor-not-allowed", false);
        button.setAttribute("aria-disabled", "false");
        button.setAttribute(
            "aria-label",
            isCdg ? t("trim.transcode_action") : t("trim.lossless_trim"),
        );
        if (iconSpan) {
            iconSpan.textContent = isCdg ? "conversion_path" : "content_cut";
        }
        if (labelSpan) {
            labelSpan.textContent = isCdg ? t("trim.transcode_action") : t("trim.lossless_trim");
        }
    });
    subtitleButtons.forEach((button) => {
        button.disabled = false;
        button.classList.toggle("opacity-50", false);
        button.classList.toggle("cursor-not-allowed", false);
        button.setAttribute("aria-disabled", "false");
    });
}

function setLoadedLyricsState(text, format, providerLabel) {
    if (!lyricsManager) return;
    const normalizedText = String(text || "").trim();
    const normalizedFormat = format || "txt";
    activeEditLyricsIsCdg = false;
    lyricsManager.setEnabled(true);
    lyricsManager.setMetadata(editTitleInput?.value || "", editArtistInput?.value || "", editTitleInput?.value || "");
    lyricsManager.setLyricsDraft(normalizedText, providerLabel, {
        format: normalizedFormat,
        isSynced: normalizedFormat === "json" || normalizedFormat === "lrc",
        lyricsState: "manual",
    });
    lyricsManager.setLineProcessingSettings(false);
    activeEditLyricsBaselineHash = hashLyricsText(normalizedText);
    activeEditLyricsBaselineFormat = normalizedFormat;
    activeEditLyricsBaselineProvider = providerLabel;
    updateMediaEditLyricsControls();
}

function setLockedSyncedLyricsState() {
    if (!lyricsManager) return;
    activeEditLyricsIsCdg = false;
    lyricsManager.reset();
    lyricsManager.setEnabled(true);
    lyricsManager.setMetadata(editTitleInput?.value || "", editArtistInput?.value || "", editTitleInput?.value || "");
    lyricsManager.setLyricsDraft("", "", {
        format: "json",
        isSynced: true,
        lyricsState: "manual",
    });
    lyricsManager.setLineProcessingSettings(false);
    activeEditLyricsBaselineHash = "";
    activeEditLyricsBaselineFormat = "json";
    activeEditLyricsBaselineProvider = "";
    updateMediaEditLyricsControls();
}

function setCdgLyricsState() {
    if (!lyricsManager) return;
    lyricsManager.reset();
    lyricsManager.setEnabled(false);
    lyricsManager.setMetadata(editTitleInput?.value || "", editArtistInput?.value || "", editTitleInput?.value || "");
    lyricsManager.setAlignLyricsRequested(false);
    lyricsManager.setLineProcessingSettings(false);
    activeEditLyricsBaselineHash = "";
    activeEditLyricsBaselineFormat = "cdg";
    activeEditLyricsBaselineProvider = "";
    updateMediaEditLyricsControls();
}

async function loadCurrentLyricsForEdit(itemNode) {
    const lyricsPath = String(itemNode?.dataset?.lyricsPath || "").trim();
    const hasLyrics = itemNode?.dataset?.hasLyrics === "true";
    const lyricsKind = String(itemNode?.dataset?.lyricsKind || "").trim().toLowerCase();
    const loadToken = ++activeEditLyricsLoadToken;
    activeEditLyricsPath = lyricsPath;
    activeEditLyricsIsCdg = isCdgLyricsPath(lyricsPath, lyricsKind);

    if (!hasLyrics || !lyricsPath) {
        activeEditLyricsBaselineHash = "";
        activeEditLyricsBaselineFormat = "";
        activeEditLyricsBaselineProvider = "";
        if (lyricsManager) {
            lyricsManager.reset();
            lyricsManager.setMetadata(editTitleInput?.value || "", editArtistInput?.value || "", editTitleInput?.value || "");
            lyricsManager.setEnabled(false);
        }
        updateMediaEditLyricsControls();
        return;
    }

    if (activeEditLyricsIsCdg) {
        setCdgLyricsState();
        return;
    }

    const cached = mediaLyricsCache.get(lyricsPath);
    const normalizedPath = appUrl(lyricsPath);
    const format = inferLyricsFormatFromPath(lyricsPath) || (lyricsKind === "json" ? "json" : "txt");

    if (isSyncedJsonLyrics(lyricsPath, itemNode?.dataset?.lyricsKind)) {
        if (loadToken !== activeEditLyricsLoadToken) {
            return;
        }
        setLockedSyncedLyricsState();
        return;
    }

    try {
        let text = cached?.text;
        if (text === undefined) {
            const response = await fetch(normalizedPath, { cache: "no-store" });
            if (!response.ok) {
                throw new Error(`lyrics ${response.status}`);
            }
            text = (await response.text()).trim();
            mediaLyricsCache.set(lyricsPath, {
                text,
                format,
                hash: hashLyricsText(text),
            });
        }
        if (loadToken !== activeEditLyricsLoadToken) {
            return;
        }
        setLoadedLyricsState(text, cached?.format || format, t("media.current_sidecar"));
    } catch (error) {
        if (loadToken !== activeEditLyricsLoadToken) {
            return;
        }
        console.warn("Failed to load media lyrics sidecar:", error);
        if (lyricsManager) {
            lyricsManager.reset();
            lyricsManager.setEnabled(false);
        }
        activeEditLyricsBaselineHash = "";
        activeEditLyricsBaselineFormat = "";
        activeEditLyricsBaselineProvider = "";
        updateMediaEditLyricsControls();
    }
}

function buildRenamedFilename(nextTitle, nextArtist) {
    const currentFilename = getFilenameFromPath(activeEditMediaPath);
    const currentExtension = currentFilename.includes(".")
        ? `.${currentFilename.split(".").pop()}`
        : ".mp4";
    const title = nextTitle.trim() || t("common.title");
    const artist = nextArtist.trim();
    const clean = [artist, title].filter(Boolean).join(" - ").replace(/\s+/g, " ").trim();
    return `${clean || "media"}${currentExtension}`;
}

function updateFilenamePreview() {
    if (!editFilenamePreview || !editTitleInput || !editArtistInput) return;

    const currentFilename = getFilenameFromPath(activeEditMediaPath) || t("common.unknown");
    const renameEnabled = Boolean(editRenameDiskCheckbox?.checked);
    const nextFilename = buildRenamedFilename(editTitleInput.value, editArtistInput.value);
    editFilenamePreview.textContent = renameEnabled
        ? t("media.will_rename_to", { filename: nextFilename })
        : t("media.current_filename", { filename: currentFilename });
}

function getMediaFileKindLabel(kind, extension = "") {
    const normalizedKind = String(kind || "").toLowerCase();
    const normalizedExtension = String(extension || "").toLowerCase();
    if (normalizedKind === "main") {
        return t("media.file_main");
    }
    if (normalizedKind === "vocals") {
        return t("media.file_vocals");
    }
    if (normalizedKind !== "lyrics") {
        return normalizedKind;
    }
    if (normalizedExtension === "json") {
        return t("media.file_lyrics_json");
    }
    if (normalizedExtension === "lrc") {
        return t("media.file_lyrics_lrc");
    }
    if (normalizedExtension === "txt") {
        return t("media.file_lyrics_txt");
    }
    if (normalizedExtension === "cdg") {
        return t("media.file_lyrics_cdg");
    }
    return t("media.file_lyrics");
}

function mediaFileKindIcon(kind, extension = "") {
    const normalizedExtension = String(extension || "").toLowerCase();
    switch (String(kind || "").toLowerCase()) {
        case "main":
            return "music_video";
        case "vocals":
            return "mic_external_on";
        case "lyrics":
            return normalizedExtension === "cdg" ? "image" : "lyrics";
        default:
            return "draft";
    }
}

function buildMediaFileDownloadUrl(kind) {
    if (!activeEditItemId) {
        return "";
    }
    return appUrl(`/api/media/${Number(activeEditItemId)}/files/${encodeURIComponent(kind)}/download`);
}

function buildMediaFileDeleteUrl(kind) {
    if (!activeEditItemId) {
        return "";
    }
    return appUrl(`/api/media/${Number(activeEditItemId)}/files/${encodeURIComponent(kind)}`);
}

function triggerDownload(url) {
    if (!url) {
        return;
    }
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.rel = "noopener";
    anchor.style.display = "none";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
}

function setFileManagementBusy(isBusy) {
    if (editFilesList) {
        editFilesList.classList.toggle("opacity-60", isBusy);
    }
}

function renderMediaFilesList(manifest) {
    if (!editFilesList) {
        return;
    }
    const files = Array.isArray(manifest?.files)
        ? manifest.files.filter((file) => Boolean(file?.exists))
        : [];
    if (!files.length) {
        editFilesList.innerHTML = `<p class="text-[11px] text-on-surface-variant">${escapeHtml(t("media.file_management_empty"))}</p>`;
        return;
    }

    editFilesList.innerHTML = files.map((file) => {
        const kind = String(file.kind || "");
        const extension = String(file.extension || "");
        const downloadable = Boolean(file.downloadable);
        const deletable = Boolean(file.deletable);
        const label = getMediaFileKindLabel(kind, extension);
        const downloadUrl = buildMediaFileDownloadUrl(kind);
        const deleteUrl = buildMediaFileDeleteUrl(kind);
        return `
            <article class="rounded-xl border border-white/5 bg-surface-container-highest/30 p-3">
                <div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div class="min-w-0 flex-1">
                        <div class="flex flex-wrap items-center gap-2">
                            <span class="inline-flex items-center gap-1 rounded-full border border-white/10 bg-surface-container-highest/50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                                <span class="material-symbols-outlined text-[13px]">${mediaFileKindIcon(kind, extension)}</span>
                                ${escapeHtml(label)}
                            </span>
                        </div>
                        <p class="mt-2 break-all text-sm font-medium text-on-surface">${escapeHtml(file.filename || "")}</p>
                    </div>
                    <div class="grid grid-cols-4 gap-2 w-full shrink-0 sm:flex sm:flex-wrap sm:justify-end md:w-auto">
                        <button
                            type="button"
                            data-action="download-media-file"
                            data-media-file-kind="${escapeHtml(kind)}"
                            data-media-file-extension="${escapeHtml(extension)}"
                            data-media-file-url="${escapeHtml(downloadUrl)}"
                            class="col-start-3 col-span-1 inline-flex w-full min-w-0 items-center justify-center gap-1 rounded-full border border-white/10 bg-surface-container-high/70 px-3 py-1.5 text-[10px] font-black uppercase tracking-wider text-on-surface transition-colors hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
                            ${downloadable ? "" : "disabled"}
                        >
                            <span class="material-symbols-outlined text-[15px]">download</span>
                        </button>
                        <button
                            type="button"
                            data-action="delete-media-file"
                            data-media-file-kind="${escapeHtml(kind)}"
                            data-media-file-extension="${escapeHtml(extension)}"
                            data-media-file-url="${escapeHtml(deleteUrl)}"
                            class="inline-flex w-full min-w-0 items-center justify-center gap-1 rounded-full border border-error/25 bg-error/10 px-3 py-1.5 text-[10px] font-black uppercase tracking-wider text-error transition-colors hover:bg-error/15 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
                            ${deletable ? "" : "disabled"}
                        >
                            <span class="material-symbols-outlined text-[15px]">delete</span>
                        </button>
                    </div>
                </div>
            </article>
        `;
    }).join("");
}

function syncEditManifestState(manifest) {
    if (!manifest) {
        return;
    }
    activeEditFileManifest = manifest;
    activeEditHasMulti = Boolean(manifest.has_multi_track);
    const hasLyrics = Boolean(manifest.has_lyrics);
    const lyricsKind = String(manifest.lyrics_kind || "");
    activeEditLyricsIsCdg = lyricsKind === "cdg";
    const displayTitle = editTitleInput?.value?.trim() || activeEditInitialTitle || manifest.title || "";
    const displayArtist = editArtistInput?.value?.trim() || activeEditInitialArtist || manifest.artist || "";
    updateMediaItemDisplay(
        Number(activeEditItemId || manifest.media_id || 0),
        displayTitle,
        displayArtist,
        activeEditHasMulti,
        hasLyrics,
        lyricsKind,
    );
    applyEditAiAvailability();
    if (editDownloadPackageButton) {
        const mainEntry = Array.isArray(manifest.files)
            ? manifest.files.find((entry) => entry?.kind === "main")
            : null;
        editDownloadPackageButton.disabled = !activeEditItemId || !Boolean(mainEntry?.exists);
    }
    if (!hasLyrics && lyricsManager) {
        lyricsManager.reset();
        lyricsManager.setEnabled(false);
        lyricsManager.setMetadata(editTitleInput?.value || "", editArtistInput?.value || "", editTitleInput?.value || "");
        activeEditLyricsBaselineHash = "";
        activeEditLyricsBaselineFormat = "";
        activeEditLyricsBaselineProvider = "";
    } else if (activeEditLyricsIsCdg && lyricsManager) {
        setCdgLyricsState();
    }
    updateMediaEditLyricsControls();
    updateMediaEditToolAvailability();
    updateFilenamePreview();
}

async function refreshMediaFileManifest() {
    if (!isAdmin || !activeEditItemId) {
        return null;
    }
    const loadToken = ++activeEditFilesLoadToken;
    setFileManagementBusy(true);
    if (editDownloadPackageButton) {
        editDownloadPackageButton.disabled = true;
    }
    if (editFilesList) {
        editFilesList.innerHTML = `<p class="text-[11px] text-on-surface-variant">${escapeHtml(t("media.file_management_loading"))}</p>`;
    }
    try {
        const response = await fetch(appUrl(`/api/media/${Number(activeEditItemId)}/files`));
        if (!response.ok) {
            throw new Error(t("media.file_management_failed"));
        }
        const manifest = await response.json();
        if (loadToken !== activeEditFilesLoadToken) {
            return null;
        }
        renderMediaFilesList(manifest);
        syncEditManifestState(manifest);
        return manifest;
    } catch (error) {
        if (loadToken !== activeEditFilesLoadToken) {
            return null;
        }
        activeEditFileManifest = null;
        const message = error instanceof Error ? error.message : t("media.file_management_failed");
        if (editFilesList) {
            editFilesList.innerHTML = `<p class="text-[11px] text-error">${escapeHtml(message)}</p>`;
        }
        if (editDownloadPackageButton) {
            editDownloadPackageButton.disabled = true;
        }
        return null;
    } finally {
        if (loadToken === activeEditFilesLoadToken) {
            setFileManagementBusy(false);
        }
    }
}

async function downloadMediaFile(button) {
    if (!button || button.disabled) {
        return;
    }
    const url = button.dataset.mediaFileUrl || "";
    if (!url) {
        showToast(t("media.file_download_failed"));
        return;
    }
    triggerDownload(url);
}

async function deleteMediaFile(button) {
    if (!button || button.disabled) {
        return;
    }
    const kind = button.dataset.mediaFileKind || "";
    const label = getMediaFileKindLabel(kind, button.dataset.mediaFileExtension || "");
    if (kind === "main") {
        showToast(t("media.main_file_not_deletable"));
        return;
    }
    if (!window.confirm(t("media.delete_sidecar_confirm", { kind: label }))) {
        return;
    }

    const originalHtml = button.innerHTML;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.innerHTML = '<span class="material-symbols-outlined animate-spin text-[15px]">sync</span>';

    try {
        const response = await fetch(button.dataset.mediaFileUrl || buildMediaFileDeleteUrl(kind), {
            method: "DELETE",
        });
        if (!response.ok) {
            let detail = t("media.delete_sidecar_failed");
            try {
                const payload = await response.json();
                if (payload?.detail) {
                    detail = payload.detail;
                }
            } catch (_error) {
                // Keep fallback text.
            }
            throw new Error(detail);
        }
        showToast(t("media.file_deleted", { kind: label }));
        await refreshMediaFileManifest();
    } catch (error) {
        const message = error instanceof Error ? error.message : t("media.delete_sidecar_failed");
        showToast(message);
        button.disabled = false;
        button.removeAttribute("aria-busy");
        button.innerHTML = originalHtml;
    }
}

function downloadMediaPackage() {
    if (!activeEditItemId) {
        return;
    }
    if (editDownloadPackageButton?.disabled) {
        showToast(t("media.file_download_failed"));
        return;
    }
    triggerDownload(appUrl(`/api/media/${Number(activeEditItemId)}/download`));
}

function syncEditPreviewLabels(title, artist) {
    const normalizedTitle = title.trim() || t("common.track_title");
    const normalizedArtist = artist.trim() || t("common.artist_name");

    if (previewTitle) previewTitle.textContent = normalizedTitle;
    if (previewArtist) previewArtist.textContent = normalizedArtist;
    if (previewTitleMobile) previewTitleMobile.textContent = normalizedTitle;
    if (previewArtistMobile) previewArtistMobile.textContent = normalizedArtist;
}

function showToast(message) {
    if (!toast || !toastText) {
        return;
    }
    toastText.textContent = message;
    toast.classList.remove("opacity-0", "translate-y-3");
    toast.classList.add("opacity-100", "translate-y-0");

    if (toastTimer) {
        clearTimeout(toastTimer);
    }
    toastTimer = setTimeout(() => {
        toast.classList.remove("opacity-100", "translate-y-0");
        toast.classList.add("opacity-0", "translate-y-3");
    }, 2200);
}

function updateEmptyState() {
    if (!emptyState) {
        return;
    }
    const visibleItems = [...mediaRows].filter((item) => !item.classList.contains("hidden")).length;
    emptyState.classList.toggle("hidden", visibleItems > 0);
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = String(text ?? "");
    return div.innerHTML;
}

function getTaskProgressLabel(task) {
    const live = task?.live || {};
    const label = live.progress_label_key
        ? t(live.progress_label_key, live.progress_label_args || {})
        : (live.progress_label || task?.stage || task?.status || "");
    const stepIndex = Number(live.progress_step_index);
    const stepTotal = Number(live.progress_step_total);
    if (Number.isFinite(stepIndex) && Number.isFinite(stepTotal) && stepIndex > 0 && stepTotal > 0) {
        return t("task.progress_step", {
            label,
            current: stepIndex,
            total: stepTotal,
        });
    }
    return label;
}

function renderTaskProgressBlock(task) {
    if (!['downloading', 'processing'].includes(task?.status)) {
        return "";
    }
    const progress = task?.live?.progress_percent;
    const label = getTaskProgressLabel(task);
    const percent = Number.isFinite(Number(progress)) ? Number(progress) : 0;
    const mode = task?.live?.progress_mode || "";
    const separator = mode === "indeterminate" ? "" : " • ";
    return `
        <div class="mt-3 max-w-xs" data-task-progress-key="media-${task.id}" data-task-progress-status="${escapeHtml(task.status)}" data-task-progress-stage="${escapeHtml(task.stage || '')}" data-task-progress-mode="${escapeHtml(mode)}" data-task-progress-reported-percent="${Math.max(0, Math.min(100, percent))}" data-task-progress-label="${escapeHtml(label)}">
            <div class="h-2 overflow-hidden rounded-full bg-surface-container-highest" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.max(0, Math.min(100, percent))}">
                <div class="h-full rounded-full bg-primary transition-all duration-300 ease-out" data-task-progress-fill style="width: ${Math.max(0, Math.min(100, percent))}%"></div>
            </div>
            <p class="mt-1 text-[11px] text-on-surface-variant">${escapeHtml(label)}${separator}<span data-task-progress-percent-text class="${mode === 'indeterminate' ? 'hidden' : ''}">${escapeHtml(String(percent))}%</span></p>
        </div>
    `;
}

function getTaskStatusLabel(status) {
    if (status === "canceled") {
        return t("task.canceled");
    }
    return status;
}

function scrollTaskPanelIntoView() {
    if (!taskPanel) {
        return;
    }
    taskPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function getMediaItemNodes(itemId) {
    if (!itemId) {
        return [];
    }
    return [...document.querySelectorAll(`[data-item-id="${itemId}"]`)];
}

function getItemFieldText(itemNode, field) {
    return itemNode.querySelector(`[data-field="${field}"]`)?.textContent?.trim() || "";
}

function normalizeArtistValue(value) {
    const cleaned = (value || "").trim();
    return cleaned;
}

function setButtonsForAction(itemId, action, options = {}) {
    const { disabled = false, label = null } = options;
    getMediaItemNodes(itemId).forEach((node) => {
        node.querySelectorAll(`button[data-action="${action}"]`).forEach((button) => {
            button.disabled = disabled;
            if (label !== null) {
                button.textContent = label;
            }
            button.classList.toggle("opacity-60", disabled);
            button.classList.toggle("cursor-not-allowed", disabled);
        });
    });
}

function setItemFieldText(itemNode, field, value) {
    const fieldNode = itemNode.querySelector(`[data-field="${field}"]`);
    if (fieldNode) {
        fieldNode.textContent = value;
    }
}

function updateMediaItemDisplay(itemId, title, artist, hasMulti, hasLyrics, lyricsKind = "") {
    const normalizedTitle = title.trim();
    const normalizedArtist = normalizeArtistValue(artist);
    const normalizedLyricsKind = String(lyricsKind || "").trim().toLowerCase();
    const hasSyncedLyrics = normalizedLyricsKind === "json";
    const hasCdgLyrics = normalizedLyricsKind === "cdg";
    const nodes = getMediaItemNodes(itemId);
    nodes.forEach((node) => {
        node.dataset.title = normalizedTitle.toLowerCase();
        node.dataset.artist = normalizedArtist.toLowerCase();
        node.dataset.hasMultiTrack = String(hasMulti);
        node.dataset.hasLyrics = String(hasLyrics);
        node.dataset.lyricsKind = normalizedLyricsKind;

        setItemFieldText(node, "title", normalizedTitle);
        setItemFieldText(node, "artist", normalizedArtist || t("common.unknown_artist"));
        
        const multiChip = node.querySelector('.rounded-full.bg-secondary\\/10');
        const lyricsChip = node.querySelector('[data-lyrics-chip="media"]');
        
        if (multiChip) {
            multiChip.classList.toggle("hidden", !hasMulti);
        }
        if (lyricsChip) {
            lyricsChip.classList.toggle("hidden", !hasLyrics);
            lyricsChip.className = [
                "rounded-full",
                "px-2",
                "py-0.5",
                "text-[10px]",
                "font-bold",
                "uppercase",
                "tracking-widest",
                hasSyncedLyrics
                    ? "border border-tertiary/30 bg-tertiary/10 text-tertiary"
                    : hasCdgLyrics
                        ? "border border-secondary/30 bg-secondary/10 text-secondary"
                    : "border border-primary/30 bg-primary/10 text-primary",
                hasLyrics ? "" : "hidden",
            ].filter(Boolean).join(" ");
            lyricsChip.textContent = hasSyncedLyrics
                ? t("media.lyrics_synced")
                : hasCdgLyrics
                    ? t("media.lyrics_cdg")
                    : t("media.lyrics_plain");
        }

        const titleImage = node.querySelector("img[alt]");
        if (titleImage) {
            titleImage.alt = `${normalizedTitle} cover`;
        }
    });
}

function rowMatchesFilter(row, query, capabilityFilters) {
    const title = row.dataset.title || "";
    const artist = row.dataset.artist || "";
    const hasMulti = row.dataset.hasMultiTrack === "true";
    const hasLyrics = row.dataset.hasLyrics === "true";
    const textMatch = title.includes(query) || artist.includes(query);

    if (!textMatch) {
        return false;
    }
    if (capabilityFilters.has("multi") && !hasMulti) {
        return false;
    }
    if (capabilityFilters.has("lyrics") && !hasLyrics) {
        return false;
    }
    return true;
}

function applyFilters() {
    const query = (searchInput?.value || "").trim().toLowerCase();
    mediaRows.forEach((row) => {
        const visible = rowMatchesFilter(row, query, activeCapabilityFilters);
        row.classList.toggle("hidden", !visible);
    });
    updateEmptyState();
}

function renderTaskList(tasks) {
    if (!taskPanel || !taskList) {
        return;
    }
    currentTasks = Array.isArray(tasks) ? tasks : [];
    taskPanel.classList.toggle("hidden", currentTasks.length === 0);
    if (!currentTasks.length) {
        taskList.innerHTML = "";
        if (taskLogShell) {
            taskLogShell.classList.add("hidden");
        }
        return;
    }
    taskList.innerHTML = currentTasks.map((task) => {
        const isSelectedTask = Number(activeTaskId) === Number(task.id);
        const targetId = task.target_media_item_id || task.target_queue_item_id || task.id;
        const summary = task.last_error_summary
            ? `<p class="mt-3 line-clamp-3 text-[11px] text-error">${escapeHtml(task.last_error_summary)}</p>`
            : "";
        const progressHtml = renderTaskProgressBlock(task) || summary;
        const statusChip = ['downloading', 'processing'].includes(task.status)
            ? ""
            : `<span class="rounded-full border border-white/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${task.status === 'canceled' ? 'border-error/30 bg-error/10 text-error' : 'text-on-surface-variant'}">${escapeHtml(getTaskStatusLabel(task.status))}</span>`;
        const actionHtml = task.status === "canceled" || task.status === "failed"
            ? `
                <div class="mt-3 flex justify-end gap-3">
                    <button
                        type="button"
                        data-action="retry-task"
                        class="inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-3 py-1.5 text-[11px] font-black uppercase tracking-wider text-primary transition-colors hover:bg-primary/15 disabled:cursor-not-allowed disabled:opacity-60"
                        data-task-id="${task.id}"
                        title="${escapeHtml(t("common.retry"))}"
                        aria-label="${escapeHtml(t("common.retry"))}"
                    >
                        <span class="material-symbols-outlined text-[16px]">refresh</span>
                        <span>${escapeHtml(t("common.retry"))}</span>
                    </button>
                    <button
                        type="button"
                        data-action="delete-task"
                        class="inline-flex items-center gap-2 rounded-full border border-error/30 bg-error/10 px-3 py-1.5 text-[11px] font-black uppercase tracking-wider text-error transition-colors hover:bg-error/15 disabled:cursor-not-allowed disabled:opacity-60"
                        data-task-id="${task.id}"
                        title="${escapeHtml(t("common.delete"))}"
                        aria-label="${escapeHtml(t("common.delete"))}"
                    >
                        <span class="material-symbols-outlined text-[16px]">delete</span>
                        <span>${escapeHtml(t("common.delete"))}</span>
                    </button>
                </div>
                `
            : `
                <div class="mt-3 flex justify-end">
                    <button
                        type="button"
                        data-action="cancel-task"
                        class="inline-flex items-center gap-2 rounded-full border border-error/30 bg-error/10 px-3 py-1.5 text-[11px] font-black uppercase tracking-wider text-error transition-colors hover:bg-error/15 disabled:cursor-not-allowed disabled:opacity-60"
                        data-task-id="${task.id}"
                        title="${escapeHtml(t("common.cancel"))}"
                        aria-label="${escapeHtml(t("common.cancel"))}"
                    >
                        <span class="material-symbols-outlined text-[16px]">close</span>
                        <span>${escapeHtml(t("common.cancel"))}</span>
                    </button>
                </div>
                `;
        return `
            <article class="rounded-xl border ${isSelectedTask ? 'border-primary/40 bg-primary/5 ring-1 ring-primary/20' : 'border-white/10 bg-surface-container-low'} p-3 ${isAdmin ? 'cursor-pointer' : 'cursor-default'} transition-colors" data-task-id="${task.id}" aria-current="${isSelectedTask ? 'true' : 'false'}">
                <div class="flex items-start justify-between gap-3">
                    <div class="min-w-0">
                        <p class="truncate text-sm font-bold text-on-surface">${escapeHtml(task.target_media_item_id ? t("media.media_task_target", { id: targetId }) : t("media.queue_task_target", { id: targetId }))}</p>
                        <p class="mt-0.5 text-[11px] uppercase tracking-wider text-on-surface-variant">${escapeHtml(task.stage || task.status)}</p>
                    </div>
                    ${statusChip}
                </div>
                ${progressHtml}
                ${actionHtml}
        </article>
        `;
    }).join("");
    window.KaraokeTaskProgress?.sync(taskList);
    if (shouldScrollToTaskPanel && currentTasks.length > 0) {
        shouldScrollToTaskPanel = false;
        scrollTaskPanelIntoView();
    }
}

async function refreshTaskList() {
    if (!taskList) {
        return;
    }
    if (taskRefreshPromise) {
        taskRefreshPending = true;
        return taskRefreshPromise;
    }

    taskRefreshPromise = (async () => {
        try {
            const response = await fetch(appUrl("/api/tasks/"));
            if (!response.ok) {
                throw new Error(`task list ${response.status}`);
            }
            const tasks = await response.json();
            renderTaskList(tasks);
            lastTaskRefreshAt = Date.now();
        } catch (error) {
            console.warn("Task list refresh failed:", error);
        } finally {
            taskRefreshPromise = null;
            if (taskRefreshPending) {
                taskRefreshPending = false;
                const elapsed = Date.now() - lastTaskRefreshAt;
                const delayMs = elapsed >= 1000 ? 0 : 1000 - elapsed;
                scheduleTaskListRefresh(delayMs);
            }
        }
    })();

    return taskRefreshPromise;
}

async function retryTask(taskId) {
    if (!Number.isFinite(taskId) || taskId <= 0) {
        return;
    }
    try {
        const response = await fetch(appUrl(`/api/tasks/${taskId}/retry`), {
            method: "POST",
        });
        if (!response.ok) {
            let detail = t("media.retry_task_failed");
            try {
                const payload = await response.json();
                if (payload?.detail) {
                    detail = payload.detail;
                }
            } catch (_error) {
                // Keep fallback text.
            }
            throw new Error(detail);
        }

        await refreshTaskList();
    } catch (error) {
        const message = error instanceof Error ? error.message : t("media.retry_task_failed");
        showToast(message);
    }
}

async function cancelProcessingTask(button) {
    if (!button) {
        return;
    }
    const taskCard = button.closest("[data-task-id]");
    const taskId = Number(taskCard?.dataset.taskId || button.dataset.taskId);
    if (!Number.isFinite(taskId) || taskId <= 0) {
        return;
    }

    const originalHtml = button.innerHTML;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.title = t("media.canceling_task");
    button.setAttribute("aria-label", t("media.canceling_task"));
    button.innerHTML = '<span class="material-symbols-outlined animate-spin text-[16px]">sync</span>';

    try {
        const response = await fetch(appUrl(`/api/tasks/${taskId}/cancel`), {
            method: "POST",
        });
        if (!response.ok) {
            let detail = t("common.cancel_failed");
            try {
                const payload = await response.json();
                if (payload?.detail) {
                    detail = payload.detail;
                }
            } catch (_error) {
                // Keep fallback text.
            }
            throw new Error(detail);
        }

        await refreshTaskList();
    } catch (error) {
        const message = error instanceof Error ? error.message : t("common.cancel_failed");
        showToast(message);
        button.disabled = false;
        button.removeAttribute("aria-busy");
        button.title = t("common.cancel");
        button.setAttribute("aria-label", t("common.cancel"));
        button.innerHTML = originalHtml || `<span class="material-symbols-outlined text-[16px]">close</span><span>${escapeHtml(t("common.cancel"))}</span>`;
    }
}

async function deleteProcessingTask(button) {
    if (!button) {
        return;
    }
    const taskCard = button.closest("[data-task-id]");
    const taskId = Number(taskCard?.dataset.taskId || button.dataset.taskId);
    if (!Number.isFinite(taskId) || taskId <= 0) {
        return;
    }
    if (!window.confirm(t("media.confirm_delete_task"))) {
        return;
    }

    const originalHtml = button.innerHTML;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.title = t("media.deleting_task");
    button.setAttribute("aria-label", t("media.deleting_task"));
    button.innerHTML = '<span class="material-symbols-outlined animate-spin text-[16px]">sync</span>';

    try {
        const response = await fetch(appUrl(`/api/tasks/${taskId}`), {
            method: "DELETE",
        });
        if (!response.ok) {
            let detail = t("common.delete_failed");
            try {
                const payload = await response.json();
                if (payload?.detail) {
                    detail = payload.detail;
                }
            } catch (_error) {
                // Keep fallback text.
            }
            throw new Error(detail);
        }

        showToast(t("media.task_deleted"));
        window.setTimeout(() => {
            window.location.reload();
        }, 350);
    } catch (error) {
        const message = error instanceof Error ? error.message : t("common.delete_failed");
        showToast(message);
        button.disabled = false;
        button.removeAttribute("aria-busy");
        button.title = t("common.delete");
        button.setAttribute("aria-label", t("common.delete"));
        button.innerHTML = originalHtml || `<span class="material-symbols-outlined text-[16px]">delete</span><span>${escapeHtml(t("common.delete"))}</span>`;
    }
}

function updateTaskLiveSnapshot(task, snapshot) {
    if (!task || !snapshot) {
        return false;
    }
    const nextProgress = snapshot.progress_percent;
    const nextLabel = snapshot.progress_label;
    const nextLabelKey = snapshot.progress_label_key;
    const nextLabelArgs = snapshot.progress_label_args;
    const nextMode = snapshot.progress_mode;
    const nextStepIndex = snapshot.progress_step_index;
    const nextStepTotal = snapshot.progress_step_total;
    const nextSequence = snapshot.sequence ?? snapshot.event_sequence ?? task.live?.event_sequence ?? 0;
    const currentProgress = task.live?.progress_percent;
    const currentLabel = task.live?.progress_label;
    const currentLabelKey = task.live?.progress_label_key;
    const currentLabelArgs = task.live?.progress_label_args;
    const currentMode = task.live?.progress_mode;
    const currentStepIndex = task.live?.progress_step_index;
    const currentStepTotal = task.live?.progress_step_total;
    const currentSequence = task.live?.event_sequence ?? 0;
    const statusChanged = snapshot.status !== undefined && snapshot.status !== null && task.status !== snapshot.status;
    const stageChanged = snapshot.stage !== undefined && snapshot.stage !== null && task.stage !== snapshot.stage;
    const liveChanged = currentProgress !== nextProgress ||
        currentLabel !== nextLabel ||
        currentLabelKey !== nextLabelKey ||
        JSON.stringify(currentLabelArgs || null) !== JSON.stringify(nextLabelArgs || null) ||
        currentMode !== nextMode ||
        currentStepIndex !== nextStepIndex ||
        currentStepTotal !== nextStepTotal ||
        currentSequence !== nextSequence;

    if (!statusChanged && !stageChanged && !liveChanged) {
        return false;
    }

    task.live = {
        ...(task.live || {}),
        progress_percent: nextProgress ?? null,
        progress_label: nextLabel ?? null,
        progress_label_key: nextLabelKey ?? null,
        progress_label_args: nextLabelArgs ?? null,
        progress_mode: nextMode ?? null,
        progress_step_index: nextStepIndex ?? null,
        progress_step_total: nextStepTotal ?? null,
        event_sequence: nextSequence,
        event_count: task.live?.event_count ?? 0,
    };
    if (statusChanged) {
        task.status = snapshot.status;
    }
    if (stageChanged) {
        task.stage = snapshot.stage;
    }
    return true;
}

function scheduleTaskListRefresh(delayMs = 1000) {
    if (!isAdmin || !taskList) {
        return;
    }
    if (taskRefreshPromise) {
        taskRefreshPending = true;
        return;
    }
    const elapsed = Date.now() - lastTaskRefreshAt;
    const effectiveDelay = Math.max(delayMs, elapsed >= 1000 ? 0 : 1000 - elapsed);
    if (taskRefreshTimer) {
        window.clearTimeout(taskRefreshTimer);
    }
    taskRefreshTimer = window.setTimeout(() => {
        taskRefreshTimer = null;
        refreshTaskList();
    }, effectiveDelay);
}

function applyTaskSummarySnapshot(snapshots) {
    if (!Array.isArray(snapshots) || !currentTasks.length) {
        if (Array.isArray(snapshots) && snapshots.length) {
            scheduleTaskListRefresh();
        }
        return;
    }
    const snapshotById = new Map(
        snapshots
            .filter((snapshot) => snapshot && snapshot.task_id !== undefined && snapshot.task_id !== null)
            .map((snapshot) => [Number(snapshot.task_id), snapshot])
    );
    let changed = false;
    currentTasks.forEach((task) => {
        const snapshot = snapshotById.get(Number(task.id));
        if (snapshot && updateTaskLiveSnapshot(task, snapshot)) {
            changed = true;
        }
    });
    if (changed) {
        renderTaskList(currentTasks);
    }
    if (snapshots.some((snapshot) => !currentTasks.some((task) => Number(task.id) === Number(snapshot.task_id)))) {
        scheduleTaskListRefresh();
    }
}

function applyTaskStreamEvent(payload) {
    if (!payload || typeof payload !== "object") {
        return;
    }
    if (payload.event_type === "snapshot" && Array.isArray(payload.tasks)) {
        applyTaskSummarySnapshot(payload.tasks);
        return;
    }

    const taskId = Number(payload.task_id);
    if (!Number.isFinite(taskId)) {
        return;
    }
    const task = currentTasks.find((entry) => Number(entry.id) === taskId);
    if (!task) {
        scheduleTaskListRefresh();
        return;
    }
    if (updateTaskLiveSnapshot(task, payload)) {
        renderTaskList(currentTasks);
    }
    if (["done", "error"].includes(payload.event_type)) {
        scheduleTaskListRefresh();
    }
}

function appendTaskLogLine(text) {
    if (!taskLogOutput) {
        return;
    }
    taskLogOutput.textContent += `${text}\n`;
    taskLogOutput.scrollTop = taskLogOutput.scrollHeight;
}

function taskLogSequence(payload) {
    const sequence = Number(payload?.sequence);
    return Number.isFinite(sequence) && sequence > 0 ? sequence : null;
}

function openTaskLog(taskId, { scrollIntoView = false } = {}) {
    if (!isAdmin || !taskLogShell || !taskLogOutput || !taskLogTitle) {
        return;
    }
    const normalizedTaskId = Number(taskId);
    if (!Number.isFinite(normalizedTaskId) || normalizedTaskId <= 0) {
        return;
    }
    activeTaskId = normalizedTaskId;
    activeTaskLogSequence = 0;
    taskLogShell.classList.remove("hidden");
    taskLogOutput.textContent = "";
    taskLogTitle.textContent = t("media.live_task_log_for", { id: String(normalizedTaskId) });
    if (taskDetailSource) {
        taskDetailSource.close();
    }
    taskDetailSource = new EventSource(appUrl(`/api/tasks/${normalizedTaskId}/stream`));
    taskDetailSource.onmessage = (event) => {
        try {
            const payload = JSON.parse(event.data);
            const sequence = taskLogSequence(payload);
            if (sequence !== null) {
                if (sequence <= activeTaskLogSequence) {
                    return;
                }
                activeTaskLogSequence = sequence;
            }
            const label = payload.progress_label_key
                ? t(payload.progress_label_key, payload.progress_label_args || {})
                : (payload.progress_label || payload.stage || payload.status || "snapshot");
            if (payload.message) {
                appendTaskLogLine(payload.message);
            } else if (payload.event_type === "snapshot" || payload.event_type === "canceled") {
                appendTaskLogLine(label);
            }
        } catch (error) {
            console.warn("Task log parse failed:", error);
        }
    };
    taskDetailSource.onerror = () => {
        appendTaskLogLine(t("media.task_stream_reconnecting"));
    };
    renderTaskList(currentTasks);
    if (scrollIntoView) {
        scrollTaskPanelIntoView();
    }
}

function openDeepLinkedTaskFromUrl() {
    if (!initialTaskId) {
        return;
    }
    shouldScrollToTaskPanel = true;
    openTaskLog(initialTaskId);
    if (!currentTasks.some((task) => Number(task.id) === initialTaskId)) {
        scheduleTaskListRefresh();
    }
}

function bootstrapMediaModalFromUrl() {
    if (!initialMediaId || !isAdmin) {
        return;
    }

    const itemNode = findMediaItemNodeById(initialMediaId);
    if (!itemNode) {
        return;
    }

    updateMediaModalHistory(null, { replace: true });
    updateMediaModalHistory(initialMediaId);
    openEditModal(itemNode, { syncHistory: false });
}

function connectTaskStream() {
    if (!isAdmin || !taskPanel || typeof EventSource === "undefined") {
        return;
    }
    if (taskSummarySource) {
        taskSummarySource.close();
    }
    taskSummarySource = new EventSource(appUrl("/api/tasks/stream"));
    taskSummarySource.onmessage = (event) => {
        try {
            applyTaskStreamEvent(JSON.parse(event.data));
        } catch (error) {
            console.warn("Task summary parse failed:", error);
            scheduleTaskListRefresh();
        }
    };
    taskSummarySource.onerror = () => {
        window.setTimeout(() => {
            if (taskSummarySource) {
                taskSummarySource.close();
                taskSummarySource = null;
            }
            connectTaskStream();
        }, 2000);
    };
}

function syncFilterButtonStyles() {
    filterButtons.forEach((button) => {
        const active = activeCapabilityFilters.has(button.dataset.capFilter || "");
        button.classList.toggle("bg-primary/10", active);
        button.classList.toggle("border-primary/30", active);
        button.classList.toggle("text-primary", active);
        button.classList.toggle("border-white/10", !active);
        button.classList.toggle("text-on-surface-variant", !active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
    });
}

function setCapabilityFilter(nextFilter) {
    if (!nextFilter || nextFilter === "all") {
        activeCapabilityFilters.clear();
    } else if (activeCapabilityFilters.has(nextFilter)) {
        activeCapabilityFilters.delete(nextFilter);
    } else {
        activeCapabilityFilters.add(nextFilter);
    }
    syncFilterButtonStyles();
    applyFilters();
}

function openEditModal(itemNode, { syncHistory = true } = {}) {
    if (!isAdmin) {
        return;
    }
    const itemId = itemNode.dataset.itemId;
    const currentTitle = getItemFieldText(itemNode, "title");
    const currentArtistText = getItemFieldText(itemNode, "artist");
    const currentArtist = currentArtistText === t("common.unknown_artist") || currentArtistText === "Unknown Artist" ? "" : currentArtistText;
    const placeholderThumbnail = appUrl("/static/placeholder.png");
    const currentThumbnail = itemNode.dataset.thumbnail || placeholderThumbnail;
    activeEditMediaPath = itemNode.dataset.mediaPath || "";
    const lyricsPath = itemNode.dataset.lyricsPath || "";
    const hasMulti = itemNode.dataset.hasMultiTrack === "true";
    const hasLyrics = itemNode.dataset.hasLyrics === "true";
    const lyricsKind = String(itemNode.dataset.lyricsKind || "").trim().toLowerCase();

    if (!itemId || !currentTitle) {
        return;
    }
    activeEditItemId = itemId;
    const normalizedItemId = Number(itemId);
    activeEditHasMulti = hasMulti;
    activeEditFileManifest = null;
    resetMediaEditLyricsState();
    resetMediaEditInitialState();
    activeEditLyricsPath = lyricsPath;
    activeEditLyricsIsCdg = isCdgLyricsPath(lyricsPath, lyricsKind);
    activeEditInitialTitle = currentTitle;
    activeEditInitialArtist = currentArtist;
    activeEditInitialRenameOnDisk = true;
    activeEditInitialAiChecked = false;
    if (editItemIdInput) {
        editItemIdInput.value = itemId;
    }
    if (editTitleInput) {
        editTitleInput.value = currentTitle;
    }
    if (editArtistInput) {
        editArtistInput.value = currentArtist;
    }

    // Populate Previews
    const hasRealThumbnail = currentThumbnail && currentThumbnail !== placeholderThumbnail;

    if (previewImg) {
        previewImg.src = hasRealThumbnail ? currentThumbnail : "";
        previewImg.classList.toggle("hidden", !hasRealThumbnail);
    }
    if (previewPlaceholder) {
        previewPlaceholder.classList.toggle("hidden", hasRealThumbnail);
    }

    if (previewImgMobile) {
        previewImgMobile.src = hasRealThumbnail ? currentThumbnail : "";
        previewImgMobile.classList.toggle("hidden", !hasRealThumbnail);
    }
    if (previewPlaceholderMobile) {
        previewPlaceholderMobile.classList.toggle("hidden", hasRealThumbnail);
    }

    if (previewTitle) previewTitle.textContent = currentTitle;
    if (previewArtist) previewArtist.textContent = currentArtist || t("common.unknown_artist");
    if (previewTitleMobile) previewTitleMobile.textContent = currentTitle;
    if (previewArtistMobile) previewArtistMobile.textContent = currentArtist || t("common.unknown_artist");

    // Set Toggles
    if (editAiToggle) editAiToggle.checked = false;
    applyEditAiAvailability();
    refreshEditDemucsHealth();
    if (editRenameDiskCheckbox) editRenameDiskCheckbox.checked = true;
    activeEditInitialAiChecked = Boolean(editAiToggle?.checked && !activeEditHasMulti);
    updateFilenamePreview();
    if (editDownloadPackageButton) {
        editDownloadPackageButton.disabled = true;
    }

    if (syncHistory && Number.isFinite(normalizedItemId) && normalizedItemId > 0) {
        const currentMediaId = getMediaIdFromUrl();
        if (currentMediaId !== normalizedItemId) {
            updateMediaModalHistory(normalizedItemId);
        }
    }

    // Initialize lyrics manager with current metadata
    initializeMediaEditLyricsManager();
    if (lyricsManager) {
        lyricsManager.reset();
        lyricsManager.setMetadata(currentTitle, currentArtist, currentTitle);
        if (hasLyrics && activeEditLyricsIsCdg) {
            setCdgLyricsState();
        } else if (hasLyrics) {
            activeEditLyricsLoadPromise = loadCurrentLyricsForEdit(itemNode);
        } else {
            lyricsManager.setEnabled(false);
            lyricsManager.setMetadata(currentTitle, currentArtist, currentTitle);
            updateMediaEditLyricsControls();
        }
    }
    updateMediaEditToolAvailability();

    refreshMediaFileManifest();

    if (editModal) {
        editModal.classList.remove("hidden");
        editModal.setAttribute("aria-hidden", "false");
    }
    
    if (!isMobile()) {
        window.setTimeout(() => {
            editTitleInput?.focus();
            editTitleInput?.select();
        }, 0);
    }
}

function closeEditModal({ syncHistory = true } = {}) {
    activeEditItemId = null;
    activeEditHasMulti = false;
    activeEditFileManifest = null;
    resetMediaEditLyricsState();
    activeEditFilesLoadToken += 1;
    if (editLyricsStatus) {
        editLyricsStatus.textContent = "";
        editLyricsStatus.className = "text-[10px] font-semibold text-on-surface-variant";
    }
    if (editFilesList) {
        editFilesList.innerHTML = "";
    }
    if (editModal) {
        editModal.classList.add("hidden");
        editModal.setAttribute("aria-hidden", "true");
    }

    if (syncHistory && history.state?.mediaModal && getMediaIdFromUrl()) {
        history.back();
    }
}

async function saveEditModal(event) {
    event.preventDefault();
    if (!isAdmin || !activeEditItemId || !editTitleInput) {
        return;
    }
    if (activeEditLyricsLoadPromise) {
        try {
            await activeEditLyricsLoadPromise;
        } catch (_error) {
            // The modal can still save metadata changes without lyrics content.
        }
    }
    const nextTitle = editTitleInput.value.trim();
    if (!nextTitle) {
        showToast(t("media.title_empty"));
        return;
    }
    const nextArtist = editArtistInput?.value.trim() || "";
    const renameOnDisk = editRenameDiskCheckbox?.checked ?? true;
    const currentLyricsState = lyricsManager?.getState?.();
    const currentLyricsText = lyricsManager?.getSubmissionText?.() || "";
    const currentLyricsHash = currentLyricsText ? hashLyricsText(currentLyricsText) : "";
    const preserveLoadedFormat =
        Boolean(activeEditLyricsBaselineProvider) &&
        currentLyricsState?.provider === activeEditLyricsBaselineProvider;
    const currentLyricsFormat = preserveLoadedFormat
        ? activeEditLyricsBaselineFormat
        : (currentLyricsState?.format || "txt");
    const submitButton = editForm?.querySelector('button[type="submit"]');
    const originalButtonLabel = submitButton?.textContent || "";

    const aiRequested = Boolean(editAiToggle?.checked && !activeEditHasMulti);
    const alignRequested = Boolean(
        !activeEditLyricsIsCdg &&
        currentLyricsState?.alignLyricsRequested &&
        currentLyricsState?.lyricsEnabled &&
        currentLyricsText &&
        currentLyricsFormat !== "json"
    );
    const lyricsChanged = Boolean(currentLyricsText) && currentLyricsHash !== activeEditLyricsBaselineHash;
    const titleChanged = nextTitle !== activeEditInitialTitle;
    const artistChanged = nextArtist !== activeEditInitialArtist;
    const renameChanged = renameOnDisk !== activeEditInitialRenameOnDisk;
    const aiChanged = aiRequested !== activeEditInitialAiChecked;
    const alignChanged = alignRequested;
    const lyricsPayloadChanged = Boolean(currentLyricsText) && (
        !activeEditLyricsBaselineHash ||
        lyricsChanged ||
        currentLyricsFormat !== activeEditLyricsBaselineFormat
    );
    const noChanges =
        !titleChanged &&
        !artistChanged &&
        !renameChanged &&
        !aiChanged &&
        !alignChanged &&
        !lyricsPayloadChanged;
    if (noChanges) {
        closeEditModal();
        return;
    }

    if (submitButton) {
        submitButton.disabled = true;
        submitButton.textContent = renameOnDisk ? t("media.renaming") : t("media.saving");
    }

    try {
        const requestBody = {
            title: nextTitle,
            artist: nextArtist || null,
            rename_on_disk: renameOnDisk,
            is_karaoke: aiRequested,
            align_lyrics: alignRequested,
        };

        // Add lyrics if available
        if (!activeEditLyricsIsCdg && (lyricsPayloadChanged || alignRequested) && currentLyricsState?.lyricsEnabled && currentLyricsText) {
            requestBody.lyrics_text = currentLyricsText;
            requestBody.lyrics_format = currentLyricsFormat;
            requestBody.process_lyrics_lines = Boolean(currentLyricsState.processLyricsLines);
            if (currentLyricsState.processLyricsLines) {
                requestBody.max_line_length = currentLyricsState.maxLineLength;
                requestBody.max_line_length_cjk = currentLyricsState.maxLineLengthCjk;
            }
            if (alignRequested && currentLyricsState.whisperxAlignLanguageOverride) {
                requestBody.whisperx_align_language_override = currentLyricsState.whisperxAlignLanguageOverride;
            }
        }

        const response = await fetch(appUrl(`/api/media/${Number(activeEditItemId)}`), {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(requestBody),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || t("media.rename_failed"));
        }

        const payload = await response.json();
        const taskId = Number(payload.karaoke_task_id);
        const redirectTarget = Number.isFinite(taskId) && taskId > 0
            ? `/media?task_id=${taskId}`
            : "/media";
        if (payload.karaoke_warning) {
            const warningKey = payload.karaoke_warning === "demucs_offline"
                ? "karaoke.saved_without_processing"
                : "karaoke.saved_task_start_failed";
            showToast(t(warningKey, {
                detail: payload.karaoke_warning_detail || t("queue.demucs_unavailable"),
            }));
        } else if (payload.karaoke_started) {
            showToast(t("media.karaoke_task_started", { title: nextTitle }));
        } else {
            showToast(renameOnDisk ? t("media.renamed_disk", { title: nextTitle }) : t("media.updated_title", { title: nextTitle }));
        }
        closeEditModal();
        window.setTimeout(() => {
            window.location.href = appUrl(redirectTarget);
        }, payload.karaoke_warning ? 1800 : 450);
    } catch (error) {
        const message = error instanceof Error ? error.message : t("media.rename_failed");
        showToast(message);
        if (submitButton) {
            submitButton.disabled = false;
            submitButton.textContent = originalButtonLabel || t("common.rename");
        }
    }
}

async function addToQueue(itemNode) {
    const itemId = itemNode.dataset.itemId;
    const title = getItemFieldText(itemNode, "title") || "item";
    const artistText = getItemFieldText(itemNode, "artist");
    const artist = artistText && artistText !== t("common.unknown_artist") && artistText !== "Unknown Artist" ? artistText : "";

    if (itemNode.dataset.missing === "true") {
        showToast(t("media.missing_from_disk"));
        return;
    }

    setButtonsForAction(itemId, "add-to-queue", { disabled: true, label: t("media.adding") });

    try {
        const payload = {
            media_item_id: Number(itemId),
            title,
            is_karaoke: false,
        };
        if (artist) {
            payload.artist = artist;
        }

        const response = await fetch(appUrl("/api/queue/"), {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || t("media.queue_failed"));
        }

        const item = await response.json();
        try {
            await fetch(appUrl(`/api/queue/${item.id}/process`), {
                method: "POST",
            });
        } catch (processError) {
            console.warn("Queue processing trigger failed:", processError);
        }

        showToast(t("media.queued", { title }));
        setButtonsForAction(itemId, "add-to-queue", { disabled: true, label: t("media.queued_label") });
    } catch (error) {
        const message = error instanceof Error ? error.message : t("media.queue_failed");
        showToast(message);
        setButtonsForAction(itemId, "add-to-queue", { disabled: false, label: t("common.add_to_queue") });
    }
}

async function deleteItem(itemNode) {
    const itemId = itemNode.dataset.itemId;
    const title = getItemFieldText(itemNode, "title") || "item";
    const confirmed = window.confirm(t("media.confirm_delete", { title }));
    if (!confirmed) {
        return;
    }

    setButtonsForAction(itemId, "delete", { disabled: true, label: t("media.deleting") });
    setButtonsForAction(itemId, "add-to-queue", { disabled: true });
    setButtonsForAction(itemId, "edit", { disabled: true });

    try {
        const response = await fetch(appUrl(`/api/media/${Number(itemId)}`), {
            method: "DELETE",
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || t("media.delete_failed"));
        }

        showToast(t("media.deleted", { title }));
        window.setTimeout(() => {
            window.location.reload();
        }, 450);
    } catch (error) {
        const message = error instanceof Error ? error.message : t("media.delete_failed");
        showToast(message);
        setButtonsForAction(itemId, "delete", { disabled: false, label: t("common.delete") });
        setButtonsForAction(itemId, "add-to-queue", { disabled: false, label: t("common.add_to_queue") });
        setButtonsForAction(itemId, "edit", { disabled: false });
    }
}

async function autoRenameMediaItem(actionButton) {
    if (!isAdmin || !editTitleInput || !editArtistInput) {
        return;
    }

    const title = editTitleInput.value.trim();
    const artist = editArtistInput.value.trim();
    if (!title) {
        showToast(t("media.add_title_before_auto"));
        return;
    }

    const button = actionButton || document.querySelector('button[data-action="auto-rename"]');
    if (!button || button.disabled) {
        return;
    }

    const originalHtml = button.innerHTML;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.classList.add("opacity-70", "cursor-wait");
    button.innerHTML = AUTO_RENAME_LOADING_HTML;

    try {
        const response = await fetch(appUrl("/api/lyrics/resolve"), {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                title,
                artist: artist || undefined,
                youtube_title: title,
            }),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || t("media.infer_failed"));
        }

        const payload = await response.json();
        const nextTitle = (payload.title || title).trim();
        const nextArtist = (payload.artist || artist).trim();

        editTitleInput.value = nextTitle;
        editArtistInput.value = nextArtist;
        syncEditPreviewLabels(nextTitle, nextArtist);
        updateFilenamePreview();

        showToast(nextArtist ? t("media.inferred_artist_title", { artist: nextArtist, title: nextTitle }) : t("media.inferred_title", { title: nextTitle }));
    } catch (error) {
        const message = error instanceof Error ? error.message : t("media.infer_failed");
        showToast(message);
    } finally {
        button.disabled = false;
        button.removeAttribute("aria-busy");
        button.classList.remove("opacity-70", "cursor-wait");
        button.innerHTML = originalHtml || AUTO_RENAME_DEFAULT_HTML;
    }
}

async function refreshMediaItemSidecars(actionButton) {
    if (!isAdmin || !activeEditItemId || !actionButton || actionButton.disabled) {
        return;
    }

    const originalHtml = actionButton.innerHTML;
    actionButton.disabled = true;
    actionButton.setAttribute("aria-busy", "true");
    actionButton.classList.add("opacity-70", "cursor-wait");
    actionButton.innerHTML = `<span class="material-symbols-outlined animate-spin text-[18px]">sync</span>`;

    try {
        const response = await fetch(appUrl(`/api/media/${Number(activeEditItemId)}/scan`), {
            method: "POST",
        });

        if (!response.ok) {
            let detail = null;
            try {
                const error = await response.json();
                detail = error.detail || null;
            } catch (_error) {
                detail = null;
            }
            throw new Error(detail || t("media.scan_failed_status", { status: response.status }));
        }

        await response.json();
        showToast(t("media.sidecars_refreshed"));
        window.setTimeout(() => {
            window.location.reload();
        }, 400);
    } catch (error) {
        const message = error instanceof Error ? error.message : t("media.scan_failed");
        showToast(message);
        actionButton.disabled = false;
        actionButton.removeAttribute("aria-busy");
        actionButton.classList.remove("opacity-70", "cursor-wait");
        actionButton.innerHTML = originalHtml || `<span class="material-symbols-outlined text-[18px]">refresh</span>`;
    }
}

async function runLibraryScan(actionButton) {
    if (!isAdmin || !actionButton) {
        return;
    }
    const originalLabel = actionButton.textContent;
    actionButton.disabled = true;
    actionButton.classList.add("opacity-70", "cursor-default");
    actionButton.textContent = t("media.scanning");
    try {
        const response = await fetch(appUrl("/api/media/scan"), { method: "POST" });
        if (!response.ok) {
            throw new Error(t("media.scan_failed_status", { status: response.status }));
        }
        const payload = await response.json();
        const summary = payload?.summary || {};
        const created = Number(summary.created || 0);
        const markedMissing = Number(summary.marked_missing || 0);
        showToast(t("media.scan_complete", { created, missing: markedMissing }));
        window.setTimeout(() => {
            window.location.reload();
        }, 500);
    } catch (error) {
        const message = error instanceof Error ? error.message : t("media.scan_failed");
        showToast(message);
        actionButton.disabled = false;
        actionButton.classList.remove("opacity-70", "cursor-default");
        actionButton.textContent = originalLabel;
    }
}

function handleActionClick(event) {
    const button = event.target.closest("button[data-action]");
    if (!button) {
        return;
    }
    const action = button.dataset.action;

    const guestAllowedActions = new Set(["add-to-queue", "retry-task", "delete-task", "cancel-task", "clear-task-log"]);
    if (!isAdmin && !guestAllowedActions.has(action)) {
        return;
    }

    if (action === "scan-library") {
        runLibraryScan(button);
        return;
    }

    if (action === "upload-media") {
        window.location.href = appUrl("/upload");
        return;
    }

    if (action === "auto-rename") {
        autoRenameMediaItem(button);
        return;
    }

    if (action === "clear-task-log") {
        if (taskLogOutput) {
            taskLogOutput.textContent = "";
        }
        return;
    }

    if (action === "cancel-task") {
        cancelProcessingTask(button);
        return;
    }

    if (action === "delete-task") {
        deleteProcessingTask(button);
        return;
    }

    if (action === "retry-task") {
        const taskId = Number(button.dataset.taskId || button.closest('[data-task-id]')?.dataset.taskId);
        if (!Number.isFinite(taskId) || taskId <= 0) {
            return;
        }
        retryTask(taskId);
        return;
    }

    if (action === "scan-item-sidecars") {
        refreshMediaItemSidecars(button);
        return;
    }

    if (action === "download-media-package") {
        downloadMediaPackage();
        return;
    }

    if (action === "download-media-file") {
        downloadMediaFile(button);
        return;
    }

    if (action === "delete-media-file") {
        deleteMediaFile(button);
        return;
    }

    if (action === "open-trim-editor") {
        if (activeEditItemId) {
            const url = new URL(appUrl(`/media-editor/${activeEditItemId}`), window.location.origin);
            if (activeEditLyricsIsCdg) {
                url.searchParams.set("mode", "cdg");
            }
            window.location.href = url.pathname + url.search;
        }
        return;
    }

    if (action === "open-subtitle-editor") {
        if (activeEditItemId) {
            window.location.href = appUrl(`/media-subtitles/${activeEditItemId}`);
        }
        return;
    }

    if (action === "open-vocals-editor") {
        if (activeEditItemId) {
            window.location.href = appUrl(`/media-vocals/${activeEditItemId}`);
        }
        return;
    }

    const itemNode = event.target.closest(".media-item-row, .media-item-card");
    if (!itemNode) {
        return;
    }

    if (action === "edit") {
        openEditModal(itemNode);
    } else if (action === "delete") {
        deleteItem(itemNode);
    } else if (action === "add-to-queue") {
        addToQueue(itemNode);
    }
}

if (editTitleInput) {
    editTitleInput.addEventListener("input", (e) => {
        const val = e.target.value.trim() || t("common.track_title");
        if (previewTitle) previewTitle.textContent = val;
        if (previewTitleMobile) previewTitleMobile.textContent = val;
        updateFilenamePreview();
        syncMediaEditLyricsMetadata();
    });
}

if (editArtistInput) {
    editArtistInput.addEventListener("input", (e) => {
        const val = e.target.value.trim() || t("common.artist_name");
        if (previewArtist) previewArtist.textContent = val;
        if (previewArtistMobile) previewArtistMobile.textContent = val;
        updateFilenamePreview();
        syncMediaEditLyricsMetadata();
    });
}

if (editRenameDiskCheckbox) {
    editRenameDiskCheckbox.addEventListener("change", updateFilenamePreview);
}

if (searchInput) {
    searchInput.addEventListener("input", applyFilters);
}

filterButtons.forEach((button) => {
    button.addEventListener("click", () => {
      setCapabilityFilter(button.dataset.capFilter || "all");
    });
});

document.addEventListener("click", handleActionClick);
editModalCloseButtons.forEach((button) => {
    button.addEventListener("click", closeEditModal);
});
editModal?.addEventListener("click", (event) => {
    if (event.target === editModal) {
        closeEditModal();
    }
});
editForm?.addEventListener("submit", saveEditModal);

// Lyrics toggle handlers
if (editLyricsToggle) {
    editLyricsToggle.addEventListener('change', () => {
        initializeMediaEditLyricsManager();
        if (lyricsManager && !activeEditLyricsIsCdg) {
            const nextEnabled = editLyricsToggle.checked;
            syncMediaEditLyricsMetadata();
            lyricsManager.setEnabled(nextEnabled);
        }
    });
}
if (editLyricsAlignToggle) {
    editLyricsAlignToggle.addEventListener("click", (event) => {
        event.preventDefault();
        initializeMediaEditLyricsManager();
        if (lyricsManager && !activeEditLyricsIsCdg) {
            const currentState = lyricsManager.getState();
            lyricsManager.setAlignLyricsRequested(!currentState.alignLyricsRequested);
        }
    });
}

document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && editModal && !editModal.classList.contains("hidden")) {
        closeEditModal();
    }
});
window.addEventListener("popstate", syncMediaModalStateFromUrl);
window.addEventListener("pageshow", (event) => {
    if (event.persisted) {
        syncMediaModalStateFromUrl();
    }
});
taskList?.addEventListener("click", (event) => {
    if (!isAdmin) {
        return;
    }
    if (event.target.closest("button[data-action]")) {
        return;
    }
    const taskCard = event.target.closest("[data-task-id]");
    if (!taskCard) {
        return;
    }
    openTaskLog(taskCard.dataset.taskId);
});
syncFilterButtonStyles();
updateEmptyState();
bootstrapMediaModalFromUrl();
refreshTaskList();
connectTaskStream();
openDeepLinkedTaskFromUrl();
