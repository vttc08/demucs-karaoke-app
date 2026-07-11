/**
 * Lyrics UI Adapter - Generic DOM manipulation and event handling for lyrics features
 * 
 * This adapter sits between the LyricsManager (state/logic) and the DOM.
 * It accepts a configuration object specifying DOM selectors, then:
 * - Syncs UI state changes from manager to DOM
 * - Binds event handlers (search, upload, text changes)
 * - Updates button states, badges, and visibility
 * 
 * Usage:
 *   const adapter = new LyricsUIAdapter(lyricsManager, {
 *     titleInput: '#lyrics-title',
 *     artistInput: '#lyrics-artist',
 *     textarea: '#lyrics-textarea',
 *     stateLabel: '#lyrics-state',
 *     ...
 *   });
 *   adapter.initialize();
 */

class LyricsUIAdapter {
  constructor(lyricsManager, config = {}) {
    this.manager = lyricsManager;
    this.config = config;
    this.elements = {};
    this.eventListeners = [];
    this.unsubscribe = null;
    
    this.resolveElements();
  }

  /**
   * Cache DOM element references from config selectors
   */
  resolveElements() {
    const selectors = {
      titleInput: 'titleInput',
      artistInput: 'artistInput',
      textarea: 'textarea',
      stateLabel: 'stateLabel',
      providerLabel: 'providerLabel',
      helpText: 'helpText',
      searchBtn: 'searchBtn',
      uploadBtn: 'uploadBtn',
      fileInput: 'fileInput',
      googleLink: 'googleLink',
      whisperxLanguageInput: 'whisperxLanguageInput',
      processLinesToggle: 'processLinesToggle',
      processLinesDetail: 'processLinesDetail',
      maxLineLengthInput: 'maxLineLengthInput',
      maxLineLengthCjkInput: 'maxLineLengthCjkInput',
      panel: 'panel',
      downgradeBtn: 'downgradeBtn',
      upgradeHint: 'upgradeHint',
    };

    Object.entries(selectors).forEach(([configKey, elementKey]) => {
      const selector = this.config[configKey];
      if (selector) {
        this.elements[elementKey] = document.querySelector(selector);
      }
    });
  }

  /**
   * Initialize event listeners and sync initial state
   */
  initialize() {
    this.bindEventListeners();
    this.syncUIFromState();
    
    this.unsubscribe = this.manager.on((state) => {
      this.syncUIFromState();
    });
  }

  /**
   * Cleanup: remove event listeners and unsubscribe from state changes
   */
  destroy() {
    this.unbindEventListeners();
    if (this.unsubscribe) {
      this.unsubscribe();
      this.unsubscribe = null;
    }
  }

