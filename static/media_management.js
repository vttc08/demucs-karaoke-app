const searchInput = document.getElementById("media-search-input");
const filterButtons = document.querySelectorAll(".media-cap-filter");
const mediaRows = document.querySelectorAll(".media-item-row, .media-item-card");
const emptyState = document.getElementById("media-empty-state");
const toast = document.getElementById("media-toast");
const toastText = document.getElementById("media-toast-text");

const activeCapabilityFilters = new Set();
let toastTimer = null;

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

function renameItem(itemNode) {
    const titleElement = itemNode.querySelector('[data-field="title"]');
    const currentTitle = titleElement?.textContent?.trim();
    if (!titleElement || !currentTitle) {
        return;
    }
    const nextTitle = window.prompt("Rename media title", currentTitle);
    if (!nextTitle || !nextTitle.trim()) {
        return;
    }
    const normalized = nextTitle.trim();
    titleElement.textContent = normalized;
    itemNode.dataset.title = normalized.toLowerCase();
    showToast(`Renamed to "${normalized}"`);
    applyFilters();
}

function deleteItem(itemNode) {
    const title = itemNode.querySelector('[data-field="title"]')?.textContent?.trim() || "item";
    const confirmed = window.confirm(`Delete "${title}" from media library?`);
    if (!confirmed) {
        return;
    }
    itemNode.remove();
    showToast(`Deleted "${title}"`);
    updateEmptyState();
}

function addToQueue(itemNode, actionButton) {
    const title = itemNode.querySelector('[data-field="title"]')?.textContent?.trim() || "item";
    actionButton.disabled = true;
    actionButton.textContent = "Queued";
    actionButton.classList.add("opacity-70", "cursor-default");
    showToast(`Added "${title}" to queue (placeholder)`);
}

function handleActionClick(event) {
    const button = event.target.closest("button[data-action]");
    if (!button) {
        return;
    }
    const itemNode = event.target.closest(".media-item-row, .media-item-card");
    if (!itemNode) {
        return;
    }
    const action = button.dataset.action;
    if (action === "rename") {
        renameItem(itemNode);
    } else if (action === "delete") {
        deleteItem(itemNode);
    } else if (action === "add-to-queue") {
        addToQueue(itemNode, button);
    } else if (action === "upload-media") {
        showToast("Upload flow is coming soon.");
    } else if (action === "scan-library") {
        showToast("Scanning library...");
    }
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
syncFilterButtonStyles();
updateEmptyState();
