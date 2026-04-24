#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-notification}"
WEBHOOK_URL="http://10.10.120.16:8123/api/webhook/-l3lyuFkwcd-DsoSMzT7T_yx6"

python3 - "$MODE" "$WEBHOOK_URL" <<'PY'
import json
import subprocess
import sys

mode = sys.argv[1]
webhook_url = sys.argv[2]
raw = sys.stdin.read().strip()
try:
    data = json.loads(raw) if raw else {}
except json.JSONDecodeError:
    data = {"raw": raw}

payload = {
    "source": "github-copilot-cli",
    "timestamp": data.get("timestamp"),
    "cwd": data.get("cwd", ""),
}

if mode == "notification":
    payload.update({
        "event_type": data.get("notification_type", "notification"),
        "title": data.get("title") or "Copilot notification",
        "message": data.get("message") or "",
    })
elif mode == "session_end":
    reason = data.get("reason", "complete")
    payload.update({
        "event_type": f"session_end_{reason}",
        "title": "Copilot session ended",
        "message": f"Session ended: {reason.replace('_', ' ')}",
        "reason": reason,
    })
elif mode == "error_occurred":
    error = data.get("error") or {}
    payload.update({
        "event_type": "error_occurred",
        "title": "Copilot error",
        "message": error.get("message") or "An error occurred",
        "error_name": error.get("name", ""),
        "error_message": error.get("message", ""),
    })
else:
    payload.update({
        "event_type": mode,
        "title": "Copilot notification",
        "message": data.get("message") or "",
    })

subprocess.run([
    "curl",
    "-sS",
    "-X",
    "POST",
    "-H",
    "Content-Type: application/json",
    "-d",
    json.dumps(payload),
    webhook_url,
], check=True, stdout=subprocess.DEVNULL)
PY
