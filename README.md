# Karaoke App

Lightweight AI-powered karaoke application for home use.

## Features

- **Mobile Queue Page**: Search YouTube, add songs to queue
- **Stage Page**: Auto-play queue with karaoke mode
- **Karaoke Mode**: Vocal removal + burned-in lyrics
- **Non-Karaoke Mode**: Play original videos
- **Real-time Queue Updates**: WebSocket push with polling fallback

## Requirements

- Python 3.11+
- `uv` for dependency management
- `yt-dlp` for YouTube downloads
- `ffmpeg` for video processing
- Demucs service for vocal separation (separate machine)

## Setup

1. **Install uv** (if not already installed):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. **Clone and navigate**:
```bash
cd /home/kevin/Documents/karaoke
```

3. **Create environment and install dependencies**:
```bash
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
```

4. **Install system dependencies**:
```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# Install yt-dlp
pip install yt-dlp
```

5. **Configure environment**:
```bash
cp .env.example .env
# Edit .env with your settings
```
For faster karaoke rendering, tune:
- `FFMPEG_PRESET` (default `veryfast`; faster options include `superfast`, `ultrafast`)
- `FFMPEG_CRF` (default `23`; higher is faster/smaller but lower quality)

6. **Initialize database**:
Database is created automatically on first run.

## Running

### Development mode
```bash
uv run python main.py
```

Or with uvicorn directly:
```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload --reload-exclude 'logs/*' --reload-exclude '*.log' --reload-exclude '*.log.*'
```

### Production mode
```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

## Usage

1. **Queue Page** (Mobile): Open `http://<server-ip>:8000/queue`
   - Search for songs (local library full-text on title/artist + YouTube in parallel)
   - Or paste a YouTube link / video id directly to add external search results
   - Local matches are preferred in results; duplicate YouTube matches are hidden
   - Toggle "Karaoke mode" checkbox
   - Optionally toggle "Burn lyrics" (enabled only in karaoke mode)
   - Add to queue
   - Use remote stage controls, including lyrics on/off, for the currently playing item
    - Queue status updates in real time (downloading, processing, ready, playing, failed)
   
2. **Stage View Page** (Desktop / Mobile Desktop Mode): Open `http://<server-ip>:8000/stage`
    - Presentation-first stage output with fullscreen-optimized player
    - Minimal controls overlay (play/pause, skip, resync, fullscreen)
    - Toggle the lyrics overlay on or off while playback is running
    - Compact "up next" chips without queue-management actions
    - Auto-advances when song ends
   - Receives queue/control updates via WebSocket (`/api/queue/ws`) without periodic polling

3. **Settings Page** (Mobile/Desktop): Open `http://<server-ip>:8000/settings`
       - View current runtime settings
       - Update Demucs URL, FFmpeg preset/CRF, media/cache paths, tool paths, and yt-dlp proxy URL
      - Enable/disable concurrent yt-dlp search mode
      - Check current yt-dlp version and run in-place update (`yt-dlp -U`) from UI
      - Apply settings immediately without restarting the app (for processing/runtime behavior)
       - Persist changes to the database so settings survive app reloads and restarts
       - View real-time Demucs engine health (online/offline with detail)

4. **Media Library Page** (Mobile/Desktop): Open `http://<server-ip>:8000/media`
      - Browse existing media entries in responsive card/table layouts
      - View title, artist, and capability badges (multi-track, lyrics)
      - Use placeholder UI actions for rename, delete, and add-to-queue flows (integration-ready template variables)

When concurrent yt-dlp search is enabled:
- Query without `karaoke` triggers two parallel searches: `<query>` and `<query> karaoke`
- Query containing `karaoke` uses single-search mode
- Combined results are staggered/interleaved and de-duplicated by video id

When karaoke mode is enabled:
- `Burn lyrics` ON: app fetches real lyrics from LRCLIB and burns subtitles.
- `Burn lyrics` OFF: app skips lyric burn and uses faster remux with vocals-removed audio.
- If Demucs is offline/unhealthy, karaoke processing fails fast and queue UI disables karaoke toggles.

## API Endpoints

See [docs/API.md](docs/API.md) for full API documentation.

### Real-time endpoint

- WebSocket: `/api/queue/ws`
  - Server heartbeat: `ping`
  - Client response: `pong`
  - Queue events: `queue_item_added`, `queue_item_updated`, `queue_item_removed`, `queue_cleared`, `current_item_changed`, `queue_item_failed`
  - Stage control events: `stage_control_command`, `stage_state_update`
  - Client command message: `stage_command` (`play`, `pause`, `skip`)

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for system design details.

## Development

### Running tests
```bash
uv run pytest
```

### With coverage
```bash
uv run pytest --cov=. --cov-report=html
```

### Logging
The app uses centralized Python logging with:
- Console output
- Rotating file logs

