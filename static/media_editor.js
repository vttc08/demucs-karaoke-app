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
    const setStartButton = document.getElementById("trim-set-start");
    const setEndButton = document.getElementById("trim-set-end");
    const jumpStartButton = document.getElementById("trim-jump-start");
    const jumpEndButton = document.getElementById("trim-jump-end");

    const mediaId = Number(root.dataset.mediaId);
    const SNAP_EPSILON = 0.000001;
    let duration = 0;
    let hasVideo = root.dataset.hasVideo === "true";
    let keyframes = [];
    let snapPoints = [0];
    let start = 0;
    let end = 0;
    let editorReady = false;
    let isSubmitting = false;
    let loadSequence = 0;
    let isDraggingPlayhead = false;

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
            hasVideo = Boolean(payload.has_video);
            keyframes = Array.isArray(payload.keyframes)
                ? payload.keyframes.map(Number).filter(Number.isFinite)
                : [];
            snapPoints = [...new Set([0, ...keyframes, duration])].sort((a, b) => a - b);
            start = 0;
            end = duration;
            root.dataset.duration = String(duration);
            root.dataset.hasVideo = hasVideo ? "true" : "false";
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

    window.addEventListener("resize", drawKeyframes);
    loadTrimInfo();
})();
