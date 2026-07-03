(() => {
    const root = document.getElementById("media-trim-editor");
    if (!root) return;

    const appUrl = window.KaraokeURLs?.appUrl || ((path) => path);
    const t = window.KaraokeI18n?.t?.bind(window.KaraokeI18n) || ((key) => key);
    const loadingState = document.getElementById("trim-loading-state");
    const loadingTitle = document.getElementById("trim-loading-title");
    const loadingDetail = document.getElementById("trim-loading-detail");
    const loadingRetry = document.getElementById("trim-loading-retry");
    const player = document.getElementById("trim-media-player");
    const timeline = document.getElementById("trim-timeline");
    const canvas = document.getElementById("trim-keyframe-canvas");
    const selection = document.getElementById("trim-selection");
    const playhead = document.getElementById("trim-playhead");
    const startRange = document.getElementById("trim-start-range");
    const endRange = document.getElementById("trim-end-range");
    const startInput = document.getElementById("trim-start-input");
    const endInput = document.getElementById("trim-end-input");
    const prevIframeButton = document.getElementById("trim-prev-iframe");
    const nextIframeButton = document.getElementById("trim-next-iframe");
    const startDisplay = document.getElementById("trim-start-display");
    const endDisplay = document.getElementById("trim-end-display");
    const durationDisplay = document.getElementById("trim-duration-display");
    const scaleEnd = document.getElementById("trim-scale-end");
    const snapMessage = document.getElementById("trim-snap-message");
    const errorBox = document.getElementById("trim-error");
    const saveButton = document.getElementById("trim-save");
    const timelinePanel = document.getElementById("trim-timeline-panel");
    const statsPanel = document.getElementById("trim-stats-panel");
    const cdgPanel = document.getElementById("trim-cdg-panel");
    const cdgOverwriteCheckbox = document.getElementById("trim-cdg-overwrite");
    const transcodeButton = document.getElementById("trim-transcode");
    const transcodeProgress = document.getElementById("trim-transcode-progress");
    const transcodeProgressLabel = document.querySelector("[data-trim-transcode-progress-label]");
    const setStartButton = document.getElementById("trim-set-start");
    const setEndButton = document.getElementById("trim-set-end");
    const jumpStartButton = document.getElementById("trim-jump-start");
    const jumpEndButton = document.getElementById("trim-jump-end");

    const mediaId = Number(root.dataset.mediaId);
    const lyricsKind = String(root.dataset.lyricsKind || "").trim().toLowerCase();
    const SNAP_EPSILON = 0.000001;
    const DEFAULT_FRAME_RATE = 30;
    let duration = 0;
    let hasVideo = root.dataset.hasVideo === "true";
    let frameRate = DEFAULT_FRAME_RATE;
    let keyframes = [];
    let snapPoints = [0];
    let start = 0;
    let end = 0;
    let editorReady = false;
    let isSubmitting = false;
    let loadSequence = 0;
    let isDraggingPlayhead = false;
    let isCdgMode = lyricsKind === "cdg";
    let transcodeTaskStream = null;
    let activeTranscodeTaskId = null;

    function setBusyState(isBusy) {
        root.dataset.editorState = isBusy ? "loading" : "ready";
        root.classList.toggle("is-loading", isBusy);
        root.classList.toggle("is-ready", !isBusy);
        root.setAttribute("aria-busy", isBusy ? "true" : "false");
    }

    function setLoadingStateVisible(visible) {
        if (!loadingState) return;
        loadingState.classList.toggle("hidden", !visible);
    }

    function setLoadingMessage(title, detail, showRetry = false) {
        if (loadingTitle) loadingTitle.textContent = title;
        if (loadingDetail) loadingDetail.textContent = detail;
        if (loadingRetry) loadingRetry.classList.toggle("hidden", !showRetry);
    }

    function setControlsEnabled(enabled) {
        [
            startRange,
            endRange,
            startInput,
            endInput,
            prevIframeButton,
            nextIframeButton,
            setStartButton,
            setEndButton,
            jumpStartButton,
            jumpEndButton,
        ].forEach((control) => {
            if (control) {
                control.disabled = !enabled;
            }
        });
        if (saveButton) {
            saveButton.disabled = !enabled || isSubmitting;
        }
    }

    function setCdgModeUi(isCdg) {
        isCdgMode = Boolean(isCdg);
        root.dataset.editorMode = isCdgMode ? "cdg" : "trim";
        timelinePanel?.classList.toggle("hidden", isCdgMode);
        statsPanel?.classList.toggle("hidden", isCdgMode);
        cdgPanel?.classList.toggle("hidden", !isCdgMode);
        if (saveButton) {
            saveButton.classList.toggle("hidden", isCdgMode);
        }
        if (transcodeButton) {
            transcodeButton.disabled = !isCdgMode || isSubmitting || activeTranscodeTaskId !== null;
        }
        if (cdgOverwriteCheckbox) {
            cdgOverwriteCheckbox.disabled = !isCdgMode || isSubmitting || activeTranscodeTaskId !== null;
        }
        if (isCdgMode) {
            setBusyState(false);
            setControlsEnabled(false);
            loadingState?.classList.add("hidden");
            showError(t("trim.cdg_unsupported_detail"));
            setLoadingStateVisible(false);
            if (transcodeProgress) {
                transcodeProgress.classList.add("hidden");
            }
        }
    }

    function setTimelineBounds() {
        const max = String(duration);
        if (startRange) startRange.max = max;
        if (endRange) endRange.max = max;
        if (startInput) startInput.max = max;
        if (endInput) endInput.max = max;
    }

    function clamp(value) {
        return Math.min(duration, Math.max(0, Number(value) || 0));
    }

    function snapStart(value) {
        if (!hasVideo) return clamp(value);
        const candidate = snapPoints.filter((point) => point <= value + 0.000001).at(-1);
        return candidate ?? 0;
    }

    function snapEnd(value) {
        if (!hasVideo) return clamp(value);
        return snapPoints.find((point) => point >= value - 0.000001) ?? duration;
    }

    function formatTime(value) {
        const totalMilliseconds = Math.round(Math.max(0, Number(value) || 0) * 1000);
        const minutes = Math.floor(totalMilliseconds / 60000);
        const seconds = Math.floor((totalMilliseconds % 60000) / 1000);
        const milliseconds = totalMilliseconds % 1000;
        return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(milliseconds).padStart(3, "0")}`;
    }

    function showError(message = "") {
        errorBox.textContent = message;
        errorBox.classList.toggle("hidden", !message);
    }

    function closeTranscodeTaskStream() {
        if (transcodeTaskStream) {
            transcodeTaskStream.close();
            transcodeTaskStream = null;
        }
    }

    function renderTranscodeProgress({
        visible = true,
        statusText = "",
        percent = 0,
        indeterminate = false,
    } = {}) {
        if (!transcodeProgress) {
            return;
        }
        transcodeProgress.classList.toggle("hidden", !visible);
        transcodeProgress.dataset.taskProgressKey = activeTranscodeTaskId ? `cdg-${activeTranscodeTaskId}` : "";
        transcodeProgress.dataset.taskProgressStatus = indeterminate ? "processing" : "";
        transcodeProgress.dataset.taskProgressStage = indeterminate ? "transcoding" : "";
        transcodeProgress.dataset.taskProgressMode = indeterminate ? "indeterminate" : "determinate";
        transcodeProgress.dataset.taskProgressReportedPercent = String(Math.max(0, Math.min(100, percent)));
        transcodeProgress.dataset.taskProgressLabel = statusText;
        transcodeProgress.dataset.taskProgressLabelText = statusText;
        if (transcodeProgressLabel) {
            transcodeProgressLabel.textContent = statusText;
        }
        window.KaraokeTaskProgress?.sync(transcodeProgress);
    }

    function updateTranscodeControlsDisabled(disabled) {
        if (transcodeButton) {
            transcodeButton.disabled = disabled;
        }
        if (cdgOverwriteCheckbox) {
            cdgOverwriteCheckbox.disabled = disabled;
        }
    }

    function finishTranscodeTask() {
        closeTranscodeTaskStream();
        activeTranscodeTaskId = null;
        renderTranscodeProgress({ visible: false, statusText: "" });
        updateTranscodeControlsDisabled(false);
    }

    function followTranscodeTask(taskId) {
        return new Promise((resolve, reject) => {
            closeTranscodeTaskStream();
            if (typeof EventSource === "undefined") {
                reject(new Error(t("trim.failed")));
                return;
            }

            let settled = false;
            transcodeTaskStream = new EventSource(appUrl(`/api/tasks/${taskId}/stream`));
            transcodeTaskStream.onmessage = (event) => {
                let payload;
                try {
                    payload = JSON.parse(event.data);
                } catch (_) {
                    return;
                }
                if (Number(payload?.task_id) !== Number(taskId)) {
                    return;
                }
                const label = payload?.progress_label_key
                    ? t(payload.progress_label_key, payload.progress_label_args || {})
                    : String(payload?.progress_label || payload?.stage || t("trim.transcode_waiting"));
                renderTranscodeProgress({
                    visible: true,
                    statusText: label,
                    percent: Number(payload?.progress_percent || 0),
                    indeterminate: payload?.progress_mode === "indeterminate",
                });
                if (payload?.status === "done") {
                    settled = true;
                    finishTranscodeTask();
                    resolve(payload);
                    return;
                }
                if (payload?.status === "failed" || payload?.status === "canceled") {
                    settled = true;
                    const failureMessage = String(payload?.message || payload?.progress_label || t("trim.failed"));
                    finishTranscodeTask();
                    reject(new Error(failureMessage));
                }
            };

            transcodeTaskStream.onerror = () => {
                if (settled) {
                    return;
                }
                renderTranscodeProgress({
                    visible: true,
                    statusText: t("media.task_stream_reconnecting"),
                    percent: 0,
                    indeterminate: true,
                });
            };
        });
    }

    async function startTranscode() {
        if (!isCdgMode || isSubmitting || activeTranscodeTaskId !== null) {
            return;
        }
        const overwriteOriginal = Boolean(cdgOverwriteCheckbox?.checked);
        const confirmed = window.confirm(
            overwriteOriginal
                ? t("trim.cdg_overwrite_confirm")
                : t("trim.cdg_keep_original_confirm"),
        );
        if (!confirmed) {
            return;
        }

        isSubmitting = true;
        updateTranscodeControlsDisabled(true);
        renderTranscodeProgress({
            visible: true,
            statusText: t("trim.transcode_waiting"),
            percent: 0,
            indeterminate: true,
        });
        try {
            const response = await fetch(appUrl(`/api/media/${mediaId}/transcode-cdg`), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ overwrite_original: overwriteOriginal }),
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(payload.detail || t("trim.failed"));
            }
            const taskId = Number(payload?.id);
            if (!Number.isFinite(taskId) || taskId <= 0) {
                throw new Error(t("trim.failed"));
            }
            activeTranscodeTaskId = taskId;
            renderTranscodeProgress({
                visible: true,
                statusText: t("trim.transcode_waiting"),
                percent: 0,
                indeterminate: true,
            });
            await followTranscodeTask(taskId);
            window.location.href = appUrl("/media");
        } catch (error) {
            showError(error instanceof Error ? error.message : t("trim.failed"));
            updateTranscodeControlsDisabled(false);
        } finally {
            isSubmitting = false;
            if (activeTranscodeTaskId === null) {
                renderTranscodeProgress({ visible: false, statusText: "" });
            }
            if (transcodeButton) {
                transcodeButton.disabled = false;
            }
            if (cdgOverwriteCheckbox) {
                cdgOverwriteCheckbox.disabled = false;
            }
        }
    }

    function updateUi(source = "") {
        if (!editorReady) return;
        start = clamp(start);
        end = clamp(end);
        if (end <= start) {
            if (hasVideo && source === "start") {
                start = snapPoints.filter((point) => point < end).at(-1) ?? 0;
            } else if (hasVideo) {
                end = snapPoints.find((point) => point > start) ?? duration;
            } else if (source === "start") {
                start = Math.max(0, end - 0.001);
            } else {
                end = Math.min(duration, start + 0.001);
            }
        }

        startRange.value = String(start);
        endRange.value = String(end);
        startInput.value = start.toFixed(3);
        endInput.value = end.toFixed(3);
        startDisplay.textContent = formatTime(start);
        endDisplay.textContent = formatTime(end);
        durationDisplay.textContent = formatTime(end - start);
        scaleEnd.textContent = formatTime(duration).slice(0, 5);

        const startPercent = duration ? (start / duration) * 100 : 0;
        const endPercent = duration ? (end / duration) * 100 : 100;
        selection.style.left = `${startPercent}%`;
        selection.style.width = `${Math.max(0, endPercent - startPercent)}%`;
        snapMessage.textContent = hasVideo
            ? t("trim.snap_explanation", {
                start: formatTime(start),
                end: formatTime(end),
            })
            : t("trim.audio_exact_explanation");
        showError();
    }

    function syncPlayheadPosition(value) {
        const percent = duration ? (player.currentTime / duration) * 100 : 0;
        playhead.style.left = `${Math.min(100, Math.max(0, percent))}%`;
        playhead.setAttribute("aria-valuenow", player.currentTime.toFixed(3));
        playhead.setAttribute("aria-valuetext", formatTime(player.currentTime));
    }

    function seekPlayer(value) {
        if (!player || !editorReady) return;
        player.currentTime = clamp(value);
        syncPlayheadPosition(player.currentTime);
    }

    function togglePlayback() {
        if (!player || !editorReady) return;
        if (player.paused) {
            player.play().catch(() => {});
        } else {
            player.pause();
        }
    }

    function updatePlayheadA11y() {
        playhead.setAttribute("aria-valuemax", duration.toFixed(3));
        playhead.setAttribute("aria-valuenow", clamp(player.currentTime).toFixed(3));
        playhead.setAttribute("aria-valuetext", formatTime(player.currentTime));
    }

    function getTimelineTimeFromClientX(clientX) {
        if (!timeline || !duration) {
            return 0;
        }
        const rect = timeline.getBoundingClientRect();
        const percent = rect.width ? (clientX - rect.left) / rect.width : 0;
        return clamp(percent * duration);
    }

    function seekAdjacentIframe(direction) {
        if (!editorReady || !snapPoints.length) return;
        const currentTime = clamp(player.currentTime);
        const target = direction < 0
            ? [...snapPoints].filter((point) => point < currentTime - SNAP_EPSILON).at(-1) ?? 0
            : snapPoints.find((point) => point > currentTime + SNAP_EPSILON) ?? duration;
        seekPlayer(target);
    }

    function getFrameStepSeconds() {
        return frameRate > 0 ? 1 / frameRate : 1 / DEFAULT_FRAME_RATE;
    }

    function stepFrame(direction) {
        if (!editorReady) return;
        if (!player.paused) {
            player.pause();
        }
        seekPlayer(player.currentTime + (direction * getFrameStepSeconds()));
    }

    function startPlayheadDrag(event) {
        if (!editorReady || event.button !== 0) return;
        event.preventDefault();
        isDraggingPlayhead = true;
        playhead.classList.add("is-dragging");
        playhead.setPointerCapture(event.pointerId);
        seekPlayer(getTimelineTimeFromClientX(event.clientX));
    }

    function movePlayheadDrag(event) {
        if (!isDraggingPlayhead) return;
        event.preventDefault();
        seekPlayer(getTimelineTimeFromClientX(event.clientX));
    }

    function endPlayheadDrag(event) {
        if (!isDraggingPlayhead) return;
        isDraggingPlayhead = false;
        playhead.classList.remove("is-dragging");
        if (playhead.hasPointerCapture(event.pointerId)) {
            playhead.releasePointerCapture(event.pointerId);
        }
    }

    function shouldAllowTextInputShortcut(target) {
        if (!(target instanceof Element)) return false;
        return Boolean(target.closest("input, textarea, [contenteditable='true']"));
    }

    function handleEditorShortcut(event) {
        if (
            !editorReady
            || event.defaultPrevented
            || event.repeat
            || event.altKey
            || event.ctrlKey
            || event.metaKey
            || shouldAllowTextInputShortcut(event.target)
        ) {
            return;
        }

        switch (event.code) {
        case "KeyI":
            event.preventDefault();
            setStart(player.currentTime);
            break;
        case "KeyO":
            event.preventDefault();
            setEnd(player.currentTime);
            break;
        case "BracketLeft":
            event.preventDefault();
            seekAdjacentIframe(-1);
            break;
        case "BracketRight":
            event.preventDefault();
            seekAdjacentIframe(1);
            break;
        case "Home":
            event.preventDefault();
            seekPlayer(0);
            break;
        case "End":
            event.preventDefault();
            seekPlayer(duration);
            break;
        case "Space":
            event.preventDefault();
            togglePlayback();
            break;
        case "Comma":
            event.preventDefault();
            stepFrame(-1);
            break;
        case "Period":
            event.preventDefault();
            stepFrame(1);
            break;
        default:
            break;
        }
    }

    function setStart(value, seek = false) {
        if (!editorReady) return;
        start = snapStart(clamp(value));
        updateUi("start");
        if (seek) seekPlayer(start);
    }

    function setEnd(value, seek = false) {
        if (!editorReady) return;
        end = snapEnd(clamp(value));
        updateUi("end");
        if (seek) seekPlayer(end);
    }

    function drawKeyframes() {
        if (!canvas || !timeline || !editorReady) return;
        const ratio = window.devicePixelRatio || 1;
        const rect = timeline.getBoundingClientRect();
        canvas.width = Math.max(1, Math.round(rect.width * ratio));
        canvas.height = Math.max(1, Math.round(rect.height * ratio));
        const context = canvas.getContext("2d");
        context.scale(ratio, ratio);
        context.clearRect(0, 0, rect.width, rect.height);
        context.fillStyle = "rgba(0, 242, 255, 0.14)";
        for (let x = 0; x < rect.width; x += 14) {
            const height = 16 + ((x * 17) % Math.max(20, rect.height - 18));
            context.fillRect(x, rect.height - height, 3, height);
        }
        context.fillStyle = "rgba(255, 110, 132, 0.9)";
        keyframes.forEach((timestamp) => {
            const x = duration ? (timestamp / duration) * rect.width : 0;
            context.fillRect(Math.round(x), rect.height - 22, 3, 18);
        });
    }

    async function loadTrimInfo() {
        if (isCdgMode) {
            setCdgModeUi(true);
            return;
        }
        const sequence = ++loadSequence;
        setBusyState(true);
        setLoadingStateVisible(true);
        setLoadingMessage(
            t("trim.loading_keyframes"),
            t("trim.loading_keyframes_detail"),
            false,
        );
        setControlsEnabled(false);
        showError();
        try {
            const response = await fetch(appUrl(`/api/media/${mediaId}/trim-info`), {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(payload.detail || t("trim.loading_failed_detail"));
            }
            if (sequence !== loadSequence) return;

            duration = Number(payload.duration);
            if (!Number.isFinite(duration) || duration <= 0) {
                throw new Error(t("trim.loading_failed_detail"));
            }
            if (String(payload?.lyrics_kind || "").trim().toLowerCase() === "cdg") {
                setCdgModeUi(true);
                return;
            }
            frameRate = Number(payload.frame_rate);
            if (!Number.isFinite(frameRate) || frameRate <= 0) {
                frameRate = DEFAULT_FRAME_RATE;
            }
            hasVideo = Boolean(payload.has_video);
            keyframes = Array.isArray(payload.keyframes)
                ? payload.keyframes.map(Number).filter(Number.isFinite)
                : [];
            snapPoints = [...new Set([0, ...keyframes, duration])].sort((a, b) => a - b);
            start = 0;
            end = duration;
            root.dataset.duration = String(duration);
            root.dataset.hasVideo = hasVideo ? "true" : "false";
            root.dataset.frameRate = String(frameRate);
            root.dataset.keyframes = JSON.stringify(keyframes);
            setTimelineBounds();
            editorReady = true;
            setControlsEnabled(true);
            setBusyState(false);
            setLoadingStateVisible(false);
            updateUi();
            updatePlayheadA11y();
            drawKeyframes();
        } catch (error) {
            if (sequence !== loadSequence) return;
            editorReady = false;
            setBusyState(false);
            setLoadingStateVisible(true);
            setLoadingMessage(
                t("trim.loading_failed"),
                error instanceof Error ? error.message : t("trim.loading_failed_detail"),
                true,
            );
            setControlsEnabled(false);
        }
    }

    startRange.addEventListener("input", () => setStart(startRange.value, true));
    endRange.addEventListener("input", () => setEnd(endRange.value, true));
    startInput.addEventListener("change", () => setStart(startInput.value, true));
    endInput.addEventListener("change", () => setEnd(endInput.value, true));
    prevIframeButton.addEventListener("click", () => seekAdjacentIframe(-1));
    nextIframeButton.addEventListener("click", () => seekAdjacentIframe(1));
    setStartButton.addEventListener("click", () => setStart(player.currentTime));
    setEndButton.addEventListener("click", () => setEnd(player.currentTime));
    jumpStartButton.addEventListener("click", () => seekPlayer(start));
    jumpEndButton.addEventListener("click", () => seekPlayer(end));
    playhead.addEventListener("pointerdown", startPlayheadDrag);
    playhead.addEventListener("pointermove", movePlayheadDrag);
    playhead.addEventListener("pointerup", endPlayheadDrag);
    playhead.addEventListener("pointercancel", endPlayheadDrag);
    playhead.addEventListener("lostpointercapture", () => {
        isDraggingPlayhead = false;
        playhead.classList.remove("is-dragging");
    });
    playhead.addEventListener("keydown", (event) => {
        if (!editorReady) return;
        if (event.key === "ArrowLeft") {
            event.preventDefault();
            seekAdjacentIframe(-1);
        } else if (event.key === "ArrowRight") {
            event.preventDefault();
            seekAdjacentIframe(1);
        } else if (event.key === "Home") {
            event.preventDefault();
            seekPlayer(0);
        } else if (event.key === "End") {
            event.preventDefault();
            seekPlayer(duration);
        }
    });
    document.addEventListener("keydown", handleEditorShortcut, true);

    if (loadingRetry) {
        loadingRetry.addEventListener("click", () => {
            loadTrimInfo();
        });
    }

    player.addEventListener("timeupdate", () => {
        if (!editorReady) return;
        syncPlayheadPosition(player.currentTime);
    });

    timeline.addEventListener("dblclick", (event) => {
        if (!editorReady) return;
        seekPlayer(getTimelineTimeFromClientX(event.clientX));
    });

    saveButton.addEventListener("click", async () => {
        if (isCdgMode) {
            await startTranscode();
            return;
        }
        if (!editorReady || isSubmitting) {
            return;
        }
        if (!window.confirm(t("trim.confirm_apply", {
            start: formatTime(start),
            end: formatTime(end),
        }))) {
            return;
        }
        isSubmitting = true;
        setControlsEnabled(false);
        saveButton.querySelector("span:last-child").textContent = t("trim.trimming");
        showError();
        try {
            const response = await fetch(appUrl(`/api/media/${mediaId}/trim`), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ start_time: start, end_time: end }),
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(payload.detail || t("trim.failed"));
            }
            const summary = payload.summary;
            start = 0;
            end = Number(summary.duration);
            root.dataset.duration = String(end);
            const refreshedUrl = new URL(root.dataset.mediaUrl, window.location.origin);
            refreshedUrl.searchParams.set("trimmed", String(Date.now()));
            player.src = refreshedUrl.pathname + refreshedUrl.search;
            window.location.href = appUrl("/media");
        } catch (error) {
            showError(error instanceof Error ? error.message : t("trim.failed"));
            isSubmitting = false;
            setControlsEnabled(true);
            saveButton.querySelector("span:last-child").textContent = t("trim.apply_trim");
        }
    });

    transcodeButton?.addEventListener("click", () => {
        startTranscode();
    });

    window.addEventListener("resize", drawKeyframes);
    setCdgModeUi(isCdgMode);
    loadTrimInfo();
})();
