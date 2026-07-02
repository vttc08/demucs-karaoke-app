# API Documentation

## Base URL
```
http://localhost:8000
```

If `KARAOKE_BASE_PATH=/karaoke` is configured, prepend `/karaoke` to every app route below. For
example, `/queue` becomes `/karaoke/queue`, `/api/queue/ws` becomes `/karaoke/api/queue/ws`, and
`/media/song.mp4` becomes `/karaoke/media/song.mp4`. The reverse proxy should forward the preserved
prefixed path to FastAPI.

## Endpoints

### Queue/Stage WebSocket
```
GET /api/queue/ws
```

WebSocket endpoint for real-time queue updates and stage control.

**Server heartbeat:**
- Server sends: `{"type":"ping","timestamp":...}`
- Client responds: `{"type":"pong","timestamp":...}`

**Client subscription message:**
```json
{
  "type": "client_subscribe",
  "data": {
    "page": "queue"
  },
  "timestamp": 1712345678901
}
```

Supported `page` values:
- `queue`
- `stage`
- `lyrics_viewer`

Clients should send this immediately after websocket connect so the server can target event delivery.

**Client → server command message:**
```json
{
  "type": "stage_command",
  "data": {
    "command": "play",
    "source": "queue"
  },
  "timestamp": 1712345678901
}
```

Allowed `command` values:
- `play`
- `pause`
- `skip`
- `resync` (force stage client(s) to hard-recover local video/vocals alignment; optional numeric `seek_time` and boolean `is_paused`)
- `seek` (requires numeric `seek_time` in seconds; optional boolean `is_paused`)
- `seek_relative` (requires numeric `offset_seconds`; the stage player resolves the final timestamp locally)
- `set_vocals_enabled` (requires boolean `vocals_enabled`)
- `set_vocals_volume` (requires numeric `vocals_volume` between `0.0` and `1.0`)
- `set_lyrics_enabled` (requires boolean `lyrics_enabled`)

Stage commands are authorized server-side. Admin sessions can control any current item. Guest clients
can send stage commands only when the currently playing queue item belongs to their `karaoke_guest_id`.
Unauthorized commands return a websocket `error` event and are not broadcast.

**Server → client events (selected):**
- Queue lifecycle:
  - `queue_item_added`
  - `queue_item_updated`
  - `queue_item_progress`
  - `queue_item_removed`
  - `queue_cleared`
  - `current_item_changed`
  - `queue_item_failed`
- Queue presence:
  - `presence_snapshot` with `{users: [...]}` after queue clients send `presence_hello`
  - `user_joined`
  - `user_updated`
  - `user_left`
- Stage control:
  - `stage_control_command` with `{command, source}`, optional seek payload (`seek_time`, `is_paused`), and `sync_version` for resync commands
  - `stage_state_update` with `{current_time, is_paused, vocals_enabled, vocals_volume, lyrics_enabled, source}`
  - `stage_clock_subscribers_update` with `{lyrics_viewer_count, clock_enabled}` for stage clients
  - `stage_time_update` with `{current_time, is_paused, source}` for lyrics viewers

Event delivery is role-based:
- `queue` clients receive queue lifecycle, lightweight progress, presence, and low-frequency stage state/control events.
- `stage` clients receive queue lifecycle plus stage state/control events and clock-subscriber demand, but not per-tick queue progress.
- `lyrics_viewer` clients receive current-item changes plus stage state/clock events.

**Client → server playback clock update:**
```json
{
  "type": "stage_time_update",
  "data": {
    "current_time": 18.25,
    "is_paused": false,
    "source": "stage"
  },
  "timestamp": 1712345678901
}
```

The stage page sends this message from the active media element so lyrics viewers can follow the authoritative playback clock instead of a local timer. Steady clock ticks are sent only while a `lyrics_viewer` client is connected.
Only admin sessions may send `stage_time_update`.

**Queue presence client message:**
```json
{
  "type": "presence_hello",
  "data": {
    "guest_id": "guest-123",
    "display_name": "Alex",
    "tab_id": "tab-123",
    "page": "queue"
  },
  "timestamp": 1712345678901
}
```

`presence_update` uses the same payload shape and refreshes the visible name for an already-connected guest.

---

### Health Check
```
GET /health
```

**Response:**
```json
{
  "status": "healthy"
}
```

---

### Set Frontend Language
```
POST /language
```

Stores the selected frontend UI language in the `karaoke_locale` cookie and redirects back to an
app-local page. Supported values are currently:
- `en`
- `zh-CN`

**Form fields:**
- `language` (required): target locale code
- `next` (optional): app-local redirect path after the cookie is set

External redirect targets are ignored and fall back to `/queue`.

---

### Search YouTube
```
GET /api/search/?q=<query>
```

**Parameters:**
- `q` (query): Search query string

**Response:**
```json
[
  {
    "source": "local",
    "media_item_id": 42,
    "video_id": "dQw4w9WgXcQ",
    "title": "Song Title",
    "channel": "Artist Name",
    "duration": null,
    "thumbnail": "https://...",
    "downloaded": true
  },
  {
    "source": "youtube",
    "media_item_id": null,
    "video_id": "dQw4w9WgXcQ",
    "title": "Video Title",
    "channel": "Channel Name",
    "duration": "3:32",
    "thumbnail": "https://...",
    "downloaded": false
  }
]
```

`media_path`, `vocals_path`, and `lyrics_path` are normalized to app-served URL prefixes (`/media/...`, `/cache/...`) when possible so browser playback requests always target backend-served file routes.
`downloaded` is true when the returned item already exists in local media. Local matches are returned before YouTube matches and duplicate YouTube hits are suppressed.

---

