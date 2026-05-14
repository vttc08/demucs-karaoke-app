const API_BASE = window.KaraokeURLs?.basePath || "";
const appWsUrl = window.KaraokeURLs?.appWsUrl || ((path) => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}${path}`;
});
const t = window.KaraokeI18n?.t?.bind(window.KaraokeI18n) || ((key) => key);

const main = document.querySelector("main[data-initial-item-id]");
const liveStatus = document.getElementById("lyrics-live-status");
const followLiveBtn = document.getElementById("lyrics-follow-live-btn");
const currentTitle = document.getElementById("lyrics-current-title");
const currentArtist = document.getElementById("lyrics-current-artist");
const modeBadge = document.getElementById("lyrics-mode-badge");
const scrollContainer = document.getElementById("lyrics-scroll-container");
const lyricsLines = document.getElementById("lyrics-lines");
const emptyState = document.getElementById("lyrics-empty-state");
const emptyTitle = document.getElementById("lyrics-empty-title");
const emptyDetail = document.getElementById("lyrics-empty-detail");
const googleLink = document.getElementById("lyrics-google-link");

let ws = null;
let currentItem = null;
let currentItemId = Number(main?.dataset.initialItemId || 0) || null;
let isSynced = false;
let cues = [];
let lines = [];
let activeCueIndex = null;
let followLive = true;
let suppressScrollEvent = false;
let suppressScrollResetTimer = null;

let paused = false;
let basePlaybackSeconds = 0;
let playbackAnchorMs = performance.now();
let tickerId = null;

function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = String(value || "");
    return div.innerHTML;
}

function setLiveStatus(text, tone = "neutral") {
    if (!liveStatus) return;
    liveStatus.textContent = text;
    liveStatus.className = "rounded-full px-3 py-1 text-xs font-bold";
    if (tone === "online") {
        liveStatus.classList.add("bg-primary/10", "text-primary");
        return;
    }
    if (tone === "offline") {
        liveStatus.classList.add("bg-error/10", "text-error");
        return;
    }
    liveStatus.classList.add("bg-surface-container-highest", "text-on-surface-variant");
}

function setNowPlaying(item) {
    if (!currentTitle || !currentArtist) return;
    if (!item || !item.id) {
        currentTitle.textContent = t("queue_lyrics.queue_empty");
        currentArtist.textContent = t("queue_lyrics.queue_empty_detail");
        return;
    }
    currentTitle.textContent = item.title || t("queue_lyrics.queue_empty");
    currentArtist.textContent = item.artist || t("common.unknown_artist");
}

function setModeBadge(text = "") {
    if (!modeBadge) return;
    modeBadge.textContent = text;
    modeBadge.classList.toggle("hidden", !text);
}

function getPlaybackSeconds() {
    if (paused) {
        return basePlaybackSeconds;
    }
    const elapsed = Math.max(0, (performance.now() - playbackAnchorMs) / 1000);
    return basePlaybackSeconds + elapsed;
}

function setPlaybackClock(seconds, nextPaused = null) {
    if (!Number.isFinite(seconds)) {
        return;
    }
    basePlaybackSeconds = Math.max(0, Number(seconds));
    playbackAnchorMs = performance.now();
    if (typeof nextPaused === "boolean") {
        paused = nextPaused;
        if (paused) {
            stopTicker();
        } else {
            startTicker();
        }
    } else if (!paused) {
        startTicker();
    }
    updateActiveCue();
}

function setPaused(nextPaused) {
    const normalized = Boolean(nextPaused);
    if (normalized === paused) {
        return;
    }
    if (normalized) {
        basePlaybackSeconds = getPlaybackSeconds();
        paused = true;
        stopTicker();
        return;
    }
    paused = false;
    playbackAnchorMs = performance.now();
    startTicker();
}

function setSeekTime(seconds) {
    setPlaybackClock(seconds);
}

function resetPlaybackClock() {
    basePlaybackSeconds = 0;
    playbackAnchorMs = performance.now();
}

function findActiveCueIndex(currentSeconds) {
    if (!cues.length) {
        return null;
    }
    if (currentSeconds < cues[0].time) {
        return -1;
    }
    let left = 0;
    let right = cues.length - 1;
    let best = 0;
    while (left <= right) {
        const mid = Math.floor((left + right) / 2);
        if (cues[mid].time <= currentSeconds) {
            best = mid;
            left = mid + 1;
        } else {
            right = mid - 1;
        }
    }
    return best;
}

function updateFollowLiveButton() {
    if (!followLiveBtn) return;
    const shouldShow = isSynced && cues.length > 0 && !followLive;
    followLiveBtn.classList.toggle("hidden", !shouldShow);
}

function scrollToActiveCue() {
    if (!scrollContainer || activeCueIndex === null || activeCueIndex < 0) {
        return;
    }
    const target = scrollContainer.querySelector(`[data-cue-index="${activeCueIndex}"]`);
    if (!target) return;
    suppressScrollEvent = true;
    if (suppressScrollResetTimer !== null) {
        window.clearTimeout(suppressScrollResetTimer);
    }
    target.scrollIntoView({ behavior: "auto", block: "center" });
    suppressScrollResetTimer = window.setTimeout(() => {
        suppressScrollEvent = false;
        suppressScrollResetTimer = null;
    }, 150);
}

function updateActiveCue(forceScroll = false) {
    if (!isSynced || !cues.length || !lyricsLines) {
        return;
    }
    const nextIndex = findActiveCueIndex(getPlaybackSeconds());
    if (nextIndex === activeCueIndex && !forceScroll) {
        return;
    }

    if (activeCueIndex !== null && activeCueIndex >= 0) {
        const prev = lyricsLines.querySelector(`[data-cue-index="${activeCueIndex}"]`);
        prev?.classList.remove("bg-primary/10", "text-primary", "border-primary/30");
        prev?.classList.add("border-transparent", "text-on-surface");
    }

    activeCueIndex = nextIndex;
    if (activeCueIndex !== null && activeCueIndex >= 0) {
        const active = lyricsLines.querySelector(`[data-cue-index="${activeCueIndex}"]`);
        active?.classList.remove("border-transparent", "text-on-surface");
        active?.classList.add("bg-primary/10", "text-primary", "border-primary/30");
        if (followLive) {
            scrollToActiveCue();
        }
    }
}

function startTicker() {
    if (!isSynced || tickerId !== null) {
        return;
    }
    const tick = () => {
        updateActiveCue();
        if (!paused && isSynced) {
            tickerId = window.requestAnimationFrame(tick);
        } else {
            tickerId = null;
        }
    };
    tickerId = window.requestAnimationFrame(tick);
}

function stopTicker() {
    if (tickerId === null) return;
    window.cancelAnimationFrame(tickerId);
    tickerId = null;
}

function setEmptyStateVisible(visible) {
    emptyState?.classList.toggle("hidden", !visible);
    lyricsLines?.classList.toggle("hidden", visible);
}

function buildGoogleLyricsUrl(item) {
    const parts = [item?.title || "", item?.artist || "", "lyrics"]
        .map((part) => String(part || "").trim())
        .filter(Boolean);
    return `https://www.google.com/search?q=${encodeURIComponent(parts.join(" "))}`;
}

