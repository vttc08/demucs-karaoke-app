(() => {
    const root = document.getElementById("media-trim-editor");
    if (!root) return;

    const appUrl = window.KaraokeURLs?.appUrl || ((path) => path);
    const t = window.KaraokeI18n?.t?.bind(window.KaraokeI18n) || ((key) => key);
    const player = document.getElementById("trim-media-player");
    const timeline = document.getElementById("trim-timeline");
    const canvas = document.getElementById("trim-keyframe-canvas");
    const selection = document.getElementById("trim-selection");
    const playhead = document.getElementById("trim-playhead");
    const startRange = document.getElementById("trim-start-range");
    const endRange = document.getElementById("trim-end-range");
    const startInput = document.getElementById("trim-start-input");
    const endInput = document.getElementById("trim-end-input");
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
    const duration = Number(root.dataset.duration);
    const hasVideo = root.dataset.hasVideo === "true";
    let keyframes = [];
    try {
        keyframes = JSON.parse(root.dataset.keyframes || "[]").map(Number).filter(Number.isFinite);
    } catch (_error) {
        keyframes = [];
    }
    const snapPoints = [...new Set([0, ...keyframes, duration])].sort((a, b) => a - b);
    let start = 0;
    let end = duration;

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

    function seekPlayer(value) {
        if (!player) return;
        player.currentTime = clamp(value);
        const percent = duration ? (player.currentTime / duration) * 100 : 0;
        playhead.style.left = `${Math.min(100, Math.max(0, percent))}%`;
    }

    function setStart(value, seek = false) {
        start = snapStart(clamp(value));
        updateUi("start");
        if (seek) seekPlayer(start);
    }

    function setEnd(value, seek = false) {
        end = snapEnd(clamp(value));
        updateUi("end");
        if (seek) seekPlayer(end);
    }

    function drawKeyframes() {
        if (!canvas || !timeline) return;
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

    startRange.addEventListener("input", () => setStart(startRange.value, true));
    endRange.addEventListener("input", () => setEnd(endRange.value, true));
    startInput.addEventListener("change", () => setStart(startInput.value, true));
    endInput.addEventListener("change", () => setEnd(endInput.value, true));
    setStartButton.addEventListener("click", () => setStart(player.currentTime));
    setEndButton.addEventListener("click", () => setEnd(player.currentTime));
    jumpStartButton.addEventListener("click", () => seekPlayer(start));
    jumpEndButton.addEventListener("click", () => seekPlayer(end));

    player.addEventListener("timeupdate", () => {
        const percent = duration ? (player.currentTime / duration) * 100 : 0;
        playhead.style.left = `${Math.min(100, Math.max(0, percent))}%`;
    });

    timeline.addEventListener("dblclick", (event) => {
        const rect = timeline.getBoundingClientRect();
        player.currentTime = clamp(((event.clientX - rect.left) / rect.width) * duration);
    });

    saveButton.addEventListener("click", async () => {
        if (!window.confirm(t("trim.confirm_apply", {
            start: formatTime(start),
            end: formatTime(end),
        }))) {
            return;
        }
        saveButton.disabled = true;
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
            saveButton.disabled = false;
            saveButton.querySelector("span:last-child").textContent = t("trim.apply_trim");
        }
    });

    window.addEventListener("resize", drawKeyframes);
    updateUi();
    drawKeyframes();
})();