### Add to Queue
```
POST /api/queue/
```

**Request Body:**
```json
{
  "youtube_id": "dQw4w9WgXcQ",
  "media_item_id": null,
  "title": "Song Title",
  "artist": "Artist Name",
  "queue_as_name": "Alex",
  "is_karaoke": true,
  "lyrics_text": "[00:01.00]Line 1",
  "lyrics_format": "lrc",
  "align_lyrics": true,
  "process_lyrics_lines": true,
  "max_line_length": 36,
  "max_line_length_cjk": 12
}
```

Queue payload can identify the target with either:
- `youtube_id` (existing behavior), or
- `media_item_id` (for direct enqueue of local library search matches).
- `queue_as_name` is optional and admin-only. When provided by an authenticated admin session, it overrides the displayed requester label for that queued item.

If the `youtube_id` already exists in `media_items` with a usable local media file, the queue item is created against that existing media row and processing reuses the stored file instead of re-downloading the video again.
When `lyrics_text` is supplied for karaoke items, the app persists it as a reusable lyrics sidecar under the cache directory so karaoke processing can skip a second lookup. `lyrics_format` is optional; if omitted, the app infers `.lrc` when timestamped lines are present, `.json` for WhisperX-style aligned payloads, and `.txt` otherwise.
- `process_lyrics_lines` is an optional queue-only WhisperX override. When true, the server rewrites long plain/LRC lines before alignment using `max_line_length` (default `36`) and `max_line_length_cjk` (default `12`).
- When line processing is enabled for synced LRC, the original line timestamps are intentionally ignored and WhisperX rebuilds timing from the rewrapped display lines.

### Synced JSON Split/Merge Editor

```
GET /api/media/{item_id}/subtitles/json
POST /api/media/{item_id}/subtitles/process
POST /api/media/{item_id}/subtitles/save
```

The split/merge editor page at `/media-subtitles/{item_id}/split-merge` uses these endpoints to load, rewrap, and save synced JSON lyrics.

`POST /api/media/{item_id}/subtitles/process` accepts:
```json
{
  "max_line_length": 36,
  "max_line_length_cjk": 12
}
```

The process endpoint reloads the synced JSON lyrics from disk before applying deterministic rewrapping, so unsaved browser edits do not affect the result. The save endpoint accepts the `segments` shape shown by the editor and writes the normalized JSON sidecar back to disk.

**Response:**
```json
{
  "id": 1,
  "media_id": 1,
  "position": 1000,
  "youtube_id": "dQw4w9WgXcQ",
  "title": "Song Title",
  "artist": "Artist Name",
  "can_remove": false,
  "can_control_stage": false,
  "is_karaoke": true,
  "status": "pending",
  "media_path": "/media/dQw4w9WgXcQ.mp4",
  "lyrics_path": null,
  "vocals_path": null,
  "task_id": 12,
  "processing_stage": "download",
  "processing_progress": 18,
  "processing_label": "Downloading video",
  "error": null,
  "created_at": "2024-01-01T00:00:00"
}
```

Guest identity is read server-side from queue-page cookies when available:
- `karaoke_guest_id`
- `karaoke_queue_tab_id`
- `karaoke_singer`

---

### Reorder Queue Item
```
POST /api/queue/{item_id}/move
```

Admin-only endpoint for moving a non-playing queue item within the active order.

**Request Body:**
```json
{
  "direction": "up"
}
```

Allowed `direction` values:
- `up`
- `down`

The endpoint updates the stored sparse `position`, reuses existing gaps when possible, and renumbers the queue only if spacing has collapsed. Successful moves broadcast `queue_item_updated` so queue and stage clients refresh their ordering.

---

### Resolve Lyrics
```
POST /api/lyrics/resolve
```

Resolve provider lyrics for the add-to-queue modal.

**Request Body:**
```json
{
  "title": "Song Title",
  "artist": "Artist Name",
  "youtube_title": "YouTube Style Title"
}
```

**Response:**
```json
{
  "status": "resolved",
  "title": "Song Title",
  "artist": "Artist Name",
  "source": "regex",
  "provider": "lrclib",
  "lyrics": "[00:01.00]Line 1",
  "is_synced": true,
  "detail": null
}
```

When no provider returns lyrics, the response still returns inferred metadata with `status: "not_found"` so the UI can fall back to manual lyrics entry.

---

### Get Queue
```
GET /api/queue/
```

**Response:**
```json
[
  {
    "id": 1,
    "media_id": 1,
    "position": 1000,
    "youtube_id": "dQw4w9WgXcQ",
    "title": "Song Title",
    "artist": "Artist Name",
    "requested_by_name": "Alex",
    "can_remove": true,
    "is_karaoke": true,
    "status": "ready",
    "media_path": "/media/dQw4w9WgXcQ.mp4",
    "lyrics_path": null,
    "vocals_path": null,
    "error": null,
    "created_at": "2024-01-01T00:00:00"
  }
]
```

`can_remove` is request-scoped. It is `true` for admins on any non-playing item, and for guests only
when the item's stored owner matches the current `karaoke_guest_id` cookie.

---

### Remove Queue Item
```
DELETE /api/queue/{item_id}
```

Removes a non-playing queue item.

- Admins may remove any non-playing item.
- Guests may remove only their own non-playing items.
- Currently playing items cannot be removed.

---

### Get Queue Presence
```
GET /api/queue/presence
```

Returns the current in-memory roster of active `/queue` viewers. This is mainly used as the fallback source when WebSocket reconnect attempts are exhausted.

**Response:**
```json
{
  "users": [
    {
      "guest_id": "guest-123",
      "display_name": "Alex",
      "joined_at": "2026-05-07T00:00:00+00:00",
      "connection_count": 1
    }
  ]
}
```

