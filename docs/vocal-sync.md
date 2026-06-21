# Add Vocals Workflow

The admin-only vocal sync workflow adds guide vocals to an existing karaoke media item without
replacing the primary media file.

## Flow

1. Open **Add Vocals** from the media edit modal.
2. Choose an unseparated vocal source from YouTube search or upload an audio/video file.
3. For YouTube, click a result to select it first, then tap **Prepare source** to create a durable
   prep task. Upload uses the same durable prep-task model after the browser finishes transferring
   the file.
4. The main app downloads or stores the source under cache and sends it to the remote Demucs service
   for two-stem separation.
5. `/media-vocals` subscribes to the task stream and shows real yt-dlp download progress for
   YouTube sources plus remote Demucs progress for both YouTube and upload sources. The final local
   sync-estimation step is shown as a generic finalizing phase.
6. The main app prepares mono WAV comparison files with ffmpeg, estimates a constant offset locally,
   and stores a review session under `cache/vocal_sync/`.
7. The browser fetches the prepared session by `task_id`, previews the existing karaoke media and
   prepared vocal stem with the estimated offset.
8. The admin can adjust the offset and commit a new `/media/<stem>.vocals.wav` sidecar, or delete
   the prepared review to remove all vocal-sync cache artifacts and return the page to idle.

Review sessions are cache-backed manifests and the YouTube prep request itself is now a durable
processing task. The task survives like other active processing rows, while the prepared review
session remains cache-backed under `cache/vocal_sync/`. The task-to-session handoff is stored under
`cache/vocal_sync_tasks/`.

On page load, `/media-vocals` calls `/api/media/{item_id}/vocals-sync/status` before enabling source
preparation. This restores an active prepare task after browser refresh by reconnecting to its task
stream, and restores a completed review session without rerunning download or Demucs. Once a review
session is ready, new source preparation is locked until the admin commits the restored review.

Deleting a ready review session removes the session directory under `cache/vocal_sync/` and the
linked task manifest under `cache/vocal_sync_tasks/`. A successful commit performs the same cleanup
after writing the final `/media/<stem>.vocals.wav` sidecar.

## Offset Semantics

The estimator compares:

- reference: separated background/no-vocals stem from the source track
- target: existing karaoke media audio

Positive offset means the source vocals are early relative to the karaoke media, so commit prepends
silence before the vocals.

Negative offset means the source vocals are late relative to the karaoke media, so commit trims the
beginning of the vocal stem by `abs(offset)`.

## Deployment Notes

The main app depends only on `numpy` and `scipy` for the local cross-correlation estimator. These
libraries are imported inside the estimator function so normal FastAPI startup does not load the
scientific stack.

The workflow intentionally does not add `librosa` to the main app. A future DTW fallback can live
behind the remote Demucs service if constant-offset cross-correlation is not reliable enough for a
specific source.
