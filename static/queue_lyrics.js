const API_BASE = window.KaraokeURLs?.basePath || "";
const appWsUrl = window.KaraokeURLs?.appWsUrl || ((path) => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}${path}`;
});
const t = window.KaraokeI18n?.t?.bind(window.KaraokeI18n) || ((key) => key);

const main = document.querySelector("main[data-initial-item-id]");
const liveStatus = document.getElementById("lyrics-live-status");
const editorToggleBtn = document.getElementById("queue-lyrics-editor-toggle");
const chineseToggle = document.getElementById("queue-lyrics-chinese-toggle");
const pinyinToggle = document.getElementById("queue-lyrics-pinyin-toggle");
const followLiveBtn = document.getElementById("lyrics-follow-live-btn");
const editorShell = document.getElementById("queue-lyrics-editor-shell");
const editorCloseBtn = document.getElementById("queue-lyrics-editor-close");
const inferBtn = document.getElementById("queue-lyrics-infer-btn");
const currentTitle = document.getElementById("lyrics-current-title");
const currentArtist = document.getElementById("lyrics-current-artist");
const modeBadge = document.getElementById("lyrics-mode-badge");
const scrollContainer = document.getElementById("lyrics-scroll-container");
const lyricsLines = document.getElementById("lyrics-lines");
const emptyState = document.getElementById("lyrics-empty-state");
const emptyTitle = document.getElementById("lyrics-empty-title");
const emptyDetail = document.getElementById("lyrics-empty-detail");
const googleLink = document.getElementById("lyrics-google-link");

const EDITOR_OPEN_STORAGE_KEY = "karaoke.queueLyrics.editorOpen";
const CHINESE_DISPLAY_STORAGE_KEY = "karaoke.queueLyrics.chineseDisplay";
const PINYIN_DISPLAY_STORAGE_KEY = "karaoke.queueLyrics.pinyinDisplay";
const DRAFT_STORAGE_PREFIX = "karaoke.queueLyrics.draft:";
const LRC_TIMESTAMP_RE = /\[(\d{1,3}):(\d{2})(?:\.(\d{1,3}))?\]/g;
const LRC_OFFSET_RE = /^\[offset:([+-]?\d+)\]\s*$/i;

const lyricsManager = new LyricsManager({ apiBase: API_BASE });
const lyricsUIAdapter = new LyricsUIAdapter(lyricsManager, {
    titleInput: "#lyrics-title",
    artistInput: "#lyrics-artist",
    textarea: "#lyrics-textarea",
    stateLabel: "#lyrics-state",
    providerLabel: "#lyrics-provider",
    helpText: "#lyrics-help",
    searchBtn: "#lyrics-search-btn",
    uploadBtn: "#lyrics-upload-btn",
    fileInput: "#lyrics-file",
    googleLink: "#lyrics-google-link",
    panel: "#lyrics-panel",
});

let ws = null;
let currentItem = null;
let currentItemId = Number(main?.dataset.initialItemId || 0) || null;
let isSynced = false;
let cues = [];
let lines = [];
let activeCueIndex = null;
let followLive = true;
let chineseDisplayEnabled = readBooleanSessionStorage(CHINESE_DISPLAY_STORAGE_KEY);
let pinyinDisplayEnabled = readBooleanSessionStorage(PINYIN_DISPLAY_STORAGE_KEY);
if (!chineseDisplayEnabled) {
    pinyinDisplayEnabled = false;
}
let suppressScrollEvent = false;
let suppressScrollResetTimer = null;
let paused = false;
let basePlaybackSeconds = 0;
let playbackAnchorMs = performance.now();
let tickerId = null;
let transformRequestId = 0;
let transformDebounceId = null;
let renderedDisplaySource = null;
let editorVisible = readEditorVisibility();
let initialLoadCompleted = false;
let isHydratingLyrics = false;

lyricsManager.setEnabled(true);
lyricsUIAdapter.initialize();
lyricsManager.on(() => {
    if (isHydratingLyrics) {
        return;
    }
    persistDraftForCurrentItem();
    if (chineseDisplayEnabled) {
        scheduleDisplayRefresh();
        return;
    }
    syncViewerFromLyricsState();
});
updateEditorVisibilityUi();
syncEditorToggleLabel();
syncChineseDisplayControls();

function safeSessionStorageGet(key) {
    try {
        return window.sessionStorage.getItem(key);
    } catch (_) {
        return null;
    }
}

function safeSessionStorageSet(key, value) {
    try {
        window.sessionStorage.setItem(key, value);
    } catch (_) {
        // Session persistence is best-effort only.
    }
}

function safeSessionStorageRemove(key) {
    try {
        window.sessionStorage.removeItem(key);
    } catch (_) {
        // Session persistence is best-effort only.
    }
}

function readBooleanSessionStorage(key) {
    return safeSessionStorageGet(key) === "true";
}

function readEditorVisibility() {
    return safeSessionStorageGet(EDITOR_OPEN_STORAGE_KEY) === "true";
}

function persistEditorVisibility(visible) {
    safeSessionStorageSet(EDITOR_OPEN_STORAGE_KEY, visible ? "true" : "false");
}

function syncEditorToggleLabel() {
    if (!editorToggleBtn) {
        return;
    }
    editorToggleBtn.textContent = editorVisible ? t("queue_lyrics.hide_editor") : t("queue_lyrics.edit_lyrics");
}

function updateEditorVisibilityUi() {
    if (!editorShell) {
        return;
    }
    editorShell.classList.toggle("hidden", !editorVisible);
    syncEditorToggleLabel();
}

function setEditorVisible(visible) {
    editorVisible = Boolean(visible);
    persistEditorVisibility(editorVisible);
    updateEditorVisibilityUi();
}

function persistChineseDisplayVisibility() {
    safeSessionStorageSet(CHINESE_DISPLAY_STORAGE_KEY, chineseDisplayEnabled ? "true" : "false");
    safeSessionStorageSet(PINYIN_DISPLAY_STORAGE_KEY, pinyinDisplayEnabled ? "true" : "false");
}

function syncChineseDisplayControls() {
    if (chineseToggle) {
        chineseToggle.checked = chineseDisplayEnabled;
    }
    if (pinyinToggle) {
        pinyinToggle.checked = pinyinDisplayEnabled;
        pinyinToggle.disabled = !chineseDisplayEnabled;
        pinyinToggle.closest("label")?.classList.toggle("opacity-60", !chineseDisplayEnabled);
    }
}

function setChineseDisplayEnabled(enabled) {
    chineseDisplayEnabled = Boolean(enabled);
    if (!chineseDisplayEnabled) {
        pinyinDisplayEnabled = false;
    }
    transformRequestId += 1;
    persistChineseDisplayVisibility();
    syncChineseDisplayControls();
    scheduleDisplayRefresh();
}

function setPinyinDisplayEnabled(enabled) {
    pinyinDisplayEnabled = Boolean(enabled) && chineseDisplayEnabled;
    transformRequestId += 1;
    persistChineseDisplayVisibility();
    syncChineseDisplayControls();
    scheduleDisplayRefresh();
}

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
    updateActiveCue(true);
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

function findActiveLyricCueIndex(currentTime) {
    if (!cues.length) {
        return null;
    }
    if (currentTime < cues[0].time) {
        return -1;
    }

    let left = 0;
    let right = cues.length - 1;
    let best = 0;
    while (left <= right) {
        const mid = Math.floor((left + right) / 2);
        if (cues[mid].time <= currentTime) {
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
    const nextIndex = findActiveLyricCueIndex(getPlaybackSeconds());
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

function buildDisplayModeLabel(isSyncedMode) {
    const parts = [isSyncedMode ? t("queue_lyrics.timed_mode") : t("queue_lyrics.plain_mode")];
    if (chineseDisplayEnabled) {
        parts.push(t("queue_lyrics.simplify_chinese"));
        if (pinyinDisplayEnabled) {
            parts.push(t("queue_lyrics.show_pinyin"));
        }
    }
    return parts.join(" • ");
}

function normalizeDisplayItem(item) {
    if (item && typeof item === "object") {
        return {
            text: typeof item.text === "string" ? item.text : "",
            pinyin: typeof item.pinyin === "string" ? item.pinyin : "",
        };
    }
    return {
        text: typeof item === "string" ? item : "",
        pinyin: "",
    };
}

function renderDisplayBlocks(items, { synced = false } = {}) {
    if (!lyricsLines) return;
    lyricsLines.innerHTML = items
        .map((item, index) => {
            const normalized = normalizeDisplayItem(item);
            const secondary = normalized.pinyin ? `
                <p class="mt-1 text-sm leading-relaxed text-on-surface-variant sm:text-base">${escapeHtml(normalized.pinyin)}</p>
            ` : "";
            const cursorClass = synced ? "cursor-default" : "";
            return `
                <div
                    data-cue-index="${index}"
                    class="rounded-xl border border-transparent px-3 py-2 text-on-surface transition-colors ${cursorClass}"
                >
                    <p class="text-xl leading-relaxed text-inherit sm:text-2xl">${escapeHtml(normalized.text)}</p>
                    ${secondary}
                </div>
            `;
        })
        .join("");
}

function renderNoLyricsState(item) {
    stopTicker();
    isSynced = false;
    cues = [];
    lines = [];
    renderedDisplaySource = null;
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

function renderSyncedLyrics(displayCues = cues) {
    if (!lyricsLines) return;
    stopTicker();
    renderDisplayBlocks(displayCues, { synced: true });
    setModeBadge(buildDisplayModeLabel(true));
    setEmptyStateVisible(false);
    activeCueIndex = null;
    updateActiveCue(true);
    if (!paused) {
        startTicker();
    }
}

function renderUnsyncedLyrics(displayLines = lines) {
    if (!lyricsLines) return;
    stopTicker();
    renderDisplayBlocks(displayLines, { synced: false });
    setModeBadge(buildDisplayModeLabel(false));
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

function parseLrcLyrics(text) {
    let offsetMs = 0;
    const parsed = [];
    for (const rawLine of String(text || "").split(/\r?\n/)) {
        const line = rawLine.trim();
        if (!line) {
            continue;
        }

        const offsetMatch = LRC_OFFSET_RE.exec(line);
        if (offsetMatch) {
            offsetMs = Number(offsetMatch[1]) || 0;
            continue;
        }

        const timestamps = [...line.matchAll(LRC_TIMESTAMP_RE)];
        if (!timestamps.length) {
            continue;
        }

        const cueText = line.replace(LRC_TIMESTAMP_RE, "").trim();
        if (!cueText) {
            continue;
        }

        timestamps.forEach((match) => {
            const minutes = Number(match[1]);
            const seconds = Number(match[2]);
            if (!Number.isFinite(minutes) || !Number.isFinite(seconds) || seconds >= 60) {
                return;
            }
            const fractionRaw = match[3] || "";
            const fraction = fractionRaw ? Number(fractionRaw) / (10 ** fractionRaw.length) : 0;
            const totalSeconds = minutes * 60 + seconds + fraction + (offsetMs / 1000);
            if (Number.isFinite(totalSeconds) && totalSeconds >= 0) {
                parsed.push({ time: totalSeconds, text: cueText });
            }
        });
    }

    parsed.sort((a, b) => a.time - b.time);
    return parsed;
}

function parsePlainLyrics(text) {
    return String(text || "")
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean);
}

function formatLrcTimestamp(seconds) {
    const totalHundredths = Math.max(0, Math.round(Number(seconds || 0) * 100));
    const minutes = Math.floor(totalHundredths / 6000);
    const remainingHundredths = totalHundredths % 6000;
    const wholeSeconds = Math.floor(remainingHundredths / 100);
    const hundredths = remainingHundredths % 100;
    return `${String(minutes).padStart(2, "0")}:${String(wholeSeconds).padStart(2, "0")}.${String(hundredths).padStart(2, "0")}`;
}

function cuesToLrc(cueRows) {
    return cueRows
        .map((cue) => `[${formatLrcTimestamp(cue.time)}]${cue.text}`)
        .join("\n");
}

function payloadToEditorText(payload) {
    if (!payload) {
        return "";
    }
    if (payload.source_format === "txt") {
        return Array.isArray(payload.lines) ? payload.lines.join("\n") : "";
    }
    if (Array.isArray(payload.cues) && payload.cues.length > 0) {
        const normalized = payload.cues.map(normalizeCue).filter((cue) => cue !== null);
        return cuesToLrc(normalized);
    }
    if (Array.isArray(payload.lines)) {
        return payload.lines.join("\n");
    }
    return "";
}

function deriveLyricsSourceFromState(state) {
    const text = String(state?.text || "").trim();
    if (!text) {
        return null;
    }

    const format = state?.format || "txt";
    const inferredSynced = format === "lrc" || LyricsManager.inferFormat(text) === "lrc";
    if (inferredSynced) {
        const parsedCues = parseLrcLyrics(text);
        if (parsedCues.length > 0) {
            return {
                isSynced: true,
                cues: parsedCues,
                lines: parsedCues.map((cue) => cue.text),
            };
        }
    }

    const parsedLines = parsePlainLyrics(text);
    if (!parsedLines.length) {
        return null;
    }
    return {
        isSynced: false,
        cues: [],
        lines: parsedLines,
    };
}

function buildDisplayTexts(source) {
    if (!source) {
        return [];
    }
    if (source.isSynced) {
        return source.cues.map((cue) => cue.text);
    }
    return source.lines.slice();
}

function makeDisplaySource(source, transformedItems) {
    if (!source || !Array.isArray(transformedItems)) {
        return null;
    }
    if (source.isSynced) {
        return {
            isSynced: true,
            cues: source.cues.map((cue, index) => ({
                time: cue.time,
                text: transformedItems[index]?.simplified || cue.text,
                pinyin: transformedItems[index]?.pinyin || "",
            })),
            lines: transformedItems.map((item) => ({
                text: item?.simplified || "",
                pinyin: item?.pinyin || "",
            })),
        };
    }
    return {
        isSynced: false,
        cues: [],
        lines: transformedItems.map((item) => ({
            text: item?.simplified || "",
            pinyin: item?.pinyin || "",
        })),
    };
}

async function fetchChineseDisplayItems(source) {
    if (!source) {
        return null;
    }
    const texts = buildDisplayTexts(source);
    if (!texts.length) {
        return null;
    }

    const requestId = ++transformRequestId;
    const response = await fetch(`${API_BASE}/api/lyrics/chinese-transform`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            texts,
            include_pinyin: pinyinDisplayEnabled,
        }),
    });
    if (!response.ok) {
        throw new Error(`Chinese transform failed: ${response.status}`);
    }
    const payload = await response.json();
    if (requestId !== transformRequestId) {
        return null;
    }
    return Array.isArray(payload?.items) ? payload.items : null;
}

function clearTransformDebounce() {
    if (transformDebounceId !== null) {
        window.clearTimeout(transformDebounceId);
        transformDebounceId = null;
    }
}

function scheduleDisplayRefresh() {
    clearTransformDebounce();
    transformDebounceId = window.setTimeout(() => {
        transformDebounceId = null;
        syncViewerFromLyricsState();
    }, 120);
}

function persistDraftForCurrentItem() {
    if (!currentItemId) {
        return;
    }
    const state = lyricsManager.getState();
    const snapshot = {
        title: String(state.title || "").trim(),
        artist: String(state.artist || "").trim(),
        provider: String(state.provider || "").trim(),
        text: String(state.text || "").trim(),
        format: state.format || "txt",
        isSynced: Boolean(state.isSynced),
    };
    const hasContent = Boolean(snapshot.text || snapshot.title || snapshot.artist || snapshot.provider);
    const storageKey = `${DRAFT_STORAGE_PREFIX}${currentItemId}`;
    if (!hasContent) {
        safeSessionStorageRemove(storageKey);
        return;
    }
    safeSessionStorageSet(storageKey, JSON.stringify(snapshot));
}

function loadDraftForItem(itemId) {
    if (!itemId) {
        return null;
    }
    const storageKey = `${DRAFT_STORAGE_PREFIX}${itemId}`;
    const raw = safeSessionStorageGet(storageKey);
    if (!raw) {
        return null;
    }
    try {
        const parsed = JSON.parse(raw);
        return parsed && typeof parsed === "object" ? parsed : null;
    } catch (_) {
        return null;
    }
}

function seedLyricsManagerForCurrentItem(payload) {
    const title = currentItem?.title || "";
    const artist = currentItem?.artist || "";
    const draft = loadDraftForItem(currentItemId);

    isHydratingLyrics = true;
    try {
        if (draft) {
            lyricsManager.setMetadata(draft.title || title, draft.artist || artist, title);
            lyricsManager.setLyricsDraft(draft.text || "", draft.provider || "", {
                format: draft.format || "txt",
                isSynced: typeof draft.isSynced === "boolean" ? draft.isSynced : false,
                lyricsState: draft.text ? "manual" : "idle",
            });
            return;
        }

        lyricsManager.setMetadata(title, artist, title);
        const seedText = payloadToEditorText(payload);
        if (seedText) {
            lyricsManager.setLyricsDraft(seedText, `saved:${payload?.source_format || "txt"}`, {
                format: payload?.source_format === "txt" ? "txt" : "lrc",
                isSynced: Boolean(payload?.is_synced),
                lyricsState: "manual",
            });
            return;
        }

        lyricsManager.setLyricsDraft("", "", {
            format: "txt",
            isSynced: false,
            lyricsState: "idle",
        });
    } finally {
        isHydratingLyrics = false;
    }

    persistDraftForCurrentItem();
    syncViewerFromLyricsState();
}

async function syncViewerFromLyricsState() {
    const source = deriveLyricsSourceFromState(lyricsManager.getState());
    if (!source) {
        cues = [];
        lines = [];
        renderedDisplaySource = null;
        isSynced = false;
        renderNoLyricsState(currentItem);
        return;
    }

    isSynced = source.isSynced;

    if (!chineseDisplayEnabled) {
        cues = source.cues;
        lines = source.lines;
        renderedDisplaySource = null;
        if (isSynced) {
            renderSyncedLyrics();
            return;
        }
        renderUnsyncedLyrics();
        return;
    }

    try {
        const items = await fetchChineseDisplayItems(source);
        if (!items) {
            cues = source.cues;
            lines = source.lines;
            renderedDisplaySource = null;
            if (isSynced) {
                renderSyncedLyrics();
                return;
            }
            renderUnsyncedLyrics();
            return;
        }

        renderedDisplaySource = makeDisplaySource(source, items);
        cues = renderedDisplaySource?.cues || source.cues;
        lines = renderedDisplaySource?.lines || source.lines;
        if (isSynced) {
            renderSyncedLyrics(cues);
            return;
        }
        renderUnsyncedLyrics(lines);
    } catch (error) {
        console.warn("Chinese lyrics display transform failed:", error);
        cues = source.cues;
        lines = source.lines;
        renderedDisplaySource = null;
        if (isSynced) {
            renderSyncedLyrics();
            return;
        }
        renderUnsyncedLyrics();
    }
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
        isHydratingLyrics = true;
        try {
            lyricsManager.setMetadata("", "", "");
            lyricsManager.setLyricsDraft("", "", {
                format: "txt",
                isSynced: false,
                lyricsState: "idle",
            });
        } finally {
            isHydratingLyrics = false;
        }
        renderNoLyricsState(null);
        return;
    }

    const payload = await fetchLyricsPayload(currentItemId);
    seedLyricsManagerForCurrentItem(payload);
    initialLoadCompleted = true;
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

function getInferenceSeed() {
    const mediaPath = currentItem?.media_path || "";
    const pathSource = mediaPath ? mediaPath.split("?")[0].split("/").pop() || "" : "";
    const pathStem = pathSource.replace(/\.[^.]+$/, "").trim();
    if (pathStem) {
        return pathStem;
    }
    const title = lyricsManager.getState().title || currentItem?.title || "";
    return String(title || "").trim();
}

async function inferMetadataFromFilename() {
    const seed = getInferenceSeed();
    if (!seed) {
        return;
    }

    if (inferBtn) {
        inferBtn.disabled = true;
    }
    try {
        const response = await fetch(`${API_BASE}/api/search/infer?title=${encodeURIComponent(seed)}`);
        if (!response.ok) {
            throw new Error(`Metadata inference failed: ${response.status}`);
        }
        const data = await response.json();
        lyricsManager.setMetadata(data.title || seed, data.artist || "", seed);
    } catch (error) {
        console.warn("Lyrics metadata inference failed:", error);
    } finally {
        if (inferBtn) {
            inferBtn.disabled = false;
        }
    }
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
});

editorToggleBtn?.addEventListener("click", () => {
    setEditorVisible(!editorVisible);
    if (editorVisible) {
        window.setTimeout(() => {
            document.getElementById("lyrics-title")?.focus();
        }, 0);
    }
});

editorCloseBtn?.addEventListener("click", () => {
    setEditorVisible(false);
});

inferBtn?.addEventListener("click", () => {
    inferMetadataFromFilename().catch((error) => {
        console.warn("Failed to infer lyrics metadata from filename:", error);
    });
});

chineseToggle?.addEventListener("change", (event) => {
    setChineseDisplayEnabled(event.target.checked);
});

pinyinToggle?.addEventListener("change", (event) => {
    setPinyinDisplayEnabled(event.target.checked);
});

refreshCurrentItem()
    .catch((error) => {
        console.warn("Initial lyrics viewer load failed:", error);
        renderNoLyricsState(currentItem);
    })
    .finally(() => {
        initialLoadCompleted = true;
    });
connectSocket();
