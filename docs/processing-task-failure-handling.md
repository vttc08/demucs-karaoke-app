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

## Restart Behavior

If the app exits during:

- `pending`
- `downloading`
- `processing`

the task is reset to `pending` on next startup and re-enqueued.

The implementation does not attempt byte-range or partial-progress resume for:

- yt-dlp downloads
- ffmpeg extraction
- local remux/finalize work
- Demucs requests

## Current Demucs Scope

The main app exposes the task abstraction and live task SSE today.

Current Demucs integration is still coarse:

- the main app can show Demucs stage progress
- terminal Demucs failures are persisted
- richer remote Demucs SSE/job orchestration is still a follow-up task

## Follow-up Work

- remote Demucs job API with native progress SSE
- optional persistence for a compact failure log tail per task
- retry/backoff policy for repeated startup failures
- explicit cancel endpoint and cancellation propagation into yt-dlp / remote Demucs
- retention cleanup for old successful tasks
