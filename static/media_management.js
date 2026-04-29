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
const editFilenameContainer = document.getElementById("media-edit-filename-container");
const editFilenamePreview = document.getElementById("media-edit-filename-preview");
const editModalCloseButtons = document.querySelectorAll("[data-edit-modal-close]");

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

function isMobile() {
    return window.innerWidth < 640;
}

function updateFilenamePreview() {
    if (!editFilenamePreview || !editTitleInput || !editArtistInput) return;
    
    const title = editTitleInput.value.trim() || "Title";
    const artist = editArtistInput.value.trim() || "Artist";
    editFilenamePreview.textContent = `${artist} - ${title}.mp4`; // Placeholder extension

    if (editRenameDiskCheckbox && editFilenameContainer) {
        editFilenameContainer.classList.toggle("hidden", !editRenameDiskCheckbox.checked);
    }
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
    const currentArtist = itemNode.dataset.artist || (getItemFieldText(itemNode, "artist") === "Unknown Artist" ? "" : getItemFieldText(itemNode, "artist"));
    const currentThumbnail = itemNode.dataset.thumbnail || "/static/placeholder.png";
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
    if (editRenameDiskCheckbox) editRenameDiskCheckbox.checked = false;
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

function saveEditModal(event) {
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
    const nextMulti = editAiToggle?.checked || false;
    const nextLyrics = editLyricsToggle?.checked || false;

    updateMediaItemDisplay(activeEditItemId, nextTitle, nextArtist, nextMulti, nextLyrics);
    showToast(`Updated "${nextTitle}" locally`);
    closeEditModal();
    applyFilters();
}

function deleteItem(itemNode) {
    const itemId = itemNode.dataset.itemId;
    const title = getItemFieldText(itemNode, "title") || "item";
    const confirmed = window.confirm(`Delete "${title}" from media library?`);
    if (!confirmed) {
        return;
    }
    getMediaItemNodes(itemId).forEach((node) => node.remove());
    showToast(`Deleted "${title}"`);
    updateEmptyState();
}

function addToQueue(itemNode) {
    const itemId = itemNode.dataset.itemId;
    const title = getItemFieldText(itemNode, "title") || "item";
    getMediaItemNodes(itemId).forEach((node) => {
        node.querySelectorAll('button[data-action="add-to-queue"]').forEach((button) => {
            button.disabled = true;
            button.textContent = "Queued";
            button.classList.add("opacity-70", "cursor-default");
        });
    });
    showToast(`Added "${title}" to queue (placeholder)`);
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
        showToast("Auto-rename magic is coming soon.");
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