---

### Upload Media
```
POST /api/media/upload
```

Uploads a local media file or ZIP bundle into the library. The request is multipart form data.

**Form Fields:**
- `file` (required): MP3, MP4, WebM, MKV, MOV, AVI, M4V, or ZIP file
- `title` (required): media title
- `artist` (optional): media artist
- `add_to_queue` (optional, default `true`): queue the uploaded media after saving
- `is_karaoke` (optional, default `false`): request karaoke processing for the uploaded media
- `lyrics_text` (optional): lyrics text to persist as a reusable sidecar
- `lyrics_format` (optional): `lrc`, `txt`, or `json`; inferred from text when omitted by queue/service paths
- `align_lyrics` (optional, default `false`): request WhisperX word alignment from submitted plain/LRC lyrics. JSON lyrics are treated as already synced and are rejected for alignment.
- `process_lyrics_lines` (optional, default `false`): rewrap lyrics into shorter display lines before WhisperX alignment
- `max_line_length` (optional, default `36` when processing is enabled): max English line length for rewrapping
- `max_line_length_cjk` (optional, default `12` when processing is enabled): max CJK line length for rewrapping

**Response:**
```json
{
  "status": "ok",
  "media_id": 1,
  "filename": "artist-song.mp4",
  "queued": true,
  "queue_item_id": 10,
  "lyrics_path": "/media/artist-song.lrc",
  "karaoke_requested": true,
  "karaoke_started": true,
  "karaoke_task_id": 12,
  "karaoke_warning": null,
  "karaoke_warning_detail": null
}
```

When `lyrics_text` is supplied, the uploaded media row stores `lyrics_path` immediately, even when the item is not queued. Upload and media-edit lyrics are saved beside the media file as `<filename>.lrc` or `<filename>.txt` so library scans can rediscover them.
When `align_lyrics` is true, the upload must include non-empty plain/LRC lyrics. Missing-vocals uploads run separation plus WhisperX alignment and later replace `lyrics_path` with the aligned JSON sidecar. When `process_lyrics_lines` is also true, the server applies the line-length rewrap before alignment and ignores any synced-LRC preservation for that submission.

ZIP uploads are treated as import bundles. The archive must include exactly one main audio/video file and may also include matching same-stem `*.vocals.*`, `*.lrc` / `*.json`, and `*.png` / `*.jpg` / `*.jpeg` / `*.webp` sidecars. Unrelated files and folders inside the archive are ignored. Karaoke and lyric submission fields are ignored for ZIP imports because the archive is expected to already contain the desired tracks/metadata.

Queued uploads use a single queue preparation task. Non-queued AI karaoke uploads use a
`media_karaoke` task. If Demucs is unavailable at submission time, the file and metadata remain
saved, `karaoke_started` is false, and the response includes a warning.

---

### Scan Media Library
```
POST /api/media/scan
```

Runs filesystem reconciliation against the configured media root.

Behavior:
- marks DB rows as `missing` when `media_path` is no longer present on disk
- creates DB rows for on-disk primary media files not yet in `media_items`
- refreshes sidecar paths (`vocals_path`, `lyrics_path`) from sibling files

**Response:**
```json
{
  "status": "ok",
  "summary": {
    "scanned_files": 12,
    "created": 2,
    "marked_missing": 1,
    "restored": 0,
    "sidecars_updated": 3,
    "skipped_rows": 0
  }
}
```

---

### Scan One Media Item
```
POST /api/media/{item_id}/scan
```

Refreshes the vocals and lyrics sidecar paths for one media row without walking the full library.
If the backing media file is missing, the row is marked missing and left otherwise unchanged.

**Response:**
```json
{
  "status": "ok",
  "summary": {
    "scanned_files": 1,
    "created": 0,
    "marked_missing": 0,
    "restored": 0,
    "sidecars_updated": 1,
    "thumbnails_updated": 0,
    "skipped_rows": 0
  }
}
```

---

### Media File Manifest
```
GET /api/media/{item_id}/files
```

Admin-only manifest for the media edit modal. Returns the main file plus any tracked vocals and
lyrics sidecars that still exist on disk. Missing sidecars are omitted so the modal does not render
broken download/delete actions.

**Response:**
```json
{
  "media_id": 42,
  "title": "Song Title",
  "artist": "Artist Name",
  "download_name": "song-title.zip",
  "has_multi_track": true,
  "has_lyrics": true,
  "lyrics_kind": "lrc",
  "files": [
    {
      "kind": "main",
      "label": "main",
      "filename": "song-title.mp4",
      "path": "/media/song-title.mp4",
      "exists": true,
      "downloadable": true,
      "deletable": false,
      "extension": "mp4"
    }
  ]
}
```

---

### Download One Media File
```
GET /api/media/{item_id}/files/{kind}/download
```

Admin-only attachment download for one tracked file. `kind` must be `main`, `vocals`, or
`lyrics`.

---

### Delete One Sidecar File
```
DELETE /api/media/{item_id}/files/{kind}
```

Admin-only sidecar deletion for the modal. `kind` must be `vocals` or `lyrics`; deleting `main`
is rejected. The server removes the file when present and clears the matching DB field.

---

### Download Media Package
```
GET /api/media/{item_id}/download
```

Admin-only ZIP download for the current main file and any available sidecars. The archive uses
stored entries only and skips missing sidecars.

---

### Rename Media Item
```
PATCH /api/media/{item_id}
```

Updates the media row title and artist. When `rename_on_disk` is true, the server also renames the media file and any discovered sidecar files so their paths continue to match the new stem.