  /**
   * Bind all event listeners to DOM elements
   */
  bindEventListeners() {
    // Title/artist inputs: sync to manager
    if (this.elements.titleInput) {
      const handler = (e) => this.manager.setMetadata(e.target.value, this.elements.artistInput?.value || '', this.manager.state.youtubeTitle || '');
      this.elements.titleInput.addEventListener('input', handler);
      this.eventListeners.push({ element: this.elements.titleInput, event: 'input', handler });
    }

    if (this.elements.artistInput) {
      const handler = (e) => this.manager.setMetadata(this.elements.titleInput?.value || '', e.target.value, this.manager.state.youtubeTitle || '');
      this.elements.artistInput.addEventListener('input', handler);
      this.eventListeners.push({ element: this.elements.artistInput, event: 'input', handler });
    }

    // Textarea: track manual edits
    if (this.elements.textarea) {
      const handler = (e) => {
        this.manager.handleTextChange(e.target.value);
        this.updateGoogleSearchLink();
      };
      this.elements.textarea.addEventListener('input', handler);
      this.eventListeners.push({ element: this.elements.textarea, event: 'input', handler });
    }

    // Search button: trigger lyrics resolution
    if (this.elements.searchBtn) {
      const handler = async (e) => {
        e.preventDefault();
        try {
          await this.manager.resolve('manual');
        } catch (error) {
          console.error('Lyrics search failed:', error);
        }
      };
      this.elements.searchBtn.addEventListener('click', handler);
      this.eventListeners.push({ element: this.elements.searchBtn, event: 'click', handler });
    }

    // Upload button: open file dialog
    if (this.elements.uploadBtn) {
      const handler = (e) => {
        e.preventDefault();
        this.elements.fileInput?.click();
      };
      this.elements.uploadBtn.addEventListener('click', handler);
      this.eventListeners.push({ element: this.elements.uploadBtn, event: 'click', handler });
    }

    // File input: handle file selection
    if (this.elements.fileInput) {
      const handler = (e) => {
        const file = e.target.files?.[0];
        if (file) {
          this.manager.handleFileUpload(file).catch((error) => {
            console.error('Lyrics upload failed:', error);
          });
        }
      };
      this.elements.fileInput.addEventListener('change', handler);
      this.eventListeners.push({ element: this.elements.fileInput, event: 'change', handler });
    }

    if (this.elements.downgradeBtn) {
      const handler = (e) => {
        e.preventDefault();
        const targetFormat = this.manager.getState().format === 'ttml' ? 'lrc' : 'ttml';
        this.manager.selectAlternative(targetFormat);
      };
      this.elements.downgradeBtn.addEventListener('click', handler);
      this.eventListeners.push({ element: this.elements.downgradeBtn, event: 'click', handler });
    }

    if (this.elements.whisperxLanguageInput) {
      const handler = (e) => this.manager.setWhisperxAlignLanguageOverride(e.target.value);
      this.elements.whisperxLanguageInput.addEventListener('input', handler);
      this.eventListeners.push({ element: this.elements.whisperxLanguageInput, event: 'input', handler });
    }

    if (this.elements.processLinesToggle) {
      const handler = (e) => {
        e.preventDefault();
        if (this.elements.processLinesToggle.disabled) {
          return;
        }
        const nextEnabled = !Boolean(this.manager.getState().processLyricsLines);
        this.manager.setLineProcessingSettings(
          nextEnabled,
          this.elements.maxLineLengthInput?.value,
          this.elements.maxLineLengthCjkInput?.value
        );
      };
      this.elements.processLinesToggle.addEventListener('click', handler);
      this.eventListeners.push({ element: this.elements.processLinesToggle, event: 'click', handler });
    }

    if (this.elements.maxLineLengthInput) {
      const handler = (e) => this.manager.setLineProcessingSettings(
        this.manager.getState().processLyricsLines,
        e.target.value,
        this.elements.maxLineLengthCjkInput?.value
      );
      this.elements.maxLineLengthInput.addEventListener('input', handler);
      this.eventListeners.push({ element: this.elements.maxLineLengthInput, event: 'input', handler });
    }

    if (this.elements.maxLineLengthCjkInput) {
      const handler = (e) => this.manager.setLineProcessingSettings(
        this.manager.getState().processLyricsLines,
        this.elements.maxLineLengthInput?.value,
        e.target.value
      );
      this.elements.maxLineLengthCjkInput.addEventListener('input', handler);
      this.eventListeners.push({ element: this.elements.maxLineLengthCjkInput, event: 'input', handler });
    }
  }

  /**
   * Unbind all event listeners
   */
  unbindEventListeners() {
    this.eventListeners.forEach(({ element, event, handler }) => {
      if (element) {
        element.removeEventListener(event, handler);
      }
    });
    this.eventListeners = [];
  }

  /**
   * Sync entire UI from manager state
   */
  syncUIFromState() {
    const state = this.manager.getState();

    this.updateStateLabel(state.lyricsState, state.isSynced);
    this.updateProviderLabel(state.provider, state.format);
    this.updateHelpText(state.lyricsState, state.isSynced);
    this.updateSearchButton(state);
    this.updateUploadButton(state);
    this.updatePanelVisibility(state.lyricsEnabled);
    this.updateMetadataInputs(state);
    this.updateWhisperxLanguageInput(state);
    this.updateLineProcessingControls(state);
    this.updateTextareaState(state);
    this.updateInputDisabledState(state.lyricsEnabled);
    this.updateGoogleSearchLink();
    this.updateUpgradeButton(state);
  }

