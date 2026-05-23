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
  - `stage_time_update` with `{current_time, is_paused, source}`

Event delivery is role-based:
- `queue` clients receive queue lifecycle, presence, and low-frequency stage state/control events.
- `stage` clients receive queue lifecycle plus stage state/control/clock events.
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

The stage page sends this message from the active media element so lyrics viewers can follow the authoritative playback clock instead of a local timer.
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
  "lyrics_format": "lrc"
}
```

Queue payload can identify the target with either:
- `youtube_id` (existing behavior), or
- `media_item_id` (for direct enqueue of local library search matches).
- `queue_as_name` is optional and admin-only. When provided by an authenticated admin session, it overrides the displayed requester label for that queued item.

If the `youtube_id` already exists in `media_items` with a usable local media file, the queue item is created against that existing media row and processing reuses the stored file instead of re-downloading the video again.
When `lyrics_text` is supplied for karaoke items, the app persists it as a reusable lyrics sidecar under the cache directory so karaoke processing can skip a second lookup. `lyrics_format` is optional; if omitted, the app infers `.lrc` when timestamped lines are present and `.txt` otherwise.

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

Uploads a local media file into the library. The request is multipart form data.

**Form Fields:**
- `file` (required): MP3, MP4, WebM, MKV, MOV, AVI, or M4V file
- `title` (required): media title
- `artist` (optional): media artist
- `add_to_queue` (optional, default `true`): queue the uploaded media after saving
- `is_karaoke` (optional, default `false`): request karaoke processing for the queued item when `add_to_queue` is true
- `lyrics_text` (optional): lyrics text to persist as a reusable sidecar
- `lyrics_format` (optional): `lrc` or `txt`; inferred from text when omitted by queue/service paths

**Response:**
```json
{
  "status": "ok",
  "media_id": 1,
  "filename": "artist-song.mp4",
  "queued": true,
  "queue_item_id": 10,
  "lyrics_path": "/cache/lyrics/artist-song.lrc"
}
```

When `lyrics_text` is supplied, the uploaded media row stores `lyrics_path` immediately, even when the item is not queued. Upload and media-edit lyrics are saved beside the media file as `<filename>.lrc` or `<filename>.txt` so library scans can rediscover them.

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
  "lyrics_text": "[00:01.00]Line 1",
  "lyrics_format": "lrc"
}
```

`lyrics_text` and `lyrics_format` are optional. When `lyrics_text` is supplied, the media row stores a reusable media-adjacent lyrics sidecar and returns its path in the summary.

**Response:**
```json
{
  "status": "ok",
  "summary": {
    "renamed_files": 3,
    "target_stem": "new-title-new-artist"
  }
}
```

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
  - `.json` files (validated/normalized cue payloads)
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
The endpoint now creates or reuses a durable processing task and starts it in the background.

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

**Response:**
```json
{
  "status": "processing",
  "media_id": 42,
  "task_id": 17
}
```

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
  "ffmpeg_preset": "superfast",
  "ffmpeg_crf": 23,
  "concurrent_ytdlp_search_enabled": false,
  "lyrics_provider_netease_enabled": true,
  "lyrics_provider_lrclib_enabled": true,
  "media_path": "/mnt/karaoke_media",
  "cache_path": "/mnt/karaoke_cache",
  "ytdlp_path": "/home/user/.venv/bin/yt-dlp",
  "ytdlp_proxy_url": "socks5://127.0.0.1:1080",
  "ffmpeg_path": "/usr/bin/ffmpeg"
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
  "ffmpeg_preset": "veryfast",
  "ffmpeg_crf": 23,
  "concurrent_ytdlp_search_enabled": true,
  "lyrics_provider_netease_enabled": false,
  "lyrics_provider_lrclib_enabled": true,
  "media_path": "/mnt/karaoke_media",
  "cache_path": "/mnt/karaoke_cache",
  "ytdlp_path": "yt-dlp",
  "ytdlp_proxy_url": "",
  "ffmpeg_path": "ffmpeg"
}
```

Validation:
- `ffmpeg_preset` must be one of FFmpeg preset values (`ultrafast` ... `veryslow`)
- `ffmpeg_crf` must be between `0` and `51`
- `demucs_device` must be `cuda` or `cpu`
- `demucs_output_format` must be `wav` or `mp3`
- `demucs_mp3_bitrate` must be between `64` and `320`
- `concurrent_ytdlp_search_enabled` toggles optional parallel search mode
- `lyrics_provider_netease_enabled` toggles NetEase in concurrent lyrics fallback
- `lyrics_provider_lrclib_enabled` toggles LRCLib in concurrent lyrics fallback
- `ytdlp_proxy_url` must be empty or use one of: `http`, `https`, `socks4`, `socks4a`, `socks5`, `socks5h`
- executable paths cannot be empty
- `media_path` and `cache_path` cannot be empty when provided

Notes:
- Updating `media_path`/`cache_path` applies immediately for processing and new outputs.
- Static file mounts are initialized at app startup; restart the app after path changes so serving mounts align with new paths.
- `ytdlp_proxy_url` applies to yt-dlp operations and lyrics-provider outbound requests.

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

Runs `yt-dlp -U` and returns before/after version comparison.

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
