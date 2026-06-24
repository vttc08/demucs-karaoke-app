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
- `status`: `pending`, `downloading`, `processing`, `done`, `failed`, `canceled`
- `stage`: coarse workflow marker such as `download`, `extract_audio`, `demucs`, `finalize`
- `attempt_count`
- `last_error_summary`
- `last_error_detail`
- lifecycle timestamps

`queue_items.status` is still the playback-facing queue state and is mirrored from the durable task status for compatibility with the existing queue and stage flow.

Cancellation is a first-class terminal state:

- `POST /api/tasks/{task_id}/cancel` stops the active worker when one exists
- same-media active or pending tasks are canceled together
- queue rows are reset back to `pending`
- media rows are marked missing again so the item can be queued afresh
- partially downloaded cache artifacts and generated outputs are removed during cleanup
- local `media_karaoke` and uploaded/library queue tasks preserve their original durable media file; only scratch and task-owned temporary outputs are removed
- canceled tasks can be retried while their task row still exists, using the same retry path as failed tasks

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

## Cache Artifact Lifecycle

Main-app processing scratch files are isolated by durable task id under:

- `cache/ytdlp/<task_id>/`
- `cache/audio/<task_id>/`
- `cache/processed/<task_id>/`
- `cache/demucs_outputs/<task_id>/`

After a task has installed its durable media and sidecars, committed their database paths, and
reached `done`, the app removes that task's scratch directories. Cleanup is best-effort: a
filesystem cleanup error is logged but does not turn a completed processing task into a failed one.

Failed task directories remain intact for manual diagnosis. Explicitly canceled tasks retain the
existing cancellation behavior and remove partial scratch data. Legacy flat files created before
task-scoped directories were introduced are not swept automatically because their ownership and
success state cannot be proven safely.

Lyrics stored under `cache/lyrics/` and generated files under `cache/media-thumbnails/` are durable
app assets and are not part of processing cleanup. Vocal-sync preparation removes its redundant
task-scoped Demucs results after the review session is ready, while the review session and task
manifest remain under `cache/vocal_sync/` and `cache/vocal_sync_tasks/` until commit or deletion.

## SSE Endpoints

- `GET /api/tasks`
- `GET /api/tasks/{task_id}`
- `GET /api/tasks/stream`
- `GET /api/tasks/{task_id}/stream`
- `POST /api/tasks/{task_id}/retry`
- `POST /api/tasks/{task_id}/cancel`

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
- download attempts try yt-dlp's default selection first, then retry explicit audio/video/progressive selectors as fallbacks
- the browser-only optimistic progress helper is limited to ffmpeg extraction and finalization stages, while download and Demucs stages rely on real progress updates

When mocks or legacy callers are used in tests, the orchestration falls back to the non-streaming youtube service methods.

## Remote Demucs Progress

Remote Demucs execution now uses an async job contract on `demucs_svc`:

- `POST /jobs` uploads audio and starts remote processing
- `GET /jobs/{job_id}` returns job status, percent, message, and recent remote output tail
- `GET /jobs/{job_id}/result` returns the final ZIP payload once the job completes
- `DELETE /jobs/{job_id}` requests remote cancellation and subprocess termination
- `DELETE /jobs/{job_id}/artifacts` deletes retained remote input/output files for a terminal job
- `GET /io` reports the current size and file count of the remote `incoming/` and `output/` trees
- `DELETE /io` deletes all remote Demucs IO scratch files once no jobs are active

The main app polls the remote job server-side and republishes the latest Demucs step progress through the existing local transports:

- task SSE for admin task panels
- `queue_item_progress` websocket events for queue clients

The polling cadence is intentionally throttled to about once per second by default so long-running
jobs stay responsive without flooding the Demucs host with status checks. The exact interval is
configurable in runtime settings through `demucs_poll_interval_seconds`.

When WhisperX lyrics alignment is requested, the remote job's `Aligning lyrics` phase is surfaced as its own local `whisperx` stage so the browser can apply the optimistic progress helper there instead of letting the Demucs bar stall at the end of the separation run.

Browsers do not connect directly to the Demucs host. Remote job ids are intentionally live-only and are not persisted in SQLite. On restart, any interrupted local task is restarted from the beginning with a fresh remote Demucs job.

Task cancellation is cooperative in the main app: the local worker sets a cancellation event and
lets the Demucs client send `DELETE /jobs/{job_id}` before the worker unwinds. The remote Demucs
service treats cancellation as terminal, terminates the active process, escalates to kill when a
process does not exit promptly, removes that job's remote IO files, and runs adaptive garbage
collection. WhisperX alignment runs in a child process so align-only jobs and separation jobs with
lyrics can be canceled while GPU inference is active.

After a task reaches durable local success, the main app best-effort calls `DELETE /jobs/{job_id}/artifacts`
to retire the corresponding remote Demucs `incoming/` and `output/` directories. Failed tasks skip this
call so remote artifacts remain available until the Demucs service's normal retention cleanup or manual
intervention.

When the main app verifies that no remote Demucs jobs remain active, it can also call `DELETE /io`
to remove every remaining scratch file under the Demucs IO workspace in one pass.