**Request Body:**
```json
{
  "title": "New Title",
  "artist": "New Artist",
  "rename_on_disk": true,
  "is_karaoke": true,
  "align_lyrics": true,
  "lyrics_text": "[00:01.00]Line 1",
  "lyrics_format": "lrc"
}
```

`lyrics_text`, `lyrics_format`, `is_karaoke`, `align_lyrics`, and the line-processing fields are optional. When `is_karaoke` is true, the
server starts a `media_karaoke` task only when the item is not already multi-track and Demucs is
online. When `align_lyrics` is true, the server requires non-empty plain/LRC lyrics, saves them, then
starts `media_lyrics_align` if `vocals_path` already exists or `media_karaoke_align` if separation is
also needed. When line processing is enabled, the same pre-alignment rewrap is applied to the queued
media task. Rename and lyrics changes remain saved if the health check fails.

**Response:**
```json
{
  "status": "ok",
  "summary": {
    "renamed_files": 3,
    "target_stem": "new-title-new-artist"
  },
  "karaoke_requested": true,
  "karaoke_started": true,
  "karaoke_task_id": 17,
  "karaoke_warning": null,
  "karaoke_warning_detail": null
}
```

---

### Add Vocals To Media Item
```
POST /api/media/{item_id}/vocals-sync/prepare-youtube
POST /api/media/{item_id}/vocals-sync/prepare-upload
GET /api/media/{item_id}/vocals-sync/status
GET /api/media/{item_id}/vocals-sync/tasks/{task_id}/session
GET /api/media/{item_id}/vocals-sync/sessions/{session_id}
POST /api/media/{item_id}/vocals-sync/sessions/{session_id}/commit
DELETE /api/media/{item_id}/vocals-sync/sessions/{session_id}
```

Admin-only workflow for preparing and committing a guide-vocal sidecar for an existing media item.
The media item must exist on disk and must not already have `vocals_path`.

`prepare-youtube` accepts:
```json
{
  "youtube_id": "abcdefghijk"
}
```

`prepare-upload` accepts multipart form data with `file`.

Preparation downloads or stores the unseparated source, sends it to the remote Demucs service, then
estimates a local constant offset using the separated background stem and the existing karaoke media
audio. Both prepare endpoints now return a durable task id:
```json
{
  "status": "processing",
  "task_id": 17
}
```

When the task finishes, fetch the prepared review session with:
```
GET /api/media/{item_id}/vocals-sync/tasks/{task_id}/session
```

The page can recover after browser refresh by calling:
```
GET /api/media/{item_id}/vocals-sync/status
```

The status response reports one of `idle`, `preparing`, `ready`, `failed`, `canceled`, or
`has_vocals`, with the matching durable task and prepared review session when available. A ready
review locks new prepare requests until the user commits the existing review.

Commit accepts the reviewed offset:
```json
{
  "offset_seconds": 0.35
}
```

Commit renders `/media/<stem>.vocals.wav`, updates `media_items.vocals_path`, and leaves
`media_items.media_path` unchanged. Deleting a prepared review session or committing it removes the
associated vocal-sync cache session and task-manifest artifacts.

---

### Delete Media Item
```
DELETE /api/media/{item_id}
```

Deletes a media row, removes any queued items for that media if it is not currently playing, and deletes local media/sidecar files when they exist.

**Response:**
```json
{
  "status": "ok",
  "summary": {
    "deleted_files": 3,
    "missing_files": 1,
    "removed_queue_items": 2
  }
}
```

---

### Serve Media File
```
GET /media/{file_path}
```

Serves files from the configured `MEDIA_PATH` (or runtime `media_path` setting)
under a stable `/media/...` URL prefix.

### Serve Cache File
```
GET /cache/{file_path}
```

Serves files from the configured `CACHE_PATH` (or runtime `cache_path` setting)
under a stable `/cache/...` URL prefix.

---

### Generate QR Code
```
GET /api/qr?data=<text>&size=<pixels>
```

**Parameters:**
- `data` (string, required): Payload to encode inside the QR code (max 1024 characters).
- `size` (number, optional): Approximate width/height of the resulting PNG (defaults to `256`, accepted range `64-1024`).

**Response:**
- Returns a binary `image/png` payload containing the QR code.
- Uses the bundled `segno` library with a fixed dark-on-light palette so no external QR service is required.

---

### Get Current Item
```
GET /api/queue/current
```

**Response:**
Same as queue item, or `null` if no item is playing.

---

### Get Next Item
```
GET /api/queue/next
```

**Response:**
Same as queue item, or `null` if no items ready.

---

### Get Queue Item Lyrics Payload
```
GET /api/queue/{item_id}/lyrics-cues
```

Returns normalized lyrics payload for stage overlay and queue lyrics viewer rendering.

Behavior:
- Reads queue item media sidecar `lyrics_path` (after server-side normalization/repair).
- Supports:
  - `.lrc` files (parsed to cues)
  - `.json` files (validated/normalized cue payloads, including aligned segment JSON from Demucs/WhisperX)
  - `.txt` files (plain unsynced lines)
- Uses configured media/cache roots for `/media/...` and `/cache/...` paths.

**Success response:**
```json
{
  "item_id": 12,
  "media_id": 45,
  "lyrics_path": "/media/song123.lrc",
  "source_format": "lrc",
  "is_synced": true,
  "cues": [
    {"time": 1.2, "text": "First line"},
    {"time": 4.8, "text": "Second line"}
  ],
  "lines": ["First line", "Second line"]
}
```

`.txt` example:
```json
{
  "item_id": 12,
  "media_id": 45,
  "lyrics_path": "/media/song123.txt",
  "source_format": "txt",
  "is_synced": false,
  "cues": [],
  "lines": ["Line one", "Line two"]
}
```

