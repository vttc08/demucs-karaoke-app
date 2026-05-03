/**
 * Media Upload Page Logic
 */

document.addEventListener('DOMContentLoaded', () => {
    const appUrl = window.KaraokeURLs?.appUrl || ((path) => path);
    const apiBase = window.KaraokeURLs?.basePath || "";
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
    const uploadLyricsToggle = document.getElementById('upload-lyrics-toggle');

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
            showToast('Could not infer metadata from filename', true);
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

    if (uploadAiToggle) {
        uploadAiToggle.addEventListener('change', () => {
            if (!addToQueueToggle?.checked && uploadAiToggle.checked) {
                showToast('AI karaoke only applies when Add to queue is enabled.', true);
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
                showToast('Supported formats: MP3, MP4, WebM, MKV, MOV, AVI, and M4V', true);
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
            showToast('Please select a file first', true);
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
        formData.append('is_karaoke', Boolean(addToQueue && uploadAiToggle?.checked));

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
            updateProgress(0, 'Connecting...');

            const xhr = new XMLHttpRequest();
            xhr.open('POST', appUrl('/api/media/upload'), true);

            xhr.upload.onprogress = (e) => {
                if (e.lengthComputable) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    updateProgress(percent, percent < 100 ? 'Uploading...' : 'Processing...');
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
                        window.location.href = appUrl('/media');
                    };

                    if (response.queued && response.queue_item_id) {
                        updateProgress(100, 'Queueing...');
                        fetch(appUrl(`/api/queue/${response.queue_item_id}/process`), { method: 'POST' })
                            .catch((processError) => {
                                console.warn('Queue processing trigger failed:', processError);
                            })
                            .finally(finalizeRedirect);
                    } else {
                        finalizeRedirect();
                    }
                } else {
                    let errorMessage = 'Upload failed';
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
                showToast('Network error occurred', true);
                submitBtn.disabled = false;
            };

            xhr.send(formData);

        } catch (err) {
            console.error('Upload error:', err);
            showToast('An unexpected error occurred', true);
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
});