  /**
   * Update state badge label
   */
  updateStateLabel(lyricsState, isSynced) {
    if (!this.elements.stateLabel) return;

    const label = LyricsManager.getStatusLabel(lyricsState);
    const className = LyricsManager.getStatusClassName(lyricsState);
    
    this.elements.stateLabel.textContent = label;
    this.elements.stateLabel.className = `rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${className}`;
  }

  /**
   * Update provider label
   */
  updateProviderLabel(provider, format) {
    if (!this.elements.providerLabel) return;

    if (provider) {
      const mode = LyricsManager.getFormatLabel(format);
      this.elements.providerLabel.textContent = `${provider} • ${mode}`;
    } else {
      this.elements.providerLabel.textContent = '';
    }
  }

  /**
   * Update help text based on state
   */
  updateHelpText(lyricsState, isSynced) {
    if (!this.elements.helpText) return;

    const text = LyricsManager.getHelpText(lyricsState, isSynced);
    this.elements.helpText.textContent = text;
  }

  /**
   * Update search button state and tooltip
   */
  updateSearchButton(state) {
    if (!this.elements.searchBtn) return;

    const isLoading = state.lyricsState === 'loading';
    this.elements.searchBtn.disabled = !state.lyricsEnabled || isLoading;
    this.elements.searchBtn.classList.toggle('opacity-60', !state.lyricsEnabled);
    this.elements.searchBtn.classList.toggle('cursor-not-allowed', !state.lyricsEnabled);
    
    if (isLoading) {
      this.elements.searchBtn.title = this.t('lyrics.search_again');
    } else if (!state.lyricsEnabled) {
      this.elements.searchBtn.title = this.t('lyrics.enable_first');
    } else {
      this.elements.searchBtn.title = this.t('lyrics.search_current');
    }
  }

  /**
   * Update upload button state
   */
  updateUploadButton(state) {
    if (!this.elements.uploadBtn) return;

    this.elements.uploadBtn.disabled = !state.lyricsEnabled;
    this.elements.uploadBtn.classList.toggle('opacity-60', !state.lyricsEnabled);
    this.elements.uploadBtn.classList.toggle('cursor-not-allowed', !state.lyricsEnabled);
  }

  updateUpgradeButton(state) {
    if (!this.elements.downgradeBtn) return;
    const hasTtml = Boolean(state.alternatives?.some((alternative) => alternative?.format === 'ttml'));
    const hasLrc = Boolean(state.alternatives?.some((alternative) => alternative?.format === 'lrc'));
    const isTtml = state.format === 'ttml';
    const canToggle = Boolean(state.lyricsEnabled && hasTtml && (isTtml ? hasLrc : state.format === 'lrc'));
    this.elements.downgradeBtn.classList.toggle('hidden', !canToggle);
    this.elements.downgradeBtn.disabled = !canToggle;
    const label = this.elements.downgradeBtn.querySelector('[data-lyrics-toggle-label]');
    if (label) {
      label.textContent = this.t(isTtml ? 'lyrics.restore_lrc' : 'lyrics.upgrade_ttml');
    }
    const icon = this.elements.downgradeBtn.querySelector('[data-lyrics-toggle-icon]');
    if (icon) {
      icon.textContent = isTtml ? 'undo' : 'auto_awesome';
    }
    if (this.elements.upgradeHint) {
      this.elements.upgradeHint.classList.toggle('hidden', !canToggle);
    }
  }

  /**
   * Update panel visibility based on lyrics enabled state
   */
  updatePanelVisibility(lyricsEnabled) {
    if (!this.elements.panel) return;

    this.elements.panel.classList.toggle('hidden', !lyricsEnabled);
  }