**Error responses:**
- `404` queue item not found
- `404` lyrics not available for queue item
- `404` sidecar file missing on disk
- `422` unsupported or invalid lyrics format/payload

---

### Transform Chinese Lyrics for Display
```
POST /api/lyrics/chinese-transform
```

Display-only helper for the queue lyrics viewer.

**Request body:**
```json
{
  "texts": ["繁體中文", "Hello 世界"],
  "include_pinyin": true
}
```

Behavior:
- Converts Traditional Chinese characters to Simplified Chinese.
- Leaves non-Chinese text unchanged.
- When `include_pinyin` is `true`, returns a pinyin rendering under each Chinese line.

**Response:**
```json
{
  "items": [
    {
      "original": "繁體中文",
      "simplified": "繁体中文",
      "pinyin": "fan ti zhong wen",
      "has_chinese": true
    },
    {
      "original": "Hello 世界",
      "simplified": "Hello 世界",
      "pinyin": "Hello shi jie",
      "has_chinese": true
    }
  ]
}
```

---

### Process Queue Item
```
POST /api/queue/{item_id}/process
```

Triggers background processing of a queue item.
The endpoint creates or reuses a durable processing task and always hands it to the in-process
execution coordinator, so a stuck active task can be restarted without waiting for an app restart.

**Response:**
```json
{
  "status": "processing",
  "item_id": 1,
  "task_id": 12
}
```

---

### Start Karaoke Processing For Existing Media
```
POST /api/media/{item_id}/karaoke
```

Admin-only endpoint for creating or reusing a durable karaoke-processing task for an existing media library item.

Returns `409` when the media file is missing, Demucs is offline, or the item already has a vocals
sidecar.

**Response:**
```json
{
  "status": "processing",
  "media_id": 42,
  "task_id": 17
}
```

---

### Get Lossless Trim Metadata
```
GET /api/media/{item_id}/trim-info
```

Admin-only endpoint returning the current duration, stream types, attached sidecars, and normalized
I-frame timestamps for the first video stream.

**Response:**
```json
{
  "media_id": 42,
  "title": "Song",
  "artist": "Artist",
  "media_url": "/media/song.mp4",
  "duration": 183.52,
  "has_video": true,
  "has_audio": true,
  "keyframes": [0.0, 2.002, 4.004],
  "vocals_path": "/media/song.vocals.wav",
  "lyrics_path": "/media/song.lrc",
  "lyrics_format": "json"
}
```

---

### Apply Lossless Trim
```
POST /api/media/{item_id}/trim
```

Admin-only synchronous endpoint that replaces the primary media and attached synchronized sidecars.
Video start/end values are snapped outward to surrounding I-frames before FFmpeg stream copy. The
same resolved timestamps trim the vocals sidecar and shift LRC, SRT, or WhisperX JSON lyrics.

**Request:**
```json
{
  "start_time": 8.2,
  "end_time": 175.0
}
```

**Response:**
```json
{
  "status": "ok",
  "summary": {
    "media_id": 42,
    "requested_start": 8.2,
    "requested_end": 175.0,
    "resolved_start": 8.008,
    "resolved_end": 176.009,
    "duration": 168.001,
    "trimmed_sidecars": ["vocals", "lyrics"]
  }
}
```

Returns `404` for a missing media row/file, `409` while the item is playing or processing, `422`
for invalid ranges or unsupported lyrics, and `500` if FFmpeg or atomic replacement fails.

---

### List Processing Tasks
```
GET /api/tasks/
```

Admin-only endpoint returning active and recently failed processing tasks.

Each item includes durable task fields plus optional live in-memory snapshot data:
- `live.progress_percent`
- `live.progress_label`
- `live.event_sequence`
- `live.event_count`

---

### Stream Task Summaries
```
GET /api/tasks/stream
```

Admin-only SSE endpoint for live task summary updates.
The initial SSE message is a snapshot payload with current active tasks, followed by incremental task events.

---

### List Tasks
```
GET /api/tasks/
```

Returns the active and recently failed durable tasks visible to the current viewer.
Admins receive all visible tasks. Guests receive only their own queue-backed tasks.

---

### Stream One Task
```
GET /api/tasks/{task_id}/stream
```

Admin-only SSE endpoint for one task's live progress/log stream.
On connect, the server emits:
- one current snapshot event
- buffered recent task events retained in memory
- live updates until disconnect

---

### Delete Processing Task
```
DELETE /api/tasks/{task_id}
```

Deletes a failed or canceled durable task and any orphaned queue/media rows it leaves behind.
Admins may delete any failed or canceled task. Guests may delete their own failed or canceled queue-backed tasks.

---

### Skip Current Item
```
POST /api/queue/skip
```

Removes the currently playing item from the active queue and promotes the next `ready` item to `playing`.
Requires an admin session unless the current item belongs to the guest sending the request.

**Response:**
- Queue item object for the newly playing item, or `null` if no next item is available.

---

### Complete Current Item
```
POST /api/queue/complete-current
```

Removes the currently playing item from the active queue and promotes the next `ready` item to `playing`.
This endpoint is used by playback `ended` handling for automatic queue advance.
Requires an admin session.

**Response:**
- Queue item object for the newly playing item, or `null` if no next item is available.

---

### Get Runtime Settings
```
GET /api/settings/
```

Returns current in-memory runtime settings used by the application.
This endpoint is optimized for fast page load and does not perform a live Demucs network probe.
It returns cached/pending health indicators and the UI should call `/api/settings/demucs-health`
for a real-time status refresh.
Persisted runtime settings are loaded from the database during application startup, so this
endpoint reflects the latest saved UI configuration after the app has booted.

