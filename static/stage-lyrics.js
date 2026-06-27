/**
 * Stage lyrics renderer and browser-local customization.
 *
 * The stage page owns playback and websocket state. This controller owns only
 * lyric cue normalization, fullscreen overlay rendering, and local appearance
 * settings so the already-large stage script stays manageable.
 */
class StageLyricsController {
  static STORAGE_KEY = "karaoke_stage_lyrics_settings_v1";
  static GENERIC_FONT_FAMILIES = new Set([
    "serif",
    "sans-serif",
    "monospace",
    "cursive",
    "fantasy",
    "system-ui",
    "ui-serif",
    "ui-sans-serif",
    "ui-monospace",
    "ui-rounded",
    "math",
    "emoji",
    "fangsong",
  ]);

  static LOCAL_FONT_FAMILIES = new Set([
    "Noto Sans SC",
    "ZCOOL QingKe HuangYou",
  ]);

  static FONT_PRESETS = {
    karaoke_cjk: {
      labelKey: "stage.lyrics_font_karaoke",
      value: '"ZCOOL QingKe HuangYou", "Noto Sans SC", "Noto Sans CJK SC", "Microsoft YaHei", "PingFang SC", sans-serif',
    },
    readable_cjk: {
      labelKey: "stage.lyrics_font_sans_serif",
      value: '"Noto Sans SC", "Noto Sans CJK SC", "Microsoft YaHei", "PingFang SC", sans-serif',
    },
    system_cjk: {
      labelKey: "stage.lyrics_font_system",
      value: '"Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif',
    },
    serif_cjk: {
      labelKey: "stage.lyrics_font_serif",
      value: '"Noto Serif SC", "Noto Sans SC", "Noto Sans CJK SC", "Microsoft YaHei", "PingFang SC", serif',
    },
    custom: {
      labelKey: "stage.lyrics_font_custom",
      value: "",
    },
  };

  static DEFAULT_SETTINGS = {
    fontPreset: "readable_cjk",
    customFontFamily: "",
    sizeVw: 4.5,
    lineWidthPct: 85,
    neighborLineScalePct: 60,
    neighborLineOpacityPct: 60,
    textColor: "#fff8df",
    activeColor: "#ffd84f",
    outlineColor: "#050505",
    outlineWidth: 5,
    previousLines: 1,
    nextLines: 2,
    lineBehavior: "rolling",
    animation: "fade",
    backgroundMediaEnabled: true,
    backgroundMediaPath: "",
    backgroundMediaOpacityPct: 100,
  };

  static BACKGROUND_IMAGE_EXTENSIONS = new Set([
    ".avif",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".webp",
  ]);

  static BACKGROUND_VIDEO_EXTENSIONS = new Set([
    ".avi",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".webm",
  ]);

  static SETTINGS_KEYS = new Set(Object.keys(StageLyricsController.DEFAULT_SETTINGS));

  constructor(options = {}) {
    this.overlay = options.overlay || null;
    this.lines = options.lines || null;
    this.panel = options.panel || null;
    this.button = options.button || null;
    this.closeButton = options.closeButton || null;
    this.resetButton = options.resetButton || null;
    this.exportButton = options.exportButton || null;
    this.applyButton = options.applyButton || null;
    this.importButton = options.importButton || null;
    this.importExport = options.importExport || null;
    this.fileInput = options.fileInput || null;
    this.status = options.status || null;
    this.backgroundLayer = options.backgroundLayer || null;
    this.backgroundImage = options.backgroundImage || null;
    this.backgroundVideo = options.backgroundVideo || null;
    this.inputs = options.inputs || {};
    this.isFullscreenActive = options.isFullscreenActive || (() => false);
    this.onPanelVisibilityChange = options.onPanelVisibilityChange || (() => {});
    this.t = options.t || ((key) => key);

    this.cues = [];
    this.enabled = true;
    this.activeCueIndex = null;
    this.activeWordIndex = null;
    this.visibleCueStart = null;
    this.visibleCueEnd = null;
    this.settingsPanelVisible = false;
    this.reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches || false;
    this.settings = this.loadSettings();
    this.appliedCustomFontFamily = String(this.settings.customFontFamily || "").trim();
    this.loadedFontFamilies = new Set();
    this.failedFontFamilies = new Set();
    this.pendingFontLoads = new Map();
    this.currentBackgroundUrl = "";
    this.currentBackgroundKind = "";
    this.backgroundLoadFailed = false;
    this.backgroundEligible = false;
    this.lineTransitionResetTimer = null;
    this.lineGhostCleanupTimer = null;

    this.backgroundImage?.addEventListener("error", () => this.handleBackgroundMediaError());
    this.backgroundVideo?.addEventListener("error", () => this.handleBackgroundMediaError());
    this.applySettings();
    this.syncSettingsUi();
    this.bindSettingsUi();
  }

  hasCues() {
    return this.cues.length > 0;
  }

  setEnabled(enabled) {
    this.enabled = Boolean(enabled);
    if (!this.enabled) {
      this.clear();
      return;
    }
    this.resetActiveState();
  }

  setCues(rawCues) {
    const normalizedCues = (Array.isArray(rawCues) ? rawCues : [])
      .map((cue) => this.normalizeCue(cue))
      .filter((cue) => cue !== null)
      .sort((a, b) => a.time - b.time);
    this.cues = this.insertCountdownCues(normalizedCues);
    this.resetActiveState();
    if (!this.cues.length) {
      this.clear();
    }
  }

