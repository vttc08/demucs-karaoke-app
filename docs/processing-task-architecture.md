# Processing Task Architecture

## Summary

The app now separates durable processing state from live progress transport:

- SQLite stores restartable task metadata and coarse status/stage.
- In-memory state stores live progress percentages and rolling log buffers.
- SSE streams expose reconnectable live task updates to admin clients.

This avoids using SQLite as a high-frequency event bus while still allowing interrupted work to be rediscovered and restarted on app startup.

## Durable Model

`processing_tasks` stores:

- `task_type`: `queue_prepare` or `media_karaoke`
- `source_kind`: `youtube`, `library_media`, or `uploaded_media`
- `target_queue_item_id` / `target_media_item_id`
- `status`: `pending`, `downloading`, `processing`, `done`, `failed`
- `stage`: coarse workflow marker such as `download`, `extract_audio`, `demucs`, `finalize`
- `attempt_count`
- `last_error_summary`
- `last_error_detail`
- lifecycle timestamps

`queue_items.status` is still the playback-facing queue state and is mirrored from the durable task status for compatibility with the existing queue and stage flow.

## Live State

`services/task_stream_service.py` keeps per-task in-memory state:

- latest status/stage
- latest progress percent
- latest progress label
- latest progress label key and arguments
- latest step index/total for compact step-aware progress rendering
- rolling event buffer
- monotonic event sequence

This state is intentionally not durable. It survives browser reconnects but not app restarts.

Terminal live state is retained only briefly:

- `done` tasks stay replayable for about 60 seconds
- `failed` tasks stay replayable for about 15 minutes

This keeps short reconnect windows for the admin SSE UI without allowing live task memory to grow without bound.

## Restart Semantics

On startup:

- tasks in `pending`, `downloading`, or `processing` are reset to restartable `pending`
- `attempt_count` increments
- the execution coordinator starts them again in background worker threads

The restart model is coarse on purpose. yt-dlp and local ffmpeg/demucs work restart from the beginning of the relevant operation instead of pretending to resume from a stale percentage.

## SSE Endpoints

- `GET /api/tasks`
- `GET /api/tasks/{task_id}`
- `GET /api/tasks/stream`
- `GET /api/tasks/{task_id}/stream`

The summary stream is for task list refreshes. The per-task stream is for admin log inspection on `/media`.

The admin task-log client de-duplicates replayed per-task SSE events by the stream `sequence`
value so automatic reconnects do not append the same buffered log lines twice.

## yt-dlp Progress

`adapters/ytdlp.py` now supports streamed download execution:

- progress lines are parsed in-process
- raw output lines are emitted into the live task stream
- queue progress is pushed to queue clients as `queue_item_progress` without additional database writes
- queue and admin task views render a compact active-progress block with current step numbering instead of a separate status chip plus bar
- admin task views still receive the task stream snapshot/log replay directly
- callback failure or timeout tears down the child `yt-dlp` process before the error is surfaced

When mocks or legacy callers are used in tests, the orchestration falls back to the non-streaming youtube service methods.
