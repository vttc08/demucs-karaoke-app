# Processing Task Failure and Restart Notes

## What Is Persisted

The database keeps only durable failure information:

- coarse `status`
- coarse `stage`
- `last_error_summary`
- `last_error_detail`
- `attempt_count`

Live progress percentages and verbose stdout/stderr logs are not persisted across app restarts.

## What Is Retained Only In Memory

- yt-dlp progress percentages
- live task progress labels
- recent log lines shown in the `/media` task panel
- SSE subscriber replay buffers

This means a browser reconnect can recover recent logs while the app stays up, but an app restart clears live log history.

The in-memory replay window is intentionally bounded:

- successful tasks expire from live memory after about 60 seconds
- failed tasks expire from live memory after about 15 minutes

After expiry, the durable task row still exists in SQLite, but recent SSE log replay is no longer available for that task.

## Restart Behavior

If the app exits during:

- `pending`
- `downloading`
- `processing`

the task is reset to `pending` on next startup and re-enqueued.

If a task is canceled explicitly, the worker is stopped, the durable row is marked `canceled`, and queue/media cleanup resets the affected media so it can be queued again.

The implementation does not attempt byte-range or partial-progress resume for:

- yt-dlp downloads
- ffmpeg extraction
- local remux/finalize work
- Demucs requests

## Current Demucs Scope

The main app now uses a remote Demucs job API:

- the remote Demucs service owns subprocess execution and stdout parsing
- the main app polls remote job state and republishes it into the local task stream and queue websocket progress updates
- terminal Demucs failures are still persisted locally as coarse durable task failure state
- remote job ids and remote stdout tails are live-only and are not persisted in SQLite

## Follow-up Work

- optional persistence for a compact failure log tail per task
- retry/backoff policy for repeated startup failures