  clear() {
    this.clearLineTransitionArtifacts();
    if (this.lines) {
      this.lines.innerHTML = "";
    }
    this.resetActiveState();
    this.setOverlayVisible(false);
  }

  clearCues() {
    this.cues = [];
    this.clear();
  }

  resetActiveState() {
    this.activeCueIndex = null;
    this.activeWordIndex = null;
    this.visibleCueStart = null;
    this.visibleCueEnd = null;
  }

  setOverlayVisible(visible) {
    if (!this.overlay) {
      return;
    }
    this.overlay.classList.toggle("hidden", !visible || !this.isFullscreenActive());
  }

  updateForTime(currentTime) {
    if (!this.enabled || !this.cues.length) {
      if (this.activeCueIndex !== null) {
        this.clear();
      }
      return;
    }

    this.currentTime = currentTime;
    const nextIndex = this.findActiveCueIndex(currentTime);
    const nextWordIndex = nextIndex !== null && nextIndex >= 0
      ? this.findActiveWordIndex(this.cues[nextIndex], currentTime)
      : null;

    const stateUnchanged = nextIndex === this.activeCueIndex && nextWordIndex === this.activeWordIndex;
    if (stateUnchanged && this.settings.animation !== "crop") {
      return;
    }

    const needsWindowRender = this.shouldRenderWindowForCue(nextIndex);
    this.activeCueIndex = nextIndex;
    this.activeWordIndex = nextWordIndex;

    if (needsWindowRender) {
      this.renderWindow(currentTime);
    } else {
      this.updateRenderedWords(currentTime);
    }
  }

  normalizeCue(rawCue) {
    if (!rawCue || typeof rawCue !== "object") {
      return null;
    }
    const rawTime = Number(rawCue.time);
    if (!Number.isFinite(rawTime)) {
      return null;
    }
    const text = typeof rawCue.text === "string" ? rawCue.text.trim() : "";
    if (!text) {
      return null;
    }

    const rawEnd = Number(rawCue.end);
    const end = Number.isFinite(rawEnd) && rawEnd >= rawTime ? Math.max(0, rawEnd) : null;
    const rawWords = Array.isArray(rawCue.words) ? rawCue.words : [];
    const words = rawWords
      .map((rawWord) => {
        if (!rawWord || typeof rawWord !== "object") {
          return null;
        }
        const word = typeof rawWord.word === "string" ? rawWord.word.trim() : "";
        const start = Number(rawWord.start);
        const end = Number(rawWord.end);
        if (!word || !Number.isFinite(start) || !Number.isFinite(end) || end < start) {
          return null;
        }
        return {
          word,
          start: Math.max(0, start),
          end: Math.max(0, end),
        };
      })
      .filter((word) => word !== null)
      .sort((a, b) => a.start - b.start);

    const countdown = this.isCountdownCueShape({
      countdown: rawCue.countdown === true,
      text,
      words,
      end,
      time: rawTime,
    });
    const normalizedWords = countdown
      ? words.map((word) => ({
          word: ".",
          start: word.start,
          end: word.end,
        }))
      : words;

    return {
      time: Math.max(0, rawTime),
      end,
      text,
      words: words.length === rawWords.length ? normalizedWords : [],
      countdown,
    };
  }

  findActiveCueIndex(currentTime) {
    if (!this.cues.length) {
      return null;
    }
    if (currentTime < this.cues[0].time) {
      return -1;
    }

    let left = 0;
    let right = this.cues.length - 1;
    let best = 0;
    while (left <= right) {
      const mid = Math.floor((left + right) / 2);
      if (this.cues[mid].time <= currentTime) {
        best = mid;
        left = mid + 1;
      } else {
        right = mid - 1;
      }
    }
    return best;
  }

  findActiveWordIndex(cue, currentTime) {
    if (!cue?.words?.length) {
      return null;
    }

    let activeIndex = -1;
    for (let index = 0; index < cue.words.length; index += 1) {
      if (cue.words[index].start > currentTime) {
        break;
      }
      activeIndex = index;
    }
    return activeIndex;
  }

  isCurrentCueRendered(activeIndex) {
    if (activeIndex === -1) {
      return this.visibleCueStart === 0;
    }
    return typeof activeIndex === "number"
      && this.visibleCueStart !== null
      && this.visibleCueEnd !== null
      && activeIndex >= this.visibleCueStart
      && activeIndex < this.visibleCueEnd;
  }

  shouldRenderWindowForCue(nextIndex) {
    if (!this.isCurrentCueRendered(nextIndex)) {
      return true;
    }
    return this.settings.lineBehavior !== "fixed_group" && nextIndex !== this.activeCueIndex;
  }

  getWindowBounds() {
    if (this.settings.lineBehavior === "fixed_group") {
      return this.getFixedGroupWindowBounds();
    }
    if (this.activeCueIndex === -1) {
      return {
        start: 0,
        end: Math.min(this.cues.length, 1 + this.settings.nextLines),
      };
    }
    if (typeof this.activeCueIndex !== "number") {
      return { start: 0, end: 0 };
    }
    return {
      start: Math.max(0, this.activeCueIndex - this.settings.previousLines),
      end: Math.min(this.cues.length, this.activeCueIndex + this.settings.nextLines + 1),
    };
  }

  getFixedGroupWindowBounds() {
    const visibleCount = Math.max(1, 1 + this.settings.nextLines);
    if (this.activeCueIndex === -1) {
      return {
        start: 0,
        end: Math.min(this.cues.length, visibleCount),
      };
    }
    if (typeof this.activeCueIndex !== "number") {
      return { start: 0, end: 0 };
    }

    const start = Math.floor(this.activeCueIndex / visibleCount) * visibleCount;
    return {
      start,
      end: Math.min(this.cues.length, start + visibleCount),
    };
  }