**Response:**
```json
{
  "demucs_api_url": "http://10.10.120.191:8001",
  "demucs_healthy": false,
  "demucs_health_detail": "Health check pending",
  "demucs_model": "htdemucs",
  "demucs_device": "cuda",
  "demucs_output_format": "wav",
  "demucs_mp3_bitrate": 320,
  "demucs_direct_media_max_mb": 500,
  "demucs_poll_interval_seconds": 1.0,
  "whisperx_transcription_model": "tiny",
  "whisperx_align_language": "en",
  "whisperx_detect_language": false,
  "whisperx_use_synced_lyrics": false,
  "whisperx_preload_models": "transcription=tiny,align=en",
  "ffmpeg_preset": "superfast",
  "ffmpeg_crf": 23,
  "concurrent_ytdlp_search_enabled": false,
  "lyrics_provider_netease_enabled": true,
  "lyrics_provider_lrclib_enabled": true,
  "media_path": "/mnt/karaoke_media",
  "cache_path": "/mnt/karaoke_cache",
  "ytdlp_path": "/home/user/.venv/bin/yt-dlp",
  "ytdlp_deno_path": "/usr/local/bin/deno",
  "ytdlp_proxy_url": "socks5://127.0.0.1:1080",
  "ytdlp_video_resolution": "default",
  "ffmpeg_path": "/usr/bin/ffmpeg",
  "stage_qr_url": "https://karaoke.example/queue",
  "stage_lobby_media_path": "/media/stage-lobby.mp4",
  "stage_vocals_volume_default": 1.0
}
```

---

### Get Storage Usage
```
GET /api/settings/storage-usage
```

Admin-only endpoint that estimates disk usage for the configured media directory, cache directory,
and SQLite database file when `DATABASE_URL` uses a file-backed SQLite URL.

**Response:**
```json
{
  "media_bytes": 123456789,
  "media_display": "117.7 MiB",
  "cache_bytes": 98765432,
  "cache_display": "94.2 MiB",
  "database_bytes": 1048576,
  "database_display": "1.0 MiB",
  "database_available": true,
  "total_bytes": 222222797,
  "total_display": "211.8 MiB"
}
```

When the configured database is not SQLite, `database_available` is `false`, `database_bytes`
is `null`, and the UI should show `N/A` for the database row.

---

### Clean Storage
```
POST /api/settings/storage-cleanup
```

Admin-only endpoint that deletes cache scratch files under the configured cache directory while
preserving `media-thumbnails/`, then removes stale database rows. The cleanup removes:
- files and directories under `cache/` except `media-thumbnails/`
- `processing_tasks` rows with `status = 'done'`
- queue rows that point at `media_items` marked missing
- `processing_tasks` rows that point at `media_items` marked missing
- `media_items` rows where `missing = 1`

**Response:**
```json
{
  "cache_deleted_files": 12,
  "cache_deleted_bytes": 3456,
  "db_deleted_done_tasks": 3,
  "db_deleted_missing_queue_items": 2,
  "db_deleted_missing_processing_tasks": 1,
  "db_deleted_missing_media_items": 4,
  "detail": "Deleted 12 cache files, 3 done tasks, and 4 missing media items"
}
```

---

### Update Runtime Settings
```
PATCH /api/settings/
```

Updates runtime settings immediately for new requests while the app is running.
The validated values are also persisted to the `runtime_settings` table so they survive reloads
and restarts when no explicit `.env` override is present.

**Request Body (partial update supported):**
```json
{
  "demucs_api_url": "http://127.0.0.1:9001",
  "demucs_model": "htdemucs",
  "demucs_device": "cuda",
  "demucs_output_format": "wav",
  "demucs_mp3_bitrate": 320,
  "demucs_direct_media_max_mb": 500,
  "demucs_poll_interval_seconds": 1.0,
  "whisperx_transcription_model": "tiny",
  "whisperx_align_language": "en",
  "whisperx_detect_language": false,
  "whisperx_use_synced_lyrics": false,
  "whisperx_preload_models": "transcription=tiny,align=en",
  "ffmpeg_preset": "veryfast",
  "ffmpeg_crf": 23,
  "concurrent_ytdlp_search_enabled": true,
  "lyrics_provider_netease_enabled": false,
  "lyrics_provider_lrclib_enabled": true,
  "media_path": "/mnt/karaoke_media",
  "cache_path": "/mnt/karaoke_cache",
  "ytdlp_path": "yt-dlp",
  "ytdlp_deno_path": "",
  "ytdlp_proxy_url": "",
  "ytdlp_video_resolution": "default",
  "ffmpeg_path": "ffmpeg",
  "stage_qr_url": "https://karaoke.example/queue",
  "stage_lobby_media_path": "/media/stage-lobby.mp4",
  "stage_vocals_volume_default": 0.75
}
```

