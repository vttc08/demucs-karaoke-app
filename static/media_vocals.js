(function () {
    const appUrl = window.KaraokeURLs?.appUrl || ((path) => path);
    const t = (key, params = {}) => window.KaraokeI18n?.t(key, params) || key;
    const root = document.getElementById("vocal-sync-page");
    if (!root) return;

    const mediaId = Number(root.dataset.mediaId);
    const hasVocals = root.dataset.hasVocals === "true";
    const media = document.getElementById("vocal-sync-media");
    const vocals = document.getElementById("vocal-sync-vocals");
    const stateLabel = document.getElementById("vocal-sync-state");
    const message = document.getElementById("vocal-sync-message");
    const searchInput = document.getElementById("vocal-sync-search-input");
    const searchBtn = document.getElementById("vocal-sync-search-btn");
    const searchResults = document.getElementById("vocal-sync-search-results");
    const uploadForm = document.getElementById("vocal-sync-upload-form");
    const uploadFile = document.getElementById("vocal-sync-upload-file");
    const uploadProgress = document.getElementById("vocal-sync-upload-progress");
    const uploadProgressStatus = document.getElementById("vocal-sync-upload-progress-status");
    const uploadProgressPercent = document.getElementById("vocal-sync-upload-progress-percent");
    const uploadProgressBar = document.getElementById("vocal-sync-upload-progress-bar");
    const uploadSubmitBtn = uploadForm?.querySelector('[type="submit"]');
    const offsetInput = document.getElementById("vocal-sync-offset");
    const offsetDetail = document.getElementById("vocal-sync-offset-detail");
    const previewPlay = document.getElementById("vocal-sync-preview-play");
    const previewStop = document.getElementById("vocal-sync-preview-stop");
    const commitBtn = document.getElementById("vocal-sync-commit");

    let activeSession = null;
    let vocalsTimer = null;

    function setMessage(text, isError = false) {
        if (!message) return;
        message.textContent = text || "";
        message.classList.toggle("text-error", Boolean(isError));
        message.classList.toggle("text-on-surface-variant", !isError);
    }

    function setState(key) {
        if (stateLabel) {
            stateLabel.textContent = t(key);
        }
    }

    function setBusy(isBusy) {
        [searchBtn, uploadSubmitBtn, commitBtn, previewPlay].forEach((el) => {
            if (el) el.disabled = Boolean(isBusy) || (el === commitBtn && !activeSession) || (el === previewPlay && !activeSession);
        });
    }

    function updateUploadProgress(percent, statusKey) {
        if (!uploadProgress || !uploadProgressStatus || !uploadProgressPercent || !uploadProgressBar) return;
        const safePercent = Math.max(0, Math.min(100, Number(percent) || 0));
        uploadProgress.classList.remove("hidden");
        uploadProgressStatus.textContent = t(statusKey);
        uploadProgressPercent.textContent = `${Math.round(safePercent)}%`;
        uploadProgressBar.style.width = `${safePercent}%`;
    }

    function resetUploadProgress() {
        if (!uploadProgress || !uploadProgressStatus || !uploadProgressPercent || !uploadProgressBar) return;
        uploadProgress.classList.add("hidden");
        uploadProgressStatus.textContent = t("upload.system_ready");
        uploadProgressPercent.textContent = "0%";
        uploadProgressBar.style.width = "0%";
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function formatOffset(value) {
        const numeric = Number(value);
        return Number.isFinite(numeric) ? numeric.toFixed(2) : "0.00";
    }

    function updateOffsetDetail() {
        const offset = Number(offsetInput?.value || 0);
        if (!offsetDetail) return;
        if (Math.abs(offset) < 0.001) {
            offsetDetail.textContent = t("vocalsync.offset_zero");
        } else if (offset > 0) {
            offsetDetail.textContent = t("vocalsync.offset_positive", { seconds: formatOffset(offset) });
        } else {
            offsetDetail.textContent = t("vocalsync.offset_negative", { seconds: formatOffset(Math.abs(offset)) });
        }
    }

    function applySession(session) {
        activeSession = session;
        vocals.src = appUrl(session.vocals_url);
        offsetInput.value = formatOffset(session.estimated_offset_seconds);
        offsetInput.disabled = false;
        previewPlay.disabled = false;
        previewStop.disabled = false;
        commitBtn.disabled = false;
        setState("vocalsync.ready");
        setMessage(t("vocalsync.prepared", { offset: formatOffset(session.estimated_offset_seconds) }));
        updateOffsetDetail();
    }

    async function parseJsonResponse(response) {
        let payload = {};
        try {
            payload = await response.json();
        } catch (error) {
            payload = {};
        }
        if (!response.ok) {
            throw new Error(payload.detail || t("vocalsync.request_failed"));
        }
        return payload;
    }

    async function searchYoutube() {
        const query = searchInput.value.trim();
        if (!query) return;
        searchBtn.disabled = true;
        searchResults.innerHTML = `<p class="rounded-xl bg-surface-container-high/50 p-3 text-sm text-on-surface-variant">${escapeHtml(t("lyrics.searching"))}</p>`;
        try {
            const response = await fetch(appUrl(`/api/search/?q=${encodeURIComponent(query)}&source=youtube&concurrent=false`));
            const results = await parseJsonResponse(response);
            if (!Array.isArray(results) || results.length === 0) {
                searchResults.innerHTML = `<p class="rounded-xl bg-surface-container-high/50 p-3 text-sm text-on-surface-variant">${escapeHtml(t("queue.no_results"))}</p>`;
                return;
            }
            searchResults.innerHTML = results.map((result) => {
                const videoId = escapeHtml(result.video_id || "");
                return `
                    <button type="button" data-youtube-id="${videoId}" class="vocal-sync-youtube-result flex w-full min-w-0 items-center gap-3 overflow-hidden rounded-xl border border-white/10 bg-surface-container-high/50 p-3 text-left transition hover:border-primary/40 hover:bg-surface-container-highest/70">
                        <img src="${escapeHtml(result.thumbnail || "")}" alt="" class="h-14 w-20 rounded-lg object-cover">
                        <span class="min-w-0 flex-1 overflow-hidden">
                            <span class="block truncate text-sm font-bold text-on-surface">${escapeHtml(result.title || t("common.unknown"))}</span>
                            <span class="block truncate text-xs text-on-surface-variant">${escapeHtml(result.channel || "")}</span>
                        </span>
                        <span class="material-symbols-outlined text-primary">graphic_eq</span>
                    </button>
                `;
            }).join("");
        } catch (error) {
            searchResults.innerHTML = "";
            setMessage(error instanceof Error ? error.message : t("vocalsync.request_failed"), true);
        } finally {
            searchBtn.disabled = false;
        }
    }

    async function prepareYoutube(youtubeId) {
        if (!youtubeId || hasVocals) return;
        stopPreview();
        setBusy(true);
        setState("vocalsync.preparing");
        setMessage(t("vocalsync.preparing_detail"));
        try {
            const response = await fetch(appUrl(`/api/media/${mediaId}/vocals-sync/prepare-youtube`), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ youtube_id: youtubeId }),
            });
            const payload = await parseJsonResponse(response);
            applySession(payload.session);
        } catch (error) {
            setState("common.failed");
            setMessage(error instanceof Error ? error.message : t("vocalsync.request_failed"), true);
        } finally {
            setBusy(false);
        }
    }

    async function prepareUpload(event) {
        event.preventDefault();
        const file = uploadFile.files?.[0];
        if (!file || hasVocals) return;
        stopPreview();
        setBusy(true);
        setState("vocalsync.preparing");
        setMessage(t("vocalsync.preparing_detail"));
        updateUploadProgress(0, "upload.connecting");
        const formData = new FormData();
        formData.append("file", file);
        try {
            const payload = await new Promise((resolve, reject) => {
                const xhr = new XMLHttpRequest();
                xhr.open("POST", appUrl(`/api/media/${mediaId}/vocals-sync/prepare-upload`), true);

                xhr.upload.onprogress = (event) => {
                    if (!event.lengthComputable) return;
                    const percent = Math.round((event.loaded / event.total) * 100);
                    updateUploadProgress(percent, percent < 100 ? "upload.uploading" : "upload.processing");
                };

                xhr.onload = () => {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        updateUploadProgress(100, "upload.processing");
                        try {
                            resolve(JSON.parse(xhr.responseText));
                        } catch (error) {
                            reject(new Error(t("vocalsync.request_failed")));
                        }
                        return;
                    }

                    let errorMessage = t("vocalsync.request_failed");
                    try {
                        const error = JSON.parse(xhr.responseText);
                        errorMessage = error.detail || errorMessage;
                    } catch (parseError) {
                        console.error("Vocal sync upload error response parse failed:", parseError);
                    }
                    reject(new Error(errorMessage));
                };

                xhr.onerror = () => {
                    reject(new Error(t("upload.network_error")));
                };

                xhr.send(formData);
            });
            applySession(payload.session);
            updateUploadProgress(100, "common.success");
        } catch (error) {
            setState("common.failed");
            setMessage(error instanceof Error ? error.message : t("vocalsync.request_failed"), true);
            updateUploadProgress(0, "upload.upload_failed");
        } finally {
            setBusy(false);
        }
    }

    function stopPreview() {
        if (vocalsTimer) {
            window.clearTimeout(vocalsTimer);
            vocalsTimer = null;
        }
        media.pause();
        vocals.pause();
    }

    async function playPreview() {
        if (!activeSession) return;
        stopPreview();
        const offset = Number(offsetInput.value || 0);
        const mediaTime = media.currentTime || 0;
        if (offset >= 0) {
            await media.play();
            if (mediaTime >= offset) {
                vocals.currentTime = Math.max(0, mediaTime - offset);
                await vocals.play();
            } else {
                vocals.currentTime = 0;
                vocalsTimer = window.setTimeout(() => {
                    vocals.play().catch(() => {});
                }, Math.round((offset - mediaTime) * 1000));
            }
        } else {
            vocals.currentTime = Math.max(0, mediaTime + Math.abs(offset));
            await Promise.all([
                media.play(),
                vocals.play(),
            ]);
        }
    }

    async function commitSession() {
        if (!activeSession) return;
        stopPreview();
        commitBtn.disabled = true;
        setState("vocalsync.committing");
        setMessage(t("vocalsync.committing_detail"));
        try {
            const response = await fetch(appUrl(`/api/media/${mediaId}/vocals-sync/sessions/${encodeURIComponent(activeSession.session_id)}/commit`), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ offset_seconds: Number(offsetInput.value || 0) }),
            });
            await parseJsonResponse(response);
            setState("common.success");
            setMessage(t("vocalsync.committed"));
            window.setTimeout(() => {
                window.location.href = appUrl("/media");
            }, 900);
        } catch (error) {
            commitBtn.disabled = false;
            setState("common.failed");
            setMessage(error instanceof Error ? error.message : t("vocalsync.request_failed"), true);
        }
    }

    searchBtn?.addEventListener("click", searchYoutube);
    searchInput?.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            searchYoutube();
        }
    });
    searchResults?.addEventListener("click", (event) => {
        const button = event.target.closest("[data-youtube-id]");
        if (button) {
            prepareYoutube(button.dataset.youtubeId);
        }
    });
    uploadForm?.addEventListener("submit", prepareUpload);
    offsetInput?.addEventListener("input", updateOffsetDetail);
    document.querySelectorAll("[data-offset-step]").forEach((button) => {
        button.addEventListener("click", () => {
            if (offsetInput.disabled) return;
            const next = Number(offsetInput.value || 0) + Number(button.dataset.offsetStep || 0);
            offsetInput.value = formatOffset(next);
            updateOffsetDetail();
        });
    });
    previewPlay?.addEventListener("click", () => {
        playPreview().catch((error) => {
            setMessage(error instanceof Error ? error.message : t("vocalsync.preview_failed"), true);
        });
    });
    previewStop?.addEventListener("click", stopPreview);
    commitBtn?.addEventListener("click", commitSession);

    if (hasVocals) {
        setState("karaoke.already_multi_track");
        setMessage(t("vocalsync.already_has_vocals"), true);
        setBusy(true);
    } else {
        resetUploadProgress();
    }
})();
