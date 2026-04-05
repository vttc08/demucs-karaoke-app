# API Documentation

## Base URL
```
http://localhost:8000
```

## Endpoints

### Queue/Stage WebSocket
```
GET /api/queue/ws
```

WebSocket endpoint for real-time queue updates and stage control.

**Server heartbeat:**
- Server sends: `{"type":"ping","timestamp":...}`
- Client responds: `{"type":"pong","timestamp":...}`

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

**Server → client events (selected):**
- Queue lifecycle:
  - `queue_item_added`
  - `queue_item_updated`
  - `queue_item_removed`
  - `queue_cleared`
  - `current_item_changed`
  - `queue_item_failed`
- Stage control:
  - `stage_control_command` with `{command, source}`
  - `stage_state_update` with `{is_paused, source}`

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
    "video_id": "dQw4w9WgXcQ",
    "title": "Video Title",
    "channel": "Channel Name",
    "duration": "3:32",
    "thumbnail": "https://..."
  }
]
```

---

### Add to Queue
```
POST /api/queue/
```

**Request Body:**
```json
{
  "youtube_id": "dQw4w9WgXcQ",
  "title": "Song Title",
  "artist": "Artist Name",
  "is_karaoke": true,
  "burn_lyrics": true
}
```

`burn_lyrics` is optional and only applies when `is_karaoke` is true.
If omitted, it defaults to `true`. For non-karaoke items, it is normalized to `false`.

**Response:**
```json
{
  "id": 1,
  "media_id": 1,
  "position": 1000,
  "youtube_id": "dQw4w9WgXcQ",
  "title": "Song Title",
  "artist": "Artist Name",
  "is_karaoke": true,
  "burn_lyrics": true,
  "status": "pending",
  "media_path": "/media/dQw4w9WgXcQ.mp4",
  "lyrics_path": null,
  "vocals_path": null,
  "error": null,
  "created_at": "2024-01-01T00:00:00"
}
```

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
    "is_karaoke": true,
    "burn_lyrics": true,
    "status": "ready",
    "media_path": "/media/dQw4w9WgXcQ.mp4",
    "lyrics_path": null,
    "vocals_path": null,
    "error": null,
    "created_at": "2024-01-01T00:00:00"
  }
]
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

### Process Queue Item
```
POST /api/queue/{item_id}/process
```

Triggers background processing of a queue item.

**Response:**
```json
{
  "status": "processing",
  "item_id": 1
}
```

---

### Skip Current Item
```
POST /api/queue/skip
```

Removes the currently playing item from the active queue and promotes the next `ready` item to `playing`.

**Response:**
- Queue item object for the newly playing item, or `null` if no next item is available.

---

### Complete Current Item
```
POST /api/queue/complete-current
```

Removes the currently playing item from the active queue and promotes the next `ready` item to `playing`.
This endpoint is used by playback `ended` handling for automatic queue advance.

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
- executable paths cannot be empty
- `media_path` and `cache_path` cannot be empty when provided

Notes:
- Updating `media_path`/`cache_path` applies immediately for processing and new outputs.
- Static file mounts are initialized at app startup; restart the app after path changes so serving mounts align with new paths.

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
- `processing`: Processing (vocal removal, subtitle burn)
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

### Playback Page (TV)
```
GET /playback
```

TV display page for auto-playing queue.

### Stage View Page (Presentation Output)
```
GET /stage
```

Presentation-first stage player optimized for fullscreen output on desktop and mobile desktop mode.
Uses minimal overlay controls (play/pause, skip, fullscreen) and compact up-next context.

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
