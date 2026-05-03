(function () {
    function normalizeBasePath(value) {
        const raw = String(value || "").trim();
        if (!raw || raw === "/") return "";
        const withSlash = raw.startsWith("/") ? raw : `/${raw}`;
        return withSlash.replace(/\/+$/, "");
    }

    const basePath = normalizeBasePath(window.KARAOKE_BASE_PATH);

    function appUrl(path) {
        if (!path) return basePath || "";
        const raw = String(path);
        if (/^(https?:|wss?:|\/\/)/i.test(raw)) return raw;
        const localPath = raw.startsWith("/") ? raw : `/${raw}`;
        if (basePath && (localPath === basePath || localPath.startsWith(`${basePath}/`))) {
            return localPath;
        }
        return `${basePath}${localPath}`;
    }

    function appWsUrl(path) {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        return `${protocol}//${window.location.host}${appUrl(path)}`;
    }

    window.KaraokeURLs = {
        basePath,
        appUrl,
        appWsUrl,
    };
})();
