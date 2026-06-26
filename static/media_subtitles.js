(() => {
    const root = document.getElementById("subtitle-workflow-page");
    if (!root) return;

    const appUrl = window.KaraokeURLs?.appUrl || ((path) => path);
    const t = window.KaraokeI18n?.t?.bind(window.KaraokeI18n) || ((key, params = {}) => key);
    const message = document.getElementById("subtitle-message");
    const filesRoot = document.getElementById("subtitle-associated-files");
    const refreshFilesBtn = document.getElementById("subtitle-refresh-files");

    const mediaId = Number(root.dataset.mediaId);
    const filesUrl = root.dataset.filesUrl || "";
    const previewUrl = root.dataset.previewUrl || "";
    const uploadUrl = root.dataset.uploadUrl || "";

    const selectedFiles = new Map();

    function setMessage(text = "", isError = false) {
        if (!message) return;
        message.textContent = text;
        message.classList.toggle("text-error", Boolean(isError));
        message.classList.toggle("text-on-surface-variant", !isError);
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
        setMessage(t("subtitle.previewing"), false);
        try {
            const formData = new FormData();
            formData.append("file", file, file.name);
            const payload = await fetchJson(previewUrl, {
                method: "POST",
                body: formData,
            });
            renderPreviewBox(format, payload.preview);
            setMessage(t("subtitle.preview_ready"));
        } catch (error) {
            renderPreviewBox(format, null);
            setMessage(error instanceof Error ? error.message : t("subtitle.request_failed"), true);
        }
    }

    async function submitSelectedFile(format, file, button) {
        if (!file) {
            setMessage(t("subtitle.choose_file_first"), true);
            return;
        }
        button.disabled = true;
        setMessage(t("subtitle.uploading"), false);
        try {
            const formData = new FormData();
            formData.append("file", file, file.name);
            const payload = await fetchJson(uploadUrl, {
                method: "POST",
                body: formData,
            });
            setMessage(t("subtitle.upload_complete"));
            renderPreviewBox(format, payload.preview);
            await loadAssociatedFiles();
        } catch (error) {
            setMessage(error instanceof Error ? error.message : t("subtitle.request_failed"), true);
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
