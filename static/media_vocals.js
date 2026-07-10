(function () {
    const appUrl = window.KaraokeURLs?.appUrl || ((path) => path);
    const t = (key, params = {}) => window.KaraokeI18n?.t(key, params) || key;
    const root = document.getElementById("vocal-sync-page");
    if (!root) return;

    const mediaId = Number(root.dataset.mediaId);
    const hasVocals = root.dataset.hasVocals === "true";
    const media = document.getElementById("vocal-sync-media");
    const vocals = document.getElementById("vocal-sync-vocals");
    const stateLabel = document.getElementById("vocal-sync-state");
    const message = document.getElementById("vocal-sync-message");
    const vocalSyncSearchHeading = document.getElementById("vocal-sync-search-heading");
    const searchInput = document.getElementById("vocal-sync-search-input");
    const searchClearBtn = document.getElementById("vocal-sync-search-clear");
    const searchBtn = document.getElementById("vocal-sync-search-btn");
    const searchResults = document.getElementById("vocal-sync-search-results");
    const youtubeSelected = document.getElementById("vocal-sync-youtube-selected");
    const youtubeHint = document.getElementById("vocal-sync-youtube-hint");
    const youtubePrepareBtn = document.getElementById("vocal-sync-prepare-youtube");
    const youtubePrepareBtnLabel = document.getElementById("vocal-sync-prepare-youtube-label");
    const youtubeProgress = document.getElementById("vocal-sync-youtube-progress");
    const youtubeProgressStatus = document.getElementById("vocal-sync-youtube-progress-status");
    const youtubeProgressPercent = document.getElementById("vocal-sync-youtube-progress-percent");
    const youtubeProgressBar = document.getElementById("vocal-sync-youtube-progress-bar");
    const uploadForm = document.getElementById("vocal-sync-upload-form");
    const uploadFile = document.getElementById("vocal-sync-upload-file");
    const uploadSubmitBtn = uploadForm?.querySelector('[type="submit"]');
    const offsetInput = document.getElementById("vocal-sync-offset");
    const offsetDetail = document.getElementById("vocal-sync-offset-detail");
    const previewPlay = document.getElementById("vocal-sync-preview-play");
    const previewStop = document.getElementById("vocal-sync-preview-stop");
    const deleteBtn = document.getElementById("vocal-sync-delete");
    const commitBtn = document.getElementById("vocal-sync-commit");

    const OFFICIAL_MV_HINT_RE = /\b(official\s*mv|official\s*music\s*video|official\s*video|mv|music\s*video)\b/i;
    const AUTO_PREVIEW_DELAY_MS = 500;

    let activeSession = null;
    let vocalsTimer = null;
    let previewRestartTimer = null;
    let previewGeneration = 0;
    let youtubeBusy = false;
    let youtubeSearchBusy = false;
    let selectedYoutubeSource = null;
    let activeYoutubeTaskId = null;
    let youtubeTaskStream = null;
    let activeUploadTaskId = null;
    let uploadTaskStream = null;
    let sourcePrepLocked = false;

    function setMessage(text, isError = false) {
        if (!message) return;
        message.textContent = text || "";
        message.classList.toggle("text-error", Boolean(isError));
        message.classList.toggle("text-on-surface-variant", !isError);
    }

    function setState(key) {
        if (stateLabel) {
            stateLabel.textContent = t(key);
        }
    }

    function closeYoutubeTaskStream() {
        if (youtubeTaskStream) {
            youtubeTaskStream.close();
            youtubeTaskStream = null;
        }
    }

    function closeUploadTaskStream() {
        if (uploadTaskStream) {
            uploadTaskStream.close();
            uploadTaskStream = null;
        }
    }

    function cancelScheduledPreviewRestart() {
        if (previewRestartTimer) {
            window.clearTimeout(previewRestartTimer);
            previewRestartTimer = null;
        }
    }

    function formatTaskLabel(payload, fallbackKey = "vocalsync.preparing") {
        const baseLabel = payload?.progress_label_key
            ? t(payload.progress_label_key, payload.progress_label_args || {})
            : String(payload?.progress_label || payload?.stage || t(fallbackKey));
        const stepIndex = Number(payload?.progress_step_index);
        const stepTotal = Number(payload?.progress_step_total);
        if (Number.isFinite(stepIndex) && Number.isFinite(stepTotal) && stepIndex > 0 && stepTotal > 0) {
            return t("task.progress_step", {
                label: baseLabel,
                current: stepIndex,
                total: stepTotal,
            });
        }
        return baseLabel;
    }

    function renderSharedProgress({ visible, statusText, percent = null, indeterminate = false }) {
        if (!youtubeProgress || !youtubeProgressStatus || !youtubeProgressBar || !youtubeProgressPercent) {
            return;
        }
        youtubeProgress.classList.toggle("hidden", !visible);
        youtubeProgressStatus.textContent = statusText || t("vocalsync.preparing");
        youtubeProgressBar.classList.toggle("animate-pulse", Boolean(indeterminate));
        if (indeterminate) {
            youtubeProgressBar.style.width = "100%";
            youtubeProgressBar.style.opacity = "0.45";
            youtubeProgressPercent.textContent = t("vocalsync.progress_pending_short");
            return;
        }
        const safePercent = Math.max(0, Math.min(100, Number(percent) || 0));
        youtubeProgressBar.style.width = `${safePercent}%`;
        youtubeProgressBar.style.opacity = "1";
        youtubeProgressPercent.textContent = `${Math.round(safePercent)}%`;
    }

    function resetSharedProgress() {
        activeYoutubeTaskId = null;
        activeUploadTaskId = null;
        closeYoutubeTaskStream();
        closeUploadTaskStream();
        renderSharedProgress({
            visible: false,
            statusText: t("vocalsync.preparing"),
            percent: 0,
        });
    }

    function updateYoutubeTaskProgress(payload) {
        const stage = String(payload?.stage || "");
        const statusText = formatTaskLabel(payload);
        const percent = Number(payload?.progress_percent);
        const isFinalizing = stage === "finalize";
        renderSharedProgress({
            visible: true,
            statusText,
            percent: Number.isFinite(percent) ? percent : 0,
            indeterminate: isFinalizing,
        });
    }

    function updateSearchControls() {
        const hasQuery = Boolean(searchInput?.value.trim());
        const isLocked = youtubeBusy || youtubeSearchBusy || sourcePrepLocked;
        if (searchInput) {
            searchInput.disabled = isLocked;
        }
        if (searchBtn) {
            searchBtn.disabled = isLocked || !hasQuery;
        }
        if (searchClearBtn) {
            searchClearBtn.disabled = isLocked || !hasQuery;
        }
    }

    function syncYoutubeResultButtons() {
        if (!searchResults) return;
        searchResults.querySelectorAll("[data-youtube-id]").forEach((button) => {
            const isSelected = Boolean(selectedYoutubeSource && button.dataset.youtubeId === selectedYoutubeSource.videoId);
            button.disabled = youtubeBusy || youtubeSearchBusy || sourcePrepLocked;
            button.classList.toggle("border-primary/60", isSelected);
            button.classList.toggle("bg-primary/10", isSelected);
            button.classList.toggle("ring-1", isSelected);
            button.classList.toggle("ring-primary/40", isSelected);
            button.classList.toggle("hover:border-primary/40", !youtubeBusy);
            button.classList.toggle("hover:bg-surface-container-highest/70", !youtubeBusy);
            button.setAttribute("aria-pressed", isSelected ? "true" : "false");
            const actionLabel = button.querySelector("[data-youtube-action]");
            const actionIcon = button.querySelector("[data-youtube-action-icon]");
            if (actionLabel) {
                actionLabel.textContent = t(isSelected ? "vocalsync.selected_source_short" : "vocalsync.select_source_short");
            }
            if (actionIcon) {
                actionIcon.textContent = isSelected ? "check" : "open_in_new";
            }
        });
    }

    function bindYoutubeResultButtons() {
        if (!searchResults) return;
        searchResults.querySelectorAll("[data-youtube-id]").forEach((button) => {
            button.onclick = () => {
                if (youtubeBusy || youtubeSearchBusy || sourcePrepLocked) return;
                setYoutubeSelection({
                    videoId: button.dataset.youtubeId,
                    title: button.dataset.youtubeTitle,
                    channel: button.dataset.youtubeChannel,
                    thumbnail: button.dataset.youtubeThumbnail,
                });
            };
        });
    }

    function setYoutubeSelection(source) {
        selectedYoutubeSource = source ? {
            videoId: String(source.videoId || ""),
            title: String(source.title || ""),
            channel: String(source.channel || ""),
            thumbnail: String(source.thumbnail || ""),
        } : null;
        updateYoutubeSelectionUi();
    }

    function updateYoutubeSelectionUi() {
        const hasSelection = Boolean(selectedYoutubeSource);
        if (youtubeSelected) {
            youtubeSelected.textContent = hasSelection
                ? `${selectedYoutubeSource.title}${selectedYoutubeSource.channel ? ` · ${selectedYoutubeSource.channel}` : ""}`
                : t("vocalsync.selected_source_empty");
            youtubeSelected.title = hasSelection
                ? `${selectedYoutubeSource.title}${selectedYoutubeSource.channel ? ` · ${selectedYoutubeSource.channel}` : ""}`
                : "";
                if (hasSelection && OFFICIAL_MV_HINT_RE.test(selectedYoutubeSource.title)) {
                    youtubeHint.textContent = t("vocalsync.official_mv_hint");
                } else {
                    youtubeHint.textContent = "";
                }
        }
        if (youtubePrepareBtn) {
            youtubePrepareBtn.disabled = youtubeBusy || youtubeSearchBusy || sourcePrepLocked || !hasSelection || hasVocals;
        }
        if (youtubePrepareBtnLabel) {
            youtubePrepareBtnLabel.textContent = youtubeBusy
                ? t("vocalsync.preparing")
                : t("vocalsync.prepare_source");
        }
        if (youtubeProgress) {
            youtubeProgress.classList.toggle("hidden", !(youtubeBusy || activeUploadTaskId));
        }
        if (youtubeBusy && !activeYoutubeTaskId) {
            renderSharedProgress({
                visible: true,
                statusText: t("vocalsync.preparing"),
                percent: 0,
            });
        }
        syncYoutubeResultButtons();
    }

    function setBusy(isBusy) {
        youtubeBusy = Boolean(isBusy);
        [searchBtn, searchClearBtn, uploadSubmitBtn, commitBtn, previewPlay, deleteBtn].forEach((el) => {
            if (el) {
                el.disabled = Boolean(isBusy)
                    || (sourcePrepLocked && el !== commitBtn && el !== previewPlay && el !== deleteBtn)
                    || (el === commitBtn && !activeSession)
                    || (el === previewPlay && !activeSession)
                    || (el === deleteBtn && !activeSession);
            }
        });
        updateSearchControls();
        updateUploadControls();
        updateYoutubeSelectionUi();
    }

    function updateUploadControls() {
        if (uploadSubmitBtn) {
            uploadSubmitBtn.disabled = youtubeBusy || sourcePrepLocked || hasVocals;
        }
        if (uploadFile) {
            uploadFile.disabled = youtubeBusy || sourcePrepLocked || hasVocals;
        }
    }

    function updateUploadTaskProgress(payload) {
        const stage = String(payload?.stage || "");
        const statusText = formatTaskLabel(payload);
        const percent = Number(payload?.progress_percent);
        const isFinalizing = stage === "finalize";
        renderSharedProgress({
            visible: true,
            statusText,
            percent: Number.isFinite(percent) ? percent : 0,
            indeterminate: isFinalizing,
        });
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function formatOffset(value) {
        const numeric = Number(value);
        return Number.isFinite(numeric) ? numeric.toFixed(2) : "0.00";
    }

    function updateOffsetDetail() {
        const offset = Number(offsetInput?.value || 0);
        if (!offsetDetail) return;
        if (Math.abs(offset) < 0.001) {
            offsetDetail.textContent = t("vocalsync.offset_zero");
        } else if (offset > 0) {
            offsetDetail.textContent = t("vocalsync.offset_positive", { seconds: formatOffset(offset) });
        } else {
            offsetDetail.textContent = t("vocalsync.offset_negative", { seconds: formatOffset(Math.abs(offset)) });
        }
    }

    function applySession(session) {
        activeSession = session;
        sourcePrepLocked = true;
        vocals.src = appUrl(session.vocals_url);
        offsetInput.value = formatOffset(session.estimated_offset_seconds);
        offsetInput.disabled = false;
        previewPlay.disabled = false;
        previewStop.disabled = false;
        deleteBtn.disabled = false;
        commitBtn.disabled = false;
        setState("vocalsync.ready");
        if (session.method === "manual_offset") {
            setMessage(t("vocalsync.manual_offset_only"));
        } else {
            setMessage(t("vocalsync.prepared", { offset: formatOffset(session.estimated_offset_seconds) }));
        }
        updateOffsetDetail();
        updateSearchControls();
        updateUploadControls();
        updateYoutubeSelectionUi();
    }

    function clearYoutubeSelection({ keepSearch = true } = {}) {
        selectedYoutubeSource = null;
        if (!keepSearch && searchResults) {
            searchResults.innerHTML = "";
        }
        updateYoutubeSelectionUi();
    }

    function clearReviewSession({ keepMessage = false } = {}) {
        stopPreview();
        activeSession = null;
        sourcePrepLocked = false;
        vocals.removeAttribute("src");
        vocals.load();
        offsetInput.value = "0";
        offsetInput.disabled = true;
        previewPlay.disabled = true;
        previewStop.disabled = true;
        deleteBtn.disabled = true;
        commitBtn.disabled = true;
        setState("vocalsync.idle");
        updateOffsetDetail();
        updateSearchControls();
        updateUploadControls();
        updateYoutubeSelectionUi();
        if (!keepMessage) {
            setMessage("");
        }
    }

    async function parseJsonResponse(response) {
        let payload = {};
        try {
            payload = await response.json();
        } catch (error) {
            payload = {};
        }
        if (!response.ok) {
            const detail = payload.detail;
            const message = typeof detail === "string"
                ? detail
                : (detail?.message || t("vocalsync.request_failed"));
            const error = new Error(message);
            error.detail = detail;
            throw error;
        }
        return payload;
    }

    function statusFallbackPayload(task) {
        const live = task?.live || {};
        const stage = String(live.stage || task?.stage || "");
        let fallbackKey = "vocalsync.preparing";
        if (stage === "download") {
            fallbackKey = "task.downloading_audio";
        } else if (stage === "demucs" || stage === "separation") {
            fallbackKey = "task.separating_vocals";
        } else if (stage === "finalize") {
            fallbackKey = "task.finalizing_vocal_sync";
        } else if (task?.status === "pending") {
            fallbackKey = "task.starting";
        }
        return {
            status: task?.status,
            stage,
            progress_percent: live.progress_percent,
            progress_label: live.progress_label,
            progress_label_key: live.progress_label_key || fallbackKey,
            progress_label_args: live.progress_label_args,
            progress_step_index: live.progress_step_index,
            progress_step_total: live.progress_step_total,
        };
    }

    function restoreTaskProgress(task) {
        const payload = statusFallbackPayload(task);
        renderSharedProgress({
            visible: true,
            statusText: formatTaskLabel(payload),
            percent: Number.isFinite(Number(payload.progress_percent)) ? Number(payload.progress_percent) : 0,
            indeterminate: payload.stage === "finalize" || !Number.isFinite(Number(payload.progress_percent)),
        });
    }

    async function restoreVocalSyncStatus() {
        const response = await fetch(appUrl(`/api/media/${mediaId}/vocals-sync/status`));
        const payload = await parseJsonResponse(response);
        const status = String(payload.status || "idle");
        if (status === "has_vocals") {
            sourcePrepLocked = true;
            setState("karaoke.already_multi_track");
            setMessage(t("vocalsync.already_has_vocals"), true);
            setBusy(true);
            return;
        }
        if (status === "ready" && payload.session) {
            resetSharedProgress();
            applySession(payload.session);
            setMessage(t("vocalsync.review_restored"));
            return;
        }
        if (status === "preparing" && payload.task) {
            const taskId = Number(payload.task.id);
            if (!Number.isFinite(taskId) || taskId <= 0) {
                return;
            }
            stopPreview();
            sourcePrepLocked = true;
            setBusy(true);
            setState("vocalsync.preparing");
            setMessage(t("vocalsync.task_restored"));
            restoreTaskProgress(payload.task);
            if (payload.task.source_kind === "upload") {
                activeUploadTaskId = taskId;
                await followUploadPrepareTask(taskId);
            } else {
                activeYoutubeTaskId = taskId;
                await followYoutubePrepareTask(taskId);
            }
            return;
        }
        if (status === "failed" || status === "canceled") {
            sourcePrepLocked = false;
            resetSharedProgress();
            setState(status === "canceled" ? "task.canceled" : "common.failed");
            setMessage(payload.message || t(status === "canceled" ? "vocalsync.previous_canceled" : "vocalsync.previous_failed"), status !== "canceled");
            return;
        }
        sourcePrepLocked = false;
        resetSharedProgress();
    }

    async function autoInferSearchBox() {
        const title = vocalSyncSearchHeading?.textContent?.trim() || "";
        if (!title) return;
        const inferURL = appUrl(`/api/search/infer/?title=${encodeURIComponent(title)}`);
        try {
            const response = await fetch(inferURL);
            const payload = await parseJsonResponse(response);
            if (payload.title && payload.artist) {
                searchInput.value = `${payload.artist} - ${payload.title}`;
                updateSearchControls();
            }
        } catch (error) {
            console.error("Failed to auto-infer search query:", error instanceof Error ? error.message : error);
        }  
    }

    async function searchYoutube() {
        const query = searchInput.value.trim();
        if (!query) return;
        youtubeSearchBusy = true;
        updateSearchControls();
        clearYoutubeSelection({ keepSearch: true });
        searchResults.innerHTML = `<p class="rounded-xl bg-surface-container-high/50 p-3 text-sm text-on-surface-variant">${escapeHtml(t("lyrics.searching"))}</p>`;
        try {
            const response = await fetch(appUrl(`/api/search/?q=${encodeURIComponent(query)}&source=youtube&concurrent=false`));
            const results = await parseJsonResponse(response);
            if (!Array.isArray(results) || results.length === 0) {
                searchResults.innerHTML = `<p class="rounded-xl bg-surface-container-high/50 p-3 text-sm text-on-surface-variant">${escapeHtml(t("queue.no_results"))}</p>`;
                return;
            }
            searchResults.innerHTML = results.map((result) => {
                const videoId = escapeHtml(result.video_id || "");
                return `
                    <button
                        type="button"
                        data-youtube-id="${videoId}"
                        data-youtube-title="${escapeHtml(result.title || "")}"
                        data-youtube-channel="${escapeHtml(result.channel || "")}"
                        data-youtube-thumbnail="${escapeHtml(result.thumbnail || "")}"
                        class="vocal-sync-youtube-result flex w-full min-w-0 items-center gap-3 overflow-hidden rounded-xl border border-white/10 bg-surface-container-high/50 p-2.5 text-left transition hover:border-primary/40 hover:bg-surface-container-highest/70"
                    >
                        <img src="${escapeHtml(result.thumbnail || "")}" alt="" class="h-12 w-20 rounded-lg object-cover">
                        <span class="min-w-0 flex-1 overflow-hidden">
                            <span class="block truncate text-xs font-bold text-on-surface">${escapeHtml(result.title || t("common.unknown"))}</span>
                            <span class="block truncate text-[10px] text-on-surface-variant">${escapeHtml(result.channel || "")}</span>
                        </span>
                        <span class="inline-flex shrink-0 items-center gap-1 rounded-full border border-white/10 bg-surface-container-highest/70 px-2 py-1 text-[10px] font-black uppercase tracking-widest text-primary">
                            <span data-youtube-action-icon class="material-symbols-outlined text-[14px]">open_in_new</span>
                            <span data-youtube-action>${escapeHtml(t("vocalsync.select_source_short"))}</span>
                        </span>
                    </button>
                `;
            }).join("");
            syncYoutubeResultButtons();
            bindYoutubeResultButtons();
        } catch (error) {
            searchResults.innerHTML = "";
            setMessage(error instanceof Error ? error.message : t("vocalsync.request_failed"), true);
        } finally {
            youtubeSearchBusy = false;
            updateSearchControls();
            syncYoutubeResultButtons();
        }
    }

    async function prepareYoutube() {
        const youtubeId = selectedYoutubeSource?.videoId;
        if (!youtubeId || hasVocals || youtubeBusy) return;
        stopPreview();
        setBusy(true);
        setState("vocalsync.preparing");
        try {
            const response = await fetch(appUrl(`/api/media/${mediaId}/vocals-sync/prepare-youtube`), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ youtube_id: youtubeId }),
            });
            const payload = await parseJsonResponse(response);
            const taskId = Number(payload.task_id);
            if (!Number.isFinite(taskId) || taskId <= 0) {
                throw new Error(t("vocalsync.request_failed"));
            }
            activeYoutubeTaskId = taskId;
            renderSharedProgress({
                visible: true,
                statusText: t("vocalsync.preparing"),
                percent: 0,
            });
            await followYoutubePrepareTask(taskId);
        } catch (error) {
            if (error?.detail?.status === "preparing" || error?.detail?.status === "ready") {
                await restoreVocalSyncStatus();
                setBusy(false);
                return;
            }
            sourcePrepLocked = false;
            setState("common.failed");
            setMessage(error instanceof Error ? error.message : t("vocalsync.request_failed"), true);
            resetSharedProgress();
            setBusy(false);
        }
    }

    async function loadPreparedSessionForTask(taskId) {
        const response = await fetch(appUrl(`/api/media/${mediaId}/vocals-sync/tasks/${taskId}/session`));
        const payload = await parseJsonResponse(response);
        applySession(payload.session);
    }

    async function finishYoutubeTask(taskId) {
        closeYoutubeTaskStream();
        try {
            await loadPreparedSessionForTask(taskId);
            resetSharedProgress();
            setBusy(false);
        } catch (error) {
            if (error?.detail?.status === "preparing" || error?.detail?.status === "ready") {
                await restoreVocalSyncStatus();
                setBusy(false);
                updateUploadControls();
                return;
            }
            sourcePrepLocked = false;
            setState("common.failed");
            setMessage(error instanceof Error ? error.message : t("vocalsync.request_failed"), true);
            resetSharedProgress();
            setBusy(false);
        }
    }

    async function finishUploadTask(taskId) {
        closeUploadTaskStream();
        try {
            await loadPreparedSessionForTask(taskId);
            resetSharedProgress();
            setBusy(false);
        } catch (error) {
            sourcePrepLocked = false;
            setState("common.failed");
            setMessage(error instanceof Error ? error.message : t("vocalsync.request_failed"), true);
            resetSharedProgress();
            setBusy(false);
        }
    }

    function followYoutubePrepareTask(taskId) {
        return new Promise((resolve, reject) => {
            closeYoutubeTaskStream();
            if (typeof EventSource === "undefined") {
                reject(new Error(t("vocalsync.request_failed")));
                return;
            }

            let settled = false;
            youtubeTaskStream = new EventSource(appUrl(`/api/tasks/${taskId}/stream`));

            youtubeTaskStream.onmessage = (event) => {
                let payload;
                try {
                    payload = JSON.parse(event.data);
                } catch (_) {
                    return;
                }
                if (Number(payload?.task_id) !== Number(taskId)) {
                    return;
                }
                updateYoutubeTaskProgress(payload);
                if (payload?.status === "done") {
                    settled = true;
                    finishYoutubeTask(taskId).then(resolve).catch(reject);
                    return;
                }
                if (payload?.status === "failed" || payload?.status === "canceled") {
                    settled = true;
                    closeYoutubeTaskStream();
                    sourcePrepLocked = false;
                    resetSharedProgress();
                    setBusy(false);
                    const failureMessage = String(payload?.message || payload?.progress_label || t("vocalsync.request_failed"));
                    setState(payload.status === "canceled" ? "task.canceled" : "common.failed");
                    setMessage(failureMessage, payload.status !== "canceled");
                    reject(new Error(failureMessage));
                }
            };

            youtubeTaskStream.onerror = () => {
                if (settled) {
                    return;
                }
                renderSharedProgress({
                    visible: true,
                    statusText: t("vocalsync.preparing"),
                    percent: 0,
                    indeterminate: true,
                });
            };
        });
    }

    function followUploadPrepareTask(taskId) {
        return new Promise((resolve, reject) => {
            closeUploadTaskStream();
            if (typeof EventSource === "undefined") {
                reject(new Error(t("vocalsync.request_failed")));
                return;
            }

            let settled = false;
            uploadTaskStream = new EventSource(appUrl(`/api/tasks/${taskId}/stream`));

            uploadTaskStream.onmessage = (event) => {
                let payload;
                try {
                    payload = JSON.parse(event.data);
                } catch (_) {
                    return;
                }
                if (Number(payload?.task_id) !== Number(taskId)) {
                    return;
                }
                updateUploadTaskProgress(payload);
                if (payload?.status === "done") {
                    settled = true;
                    finishUploadTask(taskId).then(resolve).catch(reject);
                    return;
                }
                if (payload?.status === "failed" || payload?.status === "canceled") {
                    settled = true;
                    closeUploadTaskStream();
                    sourcePrepLocked = false;
                    resetSharedProgress();
                    setBusy(false);
                    const failureMessage = String(payload?.message || payload?.progress_label || t("vocalsync.request_failed"));
                    setState(payload.status === "canceled" ? "task.canceled" : "common.failed");
                    setMessage(failureMessage, payload.status !== "canceled");
                    reject(new Error(failureMessage));
                }
            };

            uploadTaskStream.onerror = () => {
                if (settled) {
                    return;
                }
                renderSharedProgress({
                    visible: true,
                    statusText: t("media.task_stream_reconnecting"),
                    percent: 0,
                    indeterminate: true,
                });
            };
        });
    }

    async function prepareUpload(event) {
        event.preventDefault();
        const file = uploadFile.files?.[0];
        if (!file || hasVocals) return;
        stopPreview();
        setBusy(true);
        setState("vocalsync.preparing");
        renderSharedProgress({
            visible: true,
            statusText: t("upload.connecting"),
            percent: 0,
        });
        const formData = new FormData();
        formData.append("file", file);
        try {
            const payload = await new Promise((resolve, reject) => {
                const xhr = new XMLHttpRequest();
                xhr.open("POST", appUrl(`/api/media/${mediaId}/vocals-sync/prepare-upload`), true);

                xhr.upload.onprogress = (event) => {
                    if (!event.lengthComputable) return;
                    const percent = Math.round((event.loaded / event.total) * 100);
                    renderSharedProgress({
                        visible: true,
                        statusText: t(percent < 100 ? "upload.uploading" : "upload.processing"),
                        percent,
                    });
                };

                xhr.onload = () => {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        renderSharedProgress({
                            visible: true,
                            statusText: t("upload.processing"),
                            percent: 100,
                        });
                        try {
                            resolve(JSON.parse(xhr.responseText));
                        } catch (error) {
                            reject(new Error(t("vocalsync.request_failed")));
                        }
                        return;
                    }

                    let errorMessage = t("vocalsync.request_failed");
                    try {
                        const error = JSON.parse(xhr.responseText);
                        errorMessage = error.detail || errorMessage;
                    } catch (parseError) {
                        console.error("Vocal sync upload error response parse failed:", parseError);
                    }
                    reject(new Error(errorMessage));
                };

                xhr.onerror = () => {
                    reject(new Error(t("upload.network_error")));
                };

                xhr.send(formData);
            });
            const taskId = Number(payload.task_id);
            if (!Number.isFinite(taskId) || taskId <= 0) {
                throw new Error(t("vocalsync.request_failed"));
            }
            activeUploadTaskId = taskId;
            renderSharedProgress({
                visible: true,
                statusText: t("task.separating_vocals"),
                percent: 0,
            });
            await followUploadPrepareTask(taskId);
        } catch (error) {
            sourcePrepLocked = false;
            setState("common.failed");
            setMessage(error instanceof Error ? error.message : t("vocalsync.request_failed"), true);
            renderSharedProgress({
                visible: true,
                statusText: t("upload.upload_failed"),
                percent: 0,
            });
        } finally {
            setBusy(false);
            updateUploadControls();
        }
    }

    function stopPreview({ cancelScheduled = true } = {}) {
        previewGeneration += 1;
        if (cancelScheduled) {
            cancelScheduledPreviewRestart();
        }
        if (vocalsTimer) {
            window.clearTimeout(vocalsTimer);
            vocalsTimer = null;
        }
        media.pause();
        vocals.pause();
    }

    async function playPreview() {
        if (!activeSession) return;
        stopPreview({ cancelScheduled: false });
        const previewToken = ++previewGeneration;
        const offset = Number(offsetInput.value || 0);
        const mediaTime = media.currentTime || 0;
        if (offset >= 0) {
            await media.play();
            if (previewToken !== previewGeneration) {
                return;
            }
            if (mediaTime >= offset) {
                vocals.currentTime = Math.max(0, mediaTime - offset);
                await vocals.play();
            } else {
                vocals.currentTime = 0;
                vocalsTimer = window.setTimeout(() => {
                    if (previewToken !== previewGeneration) {
                        return;
                    }
                    vocals.play().catch(() => {});
                }, Math.round((offset - mediaTime) * 1000));
            }
        } else {
            vocals.currentTime = Math.max(0, mediaTime + Math.abs(offset));
            await Promise.all([
                media.play(),
                vocals.play(),
            ]);
        }
        if (previewToken !== previewGeneration) {
            stopPreview({ cancelScheduled: false });
        }
    }

    function schedulePreviewRestart() {
        if (!activeSession || offsetInput?.disabled) {
            return;
        }
        stopPreview({ cancelScheduled: false });
        cancelScheduledPreviewRestart();
        previewRestartTimer = window.setTimeout(() => {
            previewRestartTimer = null;
            playPreview().catch((error) => {
                setMessage(error instanceof Error ? error.message : t("vocalsync.preview_failed"), true);
            });
        }, AUTO_PREVIEW_DELAY_MS);
    }

    async function commitSession() {
        if (!activeSession) return;
        if (!window.confirm(t("vocalsync.confirm_commit"))) {
            return;
        }
        stopPreview();
        commitBtn.disabled = true;
        setState("vocalsync.committing");
        setMessage(t("vocalsync.committing_detail"));
        try {
            const response = await fetch(appUrl(`/api/media/${mediaId}/vocals-sync/sessions/${encodeURIComponent(activeSession.session_id)}/commit`), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ offset_seconds: Number(offsetInput.value || 0) }),
            });
            await parseJsonResponse(response);
            setState("common.success");
            setMessage(t("vocalsync.committed"));
            window.setTimeout(() => {
                window.location.href = appUrl("/media");
            }, 900);
        } catch (error) {
            commitBtn.disabled = false;
            setState("common.failed");
            setMessage(error instanceof Error ? error.message : t("vocalsync.request_failed"), true);
        }
    }

    async function deleteReviewSession() {
        if (!activeSession) return;
        if (!window.confirm(t("vocalsync.confirm_delete_review"))) {
            return;
        }
        stopPreview();
        setBusy(true);
        setState("vocalsync.deleting");
        setMessage(t("vocalsync.deleting_detail"));
        try {
            const response = await fetch(
                appUrl(`/api/media/${mediaId}/vocals-sync/sessions/${encodeURIComponent(activeSession.session_id)}`),
                { method: "DELETE" },
            );
            await parseJsonResponse(response);
            resetSharedProgress();
            clearReviewSession({ keepMessage: true });
            setMessage(t("vocalsync.deleted_review"));
        } catch (error) {
            setState("common.failed");
            setMessage(error instanceof Error ? error.message : t("vocalsync.request_failed"), true);
        } finally {
            setBusy(false);
        }
    }

    searchBtn?.addEventListener("click", searchYoutube);
    searchClearBtn?.addEventListener("click", () => {
        searchInput.value = "";
        searchResults.innerHTML = "";
        clearYoutubeSelection({ keepSearch: true });
        updateSearchControls();
        setMessage("");
    });
    searchInput?.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            searchYoutube();
        }
    });
    searchInput?.addEventListener("input", () => {
        if (!youtubeBusy) {
            clearYoutubeSelection({ keepSearch: true });
        }
        updateSearchControls();
    });
    youtubePrepareBtn?.addEventListener("click", () => {
        prepareYoutube().catch((error) => {
            setState("common.failed");
            setMessage(error instanceof Error ? error.message : t("vocalsync.request_failed"), true);
        });
    });
    uploadForm?.addEventListener("submit", prepareUpload);
    offsetInput?.addEventListener("input", () => {
        updateOffsetDetail();
        schedulePreviewRestart();
    });
    document.querySelectorAll("[data-offset-step]").forEach((button) => {
        button.addEventListener("click", () => {
            if (offsetInput.disabled) return;
            const next = Number(offsetInput.value || 0) + Number(button.dataset.offsetStep || 0);
            offsetInput.value = formatOffset(next);
            updateOffsetDetail();
            schedulePreviewRestart();
        });
    });
    previewPlay?.addEventListener("click", () => {
        cancelScheduledPreviewRestart();
        playPreview().catch((error) => {
            setMessage(error instanceof Error ? error.message : t("vocalsync.preview_failed"), true);
        });
    });
    previewStop?.addEventListener("click", () => stopPreview());
    media?.addEventListener("seeked", () => {
        if (!activeSession || offsetInput.disabled) return;
        schedulePreviewRestart();
    });
    deleteBtn?.addEventListener("click", deleteReviewSession);
    commitBtn?.addEventListener("click", commitSession);
    window.addEventListener("beforeunload", () => {
        closeYoutubeTaskStream();
        closeUploadTaskStream();
    });

    async function initializePage() {
        try {
            await restoreVocalSyncStatus();
        } catch (error) {
            sourcePrepLocked = false;
            resetSharedProgress();
            setState("common.failed");
            setMessage(error instanceof Error ? error.message : t("vocalsync.request_failed"), true);
        }
        updateSearchControls();
        updateUploadControls();
        updateYoutubeSelectionUi();
        if (!sourcePrepLocked && !activeSession) {
            Promise.race([autoInferSearchBox(), new Promise((resolve) => window.setTimeout(resolve, 1500))]);
        }
    }

    if (hasVocals) {
        setState("karaoke.already_multi_track");
        setMessage(t("vocalsync.already_has_vocals"), true);
        sourcePrepLocked = true;
        setBusy(true);
    } else {
        initializePage();
    }
})();
