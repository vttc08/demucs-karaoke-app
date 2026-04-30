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
      panel: 'panel',
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
      const handler = (e) => this.manager.setMetadata(e.target.value, this.elements.artistInput?.value || '');
      this.elements.titleInput.addEventListener('input', handler);
      this.eventListeners.push({ element: this.elements.titleInput, event: 'input', handler });
    }

    if (this.elements.artistInput) {
      const handler = (e) => this.manager.setMetadata(this.elements.titleInput?.value || '', e.target.value);
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
      const handler = (e) => {
        e.preventDefault();
        this.manager.resolve('manual');
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
          this.manager.handleFileUpload(file);
        }
      };
      this.elements.fileInput.addEventListener('change', handler);
      this.eventListeners.push({ element: this.elements.fileInput, event: 'change', handler });
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
    this.updateProviderLabel(state.provider, state.isSynced);
    this.updateHelpText(state.lyricsState, state.isSynced);
    this.updateSearchButton(state);
    this.updateUploadButton(state);
    this.updatePanelVisibility(state.lyricsEnabled);
    this.updateTextareaState(state);
    this.updateInputDisabledState(state.lyricsEnabled);
    this.updateGoogleSearchLink();
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
  updateProviderLabel(provider, isSynced) {
    if (!this.elements.providerLabel) return;

    if (provider) {
      this.elements.providerLabel.textContent = `${provider}${isSynced ? ' • synced' : ' • plain'}`;
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
      this.elements.searchBtn.title = 'Cancel the current lookup and search again';
    } else if (!state.lyricsEnabled) {
      this.elements.searchBtn.title = 'Enable lyrics first';
    } else {
      this.elements.searchBtn.title = 'Search with the current title and artist';
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

    this.elements.textarea.disabled = !state.lyricsEnabled;
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
}
