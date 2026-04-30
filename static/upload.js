/**
 * Media Upload Page Logic
 */

document.addEventListener('DOMContentLoaded', () => {
    const uploadForm = document.getElementById('upload-form');
    const fileInput = document.getElementById('file-input');
    const dropZone = document.getElementById('drop-zone');
    const dropZoneText = document.getElementById('drop-zone-text');
    const filePreview = document.getElementById('file-preview');
    const fileName = document.getElementById('file-name');
    const fileSize = document.getElementById('file-size');
    const fileTypeIcon = document.getElementById('file-type-icon');
    const removeFileBtn = document.getElementById('remove-file');
    
    const progressContainer = document.getElementById('progress-container');
    const progressStatus = document.getElementById('progress-status');
    const progressPercent = document.getElementById('progress-percent');
    const progressBar = document.getElementById('progress-bar');
    const submitBtn = document.getElementById('submit-btn');

    let selectedFile = null;

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
            if (['mp3', 'mp4'].includes(ext)) {
                selectedFile = file;
                updateFilePreview();
            } else {
                showToast('Only MP3 and MP4 files are supported', true);
            }
        }
    }

    function updateFilePreview() {
        if (selectedFile) {
            fileName.textContent = selectedFile.name;
            fileSize.textContent = (selectedFile.size / (1024 * 1024)).toFixed(2) + ' MB';
            
            const isVideo = selectedFile.name.toLowerCase().endsWith('.mp4');
            fileTypeIcon.textContent = isVideo ? 'movie' : 'music_note';
            
            dropZoneText.classList.add('hidden');
            filePreview.classList.remove('hidden');
            
            // Try to pre-fill metadata from filename
            const stem = selectedFile.name.replace(/\.[^/.]+$/, "");
            const parts = stem.split(' - ');
            if (parts.length === 2) {
                document.getElementById('artist-name').value = parts[0].trim();
                document.getElementById('song-title').value = parts[1].trim();
            } else {
                document.getElementById('song-title').value = stem;
            }
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

    // --- Form Submission ---

    uploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        if (!selectedFile) {
            showToast('Please select a file first', true);
            return;
        }

        const title = document.getElementById('song-title').value;
        const artist = document.getElementById('artist-name').value;
        const aiProcess = document.getElementById('ai-process').checked;
        const syncLyrics = document.getElementById('sync-lyrics').checked;

        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('title', title);
        formData.append('artist', artist);
        formData.append('ai_process', aiProcess);
        formData.append('sync_lyrics', syncLyrics);

        try {
            submitBtn.disabled = true;
            progressContainer.classList.remove('hidden');
            updateProgress(0, 'Connecting...');

            const xhr = new XMLHttpRequest();
            xhr.open('POST', '/api/media/upload', true);

            xhr.upload.onprogress = (e) => {
                if (e.lengthComputable) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    updateProgress(percent, percent < 100 ? 'Uploading...' : 'Processing...');
                }
            };

            xhr.onload = () => {
                if (xhr.status === 200) {
                    const response = JSON.parse(xhr.responseText);
                    showToast('Media uploaded and queued successfully!');
                    resetForm();
                    // Redirect to media library after a short delay
                    setTimeout(() => {
                        window.location.href = '/media';
                    }, 2000);
                } else {
                    const error = JSON.parse(xhr.responseText);
                    showToast(error.detail || 'Upload failed', true);
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