Validation:
- `ffmpeg_preset` must be one of FFmpeg preset values (`ultrafast` ... `veryslow`)
- `ffmpeg_crf` must be between `0` and `51`
- `demucs_device` must be `cuda` or `cpu`
- `demucs_output_format` must be `wav` or `mp3`
- `demucs_mp3_bitrate` must be between `64` and `320`
- `demucs_direct_media_max_mb` must be between `0` and `5000`
- `demucs_poll_interval_seconds` must be between `0.25` and `10.0`
- `whisperx_transcription_model` controls the model preloaded on Demucs startup and used for optional lyric alignment
- `whisperx_align_language` defaults to `en`; blank values are stored as empty strings and treated as disabled by the client
- `whisperx_detect_language` toggles WhisperX language detection for alignment jobs
- `whisperx_use_synced_lyrics` keeps timestamped LRC lyrics in line-by-line mode instead of flattening them before alignment
- `whisperx_preload_models` is a comma-separated preload list such as `transcription=tiny,align=en,fr`; bare values keep the previous item type, so `align=en,fr` preloads both `en` and `fr`
- `concurrent_ytdlp_search_enabled` toggles optional parallel search mode
- `lyrics_provider_netease_enabled` toggles NetEase in concurrent lyrics fallback
- `lyrics_provider_lrclib_enabled` toggles LRCLib in concurrent lyrics fallback
- `ytdlp_deno_path` is optional; blank keeps yt-dlp default behavior, while a value adds `--js-runtimes deno:<path>` to yt-dlp commands
- `ytdlp_proxy_url` must be empty or use one of: `http`, `https`, `socks4`, `socks4a`, `socks5`, `socks5h`
- `ytdlp_video_resolution` must be `default` or one of: `360`, `480`, `720`, `1080`, `2160`
- executable paths cannot be empty
- `media_path` and `cache_path` cannot be empty when provided
- `stage_vocals_volume_default` must be between `0.0` and `1.0`

Notes:
- Updating `media_path`/`cache_path` applies immediately for processing and new outputs.
- Static file mounts are initialized at app startup; restart the app after path changes so serving mounts align with new paths.
- `ytdlp_proxy_url` applies to yt-dlp operations and lyrics-provider outbound requests.
- `ytdlp_deno_path` applies to yt-dlp search, metadata, and download commands for videos that require external JavaScript execution.
- `ytdlp_video_resolution` applies to yt-dlp video and progressive video+audio downloads by adding a resolution sort cap such as `-S "res:720"` when a cap is selected.

---

### Demucs Service Job API
The main app's `DemucsClient` posts karaoke audio to the separate Demucs microservice with optional lyric-alignment fields:

- `lyrics_text` and `lyrics_format` when the request includes lyrics
- `transcription_model`
- `align_language`
- `detect_language`
- `use_synced_lyrics`
- `whisperx_preload_models`
- `compute_type` when provided by the caller

The Demucs service response ZIP still contains the standard `no_vocals` and `vocals` stems. When lyrics were supplied and alignment succeeded, it also includes:

- `aligned_lyrics.json`

`metadata.json` inside the ZIP records the same file list for downstream consumers.

The preferred path is `GET /jobs/{job_id}/events`, which streams the same job state over SSE as a
single long-lived connection. The main app uses that stream for live progress, then fetches
`GET /jobs/{job_id}/result` after the terminal event and still calls `DELETE /jobs/{job_id}/artifacts`
after it has durably stored the returned stems. If the stream is unavailable, the client falls back
to polling `GET /jobs/{job_id}` on the cadence controlled by `demucs_poll_interval_seconds`.
Job create/status/SSE payloads include backward-compatible `progress_percent` and `progress_message`
fields plus optional `progress_stage` and `progress_mode` fields. `progress_stage="demucs"` uses
determinate Demucs subprocess progress capped at 90 until separation exits. `progress_stage="whisperx"`
uses checkpoint messages such as `whisperx_loading_audio`, `whisperx_loading_model`,
`whisperx_detecting_language`, `whisperx_loading_alignment_model`, and `whisperx_aligning_lyrics`;
checkpoint messages use `progress_mode="indeterminate"` until actual alignment begins.
After the main app has durably committed the returned stems or aligned lyrics locally, it can call
`DELETE /jobs/{job_id}/artifacts` to remove the corresponding retained remote `incoming/` and `output/`
directories. This is separate from cancellation so failed jobs can keep their artifacts for later diagnosis.
The remote service also exposes `GET /io` for a current scratch-space size snapshot and
`DELETE /io` for a bulk cleanup pass once no jobs are active.

The Demucs service reads its own configuration from environment variables and from
`demucs_svc/.env` by default. `DEMUCS_IO_ROOT` controls the scratch root used for `incoming/` and
`output/`; it defaults to `demucs_svc/io`. Set `DEMUCS_ENV_FILE` if you want the service to read a
different `.env` file without affecting the main app config. If `DEMUCS_API_KEY` is set, the
service requires `X-API-Key` on all request paths except the plain `/transfer` HTML page.

For existing guide vocals, the main app can use the Demucs align-only job API:

- `POST /align-jobs` uploads a vocals/audio file plus `lyrics_text`, `lyrics_format`, and the same WhisperX settings fields.
- `GET /jobs/{job_id}` returns the same status payload used by separation jobs.
- `GET /align-jobs/{job_id}/result` returns `aligned_lyrics.json` directly.
- `DELETE /jobs/{job_id}` cancels the alignment job when it is still active.
- `DELETE /jobs/{job_id}/artifacts` deletes retained terminal-job IO once the caller no longer needs it.
- `GET /io` reports the current size of the remote Demucs IO workspace.
- `DELETE /io` removes all retained Demucs scratch files after the caller verifies that no jobs are active.

When alignment runs on unsynced plain-text lyrics, newline-separated lines are preserved as separate
display segments in the rebuilt `aligned_lyrics.json`, while WhisperX still receives a single
flattened transcript segment for alignment.

### Demucs Observability and Maintenance

The remote Demucs service also exposes:

- `GET /metrics`
  - fast JSON snapshot for curl and monitoring
  - includes current active and running job counts
  - includes VRAM snapshot when CUDA is available
  - includes last GC metadata
- `POST /gc?mode=adaptive`
  - conservative memory cleanup endpoint
  - `adaptive` avoids full model unload while jobs are still running
  - `partial`, `cuda`, and `full` are available for operator use

### Transfer Bench

