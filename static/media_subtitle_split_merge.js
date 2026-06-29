(() => {
    const root = document.getElementById("subtitle-split-merge-page");
    if (!root) return;

    const appUrl = window.KaraokeURLs?.appUrl || ((path) => path);
    const t = window.KaraokeI18n?.t?.bind(window.KaraokeI18n) || ((key, params = {}) => key);
    const mediaId = Number(root.dataset.mediaId || 0);
    const jsonUrl = root.dataset.jsonUrl || "";
    const processUrl = root.dataset.processUrl || "";
    const saveUrl = root.dataset.saveUrl || "";
    const backUrl = root.dataset.backUrl || appUrl("/media");
    const docsUrl = root.dataset.docsUrl || "";
    const segmentList = document.getElementById("subtitle-segment-list");
    const segmentCount = document.getElementById("subtitle-segment-count");
    const statusBox = document.getElementById("subtitle-status");
    const processButton = document.getElementById("subtitle-process-btn");
    const saveButton = document.getElementById("subtitle-save-btn");
    const undoButton = document.getElementById("subtitle-undo-btn");
    const maxLineLengthInput = document.getElementById("subtitle-max-line-length");
    const maxLineLengthCjkInput = document.getElementById("subtitle-max-line-length-cjk");

    const STORAGE_KEY = `karaoke.subtitleSplitMerge.${mediaId}`;
    const DEFAULT_MAX_LINE_LENGTH = 36;
    const DEFAULT_MAX_LINE_LENGTH_CJK = 12;
    const CJK_RE = /[\u4e00-\u9fff]/;
    const ODD_SPACES_RE = /[^\S\n]|\u00A0|\u1680|[\u2000-\u200A]|\u202F|\u205F|\u3000/g;
    const TOKEN_RE = /[\u4e00-\u9fff]|[A-Za-z]+(?:['’][A-Za-z]+)*|\d+(?:[.,]\d+)*|[^\s]/g;

    let jsonpatchPromise = null;
    let state = {
        segments: [],
        history: [],
    };

    function clone(value) {
        if (typeof structuredClone === "function") {
            return structuredClone(value);
        }
        return JSON.parse(JSON.stringify(value));
    }

    function getJsonPatch() {
        if (!jsonpatchPromise) {
            jsonpatchPromise = import("https://esm.sh/fast-json-patch@3.1.1");
        }
        return jsonpatchPromise;
    }

    function safeStorageGet() {
        try {
            return window.sessionStorage.getItem(STORAGE_KEY);
        } catch (_error) {
            return null;
        }
    }

    function safeStorageSet(value) {
        try {
            window.sessionStorage.setItem(STORAGE_KEY, value);
        } catch (_error) {
            // Session state is best-effort only.
        }
    }

    function safeStorageRemove() {
        try {
            window.sessionStorage.removeItem(STORAGE_KEY);
        } catch (_error) {
            // Session state is best-effort only.
        }
    }

    function parseNumberInput(input, fallback) {
        if (!input) return fallback;
        const value = Number(String(input.value || "").trim());
        return Number.isFinite(value) && value > 0 ? Math.trunc(value) : fallback;
    }

    function isCjkToken(token) {
        return CJK_RE.test(token);
    }

    function joinDisplayTokens(tokens) {
        const tokenList = Array.from(tokens || []).filter((token) => token && String(token).trim());
        if (!tokenList.length) return "";
        const pieces = [];
        let previousWasCjk = false;
        for (const token of tokenList) {
            const current = String(token);
            const currentIsCjk = isCjkToken(current);
            if (!pieces.length) {
                pieces.push(current);
            } else if (previousWasCjk && currentIsCjk) {
                pieces.push(current);
            } else {
                pieces.push(` ${current}`);
            }
            previousWasCjk = currentIsCjk;
        }
        return pieces.join("");
    }

    function cleanText(value) {
        return String(value || "")
            .replace(ODD_SPACES_RE, " ")
            .replace(/ +/g, " ")
            .replace(/\s+([,\.!?:;])/g, "$1")
            .trim();
    }

    function countDisplayChars(value) {
        return Array.from(cleanText(value)).length;
    }

    function splitIntoTokens(text) {
        return String(text || "").match(TOKEN_RE) || [];
    }

    function formatTime(seconds) {
        const totalMilliseconds = Math.round(Math.max(0, Number(seconds) || 0) * 1000);
        const minutes = Math.floor(totalMilliseconds / 60000);
        const secs = Math.floor((totalMilliseconds % 60000) / 1000);
        const milliseconds = totalMilliseconds % 1000;
        return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}.${String(milliseconds).padStart(3, "0")}`;
    }

    function setStatus(message, tone = "neutral") {
        if (!statusBox) return;
        statusBox.textContent = message || "";
        statusBox.className = "ml-0 text-sm font-semibold sm:ml-2";
        if (!message) return;
        if (tone === "error") {
            statusBox.classList.add("text-error");
            return;
        }
        if (tone === "success") {
            statusBox.classList.add("text-primary");
            return;
        }
        statusBox.classList.add("text-on-surface-variant");
    }

    function updateCounters() {
        if (segmentCount) {
            segmentCount.textContent = String(state.segments.length);
        }
    }

    function normalizeWords(words) {
        if (!Array.isArray(words)) return [];
        const normalized = [];
        for (const row of words) {
            if (!row || typeof row !== "object") continue;
            const word = String(row.word || "").trim();
            const start = Number(row.start);
            const end = Number(row.end);
            if (!word || !Number.isFinite(start) || !Number.isFinite(end) || end < start) continue;
            normalized.push({
                word,
                start: Number(start.toFixed(3)),
                end: Number(end.toFixed(3)),
            });
        }
        normalized.sort((left, right) => left.start - right.start);
        return normalized;
    }

    function makeSegmentFromWords(words) {
        const currentWords = (words || []).filter((word) => String(word.word || "").trim());
        if (!currentWords.length) {
            return { start: 0.0, end: 0.0, text: "", words: [] };
        }
        const text = joinDisplayTokens(currentWords.map((word) => word.word));
        return {
            start: Number((currentWords[0].start || 0).toFixed(3)),
            end: Number((currentWords.at(-1).end || 0).toFixed(3)),
            text,
            words: currentWords,
        };
    }

    function normalizeSegments(segments) {
        const normalized = Array.isArray(segments) ? clone(segments) : [];
        normalized.sort((left, right) => Number(left.start || 0) - Number(right.start || 0));
        for (let index = 0; index < normalized.length; index += 1) {
            const segment = normalized[index];
            segment.start = Number(Math.max(0, Number(segment.start || 0)).toFixed(3));
            segment.end = Number(Math.max(segment.start, Number(segment.end ?? segment.start)).toFixed(3));
            segment.words = normalizeWords(segment.words);
            if (!segment.words.length) {
                const fallbackText = cleanText(segment.text);
                if (fallbackText) {
                    segment.words = [{ word: fallbackText, start: segment.start, end: segment.end }];
                }
            }
            segment.text = cleanText(segment.text) || joinDisplayTokens(segment.words.map((word) => word.word));
            if (index + 1 < normalized.length) {
                const nextStart = Number(normalized[index + 1].start || 0);
                if (segment.end > nextStart) {
                    segment.end = Number(nextStart.toFixed(3));
                    if (segment.end < segment.start) {
                        segment.end = segment.start;
                    }
                    if (segment.words.length) {
                        segment.words[segment.words.length - 1].end = segment.end;
                    }
                }
            }
        }
        return normalized;
    }

    function splitSegmentAt(segmentIndex, wordIndex) {
        const before = clone(state.segments);
        const segment = state.segments[segmentIndex];
        if (!segment || !Array.isArray(segment.words)) return;
        if (wordIndex <= 0 || wordIndex >= segment.words.length) return;

        const firstWords = clone(segment.words.slice(0, wordIndex));
        const secondWords = clone(segment.words.slice(wordIndex));
        if (!firstWords.length || !secondWords.length) return;

        const nextSegments = clone(state.segments);
        const firstSegment = makeSegmentFromWords(firstWords);
        const secondSegment = makeSegmentFromWords(secondWords);
        nextSegments.splice(segmentIndex, 1, firstSegment, secondSegment);
        commitSegments(before, nextSegments, t("subtitle.split_applied"), "success");
    }

    function mergeSegmentAt(segmentIndex) {
        const before = clone(state.segments);
        if (segmentIndex < 0 || segmentIndex >= state.segments.length - 1) return;

        const left = state.segments[segmentIndex];
        const right = state.segments[segmentIndex + 1];
        const mergedWords = clone([...(left?.words || []), ...(right?.words || [])]);
        if (!mergedWords.length) return;

        const nextSegments = clone(state.segments);
        nextSegments.splice(segmentIndex, 2, makeSegmentFromWords(mergedWords));
        commitSegments(before, nextSegments, t("subtitle.merge_applied"), "success");
    }

    async function loadJsonPatchModule() {
        return getJsonPatch();
    }

    async function pushHistory(before, after) {
        const jsonpatch = await loadJsonPatchModule();
        const patch = jsonpatch.compare(before, after);
        if (!patch.length) return;
        const inverse = patch.map((op) => {
            const oldValue = jsonpatch.getValueByPointer(before, op.path);
            if (op.op === "replace") {
                return { op: "replace", path: op.path, value: oldValue };
            }
            if (op.op === "add") {
                return { op: "remove", path: op.path };
            }
            if (op.op === "remove") {
                return { op: "add", path: op.path, value: oldValue };
            }
            return op;
        }).reverse();
        state.history.push(inverse);
    }

    function persistSession() {
        safeStorageSet(JSON.stringify({
            segments: state.segments,
            history: state.history,
        }));
    }

    async function commitSegments(before, nextSegments, statusMessage, tone = "neutral") {
        state.segments = normalizeSegments(nextSegments);
        await pushHistory(before, state.segments);
        persistSession();
        render();
        setStatus(statusMessage, tone);
    }

    async function undoLastChange() {
        if (!state.history.length) {
            setStatus(t("subtitle.undo_empty"), "neutral");
            return;
        }
        const inverse = state.history.pop();
        const jsonpatch = await loadJsonPatchModule();
        state.segments = normalizeSegments(jsonpatch.applyPatch(clone(state.segments), inverse).newDocument);
        persistSession();
        render();
        setStatus(t("subtitle.undo_applied"), "success");
    }

    function renderWordButtons(segmentIndex, segment) {
        const wrap = document.createElement("div");
        wrap.className = "mt-2 flex flex-wrap gap-1.5";

        const words = Array.isArray(segment.words) ? segment.words : [];
        words.forEach((word, wordIndex) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "inline-flex items-center rounded border border-white/10 bg-surface-container-highest/80 px-2 py-0.5 text-sm font-semibold text-on-surface transition hover:border-primary/30 hover:bg-primary/10 active:scale-[0.99]";
            button.textContent = String(word.word || "");
            button.title = t("subtitle.split_after_word", { word: String(word.word || "") });
            button.addEventListener("click", () => splitSegmentAt(segmentIndex, wordIndex + 1));
            wrap.appendChild(button);
        });

        return wrap;
    }

    function renderSegmentTextRow(segment) {
        const row = document.createElement("div");
        row.className = "mt-1.5 flex items-start gap-3";

        const text = document.createElement("p");
        text.className = "min-w-0 flex-1 text-sm leading-relaxed text-on-surface";
        text.textContent = segment.text || "";

        const counter = document.createElement("span");
        counter.className = "shrink-0 whitespace-nowrap rounded-full border border-white/10 bg-surface-container-high px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.18em] tabular-nums text-on-surface-variant";
        counter.textContent = t("subtitle.char_count", { count: countDisplayChars(segment.text || "") });

        row.appendChild(text);
        row.appendChild(counter);
        return row;
    }

    function renderSegment(segment, index) {
        const card = document.createElement("article");
        card.className = "rounded-3xl border border-white/10 bg-surface-container-high/30 pb-2.5 p-4 shadow-[0_1px_0_rgba(255,255,255,0.03)_inset]";

        const header = document.createElement("div");
        header.className = "flex items-start justify-between gap-3";

        const meta = document.createElement("div");
        meta.className = "min-w-0";
        const indexLabel = document.createElement("p");
        indexLabel.className = "text-[10px] font-black uppercase tracking-[0.18em] text-primary";
        indexLabel.textContent = t("subtitle.segment_label", { index: index + 1 });
        const timing = document.createElement("p");
        timing.className = "mt-1 text-xs font-semibold text-on-surface-variant";
        timing.textContent = `${formatTime(segment.start)} - ${formatTime(segment.end)}`;
        meta.appendChild(indexLabel);
        meta.appendChild(timing);

        const mergeButton = document.createElement("button");
        mergeButton.type = "button";
        mergeButton.disabled = index >= state.segments.length - 1;
        mergeButton.className = "inline-flex shrink-0 items-center gap-2 rounded-full border border-white/10 bg-surface-container-high px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.18em] text-on-surface hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50";
        mergeButton.innerHTML = `<span class="material-symbols-outlined text-[16px]">merge</span><span>${t("subtitle.merge_with_next")}</span>`;
        mergeButton.addEventListener("click", () => mergeSegmentAt(index));

        header.appendChild(meta);
        header.appendChild(mergeButton);

        card.appendChild(header);
        card.appendChild(renderSegmentTextRow(segment));
        card.appendChild(renderWordButtons(index, segment));
        return card;
    }

    function renderEmptyState() {
        if (!segmentList) return;
        segmentList.innerHTML = "";
        const empty = document.createElement("div");
        empty.className = "rounded-2xl border border-white/10 bg-surface-container-high/30 p-4 text-sm text-on-surface-variant";
        empty.textContent = t("subtitle.no_segments");
        segmentList.appendChild(empty);
    }

    function render() {
        updateCounters();
        if (!segmentList) return;
        segmentList.innerHTML = "";
        if (!state.segments.length) {
            renderEmptyState();
            return;
        }
        for (const [index, segment] of state.segments.entries()) {
            segmentList.appendChild(renderSegment(segment, index));
        }
    }

    async function fetchJson(url, options = {}) {
        const response = await fetch(url, {
            credentials: "same-origin",
            ...options,
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            const detail = payload?.detail;
            throw new Error(typeof detail === "string" ? detail : t("subtitle.request_failed"));
        }
        return payload;
    }

    async function loadState() {
        const cached = safeStorageGet();
        if (cached) {
            try {
                const parsed = JSON.parse(cached);
                if (Array.isArray(parsed.segments)) {
                    state.segments = normalizeSegments(parsed.segments);
                    state.history = Array.isArray(parsed.history) ? parsed.history : [];
                    render();
                    setStatus(t("subtitle.state_restored"), "neutral");
                    return;
                }
            } catch (_error) {
                // Ignore corrupt session data and fall back to server state.
            }
        }

        setStatus(t("subtitle.loading"), "neutral");
        const payload = await fetchJson(jsonUrl);
        state.segments = normalizeSegments(payload.segments || []);
        state.history = [];
        persistSession();
        render();
        setStatus(t("subtitle.loaded"), "success");
    }

    async function processCurrentSegments() {
        const maxLineLength = parseNumberInput(maxLineLengthInput, DEFAULT_MAX_LINE_LENGTH);
        const maxLineLengthCjk = parseNumberInput(maxLineLengthCjkInput, DEFAULT_MAX_LINE_LENGTH_CJK);
        const confirmed = window.confirm(t("subtitle.confirm_reprocess"));
        if (!confirmed) {
            return;
        }
        setStatus(t("subtitle.processing"), "neutral");
        processButton.disabled = true;
        try {
            const payload = await fetchJson(processUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    max_line_length: maxLineLength,
                    max_line_length_cjk: maxLineLengthCjk,
                }),
            });
            state.segments = normalizeSegments(payload.segments || []);
            state.history = [];
            safeStorageRemove();
            persistSession();
            render();
            setStatus(t("subtitle.process_complete"), "success");
        } catch (error) {
            setStatus(error instanceof Error ? error.message : t("subtitle.request_failed"), "error");
        } finally {
            processButton.disabled = false;
        }
    }

    async function saveCurrentSegments() {
        const maxLineLength = parseNumberInput(maxLineLengthInput, DEFAULT_MAX_LINE_LENGTH);
        const maxLineLengthCjk = parseNumberInput(maxLineLengthCjkInput, DEFAULT_MAX_LINE_LENGTH_CJK);
        const confirmed = window.confirm(t("subtitle.confirm_replace", { kind: t("common.lyrics") }));
        if (!confirmed) {
            return;
        }
        setStatus(t("subtitle.saving"), "neutral");
        saveButton.disabled = true;
        try {
            const payload = await fetchJson(saveUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    segments: state.segments,
                    max_line_length: maxLineLength,
                    max_line_length_cjk: maxLineLengthCjk,
                }),
            });
            state.segments = normalizeSegments(payload.segments || state.segments);
            state.history = [];
            safeStorageRemove();
            persistSession();
            render();
            setStatus(t("subtitle.save_complete"), "success");
        } catch (error) {
            setStatus(error instanceof Error ? error.message : t("subtitle.request_failed"), "error");
        } finally {
            saveButton.disabled = false;
        }
    }

    function wireButtons() {
        if (undoButton) {
            undoButton.addEventListener("click", () => {
                undoLastChange().catch((error) => {
                    setStatus(error instanceof Error ? error.message : t("subtitle.request_failed"), "error");
                });
            });
        }
        if (processButton) {
            processButton.addEventListener("click", () => {
                processCurrentSegments();
            });
        }
        if (saveButton) {
            saveButton.addEventListener("click", () => {
                saveCurrentSegments();
            });
        }
    }

    window.addEventListener("beforeunload", () => {
        persistSession();
    });

    document.addEventListener("keydown", (event) => {
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
            event.preventDefault();
            undoLastChange();
        }
    });

    wireButtons();
    render();
    loadState().catch((error) => {
        setStatus(error instanceof Error ? error.message : t("subtitle.request_failed"), "error");
    });
})();
