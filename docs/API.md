# API Documentation

## Base URL
```
http://localhost:8000
```

## Endpoints

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
  "youtube_id": "dQw4w9WgXcQ",
  "title": "Song Title",
  "artist": "Artist Name",
  "is_karaoke": true,
  "burn_lyrics": true,
  "status": "pending",
  "media_path": null,
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
    "youtube_id": "dQw4w9WgXcQ",
    "title": "Song Title",
    "artist": "Artist Name",
    "is_karaoke": true,
    "burn_lyrics": true,
    "status": "ready",
    "media_path": "/path/to/video.mp4",
    "error": null,
    "created_at": "2024-01-01T00:00:00"
  }
]
```

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

Marks the currently playing item as `completed` and promotes the next `ready` item to `playing`.

**Response:**
- Queue item object for the newly playing item, or `null` if no next item is available.

---

### Complete Current Item
```
POST /api/queue/complete-current
```

Marks the currently playing item as `completed` and promotes the next `ready` item to `playing`.
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

**Response:**
```json
{
  "demucs_api_url": "http://10.10.120.191:8001",
  "demucs_healthy": false,
  "demucs_health_detail": "Health check pending",
  "ffmpeg_preset": "superfast",
  "ffmpeg_crf": 23,
  "ytdlp_path": "/home/user/.venv/bin/yt-dlp",
  "ffmpeg_path": "/usr/bin/ffmpeg"
}
```

---

### Update Runtime Settings
```
PATCH /api/settings/
```

Updates runtime settings immediately for new requests while the app is running.

**Request Body (partial update supported):**
```json
{
  "demucs_api_url": "http://127.0.0.1:9001",
  "ffmpeg_preset": "veryfast",
  "ffmpeg_crf": 23,
  "ytdlp_path": "yt-dlp",
  "ffmpeg_path": "ffmpeg"
}
```

Validation:
- `ffmpeg_preset` must be one of FFmpeg preset values (`ultrafast` ... `veryslow`)
- `ffmpeg_crf` must be between `0` and `51`
- executable paths cannot be empty

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

## Queue Item Status Values

- `pending`: Waiting to be processed
- `downloading`: Downloading from YouTube
- `processing`: Processing (vocal removal, subtitle burn)
- `ready`: Ready to play
- `playing`: Currently playing
- `completed`: Finished playing
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