The standalone Demucs host also serves a small throughput-testing page and helper endpoints:

- `GET /transfer`
  - browser page with a multipart upload form, a download button, a progress bar, and CLI examples
  - when `DEMUCS_API_KEY` is configured, the page keeps working but the browser must send `X-API-Key`
    with the upload and download requests
- `POST /transfer/upload`
  - multipart upload endpoint for browser testing
  - the service reads the uploaded bytes and discards them immediately
- `POST /transfer/upload/raw`
  - raw-body upload endpoint for `curl` and `wget`
  - accepts arbitrary request bodies and discards them immediately
- `GET /transfer/download/random-25mb`
  - lazily generates a cached 25 MiB random file on first request
  - reuses the cached file on later requests so repeated downloads test transfer speed instead of file generation

Example commands:

```bash
curl -F "file=@/path/to/media.bin" "http://127.0.0.1:8001/transfer/upload"
curl -X POST --data-binary "@/path/to/media.bin" "http://127.0.0.1:8001/transfer/upload/raw"
curl -OJ "http://127.0.0.1:8001/transfer/download/random-25mb"
wget --method=POST --body-file=/path/to/media.bin -O - "http://127.0.0.1:8001/transfer/upload/raw"
wget -O random-25mb.bin "http://127.0.0.1:8001/transfer/download/random-25mb"
curl -H "X-API-Key: $DEMUCS_API_KEY" -F "file=@/path/to/media.bin" "http://127.0.0.1:8001/transfer/upload"
```

At startup the service logs a healthy or degraded readiness summary, and WhisperX preload
failures are logged with the exception details so missing Demucs dependencies are visible in the
terminal immediately.

The admin settings page proxies a manual Demucs GC action through `/api/settings/demucs/gc`.

---

### Get Demucs Health
```
GET /api/settings/demucs-health
```

Returns current Demucs health for configured API URL.

**Response:**
```json
{
  "api_url": "http://10.10.120.191:8001",
  "healthy": true,
  "detail": "Demucs service is healthy"
}
```

---

### Preload WhisperX Models
```
POST /api/settings/whisperx/preload
```

Admin-only endpoint that asks the remote Demucs host to ensure the requested WhisperX models are downloaded and cached in memory.

**Request Body:**
```json
{
  "whisperx_preload_models": "transcription=tiny,align=en,fr"
}
```

If the payload is omitted or blank, the server uses the current runtime preload list.

**Response:**
```json
{
  "requested_models": "transcription=tiny,align=en,fr",
  "device": "cuda",
  "compute_type": null,
  "loaded_entries": [
    "transcription=tiny",
    "align=en",
    "align=fr"
  ],
  "detail": "Preloaded 3 WhisperX model entries"
}
```

The separate Demucs service exposes the underlying worker endpoint at `POST /whisperx/preload` and uses the same preload-list grammar.

---

### Get yt-dlp Version
```
GET /api/settings/ytdlp/version
```

Returns the version from `yt-dlp --version` using current configured `ytdlp_path`.

**Response:**
```json
{
  "version": "2026.03.15",
  "binary_path": "/home/user/.venv/bin/yt-dlp"
}
```

---

### Update yt-dlp
```
POST /api/settings/ytdlp/update
```

Runs `yt-dlp -U` for release-binary installs and falls back to an in-environment package update when yt-dlp reports a pip/wheel-managed install.

**Response:**
```json
{
  "before_version": "2026.03.01",
  "after_version": "2026.03.15",
  "updated": true,
  "detail": "Updated yt-dlp to stable@2026.03.15 from stable@2026.03.01"
}
```

If already current:

```json
{
  "before_version": "2026.03.15",
  "after_version": "2026.03.15",
  "updated": false,
  "detail": "yt-dlp is up to date (stable@2026.03.15)"
}
```

---

## Queue Item Status Values

- `pending`: Waiting to be processed
- `downloading`: Downloading from YouTube
- `processing`: Processing (vocal removal and media remux)
- `ready`: Ready to play
- `playing`: Currently playing
- `failed`: Processing failed (check `error` field)

---

## Pages

### Queue Page (Mobile)
```
GET /queue
```

Mobile-friendly page for searching and queueing songs.

### Queue Lyrics Viewer (Mobile/Desktop)
```
GET /queue/lyrics
```

Dedicated current-song lyrics viewer page:
- synced lyrics mode with active-line highlight + follow-live behavior
- unsynced lyrics mode with standard free scrolling
- empty-state fallback when no lyrics sidecar is available

### Stage View Page (Presentation Output)
```
GET /stage
```

Presentation-first stage player optimized for fullscreen output on desktop and mobile desktop mode.
Uses minimal overlay controls (play/pause, skip, fullscreen) and compact up-next context.

When the current item includes `vocals_path`, stage playback uses sidecar dual-track mixing:
- base media from `media_path`
- optional guide vocals from `vocals_path`
- real-time vocals on/off + volume control synchronized over websocket
- manual Resync performs a hard local relock for browsers that drift between the separate media clocks

### Settings Page (Mobile/Desktop)
```
GET /settings
```

Responsive settings UI for runtime configuration.

### Upload Page (Mobile/Desktop)
```
GET /upload
```

Media-library upload form. The client-side **Autopilot** action does not submit the form; it sequences the existing upload controls by inferring filename metadata, enabling AI karaoke and lyrics sync, resolving lyrics, and enabling WhisperX alignment so the user can review before uploading.

---

## Error Responses

All endpoints return standard HTTP status codes:

- `200`: Success
- `400`: Bad request
- `404`: Not found
- `500`: Server error

Error response format:
```json
{
  "detail": "Error message"
}
```
