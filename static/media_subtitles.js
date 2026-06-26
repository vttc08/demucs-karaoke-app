(() => {
    const root = document.getElementById("subtitle-workflow-page");
    if (!root) return;

    const appUrl = window.KaraokeURLs?.appUrl || ((path) => path);
    const t = window.KaraokeI18n?.t?.bind(window.KaraokeI18n) || ((key, params = {}) => key);
    const filesRoot = document.getElementById("subtitle-associated-files");
    const refreshFilesBtn = document.getElementById("subtitle-refresh-files");

    const mediaId = Number(root.dataset.mediaId);
    const filesUrl = root.dataset.filesUrl || "";
    const previewUrl = root.dataset.previewUrl || "";
    const uploadUrl = root.dataset.uploadUrl || "";

    const selectedFiles = new Map();

    function getMessageBox(format) {
        return document.querySelector(`[data-subtitle-message-box="${format}"]`);
    }

    function setMessage(format, text = "", isError = false) {
        const box = getMessageBox(format);
        if (!box) return;
        box.textContent = text;
        box.classList.toggle("hidden", !text);
        box.classList.toggle("border-error/30", Boolean(isError));
        box.classList.toggle("bg-error/10", Boolean(isError));
        box.classList.toggle("text-error", Boolean(isError));
        box.classList.toggle("text-on-surface-variant", !isError);
        box.classList.toggle("border-white/10", !isError);
        box.classList.toggle("bg-surface-container-high/30", !isError);
    }

    function escapeText(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#39;");
    }

    function formatKindLabel(kind, extension = "") {
        const normalizedKind = String(kind || "").toLowerCase();
        const normalizedExtension = String(extension || "").toLowerCase();
        if (normalizedKind === "main") return t("subtitle.file_video");
        if (normalizedKind === "vocals") return t("subtitle.file_vocals");
        if (normalizedKind !== "lyrics") return normalizedKind || t("common.unknown");
        if (normalizedExtension === "json") return t("subtitle.file_json");
        if (normalizedExtension === "lrc") return t("media.file_lyrics_lrc");
        if (normalizedExtension === "txt") return t("media.file_lyrics_txt");
        if (normalizedExtension === "srt") return t("subtitle.file_srt");
        return t("media.file_lyrics");
    }

    function formatReplaceLabel(format) {
        return String(format || "").toLowerCase() === "ass"
            ? t("subtitle.ass_label")
            : t("subtitle.srt_label");
    }

    function formatWarning(warning) {
        if (!warning || warning.type !== "overlap") {
            return "";
        }
        return t("subtitle.overlap_warning", {
            current: warning.current_text || "",
            next: warning.next_text || "",
        });
    }

    function renderPreviewBox(format, preview) {
        const box = document.querySelector(`[data-subtitle-preview-box="${format}"]`);
        if (!box) return;
        box.innerHTML = "";

        if (!preview) {
            box.classList.add("hidden");
            return;
        }

        const warningCount = Number(preview.warning_count || 0);
        const summary = document.createElement("p");
        summary.className = "font-semibold";
        summary.textContent = warningCount > 0
            ? t("subtitle.preview_warning_count", { count: warningCount })
            : t("subtitle.preview_no_warnings");
        box.appendChild(summary);

        const details = document.createElement("p");
        details.className = "mt-1 text-xs text-warning/90";
        details.textContent = t("subtitle.preview_counts", {
            segments: preview.segment_count || 0,
            words: preview.word_count || 0,
        });
        box.appendChild(details);

        if (Array.isArray(preview.warnings) && preview.warnings.length > 0) {
            const list = document.createElement("ul");
            list.className = "mt-2 space-y-1 text-xs";
            for (const warning of preview.warnings) {
                const item = document.createElement("li");
                item.textContent = formatWarning(warning);
                list.appendChild(item);
            }
            box.appendChild(list);
        }

        box.classList.remove("hidden");
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

    async function loadAssociatedFiles() {
        if (!filesRoot || !filesUrl) return;
        filesRoot.innerHTML = `<div class="rounded-2xl border border-white/10 bg-surface-container-high/30 p-3 text-sm text-on-surface-variant">${escapeText(t("subtitle.files_loading"))}</div>`;
        try {
            const manifest = await fetchJson(filesUrl);
            renderAssociatedFiles(manifest);
        } catch (error) {
            filesRoot.innerHTML = `<div class="rounded-2xl border border-error/30 bg-error/10 p-3 text-sm text-error">${escapeText(error instanceof Error ? error.message : t("subtitle.request_failed"))}</div>`;
        }
    }

    function renderAssociatedFiles(manifest) {
        if (!filesRoot) return;
        const files = Array.isArray(manifest?.files) ? manifest.files.filter((entry) => Boolean(entry?.exists)) : [];
        filesRoot.innerHTML = "";

        if (!files.length) {
            const empty = document.createElement("div");
            empty.className = "rounded-2xl border border-white/10 bg-surface-container-high/30 p-3 text-sm text-on-surface-variant";
            empty.textContent = t("subtitle.no_associated_files");
            filesRoot.appendChild(empty);
            return;
        }

        for (const file of files) {
            const kind = String(file.kind || "");
            const extension = String(file.extension || "");
            const card = document.createElement("article");
            card.className = "rounded-2xl border border-white/10 bg-surface-container-high/30 p-3";

            const header = document.createElement("div");
            header.className = "grid grid-cols-[minmax(0,1fr)_auto] items-start gap-2";

            const meta = document.createElement("div");
            meta.className = "min-w-0";
            const label = document.createElement("p");
            label.className = "text-[10px] font-black uppercase tracking-[0.18em] text-primary";
            label.textContent = formatKindLabel(kind, extension);
            const filename = document.createElement("p");
            filename.className = "mt-1 break-words text-sm font-semibold text-on-surface";
            filename.textContent = String(file.filename || "");
            meta.appendChild(label);
            meta.appendChild(filename);

            const download = document.createElement("a");
            download.className = "inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-white/10 bg-surface-container-highest/70 text-on-surface hover:brightness-110";
            download.href = appUrl(`/api/media/${mediaId}/files/${encodeURIComponent(kind)}/download`);
            const kindLabel = formatKindLabel(kind, extension);
            download.innerHTML = '<span class="material-symbols-outlined text-[18px]">download</span>';
            download.title = t("subtitle.download_kind", { kind: kindLabel || t("common.download") });
            download.setAttribute("aria-label", t("subtitle.download_kind", { kind: kindLabel || t("common.download") }));

            header.appendChild(meta);
            header.appendChild(download);
            card.appendChild(header);

            filesRoot.appendChild(card);
        }
    }

    async function previewSelectedFile(format, file) {
        if (!file) return;
        setMessage(format, t("subtitle.previewing"), false);
        try {
            const formData = new FormData();
            formData.append("file", file, file.name);
            const payload = await fetchJson(previewUrl, {
                method: "POST",
                body: formData,
            });
            renderPreviewBox(format, payload.preview);
            setMessage(format, t("subtitle.preview_ready"));
        } catch (error) {
            renderPreviewBox(format, null);
            setMessage(format, error instanceof Error ? error.message : t("subtitle.request_failed"), true);
        }
    }

    async function submitSelectedFile(format, file, button) {
        if (!file) {
            setMessage(format, t("subtitle.choose_file_first"), true);
            return;
        }
        const kindLabel = formatReplaceLabel(format);
        const confirmed = window.confirm(t("subtitle.confirm_replace", { kind: kindLabel }));
        if (!confirmed) {
            setMessage(format, t("subtitle.replace_canceled"), false);
            return;
        }
        button.disabled = true;
        setMessage(format, t("subtitle.uploading"), false);
        try {
            const formData = new FormData();
            formData.append("file", file, file.name);
            const payload = await fetchJson(uploadUrl, {
                method: "POST",
                body: formData,
            });
            setMessage(format, t("subtitle.upload_complete_refreshing", { kind: kindLabel }), false);
            renderPreviewBox(format, payload.preview);
            selectedFiles.delete(format);
            const form = document.querySelector(`[data-subtitle-upload-form="${format}"]`);
            const input = form?.querySelector('input[type="file"]');
            if (input) {
                input.value = "";
            }
            await loadAssociatedFiles();
            window.setTimeout(() => {
                window.location.reload();
            }, 2200);
        } catch (error) {
            setMessage(format, error instanceof Error ? error.message : t("subtitle.request_failed"), true);
        } finally {
            button.disabled = false;
        }
    }

    function handleFileSelection(format, input) {
        const file = input.files?.[0] || null;
        if (file) {
            selectedFiles.set(format, file);
            previewSelectedFile(format, file);
        } else {
            selectedFiles.delete(format);
            renderPreviewBox(format, null);
        }
    }

    function bindDropzone(format) {
        const form = document.querySelector(`[data-subtitle-upload-form="${format}"]`);
        if (!form) return;
        const input = form.querySelector('input[type="file"]');
        const dropzone = form.querySelector(`[data-subtitle-dropzone="${format}"]`);
        const previewTrigger = form.querySelector(`[data-subtitle-preview-trigger="${format}"]`);
        const previewBox = form.querySelector(`[data-subtitle-preview-box="${format}"]`);
        const submitButton = form.querySelector('button[type="submit"]');

        if (input) {
            input.addEventListener("change", () => handleFileSelection(format, input));
        }

        if (dropzone && input) {
            dropzone.addEventListener("dragover", (event) => {
                event.preventDefault();
                dropzone.classList.add("bg-primary/10");
            });
            dropzone.addEventListener("dragleave", () => {
                dropzone.classList.remove("bg-primary/10");
            });
            dropzone.addEventListener("drop", (event) => {
                event.preventDefault();
                dropzone.classList.remove("bg-primary/10");
                const file = event.dataTransfer?.files?.[0];
                if (!file) return;
                if (typeof DataTransfer !== "undefined") {
                    const transfer = new DataTransfer();
                    transfer.items.add(file);
                    input.files = transfer.files;
                }
                handleFileSelection(format, input);
            });
        }

        if (previewTrigger) {
            previewTrigger.addEventListener("click", () => {
                const file = selectedFiles.get(format) || input?.files?.[0] || null;
                previewSelectedFile(format, file);
            });
        }

        form.addEventListener("submit", (event) => {
            event.preventDefault();
            const file = selectedFiles.get(format) || input?.files?.[0] || null;
            if (submitButton) {
                submitSelectedFile(format, file, submitButton);
            }
        });
    }

    if (refreshFilesBtn) {
        refreshFilesBtn.addEventListener("click", () => {
            loadAssociatedFiles();
        });
    }

    bindDropzone("ass");
    bindDropzone("srt");
    loadAssociatedFiles();
})();