  renderWindow(currentTime = this.currentTime ?? 0) {
    if (!this.lines || !this.enabled || !this.cues.length) {
      this.clear();
      return;
    }

    const { start, end } = this.getWindowBounds();
    const transitionPlan = this.buildLineTransitionPlan(start, end);
    this.visibleCueStart = start;
    this.visibleCueEnd = end;
    this.lines.innerHTML = "";

    for (let cueIndex = start; cueIndex < end; cueIndex += 1) {
      this.lines.appendChild(this.renderLine(this.cues[cueIndex], cueIndex));
    }

    this.updateRenderedWords(currentTime);
    this.applyLineTransitionPlan(transitionPlan);
    this.setOverlayVisible(end > start);
  }

  buildLineTransitionPlan(nextStart, nextEnd) {
    if (!this.shouldAnimateRollingWindowTransition(nextStart, nextEnd)) {
      this.clearLineTransitionArtifacts();
      return null;
    }

    const renderedLines = Array.from(this.lines?.querySelectorAll(".stage-lyric-line") || []);
    if (!renderedLines.length) {
      this.clearLineTransitionArtifacts();
      return null;
    }

    const positions = new Map();
    const ghosts = [];
    const containerRect = this.lines.getBoundingClientRect();
    renderedLines.forEach((line) => {
      const cueIndex = Number(line.dataset.cueIndex);
      const rect = line.getBoundingClientRect();
      positions.set(cueIndex, rect.top);
      if (cueIndex < nextStart || cueIndex >= nextEnd) {
        ghosts.push({
          cueIndex,
          node: line.cloneNode(true),
          top: rect.top - containerRect.top,
          height: rect.height,
        });
      }
    });

    const direction = nextStart > this.visibleCueStart ? 1 : -1;
    const step = this.getLineTransitionStep(renderedLines);
    return {
      direction,
      positions,
      ghosts,
      step,
    };
  }

  shouldAnimateRollingWindowTransition(nextStart, nextEnd) {
    if (this.reducedMotion || this.settings.lineBehavior !== "rolling_scroll") {
      return false;
    }
    if (typeof this.visibleCueStart !== "number" || typeof this.visibleCueEnd !== "number") {
      return false;
    }
    if (nextStart === this.visibleCueStart && nextEnd === this.visibleCueEnd) {
      return false;
    }
    return Math.abs(nextStart - this.visibleCueStart) === 1
      && Math.abs(nextEnd - this.visibleCueEnd) === 1;
  }

  getLineTransitionStep(renderedLines) {
    const tops = renderedLines
      .map((line) => line.getBoundingClientRect().top)
      .sort((a, b) => a - b);
    if (tops.length >= 2) {
      const deltas = [];
      for (let index = 1; index < tops.length; index += 1) {
        const delta = tops[index] - tops[index - 1];
        if (delta > 0) {
          deltas.push(delta);
        }
      }
      if (deltas.length) {
        return deltas.reduce((sum, delta) => sum + delta, 0) / deltas.length;
      }
    }
    return 48;
  }

  applyLineTransitionPlan(plan) {
    this.clearLineTransitionArtifacts();
    if (!plan || !this.lines) {
      return;
    }

    const lines = Array.from(this.lines.querySelectorAll(".stage-lyric-line"));
    lines.forEach((line) => {
      const cueIndex = Number(line.dataset.cueIndex);
      const rect = line.getBoundingClientRect();
      const previousTop = plan.positions.get(cueIndex);
      const offsetY = Number.isFinite(previousTop)
        ? previousTop - rect.top
        : plan.direction > 0
          ? plan.step
          : -plan.step;
      line.style.setProperty("--stage-lyric-line-offset-y", `${offsetY}px`);
    });

    this.renderGhostLines(plan);
    void this.lines.offsetHeight;

    lines.forEach((line) => {
      line.classList.add("stage-lyric-line--transitioning");
      line.style.setProperty("--stage-lyric-line-offset-y", "0px");
    });

    window.requestAnimationFrame(() => {
      this.lineTransitionResetTimer = window.setTimeout(() => {
        this.lines?.querySelectorAll(".stage-lyric-line--transitioning").forEach((line) => {
          line.classList.remove("stage-lyric-line--transitioning");
          line.style.removeProperty("--stage-lyric-line-offset-y");
        });
        this.lineTransitionResetTimer = null;
      }, 960);
    });
  }

  renderGhostLines(plan) {
    if (!this.lines || !plan?.ghosts?.length) {
      return;
    }

    plan.ghosts.forEach((ghost) => {
      const node = ghost.node;
      node.classList.add("stage-lyric-line--ghost", "stage-lyric-line--transitioning");
      node.classList.remove("stage-lyric-line--current");
      node.style.top = `${ghost.top}px`;
      node.style.height = `${ghost.height}px`;
      node.style.setProperty("--stage-lyric-line-offset-y", "0px");
      this.lines.appendChild(node);
      void node.offsetHeight;
      node.style.setProperty(
        "--stage-lyric-line-offset-y",
        `${plan.direction > 0 ? -plan.step : plan.step}px`,
      );
      node.style.opacity = "0";
    });

    this.lineGhostCleanupTimer = window.setTimeout(() => {
      this.lines?.querySelectorAll(".stage-lyric-line--ghost").forEach((ghostNode) => ghostNode.remove());
      this.lineGhostCleanupTimer = null;
    }, 960);
  }

