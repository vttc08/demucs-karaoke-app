/**
 * Stage lyrics renderer and browser-local customization.
 *
 * The stage page owns playback and websocket state. This controller owns only
 * lyric cue normalization, fullscreen overlay rendering, and local appearance
 * settings so the already-large stage script stays manageable.
 */
class StageLyricsController {
  static STORAGE_KEY = "karaoke_stage_lyrics_settings_v1";

  static FONT_PRESETS = {
    karaoke_cjk: {
      labelKey: "stage.lyrics_font_karaoke_cjk",
      value: '"ZCOOL KuaiLe", "Noto Sans SC", "Noto Sans CJK SC", "Microsoft YaHei", "PingFang SC", sans-serif',
    },
    readable_cjk: {
      labelKey: "stage.lyrics_font_readable_cjk",
      value: '"Noto Sans SC", "Noto Sans CJK SC", "Microsoft YaHei", "PingFang SC", sans-serif',
    },
    system_cjk: {
      labelKey: "stage.lyrics_font_system_cjk",
      value: '"Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif',
    },
    custom: {
      labelKey: "stage.lyrics_font_custom",
      value: "",
    },
  };

  static DEFAULT_SETTINGS = {
    fontPreset: "karaoke_cjk",
    customFontFamily: "",
    sizeVw: 5.6,
    textColor: "#fff8df",
    activeColor: "#ffd84f",
    outlineColor: "#050505",
    outlineWidth: 7,
    previousLines: 1,
    nextLines: 1,
    animation: "slide",
  };

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
    this.cues = (Array.isArray(rawCues) ? rawCues : [])
      .map((cue) => this.normalizeCue(cue))
      .filter((cue) => cue !== null)
      .sort((a, b) => a.time - b.time);
    this.resetActiveState();
    if (!this.cues.length) {
      this.clear();
    }
  }

  clear() {
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

    const nextIndex = this.findActiveCueIndex(currentTime);
    const nextWordIndex = nextIndex !== null && nextIndex >= 0
      ? this.findActiveWordIndex(this.cues[nextIndex], currentTime)
      : null;

    if (nextIndex === this.activeCueIndex && nextWordIndex === this.activeWordIndex) {
      return;
    }

    const needsWindowRender = nextIndex !== this.activeCueIndex || !this.isCurrentCueRendered(nextIndex);
    this.activeCueIndex = nextIndex;
    this.activeWordIndex = nextWordIndex;

    if (needsWindowRender) {
      this.renderWindow();
    } else {
      this.updateRenderedWords();
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

    return {
      time: Math.max(0, rawTime),
      text,
      words: words.length === rawWords.length ? words : [],
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

  getWindowBounds() {
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

  renderWindow() {
    if (!this.lines || !this.enabled || !this.cues.length) {
      this.clear();
      return;
    }

    const { start, end } = this.getWindowBounds();
    this.visibleCueStart = start;
    this.visibleCueEnd = end;
    this.lines.innerHTML = "";

    for (let cueIndex = start; cueIndex < end; cueIndex += 1) {
      this.lines.appendChild(this.renderLine(this.cues[cueIndex], cueIndex));
    }

    this.updateRenderedWords();
    this.setOverlayVisible(end > start);
  }

  renderLine(cue, cueIndex) {
    const line = document.createElement("p");
    const isCurrent = cueIndex === this.activeCueIndex;
    const hasAlignedWords = cue.words.length > 0;
    line.className = [
      "stage-lyric-line",
      isCurrent ? "stage-lyric-line--current" : "",
      hasAlignedWords ? "stage-lyric-line--aligned" : "",
    ].filter(Boolean).join(" ");
    line.dataset.cueIndex = String(cueIndex);
    line.dataset.aligned = hasAlignedWords ? "true" : "false";

    if (!hasAlignedWords) {
      line.textContent = cue.text;
      return line;
    }

    cue.words.forEach((word, wordIndex) => {
      if (wordIndex > 0) {
        line.appendChild(document.createTextNode(" "));
      }
      const span = document.createElement("span");
      span.className = "stage-lyric-word";
      span.dataset.wordIndex = String(wordIndex);
      span.textContent = word.word;
      line.appendChild(span);
    });
    return line;
  }

  updateRenderedWords() {
    if (!this.lines) {
      return;
    }

    const lines = this.lines.querySelectorAll(".stage-lyric-line");
    lines.forEach((line) => {
      const cueIndex = Number(line.dataset.cueIndex);
      const isCurrent = cueIndex === this.activeCueIndex;
      const hasAlignedWords = line.dataset.aligned === "true";
      line.classList.toggle("stage-lyric-line--current", isCurrent);

      if (!hasAlignedWords) {
        return;
      }

      const shouldAnimateWords = isCurrent && !this.reducedMotion && this.settings.animation === "slide";
      line.classList.toggle("stage-lyric-line--word-slide", shouldAnimateWords);
      line.querySelectorAll(".stage-lyric-word").forEach((wordNode) => {
        const wordIndex = Number(wordNode.dataset.wordIndex);
        const highlighted = isCurrent && wordIndex <= this.activeWordIndex;
        wordNode.classList.toggle("stage-lyric-word--highlighted", highlighted);
        wordNode.classList.toggle("stage-lyric-word--active", isCurrent && wordIndex === this.activeWordIndex);
      });
    });
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
      textColor: this.normalizeColor(settings.textColor, StageLyricsController.DEFAULT_SETTINGS.textColor),
      activeColor: this.normalizeColor(settings.activeColor, StageLyricsController.DEFAULT_SETTINGS.activeColor),
      outlineColor: this.normalizeColor(settings.outlineColor, StageLyricsController.DEFAULT_SETTINGS.outlineColor),
      outlineWidth: Math.round(this.clampNumber(settings.outlineWidth, 2, 14, StageLyricsController.DEFAULT_SETTINGS.outlineWidth)),
      previousLines: Math.round(this.clampNumber(settings.previousLines, 0, 3, StageLyricsController.DEFAULT_SETTINGS.previousLines)),
      nextLines: Math.round(this.clampNumber(settings.nextLines, 0, 3, StageLyricsController.DEFAULT_SETTINGS.nextLines)),
      animation: ["slide", "fade", "none"].includes(settings.animation)
        ? settings.animation
        : StageLyricsController.DEFAULT_SETTINGS.animation,
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

  saveSettings() {
    try {
      window.localStorage?.setItem(StageLyricsController.STORAGE_KEY, JSON.stringify(this.settings));
    } catch (_) {
      this.setStatus(this.t("stage.lyrics_settings_save_failed"));
    }
  }

  applySettings() {
    if (!this.overlay) {
      return;
    }
    const preset = StageLyricsController.FONT_PRESETS[this.settings.fontPreset] || StageLyricsController.FONT_PRESETS.karaoke_cjk;
    const fontFamily = this.settings.fontPreset === "custom" && this.settings.customFontFamily.trim()
      ? this.settings.customFontFamily.trim()
      : preset.value;

    this.overlay.style.setProperty("--stage-lyrics-font-family", fontFamily);
    this.overlay.style.setProperty("--stage-lyrics-size", `clamp(2.4rem, ${this.settings.sizeVw}vw, 6.8rem)`);
    this.overlay.style.setProperty("--stage-lyrics-text-color", this.settings.textColor);
    this.overlay.style.setProperty("--stage-lyrics-active-color", this.settings.activeColor);
    this.overlay.style.setProperty("--stage-lyrics-outline-color", this.settings.outlineColor);
    this.overlay.style.setProperty("--stage-lyrics-outline-width", `${this.settings.outlineWidth}px`);
    this.overlay.dataset.animation = this.reducedMotion ? "none" : this.settings.animation;
    this.renderWindow();
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
      this.saveSettings();
      this.applySettings();
      this.syncSettingsUi();
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
        this.saveSettings();
        this.applySettings();
        this.syncSettingsUi({ keepFocus: true });
      });
      input.addEventListener("change", () => {
        this.updateSettingFromInput(name, input);
        this.saveSettings();
        this.applySettings();
        this.syncSettingsUi({ keepFocus: true });
      });
    });
  }

  setSettingsPanelVisible(visible) {
    this.settingsPanelVisible = Boolean(visible);
    this.panel?.classList.toggle("hidden", !this.settingsPanelVisible);
    this.button?.setAttribute("aria-expanded", this.settingsPanelVisible ? "true" : "false");
    this.onPanelVisibilityChange(this.settingsPanelVisible);
  }

  updateSettingFromInput(name, input) {
    const value = input.type === "number" || input.type === "range" ? Number(input.value) : input.value;
    this.settings = this.normalizeSettings({
      ...this.settings,
      [name]: value,
    });
  }

  syncSettingsUi(options = {}) {
    const activeElement = options.keepFocus ? document.activeElement : null;
    Object.entries(this.inputs).forEach(([name, input]) => {
      if (!input || activeElement === input) {
        return;
      }
      input.value = this.settings[name];
    });
    if (this.inputs.customFontFamily) {
      this.inputs.customFontFamily.disabled = this.settings.fontPreset !== "custom";
    }
    if (this.inputs.sizeVwValue) {
      this.inputs.sizeVwValue.textContent = `${this.settings.sizeVw.toFixed(1)}vw`;
    }
    if (this.inputs.outlineWidthValue) {
      this.inputs.outlineWidthValue.textContent = `${this.settings.outlineWidth}px`;
    }
  }

  applySettingsFromTextarea() {
    if (!this.importExport) {
      return;
    }
    try {
      const parsed = JSON.parse(this.importExport.value || "{}");
      this.settings = this.normalizeSettings({
        ...StageLyricsController.DEFAULT_SETTINGS,
        ...parsed,
      });
      this.saveSettings();
      this.applySettings();
      this.syncSettingsUi();
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
      this.settings = this.normalizeSettings({
        ...StageLyricsController.DEFAULT_SETTINGS,
        ...parsed,
      });
      this.saveSettings();
      this.applySettings();
      this.syncSettingsUi();
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
}

window.StageLyricsController = StageLyricsController;