Configure via `.env`:
- `LOG_LEVEL` (e.g. `DEBUG`, `INFO`, `WARNING`, `ERROR`)
- `LOG_DIR` (default `./logs`)
- `LOG_FILE_NAME` (default `karaoke.log`)
- `LOG_MAX_BYTES` (default `5242880`)
- `LOG_BACKUP_COUNT` (default `5`)
- `LOG_TO_FILE_IN_RELOAD` (default `false`)

Example:
```bash
LOG_LEVEL=DEBUG
LOG_DIR=./logs
```

Logs are written to `${LOG_DIR}/${LOG_FILE_NAME}` and rotated automatically.

Hot reload note: by default file logging is disabled while running under reload mode to prevent log-write reload loops. Set `LOG_TO_FILE_IN_RELOAD=true` only if needed.

## Project Structure

```
karaoke/
├── main.py                 # FastAPI app entry point
├── config.py              # Configuration
├── models.py              # Data models
├── database.py            # Database setup
├── routes/                # API routes
│   ├── queue.py          # Queue endpoints
│   ├── search.py         # Search endpoints
│   └── pages.py          # HTML pages
├── services/              # Business logic
│   ├── queue_service.py
│   ├── youtube_service.py
│   ├── lyrics_service.py
│   ├── karaoke_service.py
│   └── demucs_client.py
├── adapters/              # External tool wrappers
│   ├── ytdlp.py
│   └── ffmpeg.py
├── templates/             # HTML templates
├── static/                # CSS/JS
└── tests/                 # Test files
```

## Troubleshooting

### yt-dlp issues
```bash
# Update yt-dlp
pip install --upgrade yt-dlp
```

For karaoke mode, this app downloads source audio directly from yt-dlp formats (instead of yt-dlp ffmpeg postprocessing), which avoids `ffprobe/ffmpeg not found` during the audio-download step.
The downloader uses progressive fallback for unavailable formats and logs expected format-unavailable fallbacks at `INFO` level to reduce warning noise.
Runtime proxy is supported through settings (`yt-dlp Proxy URL`) and applied to both search and download commands.
Supported schemes: `http`, `https`, `socks4`, `socks4a`, `socks5`, `socks5h`.
Leave proxy empty for direct connections.

Manual yt-dlp debugging commands (replace `VIDEO_ID`):

```bash
# Inspect available formats
yt-dlp -F "https://www.youtube.com/watch?v=VIDEO_ID"

# Karaoke mode: separate video-only file
yt-dlp "https://www.youtube.com/watch?v=VIDEO_ID" \
  -f "bestvideo[ext=mp4]/best[ext=mp4]/bestvideo/best" \
  --extractor-args "youtube:player_client=web" \
  --no-playlist \
  -o "/tmp/karaoke_media/VIDEO_ID.%(ext)s"

# Karaoke mode: separate audio-only file
yt-dlp "https://www.youtube.com/watch?v=VIDEO_ID" \
  -f "bestaudio[ext=m4a]/bestaudio/best" \
  --extractor-args "youtube:player_client=web" \
  --no-playlist \
  -o "/tmp/karaoke_media/VIDEO_ID.%(ext)s"

# Non-karaoke mode: single progressive file (video+audio)
yt-dlp "https://www.youtube.com/watch?v=VIDEO_ID" \
  -f "best[ext=mp4]/best" \
  --extractor-args "youtube:player_client=web" \
  --no-playlist \
  -o "/tmp/karaoke_media/VIDEO_ID.%(ext)s"

# Last-resort default selection (lets yt-dlp choose)
yt-dlp "https://www.youtube.com/watch?v=VIDEO_ID" \
  --no-playlist \
  -o "/tmp/karaoke_media/VIDEO_ID.%(ext)s"
```

If you want to manually test via proxy, add:

```bash
--proxy "socks5://127.0.0.1:1080"
```

### ffmpeg issues
```bash
# Check ffmpeg installation
ffmpeg -version
```
`ffmpeg` is still required for karaoke subtitle burn and final video rendering.

### Demucs service not available
Karaoke mode requires Demucs service running. Configure `DEMUCS_API_URL` in `.env`.

### WebSocket troubleshooting

- If real-time updates are unavailable, the queue page automatically falls back to periodic polling.
- Stage view (`/stage`) is WebSocket-first and reconnects automatically for real-time updates/control.
- Verify reverse proxy/network path allows WebSocket upgrade requests to `/api/queue/ws`.

### Remote Demucs (Windows + NVIDIA)
Use your Windows project venv/service path:

```powershell
cd C:\Users\hubcc\Documents\Projects\karaoke\demucs_svc
C:\Users\hubcc\Documents\Projects\karaoke\.venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8001
```

Then verify from Linux host:

```bash
curl http://10.10.120.191:8001/health
```

## License

MIT