  clearLineTransitionArtifacts() {
    if (this.lineTransitionResetTimer !== null) {
      window.clearTimeout(this.lineTransitionResetTimer);
      this.lineTransitionResetTimer = null;
    }
    if (this.lineGhostCleanupTimer !== null) {
      window.clearTimeout(this.lineGhostCleanupTimer);
      this.lineGhostCleanupTimer = null;
    }
    this.lines?.querySelectorAll(".stage-lyric-line--transitioning").forEach((line) => {
      line.classList.remove("stage-lyric-line--transitioning");
      line.style.removeProperty("--stage-lyric-line-offset-y");
    });
    this.lines?.querySelectorAll(".stage-lyric-line--ghost").forEach((ghostNode) => ghostNode.remove());
  }

  renderLine(cue, cueIndex) {
    const line = document.createElement("p");
    const isCurrent = cueIndex === this.activeCueIndex;
    const hasAlignedWords = cue.words.length > 0;
    const isCountdown = Boolean(cue.countdown);
    line.className = [
      "stage-lyric-line",
      isCurrent ? "stage-lyric-line--current" : "",
      hasAlignedWords ? "stage-lyric-line--aligned" : "",
      isCountdown ? "stage-lyric-line--countdown" : "",
    ].filter(Boolean).join(" ");
    line.dataset.cueIndex = String(cueIndex);
    line.dataset.text = cue.text;
    line.dataset.aligned = hasAlignedWords ? "true" : "false";
    line.dataset.countdown = isCountdown ? "true" : "false";

    if (!hasAlignedWords) {
      line.textContent = cue.text;
      return line;
    }

    cue.words.forEach((word, wordIndex) => {
      if (wordIndex > 0 && !isCountdown) {
        line.appendChild(document.createTextNode(" "));
      }
      const span = document.createElement("span");
      span.className = "stage-lyric-word";
      span.dataset.wordIndex = String(wordIndex);
      span.dataset.word = word.word;
      span.textContent = word.word;
      line.appendChild(span);
    });
    return line;
  }

  updateRenderedWords(currentTime = this.currentTime ?? 0) {
    if (!this.lines) {
      return;
    }

    const lines = this.lines.querySelectorAll(".stage-lyric-line");
    lines.forEach((line) => {
      const cueIndex = Number(line.dataset.cueIndex);
      const isCurrent = cueIndex === this.activeCueIndex;
      const isPlayed = typeof this.activeCueIndex === "number" && this.activeCueIndex >= 0 && cueIndex < this.activeCueIndex;
      const hasAlignedWords = line.dataset.aligned === "true";
      const isCountdown = line.dataset.countdown === "true";
      line.classList.toggle("stage-lyric-line--current", isCurrent);
      line.classList.toggle("stage-lyric-line--played", isPlayed);

      if (!hasAlignedWords) {
        return;
      }

      const shouldSlideWords = isCurrent && !this.reducedMotion && this.settings.animation === "slide" && !isCountdown;
      const shouldCropWords = isCurrent && !this.reducedMotion && this.settings.animation === "crop" && !isCountdown;
      line.classList.toggle("stage-lyric-line--word-slide", shouldSlideWords);
      line.classList.toggle("stage-lyric-line--word-crop", shouldCropWords);
      line.querySelectorAll(".stage-lyric-word").forEach((wordNode) => {
        const wordIndex = Number(wordNode.dataset.wordIndex);
        const isActiveWord = isCurrent && wordIndex === this.activeWordIndex;
        const isPlayedWord = isPlayed || (isCurrent && wordIndex <= this.activeWordIndex);
        if (shouldCropWords) {
          const progress = wordIndex < this.activeWordIndex
            ? 1
            : isActiveWord
              ? this.getWordProgress(cueIndex, wordIndex, currentTime)
              : 0;
          wordNode.style.setProperty("--stage-word-progress", String(Math.max(0, Math.min(1, progress))));
          wordNode.classList.toggle("stage-lyric-word--highlighted", progress >= 1);
          wordNode.classList.toggle("stage-lyric-word--active", isActiveWord);
          return;
        }

        wordNode.style.removeProperty("--stage-word-progress");
        wordNode.classList.toggle("stage-lyric-word--highlighted", isPlayedWord);
        wordNode.classList.toggle("stage-lyric-word--active", isActiveWord);
      });
    });
  }

  getWordProgress(cueIndex, wordIndex, currentTime) {
    const cue = this.cues[cueIndex];
    const word = cue?.words?.[wordIndex];
    if (!word) {
      return 0;
    }
    if (currentTime <= word.start) {
      return 0;
    }
    if (currentTime >= word.end) {
      return 1;
    }
    const duration = word.end - word.start;
    if (duration <= 0) {
      return 1;
    }
    return (currentTime - word.start) / duration;
  }

  insertCountdownCues(cues) {
    const expanded = [];
    let previousBoundary = 0;

    cues.forEach((cue) => {
      if (!cue) {
        return;
      }

      const cueStart = Number(cue.time);
      const cueEnd = Number.isFinite(cue.end) && cue.end !== null ? Number(cue.end) : cueStart;
      if (!cue.countdown && Number.isFinite(cueStart) && cueStart - previousBoundary > 4) {
        expanded.push(this.makeCountdownCue(cueStart));
      }

      expanded.push(cue);
      previousBoundary = Math.max(previousBoundary, Number.isFinite(cueEnd) ? cueEnd : cueStart);
    });

    return expanded;
  }

