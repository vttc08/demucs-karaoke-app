/**
 * Lyrics Manager - Core logic for lyrics resolution, format detection, and state management
 * 
 * This module handles all lyrics operations independent of DOM or UI concerns.
 * It can be instantiated per-context (queue modal, upload form, media edit modal) to manage state atomically.
 * 
 * Usage:
 *   const lyricsManager = new LyricsManager({ apiBase: window.KaraokeURLs.basePath });
 *   await lyricsManager.resolve({ title: 'Song', artist: 'Artist' });
 *   const state = lyricsManager.getState();
 */

class LyricsManager {
  constructor(options = {}) {
    this.apiBase = options.apiBase ?? (window.KaraokeURLs?.basePath || "");
    this.requestId = 0;
    this.abortController = null;
    
    this.state = {
      lyricsEnabled: false,
      lyricsState: 'idle',
      provider: '',
      isSynced: false,
      format: 'txt',
      text: '',
      title: '',
      artist: '',
      youtubeTitle: '',
    };
    
    this.listeners = [];
  }

  /**
   * Subscribe to state change events
   */
  on(callback) {
    this.listeners.push(callback);
    return () => {
      this.listeners = this.listeners.filter(cb => cb !== callback);
    };
  }

  /**
   * Notify all listeners of state change
   */
  notifyListeners() {
    this.listeners.forEach(cb => cb(this.state));
  }

  /**
   * Get current state (immutable snapshot)
   */
  getState() {
    return { ...this.state };
  }

  /**
   * Set enabled state and reset lyrics if disabling
   */
  setEnabled(enabled) {
    this.state.lyricsEnabled = enabled;
    if (!enabled) {
      this.reset();
    }
    this.notifyListeners();
  }

  /**
   * Reset lyrics state (called when lyrics are disabled or modal is closed)
   */
  reset() {
    this.cancelInFlight();
    this.state.lyricsState = 'idle';
    this.state.provider = '';
    this.state.isSynced = false;
    this.state.format = 'txt';
    this.state.text = '';
    this.state.title = '';
    this.state.artist = '';
    this.state.youtubeTitle = '';
    this.notifyListeners();
  }

  /**
   * Cancel any in-flight lyrics resolution request
   */
  cancelInFlight() {
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
    if (this.state.lyricsState === 'loading') {
      this.requestId += 1;
    }
  }