  /**
   * Update textarea content and state
   */
  updateTextareaState(state) {
    if (!this.elements.textarea) return;

    if (this.elements.textarea.value !== (state.text || '')) {
      this.elements.textarea.value = state.text || '';
    }
    this.elements.textarea.disabled = !state.lyricsEnabled;
  }

  /**
   * Keep metadata inputs in sync when providers normalize title/artist.
   */
  updateMetadataInputs(state) {
    if (this.elements.titleInput && this.elements.titleInput.value !== (state.title || '')) {
      this.elements.titleInput.value = state.title || '';
    }
    if (this.elements.artistInput && this.elements.artistInput.value !== (state.artist || '')) {
      this.elements.artistInput.value = state.artist || '';
    }
  }

  /**
   * Keep optional WhisperX override input in sync with manager state.
   */
  updateWhisperxLanguageInput(state) {
    if (!this.elements.whisperxLanguageInput) return;

    const value = state.whisperxAlignLanguageOverride || '';
    if (this.elements.whisperxLanguageInput.value !== value) {
      this.elements.whisperxLanguageInput.value = value;
    }
    const enabled = Boolean(state.lyricsEnabled && state.alignLyricsRequested);
    this.elements.whisperxLanguageInput.disabled = !enabled;
    this.elements.whisperxLanguageInput.classList.toggle('opacity-60', !enabled);
  }

  /**
   * Keep line-processing controls in sync with manager state.
   */
  updateLineProcessingControls(state) {
    const hasControls = Boolean(
      this.elements.processLinesToggle ||
      this.elements.maxLineLengthInput ||
      this.elements.maxLineLengthCjkInput
    );
    if (!hasControls) return;

    const enabled = Boolean(
      state.lyricsEnabled &&
      state.alignLyricsRequested &&
      state.format !== 'json' &&
      state.format !== 'ttml'
    );
    const processEnabled = Boolean(state.processLyricsLines);

    if (this.elements.processLinesToggle) {
      if (this.elements.processLinesToggle.getAttribute('aria-checked') !== String(processEnabled)) {
        this.elements.processLinesToggle.setAttribute('aria-checked', String(processEnabled));
      }
      this.elements.processLinesToggle.disabled = !enabled;
      this.elements.processLinesToggle.setAttribute('aria-disabled', String(!enabled));
      this.elements.processLinesToggle.classList.toggle('opacity-60', !enabled);
      this.elements.processLinesToggle.classList.toggle('cursor-not-allowed', !enabled);
      this.elements.processLinesToggle.classList.toggle('bg-secondary', processEnabled && enabled);
      this.elements.processLinesToggle.classList.toggle('bg-surface-container-highest', !processEnabled || !enabled);
      const knob = this.elements.processLinesToggle.querySelector('span');
      if (knob) {
        knob.classList.toggle('translate-x-5', processEnabled);
        knob.classList.toggle('translate-x-0', !processEnabled);
      }
    }

    if (this.elements.maxLineLengthInput) {
      if (String(this.elements.maxLineLengthInput.value || '') !== String(state.maxLineLength ?? 36)) {
        this.elements.maxLineLengthInput.value = String(state.maxLineLength ?? 36);
      }
      this.elements.maxLineLengthInput.disabled = !enabled || !processEnabled;
      this.elements.maxLineLengthInput.classList.toggle('opacity-60', this.elements.maxLineLengthInput.disabled);
    }

    if (this.elements.maxLineLengthCjkInput) {
      if (String(this.elements.maxLineLengthCjkInput.value || '') !== String(state.maxLineLengthCjk ?? 12)) {
        this.elements.maxLineLengthCjkInput.value = String(state.maxLineLengthCjk ?? 12);
      }
      this.elements.maxLineLengthCjkInput.disabled = !enabled || !processEnabled;
      this.elements.maxLineLengthCjkInput.classList.toggle('opacity-60', this.elements.maxLineLengthCjkInput.disabled);
    }

    if (this.elements.processLinesDetail) {
      if (!enabled && state.format === 'json') {
        this.elements.processLinesDetail.textContent = this.t('queue.process_lyrics_lines_json_unsupported');
      } else if (!enabled && state.format === 'ttml') {
        this.elements.processLinesDetail.textContent = this.t('lyrics.align_xml_skipped');
      } else {
        this.elements.processLinesDetail.textContent = this.t('queue.process_lyrics_lines_detail');
      }
    }
  }