  makeCountdownCue(time) {
    const end = this.roundTime(time);
    const start = this.roundTime(Math.max(0, end - 4));
    return {
      time: start,
      end,
      text: "....",
      countdown: true,
      words: Array.from({ length: 4 }, (_, index) => ({
        word: ".",
        start: this.roundTime(start + index),
        end: this.roundTime(start + index + 1),
      })),
    };
  }

  roundTime(value) {
    return Math.round(Number(value) * 1000) / 1000;
  }

  isCountdownCueShape(cue) {
    if (cue?.countdown === true) {
      return true;
    }
    if (cue?.text !== "...." || !Array.isArray(cue?.words) || cue.words.length !== 4) {
      return false;
    }
    if (typeof cue.end !== "number" || !Number.isFinite(cue.end) || cue.end <= cue.time) {
      return false;
    }
    return cue.words.every((word) => typeof word?.word === "string" && /^\.+$/.test(word.word.trim()));
  }

  loadSettings() {
    try {
      const stored = window.localStorage?.getItem(StageLyricsController.STORAGE_KEY);
      if (!stored) {
        return { ...StageLyricsController.DEFAULT_SETTINGS };
      }
      return this.normalizeSettings({
        ...StageLyricsController.DEFAULT_SETTINGS,
        ...JSON.parse(stored),
      });
    } catch (_) {
      return { ...StageLyricsController.DEFAULT_SETTINGS };
    }
  }

  normalizeSettings(settings) {
    const fontPreset = Object.prototype.hasOwnProperty.call(StageLyricsController.FONT_PRESETS, settings.fontPreset)
      ? settings.fontPreset
      : StageLyricsController.DEFAULT_SETTINGS.fontPreset;
    return {
      fontPreset,
      customFontFamily: String(settings.customFontFamily || "").slice(0, 220),
      sizeVw: this.clampNumber(settings.sizeVw, 3.2, 8.8, StageLyricsController.DEFAULT_SETTINGS.sizeVw),
      lineWidthPct: Math.round(this.clampNumber(settings.lineWidthPct, 60, 100, StageLyricsController.DEFAULT_SETTINGS.lineWidthPct)),
      neighborLineScalePct: Math.round(this.clampNumber(settings.neighborLineScalePct, 30, 100, StageLyricsController.DEFAULT_SETTINGS.neighborLineScalePct)),
      neighborLineOpacityPct: Math.round(this.clampNumber(settings.neighborLineOpacityPct, 10, 100, StageLyricsController.DEFAULT_SETTINGS.neighborLineOpacityPct)),
      textColor: this.normalizeColor(settings.textColor, StageLyricsController.DEFAULT_SETTINGS.textColor),
      activeColor: this.normalizeColor(settings.activeColor, StageLyricsController.DEFAULT_SETTINGS.activeColor),
      outlineColor: this.normalizeColor(settings.outlineColor, StageLyricsController.DEFAULT_SETTINGS.outlineColor),
      outlineWidth: Math.round(this.clampNumber(settings.outlineWidth, 2, 14, StageLyricsController.DEFAULT_SETTINGS.outlineWidth)),
      previousLines: Math.round(this.clampNumber(settings.previousLines, 0, 3, StageLyricsController.DEFAULT_SETTINGS.previousLines)),
      nextLines: Math.round(this.clampNumber(settings.nextLines, 0, 3, StageLyricsController.DEFAULT_SETTINGS.nextLines)),
      lineBehavior: ["rolling", "rolling_scroll", "fixed_group"].includes(settings.lineBehavior)
        ? settings.lineBehavior
        : StageLyricsController.DEFAULT_SETTINGS.lineBehavior,
      animation: ["slide", "crop", "fade", "none"].includes(settings.animation)
        ? settings.animation
        : StageLyricsController.DEFAULT_SETTINGS.animation,
      backgroundMediaEnabled: settings.backgroundMediaEnabled !== false,
      backgroundMediaPath: this.normalizeBackgroundMediaPath(settings.backgroundMediaPath),
      backgroundMediaOpacityPct: Math.round(this.clampNumber(settings.backgroundMediaOpacityPct, 10, 100, StageLyricsController.DEFAULT_SETTINGS.backgroundMediaOpacityPct)),
    };
  }

  clampNumber(value, min, max, fallback) {
    const number = Number(value);
    if (!Number.isFinite(number)) {
      return fallback;
    }
    return Math.max(min, Math.min(max, number));
  }

  normalizeColor(value, fallback) {
    const color = String(value || "").trim();
    return /^#[0-9a-f]{6}$/i.test(color) ? color : fallback;
  }

  normalizeBackgroundMediaPath(value) {
    let path = String(value || "").trim();
    if (!path) {
      return "";
    }
    const basePath = String(window.KaraokeURLs?.basePath || "").replace(/\/+$/, "");
    if (basePath && path.startsWith(`${basePath}/media/`)) {
      path = path.slice(basePath.length);
    }
    if (/^(https?:|wss?:|ws:|\/\/)/i.test(path)) {
      return "";
    }
    if (!path.startsWith("/media/")) {
      return "";
    }
    try {
      const url = new URL(path, window.location.origin);
      if (url.origin !== window.location.origin || !url.pathname.startsWith("/media/")) {
        return "";
      }
      path = `${url.pathname}${url.search}`;
    } catch (_) {
      return "";
    }
    if (path.includes("..") || path.includes("\\") || path.length > 500) {
      return "";
    }
    return path;
  }

