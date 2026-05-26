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
const initialTaskId = (() => {
    const rawTaskId = new URLSearchParams(window.location.search).get("task_id");
    const parsedTaskId = Number(rawTaskId);
    return Number.isFinite(parsedTaskId) && parsedTaskId > 0 ? parsedTaskId : null;
})();

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
    return `
        <div class="mt-3 max-w-xs">
            <div class="h-2 overflow-hidden rounded-full bg-surface-container-highest">
                <div class="h-full rounded-full bg-primary transition-all" style="width: ${Math.max(0, Math.min(100, percent))}%"></div>
            </div>
            <p class="mt-1 text-[11px] text-on-surface-variant">${escapeHtml(label)} • ${escapeHtml(String(percent))}%</p>
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
        const actionHtml = task.status === "canceled"
            ? `
                <div class="mt-3 flex justify-end">
                    <button
                        type="button"
                        data-action="delete-task"
                        class="inline-flex items-center gap-2 rounded-full border border-error/30 bg-error/10 px-3 py-1.5 text-[11px] font-black uppercase tracking-wider text-error transition-colors hover:bg-error/15 disabled:cursor-not-allowed disabled:opacity-60"
                        data-task-id="${task.id}"
                        title="${escapeHtml(t("media.delete_task"))}"
                        aria-label="${escapeHtml(t("media.delete_task"))}"
                    >
                        <span class="material-symbols-outlined text-[16px]">delete</span>
                        <span>${escapeHtml(t("media.delete_task"))}</span>
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
                        title="${escapeHtml(t("media.cancel_task"))}"
                        aria-label="${escapeHtml(t("media.cancel_task"))}"
                    >
                        <span class="material-symbols-outlined text-[16px]">close</span>
                        <span>${escapeHtml(t("media.cancel_task"))}</span>
                    </button>
                </div>
                `;
        return `
            <article class="rounded-xl border ${isSelectedTask ? 'border-primary/40 bg-primary/5 ring-1 ring-primary/20' : 'border-white/10 bg-surface-container-low'} p-3 cursor-pointer transition-colors" data-task-id="${task.id}" aria-current="${isSelectedTask ? 'true' : 'false'}">
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
    if (shouldScrollToTaskPanel && currentTasks.length > 0) {
        shouldScrollToTaskPanel = false;
        scrollTaskPanelIntoView();
    }
}

async function refreshTaskList() {
    if (!isAdmin || !taskList) {
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

async function cancelProcessingTask(button) {
    if (!button || !isAdmin) {
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
            let detail = t("media.cancel_task_failed");
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
        const message = error instanceof Error ? error.message : t("media.cancel_task_failed");
        showToast(message);
        button.disabled = false;
        button.removeAttribute("aria-busy");
        button.title = t("media.cancel_task");
        button.setAttribute("aria-label", t("media.cancel_task"));
        button.innerHTML = originalHtml || `<span class="material-symbols-outlined text-[16px]">close</span><span>${escapeHtml(t("media.cancel_task"))}</span>`;
    }
}

async function deleteProcessingTask(button) {
    if (!button || !isAdmin) {
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
            let detail = t("media.delete_task_failed");
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
        const message = error instanceof Error ? error.message : t("media.delete_task_failed");
        showToast(message);
        button.disabled = false;
        button.removeAttribute("aria-busy");
        button.title = t("media.delete_task");
        button.setAttribute("aria-label", t("media.delete_task"));
        button.innerHTML = originalHtml || `<span class="material-symbols-outlined text-[16px]">delete</span><span>${escapeHtml(t("media.delete_task"))}</span>`;
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
    const nextStepIndex = snapshot.progress_step_index;
    const nextStepTotal = snapshot.progress_step_total;
    const nextSequence = snapshot.sequence ?? snapshot.event_sequence ?? task.live?.event_sequence ?? 0;
    const currentProgress = task.live?.progress_percent;
    const currentLabel = task.live?.progress_label;
    const currentLabelKey = task.live?.progress_label_key;
    const currentLabelArgs = task.live?.progress_label_args;
    const currentStepIndex = task.live?.progress_step_index;
    const currentStepTotal = task.live?.progress_step_total;
    const currentSequence = task.live?.event_sequence ?? 0;
    const statusChanged = snapshot.status !== undefined && snapshot.status !== null && task.status !== snapshot.status;
    const stageChanged = snapshot.stage !== undefined && snapshot.stage !== null && task.stage !== snapshot.stage;
    const liveChanged = currentProgress !== nextProgress ||
        currentLabel !== nextLabel ||
        currentLabelKey !== nextLabelKey ||
        JSON.stringify(currentLabelArgs || null) !== JSON.stringify(nextLabelArgs || null) ||
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

function openEditModal(itemNode) {
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
    if (!isAdmin || !activeEditItemId || !editTitleInput) {
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

    if (!isAdmin && action !== "add-to-queue") {
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

    if (action === "scan-item-sidecars") {
        refreshMediaItemSidecars(button);
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
taskList?.addEventListener("click", (event) => {
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
refreshTaskList();
connectTaskStream();
openDeepLinkedTaskFromUrl();
