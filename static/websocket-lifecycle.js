(function initKaraokeWebSocketLifecycle(global) {
    const heartbeatSeconds = Number(global.KARAOKE_WS_HEARTBEAT_INTERVAL_SECONDS);
    const heartbeatIntervalMs = Number.isFinite(heartbeatSeconds) && heartbeatSeconds > 0
        ? heartbeatSeconds * 1000
        : 30000;

    function isVisible() {
        return document.visibilityState === "visible";
    }

    function getStaleAfterMs(graceMs = 5000) {
        return heartbeatIntervalMs * 2 + Math.max(0, graceMs);
    }

    function withJitter(delayMs, jitterRatio = 0.2) {
        const baseDelay = Math.max(0, Number(delayMs) || 0);
        if (!baseDelay) {
            return 0;
        }
        const spread = Math.max(0, Math.floor(baseDelay * Math.min(Math.max(jitterRatio, 0), 0.5)));
        if (!spread) {
            return baseDelay;
        }
        const jitter = Math.floor((Math.random() * (spread * 2 + 1)) - spread);
        return Math.max(0, baseDelay + jitter);
    }

    function installPageLifecycle(handlers = {}) {
        const {
            onVisible,
            onHidden,
            onOnline,
            onOffline,
            onPageShow,
            onPageHide,
        } = handlers;

        const handleVisibilityChange = () => {
            if (isVisible()) {
                onVisible?.();
            } else {
                onHidden?.();
            }
        };
        const handleOnline = () => onOnline?.();
        const handleOffline = () => onOffline?.();
        const handlePageShow = (event) => onPageShow?.(event);
        const handlePageHide = (event) => onPageHide?.(event);

        document.addEventListener("visibilitychange", handleVisibilityChange);
        window.addEventListener("online", handleOnline);
        window.addEventListener("offline", handleOffline);
        window.addEventListener("pageshow", handlePageShow);
        window.addEventListener("pagehide", handlePageHide);

        return () => {
            document.removeEventListener("visibilitychange", handleVisibilityChange);
            window.removeEventListener("online", handleOnline);
            window.removeEventListener("offline", handleOffline);
            window.removeEventListener("pageshow", handlePageShow);
            window.removeEventListener("pagehide", handlePageHide);
        };
    }

    function isSocketStale({
        socket,
        lastActivityAt = 0,
        graceMs = 5000,
        now = Date.now(),
    } = {}) {
        if (!socket || socket.readyState !== WebSocket.OPEN) {
            return false;
        }
        const staleAfterMs = getStaleAfterMs(graceMs);
        const activityAt = Number(lastActivityAt) || 0;
        return activityAt > 0 && now - activityAt > staleAfterMs;
    }

    global.KaraokeWebSocketLifecycle = {
        heartbeatIntervalMs,
        getStaleAfterMs,
        installPageLifecycle,
        isSocketStale,
        isVisible,
        withJitter,
    };
})(window);