  saveSettings() {
    try {
      window.localStorage?.setItem(StageLyricsController.STORAGE_KEY, JSON.stringify(this.settings));
    } catch (_) {
      this.setStatus(this.t("stage.lyrics_settings_save_failed"));
    }
  }

  getSettingsSnapshot() {
    return this.normalizeSettings({ ...this.settings });
  }

  applySettingsObject(rawSettings, options = {}) {
    if (!this.isPlainObject(rawSettings)) {
      return false;
    }

    const nextSettings = this.normalizeSettings({
      ...StageLyricsController.DEFAULT_SETTINGS,
      ...rawSettings,
    });
    this.settings = nextSettings;

    if (options.persist !== false) {
      this.persistSettings();
    } else {
      this.applySettings();
      this.syncSettingsUi();
    }
    return true;
  }

  applySettings() {
    if (!this.overlay) {
      return;
    }
    const preset = StageLyricsController.FONT_PRESETS[this.settings.fontPreset] || StageLyricsController.FONT_PRESETS.karaoke_cjk;
    const customFontFamily = this.settings.fontPreset === "custom" ? this.appliedCustomFontFamily : "";
    const fontFamily = customFontFamily
      ? this.normalizeCustomFontStack(customFontFamily)
      : (preset.value || StageLyricsController.FONT_PRESETS.readable_cjk.value);

    this.overlay.style.setProperty("--stage-lyrics-font-family", fontFamily);
    this.overlay.style.setProperty("--stage-lyrics-size", `clamp(2.4rem, ${this.settings.sizeVw}vw, 6.8rem)`);
    this.overlay.style.setProperty("--stage-lyrics-lines-width", `${this.settings.lineWidthPct}vw`);
    this.overlay.style.setProperty("--stage-lyrics-line-scale", `${this.settings.neighborLineScalePct / 100}`);
    this.overlay.style.setProperty("--stage-lyrics-line-opacity", `${this.settings.neighborLineOpacityPct / 100}`);
    this.overlay.style.setProperty("--stage-lyrics-text-color", this.settings.textColor);
    this.overlay.style.setProperty("--stage-lyrics-active-color", this.settings.activeColor);
    this.overlay.style.setProperty("--stage-lyrics-outline-color", this.settings.outlineColor);
    this.overlay.style.setProperty("--stage-lyrics-outline-width", `${this.settings.outlineWidth}px`);
    this.overlay.dataset.animation = this.reducedMotion ? "none" : this.settings.animation;
    this.applyBackgroundSettings();
    void this.ensureFontStackLoaded(fontFamily);
    this.renderWindow();
  }

  applyBackgroundSettings() {
    if (!this.backgroundLayer) {
      return;
    }

    this.backgroundLayer.style.setProperty("--stage-lyrics-background-opacity", `${this.settings.backgroundMediaOpacityPct / 100}`);
    if (!this.backgroundEligible || !this.settings.backgroundMediaEnabled) {
      this.clearBackgroundMedia();
      return;
    }
    const path = this.normalizeBackgroundMediaPath(this.settings.backgroundMediaPath);
    const kind = this.getBackgroundMediaKind(path);
    const url = path ? window.KaraokeURLs?.appUrl?.(path) || path : "";

    if (!url || !kind) {
      this.clearBackgroundMedia();
      return;
    }

    if (url !== this.currentBackgroundUrl || kind !== this.currentBackgroundKind) {
      this.backgroundLoadFailed = false;
      this.currentBackgroundUrl = url;
      this.currentBackgroundKind = kind;
      if (kind === "video") {
        this.showBackgroundVideo(url);
      } else {
        this.showBackgroundImage(url);
      }
    }

    this.syncBackgroundVisibility();
  }

  getBackgroundMediaKind(path) {
    const extension = this.getPathExtension(path);
    if (StageLyricsController.BACKGROUND_VIDEO_EXTENSIONS.has(extension)) {
      return "video";
    }
    if (StageLyricsController.BACKGROUND_IMAGE_EXTENSIONS.has(extension)) {
      return "image";
    }
    return "";
  }

  getPathExtension(path) {
    try {
      const url = new URL(path, window.location.origin);
      const pathname = url.pathname.toLowerCase();
      return pathname.includes(".") ? `.${pathname.split(".").pop()}` : "";
    } catch (_) {
      const normalized = String(path || "").split("?")[0].toLowerCase();
      return normalized.includes(".") ? `.${normalized.split(".").pop()}` : "";
    }
  }

  showBackgroundVideo(url) {
    if (!this.backgroundVideo) {
      this.clearBackgroundMedia();
      return;
    }
    this.hideBackgroundImage();
    this.backgroundVideo.src = url;
    this.backgroundVideo.load();
    this.backgroundVideo.classList.remove("hidden");
    this.backgroundVideo.play().catch(() => {
      // Muted inline background videos should autoplay; if a browser blocks it,
      // leave the source ready and let the next user gesture/fullscreen retry.
    });
  }

  showBackgroundImage(url) {
    if (!this.backgroundImage) {
      this.clearBackgroundMedia();
      return;
    }
    this.hideBackgroundVideo();
    this.backgroundImage.src = url;
    this.backgroundImage.classList.remove("hidden");
  }

  hideBackgroundImage() {
    if (!this.backgroundImage) {
      return;
    }
    this.backgroundImage.classList.add("hidden");
    this.backgroundImage.removeAttribute("src");
  }