function renderNoLyricsState(item) {
    stopTicker();
    isSynced = false;
    cues = [];
    lines = [];
    activeCueIndex = null;
    setModeBadge("");
    setEmptyStateVisible(true);
    if (emptyTitle) {
        emptyTitle.textContent = item?.id
            ? t("queue_lyrics.no_lyrics_title")
            : t("queue_lyrics.queue_empty");
    }
    if (emptyDetail) {
        emptyDetail.textContent = item?.id
            ? t("queue_lyrics.no_lyrics_detail")
            : t("queue_lyrics.queue_empty_detail");
    }
    if (googleLink) {
        googleLink.href = buildGoogleLyricsUrl(item);
        googleLink.classList.toggle("hidden", !item?.id);
    }
    updateFollowLiveButton();
}

function renderSyncedLyrics() {
    if (!lyricsLines) return;
    lyricsLines.innerHTML = cues
        .map((cue, index) => `
            <p
                data-cue-index="${index}"
                class="rounded-xl border border-transparent px-3 py-2 text-xl leading-relaxed text-on-surface transition-colors sm:text-2xl"
            >${escapeHtml(cue.text)}</p>
        `)
        .join("");
    setModeBadge(t("queue_lyrics.timed_mode"));
    setEmptyStateVisible(false);
    activeCueIndex = null;
    updateActiveCue();
    if (!paused) {
        startTicker();
    }
}

function renderUnsyncedLyrics() {
    if (!lyricsLines) return;
    stopTicker();
    lyricsLines.innerHTML = lines
        .map((line) => `
            <p class="rounded-xl px-3 py-2 text-xl leading-relaxed text-on-surface sm:text-2xl">${escapeHtml(line)}</p>
        `)
        .join("");
    setModeBadge(t("queue_lyrics.plain_mode"));
    setEmptyStateVisible(false);
    updateFollowLiveButton();
}

function normalizeCue(rawCue) {
    if (!rawCue || typeof rawCue !== "object") return null;
    const time = Number(rawCue.time);
    const text = typeof rawCue.text === "string" ? rawCue.text.trim() : "";
    if (!Number.isFinite(time) || !text) return null;
    return { time: Math.max(0, time), text };
}

