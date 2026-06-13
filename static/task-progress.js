(() => {
    const ACTIVE_STATUSES = new Set(["downloading", "processing"]);
    const EXPECTED_DURATION_MS = 5000;
    const LINEAR_CAP_PERCENT = 72;
    const TAIL_CAP_PERCENT = 96;
    const TAIL_DECAY_MS = 4500;
    const TICK_MS = 120;

    const stateByKey = new Map();
    let tickHandle = null;

    function clamp(value, min, max) {
        return Math.min(max, Math.max(min, value));
    }

    function parseTimestamp(value) {
        if (!value) {
            return null;
        }
        const timestamp = Date.parse(String(value));
        return Number.isFinite(timestamp) ? timestamp : null;
    }

    function parsePercent(value) {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? clamp(parsed, 0, 100) : 0;
    }

    function estimatePercent(entry, nowMs) {
        const reported = parsePercent(entry.reportedPercent);
        if (!ACTIVE_STATUSES.has(entry.status) || reported >= 100 || reported > 0) {
            return reported;
        }

        const startedAtMs = entry.startedAtMs ?? entry.firstSeenAtMs ?? nowMs;
        const elapsedMs = Math.max(0, nowMs - startedAtMs);
        if (elapsedMs <= 0) {
            return 0;
        }

        if (elapsedMs <= EXPECTED_DURATION_MS) {
            return clamp((elapsedMs / EXPECTED_DURATION_MS) * LINEAR_CAP_PERCENT, 0, LINEAR_CAP_PERCENT);
        }

        const tailElapsedMs = elapsedMs - EXPECTED_DURATION_MS;
        const tailPercent =
            LINEAR_CAP_PERCENT +
            (1 - Math.exp(-tailElapsedMs / TAIL_DECAY_MS)) * (TAIL_CAP_PERCENT - LINEAR_CAP_PERCENT);
        return clamp(tailPercent, LINEAR_CAP_PERCENT, TAIL_CAP_PERCENT);
    }

    function applyProgressNode(node, nowMs) {
        const key = node.dataset.taskProgressKey;
        if (!key) {
            return false;
        }

        const nextReportedPercent = parsePercent(node.dataset.taskProgressReportedPercent);
        const nextStartedAtMs = parseTimestamp(node.dataset.taskProgressStartedAt);
        const nextStatus = String(node.dataset.taskProgressStatus || "");
        const nextLabel = node.dataset.taskProgressLabel || "";
        const nextLabelText = node.dataset.taskProgressLabelText || "";

        const current = stateByKey.get(key) || {
            firstSeenAtMs: nowMs,
        };
        current.status = nextStatus || current.status || "";
        current.reportedPercent = nextReportedPercent;
        current.label = nextLabel;
        current.labelText = nextLabelText;
        if (nextStartedAtMs !== null) {
            current.startedAtMs = nextStartedAtMs;
        } else if (ACTIVE_STATUSES.has(current.status) && current.startedAtMs === undefined) {
            current.startedAtMs = current.firstSeenAtMs ?? nowMs;
        }
        if (current.firstSeenAtMs === undefined) {
            current.firstSeenAtMs = nowMs;
        }
        stateByKey.set(key, current);

        const displayPercent = Math.round(estimatePercent(current, nowMs));
        const fill = node.querySelector("[data-task-progress-fill]");
        if (fill) {
            fill.style.width = `${displayPercent}%`;
            fill.setAttribute("aria-valuenow", String(displayPercent));
        }
        const percentLabel = node.querySelector("[data-task-progress-percent-text]");
        if (percentLabel) {
            percentLabel.textContent = `${displayPercent}%`;
        }
        return ACTIVE_STATUSES.has(current.status) && nextReportedPercent <= 0 && displayPercent < 100;
    }

    function sync(root = document) {
        if (!root || typeof root.querySelectorAll !== "function") {
            return;
        }

        const nowMs = Date.now();
        let hasActiveTasks = false;
        root.querySelectorAll("[data-task-progress-key]").forEach((node) => {
            if (applyProgressNode(node, nowMs)) {
                hasActiveTasks = true;
            }
        });

        if (hasActiveTasks) {
            scheduleTick();
        }
    }

    function tick() {
        tickHandle = null;
        const nowMs = Date.now();
        let hasActiveTasks = false;
        document.querySelectorAll("[data-task-progress-key]").forEach((node) => {
            if (applyProgressNode(node, nowMs)) {
                hasActiveTasks = true;
            }
        });
        if (hasActiveTasks) {
            scheduleTick();
        }
    }

    function scheduleTick() {
        if (tickHandle !== null) {
            return;
        }
        tickHandle = window.setTimeout(tick, TICK_MS);
    }

    window.KaraokeTaskProgress = {
        sync,
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => sync(document), { once: true });
    } else {
        sync(document);
    }
})();