  hideBackgroundVideo() {
    if (!this.backgroundVideo) {
      return;
    }
    this.backgroundVideo.pause();
    this.backgroundVideo.classList.add("hidden");
    this.backgroundVideo.removeAttribute("src");
    this.backgroundVideo.load();
  }

  clearBackgroundMedia() {
    this.currentBackgroundUrl = "";
    this.currentBackgroundKind = "";
    this.backgroundLoadFailed = false;
    this.hideBackgroundImage();
    this.hideBackgroundVideo();
    this.syncBackgroundVisibility();
  }

  setBackgroundEligible(eligible) {
    this.backgroundEligible = Boolean(eligible);
    this.applyBackgroundSettings();
  }

  handleBackgroundMediaError() {
    this.backgroundLoadFailed = true;
    this.syncBackgroundVisibility();
  }

  syncBackgroundVisibility() {
    if (!this.backgroundLayer) {
      return;
    }
    const visible = Boolean(this.currentBackgroundUrl && this.currentBackgroundKind && !this.backgroundLoadFailed);
    this.backgroundLayer.classList.toggle("is-visible", visible);
  }

  async ensureFontStackLoaded(fontStack) {
    const primaryFamily = this.getPrimaryFontFamily(fontStack);
    if (!primaryFamily || this.isGenericFontFamily(primaryFamily) || this.isLocalFontFamily(primaryFamily)) {
      return;
    }
    await this.loadGoogleFont(primaryFamily);
  }

  getPrimaryFontFamily(fontStack) {
    const families = this.splitFontFamilyStack(fontStack);
    return families.find((family) => !this.isGenericFontFamily(family)) || "";
  }

  isLocalFontFamily(fontFamily) {
    return StageLyricsController.LOCAL_FONT_FAMILIES.has(String(fontFamily || "").trim());
  }