  /**
   * Update input disabled state
   */
  updateInputDisabledState(lyricsEnabled) {
    if (this.elements.titleInput) {
      this.elements.titleInput.disabled = !lyricsEnabled;
    }
    if (this.elements.artistInput) {
      this.elements.artistInput.disabled = !lyricsEnabled;
    }
  }

  /**
   * Update Google search link href
   */
  updateGoogleSearchLink() {
    if (!this.elements.googleLink) return;

    const url = this.manager.buildGoogleSearchUrl();
    this.elements.googleLink.href = url;
  }

  /**
   * Set initial title and artist values (called when modal opens)
   */
  setInitialMetadata(title, artist, youtubeTitle = '') {
    if (this.elements.titleInput) {
      this.elements.titleInput.value = title;
    }
    if (this.elements.artistInput) {
      this.elements.artistInput.value = artist;
    }
    this.manager.setMetadata(title, artist, youtubeTitle);
  }

  /**
   * Clear all fields
   */
  clear() {
    if (this.elements.titleInput) {
      this.elements.titleInput.value = '';
    }
    if (this.elements.artistInput) {
      this.elements.artistInput.value = '';
    }
    if (this.elements.textarea) {
      this.elements.textarea.value = '';
    }
    if (this.elements.whisperxLanguageInput) {
      this.elements.whisperxLanguageInput.value = '';
    }
    if (this.elements.processLinesToggle) {
      this.elements.processLinesToggle.setAttribute('aria-checked', 'false');
      this.elements.processLinesToggle.setAttribute('aria-disabled', 'true');
      this.elements.processLinesToggle.classList.remove('bg-secondary');
      this.elements.processLinesToggle.classList.add('bg-surface-container-highest');
      const knob = this.elements.processLinesToggle.querySelector('span');
      if (knob) {
        knob.classList.remove('translate-x-5');
        knob.classList.add('translate-x-0');
      }
    }
    if (this.elements.maxLineLengthInput) {
      this.elements.maxLineLengthInput.value = '36';
    }
    if (this.elements.maxLineLengthCjkInput) {
      this.elements.maxLineLengthCjkInput.value = '12';
    }
    this.manager.reset();
  }

  /**
   * Get current textarea value
   */
  getTextareaValue() {
    return (this.elements.textarea?.value || '').trim();
  }

  /**
   * Set textarea value
   */
  setTextareaValue(text) {
    if (this.elements.textarea) {
      this.elements.textarea.value = text;
    }
  }

  /**
   * Get current title input value
   */
  getTitleValue() {
    return (this.elements.titleInput?.value || '').trim();
  }

  /**
   * Get current artist input value
   */
  getArtistValue() {
    return (this.elements.artistInput?.value || '').trim();
  }

  /**
   * Show a toast/notification message
   */
  showNotification(message, type = 'info') {
    if (this.config.toastElement) {
      const toastEl = document.querySelector(this.config.toastElement);
      const textEl = toastEl?.querySelector('[data-toast-text]') || toastEl;
      
      if (textEl) {
        textEl.textContent = message;
        toastEl?.classList.remove('hidden', 'opacity-0');
        toastEl?.classList.add('opacity-100');
        
        setTimeout(() => {
          toastEl?.classList.add('opacity-0');
          setTimeout(() => {
            toastEl?.classList.add('hidden');
          }, 200);
        }, 2200);
      }
    }
  }

  t(key, params = {}) {
    return window.KaraokeI18n?.t(key, params) || key;
  }
}
