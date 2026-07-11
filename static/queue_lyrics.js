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
const TTML_TIME_RE = /^(?:(\d+):)?(\d{2}):(\d{2})(?:\.(\d{1,3}))?$/;

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
    downgradeBtn: "#lyrics-downgrade-btn",
    upgradeHint: "#lyrics-upgrade-hint",
    fileInput: "#lyrics-file",
    googleLink: "#lyrics-google-link",
    processLinesToggle: "#lyrics-process-lines-toggle",
    processLinesDetail: "#lyrics-process-lines-detail",
    maxLineLengthInput: "#lyrics-max-line-length",
    maxLineLengthCjkInput: "#lyrics-max-line-length-cjk",
    whisperxLanguageInput: "#lyrics-whisperx-language-code",
    panel: "#lyrics-panel",
});

let ws = null;
let shouldReconnectSocket = true;
let reconnectTimer = null;
let reconnectAttempts = 0;
let reconnectDelayMs = 1000;
let lastSocketMessageAt = 0;
let lastSocketPingAt = 0;
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
let currentDisplaySource = null;
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
    scheduleDisplayRefresh();
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

function applyLyricsDraft(manager, text, providerInfo, options = {}) {
    if (!manager) {
        return;
    }
    if (typeof manager.setLyricsDraft === "function") {
        manager.setLyricsDraft(text, providerInfo, options);
        return;
    }
    if (typeof manager.setManualLyrics === "function") {
        manager.setManualLyrics(text, providerInfo);
        return;
    }

    // Compatibility fallback for older manager bundles.
    const trimmedText = String(text || "").trim();
    const inferredFormat = options.format || LyricsManager.inferFormat(trimmedText);
    if (typeof manager.cancelInFlight === "function") {
        manager.cancelInFlight();
    }
    if (manager.state && typeof manager.state === "object") {
        manager.state.text = trimmedText;
        manager.state.format = inferredFormat;
        manager.state.provider = providerInfo || "";
        manager.state.isSynced = typeof options.isSynced === "boolean" ? options.isSynced : inferredFormat !== "txt";
        manager.state.lyricsState = options.lyricsState || (trimmedText ? "manual" : "idle");
    }
    if (typeof manager.notifyListeners === "function") {
        manager.notifyListeners();
    }
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

function isCdgLyricsPath(path) {
    return String(path || "").toLowerCase().split("?")[0].endsWith(".cdg");
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

function parseJsonLyrics(text) {
    let payload;
    try {
        payload = JSON.parse(String(text || "").trim());
    } catch (_) {
        return [];
    }

    const rows = Array.isArray(payload)
        ? payload
        : (payload && typeof payload === "object" && Array.isArray(payload.cues))
            ? payload.cues
            : null;
    if (!Array.isArray(rows)) {
        return [];
    }

    const cues = [];
    for (const row of rows) {
        if (!row || typeof row !== "object") {
            continue;
        }

        const time = Number(row.time ?? row.start ?? row.timestamp);
        if (!Number.isFinite(time)) {
            continue;
        }

        let textValue = "";
        if (typeof row.text === "string" && row.text.trim()) {
            textValue = row.text.trim();
        } else if (typeof row.line === "string" && row.line.trim()) {
            textValue = row.line.trim();
        } else if (typeof row.lyric === "string" && row.lyric.trim()) {
            textValue = row.lyric.trim();
        } else if (Array.isArray(row.words)) {
            textValue = row.words
                .filter((word) => word && typeof word === "object" && typeof word.word === "string" && word.word.trim())
                .map((word) => word.word.trim())
                .join(" ");
        }

        if (!textValue) {
            continue;
        }

        const cue = { time: Math.max(0, time), text: textValue };
        const end = Number(row.end);
        if (Number.isFinite(end) && end >= time) {
            cue.end = Math.max(0, end);
        }

        if (Array.isArray(row.words)) {
            const words = [];
            let complete = Boolean(row.words.length);
            for (const word of row.words) {
                if (!word || typeof word !== "object") {
                    complete = false;
                    continue;
                }

                const wordText = typeof word.word === "string" ? word.word.trim() : "";
                const wordStart = Number(word.start);
                const wordEnd = Number(word.end);
                if (!wordText || !Number.isFinite(wordStart) || !Number.isFinite(wordEnd) || wordEnd < wordStart) {
                    complete = false;
                    continue;
                }

                words.push({
                    word: wordText,
                    start: Math.max(0, wordStart),
                    end: Math.max(0, wordEnd),
                });
            }

            if (complete && words.length > 0) {
                words.sort((a, b) => a.start - b.start);
                cue.words = words;
            }
        }

        cues.push(cue);
    }

    cues.sort((a, b) => a.time - b.time);
    return cues;
}

function parseTtmlTime(text) {
    const match = String(text || "").trim().match(TTML_TIME_RE);
    if (!match) {
        return null;
    }

    const hours = Number(match[1] || 0);
    const minutes = Number(match[2] || 0);
    const seconds = Number(match[3] || 0);
    if (!Number.isFinite(hours) || !Number.isFinite(minutes) || !Number.isFinite(seconds)) {
        return null;
    }

    const fractionRaw = match[4] || "";
    const fraction = fractionRaw ? Number(fractionRaw) / (10 ** fractionRaw.length) : 0;
    const total = (hours * 3600) + (minutes * 60) + seconds + fraction;
    return Number.isFinite(total) ? Math.max(0, total) : null;
}

function parseTtmlLyrics(text) {
    const trimmed = String(text || "").trim();
    if (!trimmed) {
        return [];
    }

    try {
        const parser = new DOMParser();
        const doc = parser.parseFromString(trimmed, "application/xml");
        if (doc.querySelector("parsererror")) {
            return [];
        }

        const nodes = Array.from(doc.getElementsByTagNameNS("*", "p"));
        const cues = [];
        for (const node of nodes) {
            const time = parseTtmlTime(node.getAttribute("begin") || node.getAttribute("start") || node.getAttribute("time"));
            if (time === null) {
                continue;
            }

            const end = parseTtmlTime(node.getAttribute("end"));
            const spans = Array.from(node.childNodes).filter((child) => child.nodeType === Node.ELEMENT_NODE && child.localName === "span");
            const rawText = spans.length > 0
                ? spans.map((span) => span.textContent || "").join("")
                : (node.textContent || "");
            const textValue = String(rawText).replace(/\s+/g, " ").trim();
            if (!textValue) {
                continue;
            }

            const cue = { time, text: textValue };
            if (end !== null && end >= time) {
                cue.end = end;
            }
            cues.push(cue);
        }

        cues.sort((a, b) => a.time - b.time);
        return cues;
    } catch (_) {
        return [];
    }
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

function buildDisplaySourceFromPayload(payload) {
    if (!payload) {
        return null;
    }

    const normalizedCues = Array.isArray(payload.cues)
        ? payload.cues.map(normalizeCue).filter((cue) => cue !== null).sort((a, b) => a.time - b.time)
        : [];
    const normalizedLines = Array.isArray(payload.lines)
        ? payload.lines.map((line) => String(line || "").trim()).filter(Boolean)
        : [];

    if (payload.is_synced && normalizedCues.length > 0) {
        return {
            isSynced: true,
            cues: normalizedCues,
            lines: normalizedCues.map((cue) => cue.text),
        };
    }
    if (normalizedLines.length > 0) {
        return {
            isSynced: false,
            cues: [],
            lines: normalizedLines,
        };
    }
    if (normalizedCues.length > 0) {
        return {
            isSynced: true,
            cues: normalizedCues,
            lines: normalizedCues.map((cue) => cue.text),
        };
    }
    return null;
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
        renderCurrentLyricsSource();
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

function buildSourceFromText(text, format = "txt") {
    const trimmedText = String(text || "").trim();
    if (!trimmedText) {
        return null;
    }

    const inferredFormat = format || LyricsManager.inferFormat(trimmedText);
    if (inferredFormat === "json" || LyricsManager.inferFormat(trimmedText) === "json") {
        const parsedCues = parseJsonLyrics(trimmedText);
        if (parsedCues.length > 0) {
            return {
                isSynced: true,
                cues: parsedCues,
                lines: parsedCues.map((cue) => cue.text),
            };
        }
    }

    if (inferredFormat === "lrc" || LyricsManager.inferFormat(trimmedText) === "lrc") {
        const parsedCues = parseLrcLyrics(trimmedText);
        if (parsedCues.length > 0) {
            return {
                isSynced: true,
                cues: parsedCues,
                lines: parsedCues.map((cue) => cue.text),
            };
        }
    }

    if (inferredFormat === "ttml" || LyricsManager.inferFormat(trimmedText) === "ttml") {
        const parsedCues = parseTtmlLyrics(trimmedText);
        if (parsedCues.length > 0) {
            return {
                isSynced: true,
                cues: parsedCues,
                lines: parsedCues.map((cue) => cue.text),
            };
        }
    }

    const parsedLines = parsePlainLyrics(trimmedText);
    if (!parsedLines.length) {
        return null;
    }
    return {
        isSynced: false,
        cues: [],
        lines: parsedLines,
    };
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

function getActiveViewerSource() {
    const state = lyricsManager.getState();
    const editorSource = buildSourceFromText(state.text, state.format);
    return editorSource || currentDisplaySource;
}

function seedLyricsManagerForCurrentItem(payload) {
    const title = currentItem?.title || "";
    const artist = currentItem?.artist || "";
    const draft = loadDraftForItem(currentItemId);

    isHydratingLyrics = true;
    try {
        if (draft) {
            lyricsManager.setMetadata(draft.title || title, draft.artist || artist, title);
            applyLyricsDraft(lyricsManager, draft.text || "", draft.provider || "", {
                format: draft.format || "txt",
                isSynced: typeof draft.isSynced === "boolean" ? draft.isSynced : false,
                lyricsState: draft.text ? "manual" : "idle",
            });
            return;
        }

        lyricsManager.setMetadata(title, artist, title);
        const seedText = payloadToEditorText(payload);
        if (seedText) {
            const sourceFormat = payload?.source_format || (payload?.is_synced ? "lrc" : "txt");
            applyLyricsDraft(lyricsManager, seedText, `saved:${payload?.source_format || "txt"}`, {
                format: sourceFormat,
                isSynced: Boolean(payload?.is_synced),
                lyricsState: "manual",
            });
            return;
        }

        applyLyricsDraft(lyricsManager, "", "", {
            format: "txt",
            isSynced: false,
            lyricsState: "idle",
        });
    } finally {
        isHydratingLyrics = false;
    }

    persistDraftForCurrentItem();
}

async function renderCurrentLyricsSource() {
    const source = getActiveViewerSource();
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
            applyLyricsDraft(lyricsManager, "", "", {
                format: "txt",
                isSynced: false,
                lyricsState: "idle",
            });
        } finally {
            isHydratingLyrics = false;
        }
        currentDisplaySource = null;
        renderNoLyricsState(null);
        return;
    }

    if (isCdgLyricsPath(currentItem?.lyrics_path)) {
        currentDisplaySource = null;
        seedLyricsManagerForCurrentItem(null);
        renderNoLyricsState(currentItem);
        initialLoadCompleted = true;
        return;
    }

    const payload = await fetchLyricsPayload(currentItemId);
    currentDisplaySource = buildDisplaySourceFromPayload(payload);
    seedLyricsManagerForCurrentItem(payload);
    await renderCurrentLyricsSource();
    initialLoadCompleted = true;
}

function handleSocketMessage(message) {
    lastSocketMessageAt = Date.now();
    const type = message?.type;
    if (type === "ping") {
        lastSocketPingAt = Date.now();
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

function clearReconnectTimer() {
    if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
}

function isSocketStale() {
    return window.KaraokeWebSocketLifecycle?.isSocketStale({
        socket: ws,
        lastActivityAt: Math.max(lastSocketMessageAt || 0, lastSocketPingAt || 0),
        graceMs: 5000,
    }) || false;
}

function resetReconnectState() {
    clearReconnectTimer();
    reconnectAttempts = 0;
    reconnectDelayMs = 1000;
}

function scheduleReconnect() {
    if (!shouldReconnectSocket) {
        return;
    }
    reconnectAttempts += 1;
    const rawDelay = Math.min(reconnectDelayMs * Math.pow(2, reconnectAttempts - 1), 8000);
    const delay = window.KaraokeWebSocketLifecycle?.withJitter(rawDelay) ?? rawDelay;
    clearReconnectTimer();
    reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        connectSocket(true);
    }, delay);
}

function reconnectNow(reason = "manual") {
    shouldReconnectSocket = true;
    clearReconnectTimer();
    if (ws && ws.readyState !== WebSocket.CLOSED) {
        try {
            ws.close(4000, reason);
        } catch (_) {
            // Best-effort only.
        }
    }
    ws = null;
    resetReconnectState();
    connectSocket(true);
}

function handleVisibleResume(event) {
    shouldReconnectSocket = true;
    if (!window.KaraokeWebSocketLifecycle?.isVisible()) {
        return;
    }
    if (ws && ws.readyState === WebSocket.CONNECTING) {
        return;
    }
    if (!ws || ws.readyState === WebSocket.CLOSED || isSocketStale() || event?.persisted) {
        reconnectNow(event?.persisted ? "pageshow" : "foreground");
        return;
    }
    refreshCurrentItem().catch((error) => {
        console.warn("Failed to refresh lyrics on resume:", error);
    });
}

function handlePageHide() {
    shouldReconnectSocket = false;
    clearReconnectTimer();
    if (!ws) {
        return;
    }
    try {
        ws.close(1000, "page hide");
    } catch (_) {
        // Best-effort shutdown only.
    }
}

function connectSocket(force = false) {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        if (!force) {
            return;
        }
        try {
            ws.close(4000, "force reconnect");
        } catch (_) {
            // Best-effort only.
        }
        ws = null;
    }
    if (!shouldReconnectSocket) {
        return;
    }
    setLiveStatus(t("queue_lyrics.connecting"));
    try {
        ws = new WebSocket(appWsUrl("/api/queue/ws"));
        const socket = ws;

        ws.onopen = () => {
            if (ws !== socket) {
                return;
            }
            resetReconnectState();
            lastSocketMessageAt = Date.now();
            lastSocketPingAt = 0;
            socket.send(JSON.stringify({
                type: "client_subscribe",
                data: { page: "lyrics_viewer" },
                timestamp: Date.now(),
            }));
            setLiveStatus(t("queue.connected"), "online");
            refreshCurrentItem().catch((error) => {
                console.warn("Failed to refresh lyrics after reconnect:", error);
            });
        };

        ws.onmessage = (event) => {
            if (ws !== socket) {
                return;
            }
            try {
                handleSocketMessage(JSON.parse(event.data));
            } catch (error) {
                console.warn("Invalid websocket message:", error);
            }
        };

        ws.onclose = () => {
            if (ws !== socket) {
                return;
            }
            ws = null;
            setLiveStatus(t("queue.offline"), "offline");
            if (shouldReconnectSocket) {
                scheduleReconnect();
            }
        };

        ws.onerror = () => {
            if (ws !== socket) {
                return;
            }
            setLiveStatus(t("queue.offline"), "offline");
        };
    } catch (error) {
        console.warn("Failed to open lyrics websocket:", error);
        setLiveStatus(t("queue.offline"), "offline");
        if (shouldReconnectSocket) {
            scheduleReconnect();
        }
    }
}

window.KaraokeWebSocketLifecycle?.installPageLifecycle({
    onVisible: () => handleVisibleResume(),
    onOnline: () => handleVisibleResume(),
    onPageShow: (event) => handleVisibleResume(event),
    onPageHide: () => handlePageHide(),
    onOffline: () => setLiveStatus(t("queue.offline"), "offline"),
});

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
