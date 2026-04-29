const searchInput = document.getElementById("media-search-input");
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
const AUTO_RENAME_DEFAULT_HTML = '<span class="material-symbols-outlined text-[16px]">auto_fix_high</span><span>Auto</span>';
const AUTO_RENAME_LOADING_HTML = '<span class="material-symbols-outlined animate-spin text-[16px]">sync</span><span>Inferring...</span>';

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
    const title = nextTitle.trim() || "Title";
    const artist = nextArtist.trim();
    const clean = [artist, title].filter(Boolean).join(" - ").replace(/\s+/g, " ").trim();
    return `${clean || "media"}${currentExtension}`;
}

function updateFilenamePreview() {
    if (!editFilenamePreview || !editTitleInput || !editArtistInput) return;

    const currentFilename = getFilenameFromPath(activeEditMediaPath) || "unknown";
    const renameEnabled = Boolean(editRenameDiskCheckbox?.checked);
    const nextFilename = buildRenamedFilename(editTitleInput.value, editArtistInput.value);
    editFilenamePreview.textContent = renameEnabled
        ? `Will rename to: ${nextFilename}`
        : `Current on-disk filename: ${currentFilename}`;
}

function syncEditPreviewLabels(title, artist) {
    const normalizedTitle = title.trim() || "Track Title";
    const normalizedArtist = artist.trim() || "Artist Name";

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
        setItemFieldText(node, "artist", normalizedArtist || "Unknown Artist");
        
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
    const currentArtist = currentArtistText === "Unknown Artist" ? "" : currentArtistText;
    const currentThumbnail = itemNode.dataset.thumbnail || "/static/placeholder.png";
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
    const hasRealThumbnail = currentThumbnail && currentThumbnail !== "/static/placeholder.png";

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
    if (previewArtist) previewArtist.textContent = currentArtist || "Unknown Artist";
    if (previewTitleMobile) previewTitleMobile.textContent = currentTitle;
    if (previewArtistMobile) previewArtistMobile.textContent = currentArtist || "Unknown Artist";

    // Set Toggles
    if (editAiToggle) editAiToggle.checked = hasMulti;
    if (editLyricsToggle) editLyricsToggle.checked = hasLyrics;
    if (editRenameDiskCheckbox) editRenameDiskCheckbox.checked = true;
    updateFilenamePreview();

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
        showToast("Title cannot be empty.");
        return;
    }
    const nextArtist = editArtistInput?.value.trim() || "";
    const renameOnDisk = editRenameDiskCheckbox?.checked ?? true;
    const submitButton = editForm?.querySelector('button[type="submit"]');
    const originalButtonLabel = submitButton?.textContent || "";

    if (submitButton) {
        submitButton.disabled = true;
        submitButton.textContent = renameOnDisk ? "Renaming..." : "Saving...";
    }

    try {
        const response = await fetch(`/api/media/${Number(activeEditItemId)}`, {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                title: nextTitle,
                artist: nextArtist || null,
                rename_on_disk: renameOnDisk,
            }),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || "Failed to rename media item");
        }

        showToast(renameOnDisk ? `Renamed "${nextTitle}" on disk` : `Updated "${nextTitle}"`);
        closeEditModal();
        window.setTimeout(() => {
            window.location.reload();
        }, 450);
    } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to rename media item";
        showToast(message);
        if (submitButton) {
            submitButton.disabled = false;
            submitButton.textContent = originalButtonLabel || "Rename";
        }
    }
}

async function addToQueue(itemNode) {
    const itemId = itemNode.dataset.itemId;
    const title = getItemFieldText(itemNode, "title") || "item";
    const artistText = getItemFieldText(itemNode, "artist");
    const artist = artistText && artistText !== "Unknown Artist" ? artistText : "";

    if (itemNode.dataset.missing === "true") {
        showToast("This media item is missing from disk.");
        return;
    }

    setButtonsForAction(itemId, "add-to-queue", { disabled: true, label: "Adding..." });

    try {
        const payload = {
            media_item_id: Number(itemId),
            title,
            is_karaoke: false,
        };
        if (artist) {
            payload.artist = artist;
        }

        const response = await fetch("/api/queue/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || "Failed to add to queue");
        }

        const item = await response.json();
        try {
            await fetch(`/api/queue/${item.id}/process`, {
                method: "POST",
            });
        } catch (processError) {
            console.warn("Queue processing trigger failed:", processError);
        }

        showToast(`Queued "${title}"`);
        setButtonsForAction(itemId, "add-to-queue", { disabled: true, label: "Queued" });
    } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to add to queue";
        showToast(message);
        setButtonsForAction(itemId, "add-to-queue", { disabled: false, label: "Add to Queue" });
    }
}

async function deleteItem(itemNode) {
    const itemId = itemNode.dataset.itemId;
    const title = getItemFieldText(itemNode, "title") || "item";
    const confirmed = window.confirm(`Delete "${title}" from media library?`);
    if (!confirmed) {
        return;
    }

    setButtonsForAction(itemId, "delete", { disabled: true, label: "Deleting..." });
    setButtonsForAction(itemId, "add-to-queue", { disabled: true });
    setButtonsForAction(itemId, "edit", { disabled: true });

    try {
        const response = await fetch(`/api/media/${Number(itemId)}`, {
            method: "DELETE",
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || "Failed to delete media item");
        }

        showToast(`Deleted "${title}"`);
        window.setTimeout(() => {
            window.location.reload();
        }, 450);
    } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to delete media item";
        showToast(message);
        setButtonsForAction(itemId, "delete", { disabled: false, label: "Delete" });
        setButtonsForAction(itemId, "add-to-queue", { disabled: false, label: "Add to Queue" });
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
        showToast("Add a title before using Auto.");
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
        const response = await fetch("/api/lyrics/resolve", {
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
            throw new Error(error.detail || "Failed to infer metadata");
        }

        const payload = await response.json();
        const nextTitle = (payload.title || title).trim();
        const nextArtist = (payload.artist || artist).trim();

        editTitleInput.value = nextTitle;
        editArtistInput.value = nextArtist;
        syncEditPreviewLabels(nextTitle, nextArtist);
        updateFilenamePreview();

        showToast(nextArtist ? `Inferred "${nextArtist} - ${nextTitle}"` : `Inferred "${nextTitle}"`);
    } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to infer metadata";
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
    actionButton.textContent = "Scanning...";
    try {
        const response = await fetch("/api/media/scan", { method: "POST" });
        if (!response.ok) {
            throw new Error(`Scan failed (${response.status})`);
        }
        const payload = await response.json();
        const summary = payload?.summary || {};
        const created = Number(summary.created || 0);
        const markedMissing = Number(summary.marked_missing || 0);
        showToast(`Scan complete: +${created} new, ${markedMissing} missing`);
        window.setTimeout(() => {
            window.location.reload();
        }, 500);
    } catch (error) {
        const message = error instanceof Error ? error.message : "Scan failed";
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
        showToast("Upload flow is coming soon.");
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
        const val = e.target.value.trim() || "Track Title";
        if (previewTitle) previewTitle.textContent = val;
        if (previewTitleMobile) previewTitleMobile.textContent = val;
        updateFilenamePreview();
    });
}

if (editArtistInput) {
    editArtistInput.addEventListener("input", (e) => {
        const val = e.target.value.trim() || "Artist Name";
        if (previewArtist) previewArtist.textContent = val;
        if (previewArtistMobile) previewArtistMobile.textContent = val;
        updateFilenamePreview();
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
document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && editModal && !editModal.classList.contains("hidden")) {
        closeEditModal();
    }
});
syncFilterButtonStyles();
updateEmptyState();