  async loadGoogleFont(fontFamily) {
    const normalized = String(fontFamily || "").trim();
    if (
      !normalized
      || this.loadedFontFamilies.has(normalized)
      || this.failedFontFamilies.has(normalized)
      || this.pendingFontLoads.has(normalized)
    ) {
      return this.pendingFontLoads.get(normalized) || null;
    }

    const promise = new Promise((resolve) => {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(normalized).replace(/%20/g, "+")}&display=swap`;
      link.crossOrigin = "anonymous";
      link.onload = () => {
        this.loadedFontFamilies.add(normalized);
        this.pendingFontLoads.delete(normalized);
        resolve();
      };
      link.onerror = () => {
        this.failedFontFamilies.add(normalized);
        this.pendingFontLoads.delete(normalized);
        resolve();
      };
      document.head.appendChild(link);
    });

    this.pendingFontLoads.set(normalized, promise);
    return promise;
  }

  normalizeCustomFontStack(fontStack) {
    const stack = String(fontStack || "").trim();
    if (!stack) {
      return "";
    }
    return this.splitFontFamilyStack(stack).some((family) => this.isGenericFontFamily(family))
      ? stack
      : `${stack}, sans-serif`;
  }

  splitFontFamilyStack(fontStack) {
    const stack = String(fontStack || "").trim();
    if (!stack) {
      return [];
    }

    const families = [];
    let current = "";
    let quote = "";
    for (let index = 0; index < stack.length; index += 1) {
      const char = stack[index];
      if (quote) {
        if (char === quote) {
          quote = "";
        } else {
          current += char;
        }
        continue;
      }
      if (char === "'" || char === '"') {
        quote = char;
        continue;
      }
      if (char === ",") {
        const family = current.trim();
        if (family) {
          families.push(this.stripOuterQuotes(family));
        }
        current = "";
        continue;
      }
      current += char;
    }

    const lastFamily = current.trim();
    if (lastFamily) {
      families.push(this.stripOuterQuotes(lastFamily));
    }
    return families;
  }

  stripOuterQuotes(value) {
    const text = String(value || "").trim();
    if ((text.startsWith('"') && text.endsWith('"')) || (text.startsWith("'") && text.endsWith("'"))) {
      return text.slice(1, -1).trim();
    }
    return text;
  }

  isGenericFontFamily(fontFamily) {
    return StageLyricsController.GENERIC_FONT_FAMILIES.has(String(fontFamily || "").trim().toLowerCase());
  }

  bindSettingsUi() {
    if (!this.button || !this.panel) {
      return;
    }

    this.button.addEventListener("click", () => {
      this.setSettingsPanelVisible(!this.settingsPanelVisible);
    });
    this.closeButton?.addEventListener("click", () => this.setSettingsPanelVisible(false));
    this.resetButton?.addEventListener("click", () => {
      this.settings = { ...StageLyricsController.DEFAULT_SETTINGS };
      this.persistSettings();
      this.setStatus(this.t("stage.lyrics_settings_reset_done"));
    });
    this.exportButton?.addEventListener("click", () => {
      this.downloadSettings();
    });
    this.applyButton?.addEventListener("click", () => {
      this.applySettingsFromTextarea();
    });
    this.importButton?.addEventListener("click", () => {
      if (this.fileInput) {
        this.fileInput.value = "";
        this.fileInput.click();
        return;
      }
      this.applySettingsFromTextarea();
    });
    this.fileInput?.addEventListener("change", () => {
      void this.importSettingsFromFile(this.fileInput?.files?.[0] || null);
    });

    Object.entries(this.inputs).forEach(([name, input]) => {
      if (!input) {
        return;
      }
      input.addEventListener("input", () => {
        this.updateSettingFromInput(name, input);
        if (name !== "customFontFamily") {
          this.applySettings();
        }
        this.syncSettingsUi({ keepFocus: true });
      });
      input.addEventListener("change", () => {
        this.updateSettingFromInput(name, input);
        if (name !== "customFontFamily") {
          this.applySettings();
        }
        this.syncSettingsUi({ keepFocus: true });
      });
    });
  }

  persistSettings() {
    this.commitCustomFontFamily();
    this.failedFontFamilies.clear();
    this.saveSettings();
    this.applySettings();
    this.syncSettingsUi();
  }

  commitCustomFontFamily() {
    this.appliedCustomFontFamily = String(this.settings.customFontFamily || "").trim();
  }

  setSettingsPanelVisible(visible) {
    this.settingsPanelVisible = Boolean(visible);
    this.panel?.classList.toggle("hidden", !this.settingsPanelVisible);
    this.button?.setAttribute("aria-expanded", this.settingsPanelVisible ? "true" : "false");
    this.onPanelVisibilityChange(this.settingsPanelVisible);
  }

  updateSettingFromInput(name, input) {
    let value = input.value;
    if (input.type === "number" || input.type === "range") {
      value = Number(input.value);
    } else if (input.type === "checkbox") {
      value = input.checked;
    }
    const previousFontPreset = this.settings.fontPreset;
    this.settings = this.normalizeSettings({
      ...this.settings,
      [name]: value,
    });
    if (name === "fontPreset" && this.settings.fontPreset !== previousFontPreset) {
      this.failedFontFamilies.clear();
    }
  }

  syncSettingsUi(options = {}) {
    const activeElement = options.keepFocus ? document.activeElement : null;
    Object.entries(this.inputs).forEach(([name, input]) => {
      if (!input || activeElement === input) {
        return;
      }
      if (input.type === "checkbox") {
        input.checked = Boolean(this.settings[name]);
      } else {
        input.value = this.settings[name];
      }
    });
    if (this.inputs.customFontFamily) {
      this.inputs.customFontFamily.disabled = this.settings.fontPreset !== "custom";
    }
    if (this.inputs.sizeVwValue) {
      this.inputs.sizeVwValue.textContent = `${this.settings.sizeVw.toFixed(1)}vw`;
    }
    if (this.inputs.lineWidthPctValue) {
      this.inputs.lineWidthPctValue.textContent = `${this.settings.lineWidthPct}%`;
    }
    if (this.inputs.neighborLineScalePctValue) {
      this.inputs.neighborLineScalePctValue.textContent = `${this.settings.neighborLineScalePct}%`;
    }
    if (this.inputs.neighborLineOpacityPctValue) {
      this.inputs.neighborLineOpacityPctValue.textContent = `${this.settings.neighborLineOpacityPct}%`;
    }
    if (this.inputs.outlineWidthValue) {
      this.inputs.outlineWidthValue.textContent = `${this.settings.outlineWidth}px`;
    }
    if (this.inputs.backgroundMediaOpacityPctValue) {
      this.inputs.backgroundMediaOpacityPctValue.textContent = `${this.settings.backgroundMediaOpacityPct}%`;
    }
  }

  applySettingsFromTextarea() {
    if (!this.importExport) {
      return;
    }
    const raw = this.importExport.value.trim();
    if (!raw) {
      return;
    }
    try {
      const parsed = JSON.parse(raw);
      if (!this.isPlainObject(parsed) || !this.hasEditableSettingKey(parsed)) {
        throw new Error("Invalid settings payload");
      }
      this.settings = this.normalizeSettings({
        ...StageLyricsController.DEFAULT_SETTINGS,
        ...parsed,
      });
      this.persistSettings();
      this.setStatus(this.t("stage.lyrics_settings_applied"));
    } catch (_) {
      this.setStatus(this.t("stage.lyrics_settings_import_failed"));
    }
  }

  downloadSettings() {
    const payload = JSON.stringify(this.settings, null, 2);
    if (this.importExport) {
      this.importExport.value = payload;
    }

    try {
      const blob = new Blob([payload], { type: "application/json" });
      const objectUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = "karaoke-stage-lyrics-settings.json";
      link.rel = "noopener";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 0);
      this.setStatus(this.t("stage.lyrics_settings_downloaded"));
    } catch (_) {
      this.setStatus(this.t("stage.lyrics_settings_download_failed"));
    }
  }

  async importSettingsFromFile(file) {
    if (!file) {
      return;
    }
    try {
      const raw = await file.text();
      const parsed = JSON.parse(raw);
      if (!this.isPlainObject(parsed) || !this.hasEditableSettingKey(parsed)) {
        throw new Error("Invalid settings payload");
      }
      this.settings = this.normalizeSettings({
        ...StageLyricsController.DEFAULT_SETTINGS,
        ...parsed,
      });
      this.persistSettings();
      if (this.importExport) {
        this.importExport.value = JSON.stringify(this.settings, null, 2);
      }
      this.setStatus(this.t("stage.lyrics_settings_imported"));
    } catch (_) {
      this.setStatus(this.t("stage.lyrics_settings_import_failed"));
    } finally {
      if (this.fileInput) {
        this.fileInput.value = "";
      }
    }
  }

  setStatus(message) {
    if (!this.status) {
      return;
    }
    this.status.textContent = message || "";
  }

  isPlainObject(value) {
    return Boolean(value) && typeof value === "object" && !Array.isArray(value);
  }

  hasEditableSettingKey(value) {
    return Object.keys(value).some((key) => StageLyricsController.SETTINGS_KEYS.has(key));
  }
}

window.StageLyricsController = StageLyricsController;