  /**
   * Infer lyrics format from text content
   * Returns 'lrc' if synced (contains [MM:SS.mmm] timestamps), otherwise 'txt'
   */
  static inferFormat(text) {
    const trimmed = (text || '').trim();
    if (!trimmed) return 'txt';
    if (/^\[\d{1,2}:\d{2}(?:\.\d{1,3})?\]/m.test(trimmed)) {
      return 'lrc';
    }
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
      try {
        const parsed = JSON.parse(trimmed);
        if (Array.isArray(parsed) || (parsed && typeof parsed === 'object')) {
          return 'json';
        }
      } catch (_error) {
        // Fall back to plain text.
      }
    }
    return 'txt';
  }

  /**
   * Infer lyrics format from a filename.
   */
  static inferFormatFromFilename(filename) {
    const lower = String(filename || '').toLowerCase();
    if (lower.endsWith('.json')) return 'json';
    if (lower.endsWith('.lrc')) return 'lrc';
    return 'txt';
  }

  /**
   * Map a lyrics format to a compact display label.
   */
  static getFormatLabel(format) {
    switch (format) {
      case 'json':
        return LyricsManager.t('lyrics.whisperx_json');
      case 'lrc':
        return LyricsManager.t('lyrics.timed');
      case 'txt':
        return LyricsManager.t('lyrics.plain');
      default:
        return LyricsManager.t('common.unknown');
    }
  }

  /**
   * Get lyrics submission text (current text in editor)
   */
  getSubmissionText() {
    return (this.state.text || '').trim();
  }

  /**
   * Check if user has provided manual lyrics
   */
  hasManualLyrics() {
    return Boolean(this.getSubmissionText());
  }

  /**
   * Set manual lyrics text (from editor or upload)
   */
  setManualLyrics(text, providerInfo = '') {
    this.setLyricsDraft(text, providerInfo, { lyricsState: 'manual' });
  }

  /**
   * Set lyrics content without forcing a backend-save workflow.
   */
  setLyricsDraft(text, providerInfo = '', options = {}) {
    this.cancelInFlight();
    const trimmedText = (text || '').trim();
    const format = options.format || LyricsManager.inferFormat(trimmedText);
    this.state.text = trimmedText;
    this.state.format = format;
    this.state.provider = providerInfo;
    this.state.isSynced = typeof options.isSynced === 'boolean' ? options.isSynced : format !== 'txt';
    this.state.lyricsState = options.lyricsState || (trimmedText ? 'manual' : 'idle');
    this.notifyListeners();
  }

  /**
   * Set title and artist for resolution
   */
  setMetadata(title, artist, youtubeTitle = '') {
    this.state.title = (title || '').trim();
    this.state.artist = (artist || '').trim();
    this.state.youtubeTitle = (youtubeTitle || '').trim();
    this.notifyListeners();
  }

  /**
   * Get metadata for submission (used when adding to queue/saving)
   */
  getSubmissionMetadata(fallbackTitle = '', fallbackArtist = '') {
    return {
      title: this.state.title || fallbackTitle,
      artist: this.state.artist || fallbackArtist,
    };
  }

  /**
   * Check if lyrics should auto-resolve
   * (enabled, not already loading, no manual content, no completed lookup)
   */
  shouldAutoResolve() {
    if (!this.state.lyricsEnabled) return false;
    if (this.state.lyricsState === 'loading') return false;
    if (this.hasManualLyrics()) return false;
    const hasCompletedLookup = ['resolved', 'not_found', 'error', 'manual'].includes(this.state.lyricsState);
    return !hasCompletedLookup;
  }

  /**
   * Resolve lyrics via API call
   * Supports 'manual' trigger (user clicked search) or 'auto' trigger (modal opened)
   */
  async resolve(trigger = 'manual') {
    if (!this.state.lyricsEnabled) return;

    const title = this.state.title || '';
    if (!title) {
      this.state.lyricsState = 'error';
      this.notifyListeners();
      return;
    }

    this.cancelInFlight();
    const requestId = ++this.requestId;
    const abortController = new AbortController();
    this.abortController = abortController;
    
    this.state.lyricsState = 'loading';
    this.state.provider = '';
    this.state.isSynced = false;
    this.notifyListeners();

    const payload = { title };
    if (this.state.artist) {
      payload.artist = this.state.artist;
    }
    if (trigger === 'auto' && this.state.youtubeTitle) {
      payload.youtube_title = this.state.youtubeTitle;
    }

    try {
      const response = await fetch(`${this.apiBase}/api/lyrics/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: abortController.signal,
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || LyricsManager.t('lyrics.search_failed'));
      }

      const result = await response.json();
      
      if (requestId !== this.requestId) return;

      this.state.lyricsState = result.status;
      this.state.provider = result.provider || '';
      this.state.isSynced = Boolean(result.is_synced);
      this.state.format = this.state.isSynced ? 'lrc' : 'txt';

      if (result.title) {
        this.state.title = result.title;
      }
      if (result.artist) {
        this.state.artist = result.artist;
      }
      if (result.status === 'resolved' && result.lyrics) {
        this.state.text = result.lyrics;
      }

      this.notifyListeners();
    } catch (error) {
      if (requestId !== this.requestId) return;
      if (error?.name === 'AbortError') return;
      
      this.state.lyricsState = 'error';
      this.state.provider = '';
      this.state.isSynced = false;
      this.notifyListeners();
      
      throw error;
    } finally {
      if (requestId === this.requestId) {
        this.abortController = null;
      }
    }
  }

  /**
   * Handle manual text change (user editing the textarea)
   */
  handleTextChange(newText) {
    if (!this.state.lyricsEnabled) return;
    
    this.cancelInFlight();
    const trimmedText = (newText || '').trim();
    this.state.text = trimmedText;

    if (trimmedText) {
      this.state.lyricsState = 'manual';
      this.state.format = LyricsManager.inferFormat(trimmedText);
      this.state.isSynced = this.state.format !== 'txt';
    } else if (this.state.lyricsState === 'manual') {
      this.state.lyricsState = 'idle';
      this.state.format = 'txt';
      this.state.isSynced = false;
    }
    
    this.notifyListeners();
  }

  /**
   * Handle file upload (from file input)
   */
  async handleFileUpload(file) {
    if (!file) return;
    
    this.cancelInFlight();
    
    try {
      const text = await file.text();
      this.state.text = text.trim();
      this.state.format = LyricsManager.inferFormatFromFilename(file.name);
      this.state.isSynced = this.state.format !== 'txt';
      this.state.provider = `upload:${file.name}`;
      this.state.lyricsState = 'manual';
      this.notifyListeners();
    } catch (error) {
      console.error('Failed to read lyrics file:', error);
      throw error;
    }
  }

  /**
   * Build Google search URL for lyrics
   */
  buildGoogleSearchUrl() {
    const query = [
      this.state.title,
      this.state.artist,
      'lyrics'
    ].filter(Boolean).join(' ') || 'lyrics';
    return `https://www.google.com/search?q=${encodeURIComponent(query)}`;
  }

  /**
   * Get lyrics submission payload for queue/media operations
   */
  getLyricsSubmissionPayload() {
    if (!this.state.lyricsEnabled) {
      return null;
    }

    const lyricsText = this.getSubmissionText();
    if (!lyricsText) {
      return null;
    }

    return {
      lyrics_text: lyricsText,
      lyrics_format: this.state.format,
    };
  }

  /**
   * Utility: Get status label for UI display
   */
  static getStatusLabel(state) {
    const labels = {
      idle: LyricsManager.t('lyrics.idle'),
      loading: LyricsManager.t('lyrics.searching'),
      resolved: LyricsManager.t('lyrics.resolved'),
      not_found: LyricsManager.t('lyrics.not_found'),
      error: LyricsManager.t('lyrics.status_error'),
      manual: LyricsManager.t('lyrics.manual'),
    };
    return labels[state] || LyricsManager.t('common.unknown');
  }

  /**
   * Utility: Get status CSS class for UI display
   */
  static getStatusClassName(state) {
    const classes = {
      idle: 'bg-on-surface/5 text-on-surface-variant',
      loading: 'bg-primary/10 text-primary',
      resolved: 'bg-secondary/10 text-secondary',
      not_found: 'bg-error/10 text-error',
      error: 'bg-error/10 text-error',
      manual: 'bg-secondary/10 text-secondary',
    };
    return classes[state] || classes.idle;
  }

  /**
   * Utility: Get help text for given state
   */
  static getHelpText(state, isSynced = false) {
    const texts = {
      idle: LyricsManager.t('lyrics.help_default'),
      loading: LyricsManager.t('lyrics.help_loading'),
      not_found: LyricsManager.t('lyrics.help_not_found'),
      error: LyricsManager.t('lyrics.help_error'),
      resolved: isSynced
        ? LyricsManager.t('lyrics.help_resolved_timed')
        : LyricsManager.t('lyrics.help_resolved_plain'),
      manual: LyricsManager.t('lyrics.help_manual'),
    };
    return texts[state] || texts.idle;
  }

  static t(key, params = {}) {
    return window.KaraokeI18n?.t(key, params) || key;
  }
}
