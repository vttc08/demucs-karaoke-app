/**
 * Media Upload Page Logic
 */

document.addEventListener('DOMContentLoaded', () => {
    const appUrl = window.KaraokeURLs?.appUrl || ((path) => path);
    const apiBase = window.KaraokeURLs?.basePath || "";
    const t = window.KaraokeI18n?.t?.bind(window.KaraokeI18n) || ((key, params = {}) => key);
    const uploadForm = document.getElementById('upload-form');
    const fileInput = document.getElementById('file-input');
    const dropZone = document.getElementById('drop-zone');
    const dropZoneText = document.getElementById('drop-zone-text');
    const filePreview = document.getElementById('file-preview');
    const fileName = document.getElementById('file-name');
    const fileSize = document.getElementById('file-size');
    const fileTypeIcon = document.getElementById('file-type-icon');
    const removeFileBtn = document.getElementById('remove-file');
    const addToQueueToggle = document.getElementById('add-to-queue');
    
    const progressContainer = document.getElementById('progress-container');
    const progressStatus = document.getElementById('progress-status');
    const progressPercent = document.getElementById('progress-percent');
    const progressBar = document.getElementById('progress-bar');
    const submitBtn = document.getElementById('submit-btn');
    const videoExtensions = new Set(['mp4', 'webm', 'mkv', 'mov', 'avi', 'm4v']);

    let selectedFile = null;
    const inferMetadataBtn = document.getElementById('infer-metadata-btn');

    // --- Lyrics Manager Setup ---
    let lyricsManager = null;
    let lyricsUIAdapter = null;
    const uploadLyricsSection = document.getElementById('upload-lyrics-section');
    const uploadAiToggle = document.getElementById('upload-ai-toggle');
    const uploadAiStatus = document.getElementById('upload-ai-status');
    const uploadLyricsToggle = document.getElementById('upload-lyrics-toggle');
    let demucsHealth = { healthy: false, detail: t('karaoke.checking_availability') };

    function applyDemucsAvailability() {
        if (!uploadAiToggle) return;
        uploadAiToggle.disabled = !demucsHealth.healthy;
        if (!demucsHealth.healthy) {
            uploadAiToggle.checked = false;
        }
        if (uploadAiStatus) {
            uploadAiStatus.textContent = demucsHealth.healthy
                ? t('karaoke.available')
                : t('karaoke.unavailable_detail', { detail: demucsHealth.detail });
        }
    }

    async function refreshDemucsHealth() {
        if (uploadAiToggle) {
            uploadAiToggle.disabled = true;
        }
        if (uploadAiStatus) {
            uploadAiStatus.textContent = t('karaoke.checking_availability');
        }
        try {
            const response = await fetch(appUrl('/api/settings/demucs-health'));
            if (!response.ok) {
                throw new Error(t('queue.demucs_health_failed'));
            }
            demucsHealth = await response.json();
        } catch (error) {
            demucsHealth = {
                healthy: false,
                detail: error instanceof Error ? error.message : t('queue.demucs_unavailable'),
            };
        }
        applyDemucsAvailability();
    }

    function initializeUploadLyricsManager() {
        if (lyricsManager) return;
        
        lyricsManager = new LyricsManager({ apiBase });
        lyricsUIAdapter = new LyricsUIAdapter(lyricsManager, {
            titleInput: '#upload-lyrics-title',
            artistInput: '#upload-lyrics-artist',
            textarea: '#upload-lyrics-textarea',
            stateLabel: '#upload-lyrics-status',
            providerLabel: '#upload-lyrics-provider',
            searchBtn: '#upload-lyrics-search-btn',
            googleLink: '#upload-lyrics-google-btn',
            uploadBtn: '#upload-lyrics-upload-btn',
            fileInput: '#upload-lyrics-file',
            panel: '#upload-lyrics-form-section'
        });
        lyricsUIAdapter.initialize();
        syncUploadLyricsMetadata();
    }

    function syncUploadLyricsMetadata() {
        if (!lyricsManager) return;
        const title = document.getElementById('song-title')?.value || '';
        const artist = document.getElementById('artist-name')?.value || '';
        lyricsManager.setMetadata(title, artist, title);
    }

    // --- Metadata Inference ---

    function inferMetadataFromFilename(filename) {
        const stem = filename.replace(/\.[^/.]+$/, "");
        return stem;
    }

    async function inferMetadataViaAPI(filename) {
        const stem = inferMetadataFromFilename(filename);
        
        try {
            inferMetadataBtn.disabled = true;
            const response = await fetch(appUrl(`/api/search/infer?title=${encodeURIComponent(stem)}`));
            if (!response.ok) {
                throw new Error(`API error: ${response.status}`);
            }
            const data = await response.json();
            document.getElementById('song-title').value = data.title;
            document.getElementById('artist-name').value = data.artist || '';
            syncUploadLyricsMetadata();
        } catch (error) {
            console.error('Metadata inference failed:', error);
            showToast(t('upload.infer_failed'), true);
        } finally {
            inferMetadataBtn.disabled = false;
        }
    }

    async function applyInferredMetadata(filename) {
        await inferMetadataViaAPI(filename);
    }

    if (inferMetadataBtn) {
        inferMetadataBtn.addEventListener('click', (e) => {
            e.preventDefault();
            if (selectedFile) {
                applyInferredMetadata(selectedFile.name);
            }
        });
    }

    // --- Upload Lyrics Toggle Handlers ---
    if (uploadLyricsSection) {
        uploadLyricsSection.style.display = '';
    }
    initializeUploadLyricsManager();

    if (uploadLyricsToggle) {
        uploadLyricsToggle.addEventListener('change', () => {
            initializeUploadLyricsManager();
            if (lyricsManager) {
                syncUploadLyricsMetadata();
                lyricsManager.setEnabled(uploadLyricsToggle.checked);
            }
        });
    }

    document.getElementById('song-title')?.addEventListener('input', syncUploadLyricsMetadata);
    document.getElementById('artist-name')?.addEventListener('input', syncUploadLyricsMetadata);

    // --- Drag & Drop Handlers ---

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
        }, false);
    });

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => {
            dropZone.classList.add('border-primary/60', 'bg-surface-container-low/80');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => {
            dropZone.classList.remove('border-primary/60', 'bg-surface-container-low/80');
        }, false);
    });

    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        handleFiles(files);
    });

    fileInput.addEventListener('change', (e) => {
        handleFiles(e.target.files);
    });

    function handleFiles(files) {
        if (files.length > 0) {
            const file = files[0];
            const ext = file.name.split('.').pop().toLowerCase();
            if (['mp3', 'mp4', 'webm', 'mkv', 'mov', 'avi', 'm4v'].includes(ext)) {
                selectedFile = file;
                updateFilePreview();
            } else {
                showToast(t('upload.supported_formats'), true);
            }
        }
    }

    function updateFilePreview() {
        if (selectedFile) {
            fileName.textContent = selectedFile.name;
            fileSize.textContent = (selectedFile.size / (1024 * 1024)).toFixed(2) + ' MB';
            
            const ext = selectedFile.name.split('.').pop().toLowerCase();
            const isVideo = videoExtensions.has(ext);
            fileTypeIcon.textContent = isVideo ? 'movie' : 'music_note';
            
            dropZoneText.classList.add('hidden');
            filePreview.classList.remove('hidden');
        } else {
            dropZoneText.classList.remove('hidden');
            filePreview.classList.add('hidden');
        }
    }

    removeFileBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        selectedFile = null;
        fileInput.value = '';
        updateFilePreview();
    });

    dropZone.addEventListener('click', (e) => {
        if (e.target === fileInput || e.target.closest('#remove-file')) {
            return;
        }
        fileInput.click();
    });

    // --- Form Submission ---

    uploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        if (!selectedFile) {
            showToast(t('upload.select_file'), true);
            return;
        }

        const title = document.getElementById('song-title').value;
        const artist = document.getElementById('artist-name').value;
        const addToQueue = addToQueueToggle?.checked ?? true;

        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('title', title);
        formData.append('artist', artist);
        formData.append('add_to_queue', addToQueue);
        formData.append('is_karaoke', Boolean(uploadAiToggle?.checked));

        // Add lyrics if available
        if (lyricsManager && lyricsManager.state.lyricsEnabled) {
            syncUploadLyricsMetadata();
            const lyricsPayload = lyricsManager.getLyricsSubmissionPayload();
            if (lyricsPayload) {
                formData.append('lyrics_text', lyricsPayload.lyrics_text);
                formData.append('lyrics_format', lyricsPayload.lyrics_format);
            }
        }

        try {
            submitBtn.disabled = true;
            progressContainer.classList.remove('hidden');
            updateProgress(0, t('upload.connecting'));

            const xhr = new XMLHttpRequest();
            xhr.open('POST', appUrl('/api/media/upload'), true);

            xhr.upload.onprogress = (e) => {
                if (e.lengthComputable) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    updateProgress(percent, percent < 100 ? t('upload.uploading') : t('upload.processing'));
                }
            };

            xhr.onload = () => {
                if (xhr.status === 200) {
                    let response = {};
                    try {
                        response = JSON.parse(xhr.responseText);
                    } catch (parseError) {
                        console.error('Upload success response parse failed:', parseError);
                    }

                    const finalizeRedirect = () => {
                        const taskId = Number(response.karaoke_task_id);
                        const target = Number.isFinite(taskId) && taskId > 0
                            ? `/media?task_id=${taskId}`
                            : '/media';
                        window.location.href = appUrl(target);
                    };

                    if (response.karaoke_warning) {
                        const warningKey = response.karaoke_warning === 'demucs_offline'
                            ? 'karaoke.saved_without_processing'
                            : 'karaoke.saved_task_start_failed';
                        showToast(t(warningKey, {
                            detail: response.karaoke_warning_detail || t('queue.demucs_unavailable'),
                        }), true);
                        window.setTimeout(finalizeRedirect, 1800);
                    } else {
                        finalizeRedirect();
                    }
                } else {
                    let errorMessage = t('upload.upload_failed');
                    try {
                        const error = JSON.parse(xhr.responseText);
                        errorMessage = error.detail || errorMessage;
                    } catch (parseError) {
                        console.error('Upload error response parse failed:', parseError);
                    }
                    showToast(errorMessage, true);
                    submitBtn.disabled = false;
                }
            };

            xhr.onerror = () => {
                showToast(t('upload.network_error'), true);
                submitBtn.disabled = false;
            };

            xhr.send(formData);

        } catch (err) {
            console.error('Upload error:', err);
            showToast(t('upload.unexpected_error'), true);
            submitBtn.disabled = false;
        }
    });

    function updateProgress(percent, status) {
        progressPercent.textContent = percent + '%';
        progressStatus.textContent = status;
        progressBar.style.width = percent + '%';
    }

    function resetForm() {
        uploadForm.reset();
        selectedFile = null;
        fileInput.value = '';
        updateFilePreview();
        progressContainer.classList.add('hidden');
        submitBtn.disabled = false;
    }

    function showToast(message, isError = false) {
        const toast = document.getElementById('upload-toast');
        const text = document.getElementById('upload-toast-text');
        
        text.textContent = message;
        toast.classList.toggle('border-error/30', isError);
        toast.classList.toggle('border-primary/30', !isError);
        toast.classList.remove('opacity-0', 'translate-y-3');
        
        setTimeout(() => {
            toast.classList.add('opacity-0', 'translate-y-3');
        }, 3000);
    }

    applyDemucsAvailability();
    refreshDemucsHealth();
});