async function fetchLyricsPayload(itemId) {
    const response = await fetch(`${API_BASE}/api/queue/${itemId}/lyrics-cues`);
    if (!response.ok) {
        return null;
    }
    return response.json();
}

async function refreshCurrentItem() {
    const response = await fetch(`${API_BASE}/api/queue/current`);
    if (!response.ok) {
        throw new Error(`Failed to load current item: ${response.status}`);
    }
    const item = await response.json();
    currentItem = item?.id ? item : null;
    currentItemId = currentItem?.id || null;
    setNowPlaying(currentItem);

    if (!currentItemId) {
        renderNoLyricsState(null);
        return;
    }

    const payload = await fetchLyricsPayload(currentItemId);
    if (!payload) {
        renderNoLyricsState(currentItem);
        return;
    }

    isSynced = Boolean(payload.is_synced);
    cues = Array.isArray(payload.cues)
        ? payload.cues.map(normalizeCue).filter((cue) => cue !== null).sort((a, b) => a.time - b.time)
        : [];
    lines = Array.isArray(payload.lines)
        ? payload.lines.map((line) => String(line || "").trim()).filter(Boolean)
        : [];

    followLive = true;
    updateFollowLiveButton();

    if (isSynced && cues.length > 0) {
        renderSyncedLyrics();
        return;
    }
    if (lines.length > 0) {
        renderUnsyncedLyrics();
        return;
    }
    renderNoLyricsState(currentItem);
}

function handleSocketMessage(message) {
    const type = message?.type;
    if (type === "ping") {
        ws?.send(JSON.stringify({ type: "pong", timestamp: Date.now() }));
        return;
    }
    if (type === "connected") {
        setLiveStatus(t("queue.connected"), "online");
        const state = message?.data?.stage_state;
        if (typeof state?.is_paused === "boolean") {
            setPaused(state.is_paused);
        }
        if (typeof state?.current_time === "number") {
            setPlaybackClock(state.current_time, typeof state?.is_paused === "boolean" ? state.is_paused : null);
        }
        return;
    }
    if (type === "stage_state_update") {
        if (typeof message?.data?.current_time === "number") {
            setPlaybackClock(message.data.current_time, typeof message?.data?.is_paused === "boolean" ? message.data.is_paused : null);
        } else if (typeof message?.data?.is_paused === "boolean") {
            setPaused(message.data.is_paused);
        }
        updateFollowLiveButton();
        return;
    }
    if (type === "stage_time_update") {
        const currentTime = Number(message?.data?.current_time);
        if (Number.isFinite(currentTime)) {
            setPlaybackClock(currentTime, typeof message?.data?.is_paused === "boolean" ? message.data.is_paused : null);
        }
        return;
    }
    if (type === "stage_control_command") {
        const command = message?.data?.command;
        if (command === "play") {
            setPaused(false);
            return;
        }
        if (command === "pause") {
            setPaused(true);
            return;
        }
        if (command === "seek") {
            const seekTime = Number(message?.data?.seek_time);
            if (Number.isFinite(seekTime)) {
                setSeekTime(seekTime);
            }
            if (typeof message?.data?.is_paused === "boolean") {
                setPaused(message.data.is_paused);
            }
            return;
        }
        return;
    }
    if (type === "current_item_changed") {
        setPlaybackClock(0, false);
        refreshCurrentItem().catch((error) => {
            console.warn("Failed to refresh current lyrics item:", error);
            renderNoLyricsState(currentItem);
        });
    }
}

function connectSocket() {
    ws = new WebSocket(appWsUrl("/api/queue/ws"));
    setLiveStatus(t("queue_lyrics.connecting"));

    ws.onopen = () => {
        setLiveStatus(t("queue.connected"), "online");
    };

    ws.onmessage = (event) => {
        try {
            handleSocketMessage(JSON.parse(event.data));
        } catch (error) {
            console.warn("Invalid websocket message:", error);
        }
    };

    ws.onclose = () => {
        setLiveStatus(t("queue.offline"), "offline");
        window.setTimeout(connectSocket, 2000);
    };

    ws.onerror = () => {
        setLiveStatus(t("queue.offline"), "offline");
    };
}

if (scrollContainer) {
    scrollContainer.addEventListener("scroll", () => {
        if (!isSynced || suppressScrollEvent || !followLive) {
            return;
        }
        followLive = false;
        updateFollowLiveButton();
    });
}

followLiveBtn?.addEventListener("click", () => {
    followLive = true;
    updateFollowLiveButton();
    updateActiveCue(true);
    scrollToActiveCue();
});

refreshCurrentItem().catch((error) => {
    console.warn("Initial lyrics viewer load failed:", error);
    renderNoLyricsState(currentItem);
});
connectSocket();
