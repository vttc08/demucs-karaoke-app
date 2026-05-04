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
const editLyricsToggle = document.getElementById("media-edit-lyrics-toggle");
const editFilenamePreview = document.getElementById("media-edit-filename-preview");
const editModalCloseButtons = document.querySelectorAll("[data-edit-modal-close]");
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
        stateLabel: '#media-edit-lyrics-status',
        providerLabel: '#media-edit-lyrics-provider',
        searchBtn: '#media-edit-lyrics-search-btn',
        googleLink: '#media-edit-lyrics-google-btn',
        uploadBtn: '#media-edit-lyrics-upload-btn',
        fileInput: '#media-edit-lyrics-file',
        panel: '#media-edit-lyrics-form-section'
    });
    lyricsUIAdapter.initialize();
}

function syncMediaEditLyricsMetadata() {
    if (!lyricsManager) return;
    lyricsManager.setMetadata(editTitleInput?.value || "", editArtistInput?.value || "", editTitleInput?.value || "");
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

function isMobile() {
    return window.innerWidth < 640;
}

function getFilenameFromPath(mediaPath) {
    const cleanPath = String(mediaPath || "").split("?")[0];
    const parts = cleanPath.split("/").filter(Boolean);
    return parts.length > 0 ? decodeURIComponent(parts[parts.length - 1]) : "";
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

function updateMediaItemDisplay(itemId, title, artist, hasMulti, hasLyrics) {
    const normalizedTitle = title.trim();
    const normalizedArtist = normalizeArtistValue(artist);
    const nodes = getMediaItemNodes(itemId);
    nodes.forEach((node) => {
        node.dataset.title = normalizedTitle.toLowerCase();
        node.dataset.artist = normalizedArtist.toLowerCase();
        node.dataset.hasMultiTrack = String(hasMulti);
        node.dataset.hasLyrics = String(hasLyrics);

        setItemFieldText(node, "title", normalizedTitle);
        setItemFieldText(node, "artist", normalizedArtist || t("common.unknown_artist"));
        
        // Update Chips (using escaping for the slash in class selector)
        const multiChip = node.querySelector('.rounded-full.bg-secondary\\/10');
        const lyricsChip = node.querySelector('.rounded-full.bg-primary\\/10');
        
        if (multiChip) {
            multiChip.classList.toggle("hidden", !hasMulti);
        }
        if (lyricsChip) {
            lyricsChip.classList.toggle("hidden", !hasLyrics);
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

function openEditModal(itemNode) {
    const itemId = itemNode.dataset.itemId;
    const currentTitle = getItemFieldText(itemNode, "title");
    const currentArtistText = getItemFieldText(itemNode, "artist");
    const currentArtist = currentArtistText === t("common.unknown_artist") || currentArtistText === "Unknown Artist" ? "" : currentArtistText;
    const placeholderThumbnail = appUrl("/static/placeholder.png");
    const currentThumbnail = itemNode.dataset.thumbnail || placeholderThumbnail;
    activeEditMediaPath = itemNode.dataset.mediaPath || "";
    const hasMulti = itemNode.dataset.hasMultiTrack === "true";
    const hasLyrics = itemNode.dataset.hasLyrics === "true";

    if (!itemId || !currentTitle) {
        return;
    }
    activeEditItemId = itemId;
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
    if (editAiToggle) editAiToggle.checked = hasMulti;
    if (editLyricsToggle) editLyricsToggle.checked = hasLyrics;
    if (editRenameDiskCheckbox) editRenameDiskCheckbox.checked = true;
    updateFilenamePreview();

    // Initialize lyrics manager with current metadata
    initializeMediaEditLyricsManager();
    if (lyricsManager) {
        lyricsManager.reset();
        lyricsManager.setMetadata(currentTitle, currentArtist, currentTitle);
        lyricsManager.setEnabled(hasLyrics);
    }

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

function closeEditModal() {
    activeEditItemId = null;
    if (editModal) {
        editModal.classList.add("hidden");
        editModal.setAttribute("aria-hidden", "true");
    }
}

async function saveEditModal(event) {
    event.preventDefault();
    if (!activeEditItemId || !editTitleInput) {
        return;
    }
    const nextTitle = editTitleInput.value.trim();
    if (!nextTitle) {
        showToast(t("media.title_empty"));
        return;
    }
    const nextArtist = editArtistInput?.value.trim() || "";
    const renameOnDisk = editRenameDiskCheckbox?.checked ?? true;
    const submitButton = editForm?.querySelector('button[type="submit"]');
    const originalButtonLabel = submitButton?.textContent || "";

    if (submitButton) {
        submitButton.disabled = true;
        submitButton.textContent = renameOnDisk ? t("media.renaming") : t("media.saving");
    }

    try {
        const requestBody = {
            title: nextTitle,
            artist: nextArtist || null,
            rename_on_disk: renameOnDisk,
        };

        // Add lyrics if available
        if (lyricsManager && lyricsManager.state.lyricsEnabled) {
            syncMediaEditLyricsMetadata();
            const lyricsPayload = lyricsManager.getLyricsSubmissionPayload();
            if (lyricsPayload) {
                requestBody.lyrics_text = lyricsPayload.lyrics_text;
                requestBody.lyrics_format = lyricsPayload.lyrics_format;
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

        showToast(renameOnDisk ? t("media.renamed_disk", { title: nextTitle }) : t("media.updated_title", { title: nextTitle }));
        closeEditModal();
        window.setTimeout(() => {
            window.location.reload();
        }, 450);
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
    if (!editTitleInput || !editArtistInput) {
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

async function runLibraryScan(actionButton) {
    if (!actionButton) {
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
if (editAiToggle) {
    editAiToggle.addEventListener('change', () => {
        if (editAiToggle.checked) {
            showToast(t("media.ai_applies_on_queue"));
        }
    });
}

if (editLyricsToggle) {
    editLyricsToggle.addEventListener('change', () => {
        initializeMediaEditLyricsManager();
        if (lyricsManager) {
            syncMediaEditLyricsMetadata();
            lyricsManager.setEnabled(editLyricsToggle.checked);
        }
    });
}

document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && editModal && !editModal.classList.contains("hidden")) {
        closeEditModal();
    }
});
syncFilterButtonStyles();
updateEmptyState();
