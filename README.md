# Karaoke App

Lightweight AI-powered karaoke application for home use.

## Features

- **Mobile Queue Page**: Search YouTube, add songs to queue
- **Stage Page**: Auto-play queue with karaoke mode
- **Karaoke Mode**: Vocal removal + optional sidecar lyrics overlay
- **Queue Lyrics Viewer**: Phone-friendly lyrics page for the currently playing song (synced + unsynced, line-based cues, aligned JSON preferred when AI karaoke returns it)
- **Non-Karaoke Mode**: Play original videos
- **Real-time Queue Updates**: WebSocket push with polling fallback
- **Live Queue Presence**: Queue page shows active guests and join toasts in real time
- **Frontend Language Switching**: English and Simplified Chinese UI labels with a header selector

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
Set `KARAOKE_BASE_PATH=/karaoke` only when a reverse proxy forwards requests with that prefix
preserved. Leave it empty to serve the app at `/`, which is the default and keeps existing local
URLs unchanged.

For faster karaoke rendering, tune:
- `FFMPEG_PRESET` (default `veryfast`; faster options include `superfast`, `ultrafast`)
- `FFMPEG_CRF` (default `23`; higher is faster/smaller but lower quality)

6. **Initialize database**:
Database is created automatically on first run.

7. **Create an admin user**:
Admin accounts are managed from the server, not from the browser. Create or reset an admin password
with:
```bash
uv run python scripts/admin_user.py create --username admin
```
The password is stored in SQLite as a PBKDF2-SHA256 hash with a random salt. The login page creates
a server-side admin session after successful authentication.

## Running

### Development mode
```bash
uv run python main.py
```
The dev entrypoint uses a finite graceful-shutdown timeout, so active SSE/WebSocket clients will not block Ctrl-C or hot reload forever.

Or with uvicorn directly:
```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload --reload-exclude 'logs/*' --reload-exclude '*.log' --reload-exclude '*.log.*'
```

### Production mode
```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

### Reverse proxy subpath

To serve the app from a subpath such as `/karaoke`, set:

```bash
KARAOKE_BASE_PATH=/karaoke
```

The proxy should preserve the prefix when forwarding, so upstream requests arrive as
`/karaoke/queue`, `/karaoke/api/queue/ws`, `/karaoke/static/...`, and `/karaoke/media/...`.
When this variable is unset, the app continues to serve `/queue`, `/stage`, `/api/...`, `/media/...`,
and `/static/...`.

## Usage

1. **Queue Page** (Mobile): Open `http://<server-ip>:8000/queue`
     - First-time guests see a dismissible stage-name prompt on the queue page instead of a blocking login page
     - Guests can skip naming and continue as a generated `Guest ####` name, or edit their name from the queue greeting
     - See who is currently on the queue page in a live roster, with a small toast when new guests join
     - Search for songs (local library full-text on title/artist + YouTube in parallel)
     - Use the library and upload shortcuts under search to browse local media or add your own files
     - Or paste a YouTube link / video id directly to add external search results
     - Local matches are preferred in results; duplicate YouTube matches are hidden
     - Tap **Add** on a YouTube result to open the queue configuration interaction
     - Tap **Add** on a local library result to enqueue it immediately as a local file
    - Choose **AI Karaoke Processing** and enable **Lyrics** to reveal title/artist inputs, manual search, a Google search link, an editable lyrics box, and lyrics file upload before adding to queue; resolved metadata is saved back into the media entry before queueing
     - Confirm to add to queue
     - Queue items show who requested them
      - Open **Lyrics Viewer** from the queue page to read current-song lyrics on phone/secondary display
     - Admins can use remote stage controls for any current song; guests can use them only while their own queued song is playing
     - Queue remote controls include `play/pause`, `skip`, `resync`, and a `+5` forward seek button driven by the live stage playback clock
     - When an admin queues a song as a live guest from the queue presence list, that guest becomes the owner for later stage controls and queue-item actions; manual typed queue-as names remain display-only
    - Admin users can clear queued songs, remove individual queued items, and move non-playing queue items up or down
    - Guest users can remove only their own non-playing queue items from the queue page
    - Queue status updates in real time (downloading, processing, ready, playing, failed)
   
2. **Queue Lyrics Viewer** (Mobile/Desktop): Open `http://<server-ip>:8000/queue/lyrics`
      - Dedicated lyrics companion view for the currently playing queue item
      - Synced `.lrc` / `.json` lyrics highlight and auto-follow playback time
      - Manual scrolling pauses auto-follow until **Follow live** is tapped
      - Unsynced `.txt` lyrics render as large, freely scrollable text
      - Optional simplified-Chinese and pinyin display toggles re-render Chinese lyrics only, leaving non-Chinese text unchanged
      - If no lyrics sidecar is present, the page shows title/artist plus a Google lyrics link

3. **Stage View Page** (Desktop / Mobile Desktop Mode): Open `http://<server-ip>:8000/stage`
     - Requires an admin session created by the server-managed admin login flow
     - Presentation-first stage output with fullscreen-optimized player
     - Always-on playback shell: queue items switch in-place without full page reload, so fullscreen is preserved during track transitions
     - Audio-only items such as MP3s use embedded album art as the stage background when available, with a branded fallback background otherwise
     - When the queue is empty, stage loops lobby media; when a song becomes playable, stage switches to it automatically and returns to lobby when queue drains
     - Responsive controls overlay: desktop adds a dedicated playback seek bar row, while mobile stays icon-first and moves detailed vocals volume adjustment to `/queue`
     - Toggle the lyrics overlay on or off while playback is running; vocal mix and lyrics visibility persist across song changes, and the overlay only appears in fullscreen so it does not block stage controls on mobile
     - Desktop stage also includes keyboard shortcuts and a help icon: `←`/`→` seek 5 seconds, `R` resync, `V` vocals, `L` lyrics, `Q` QR, `?` help; the help panel stays open until you close it explicitly
    - Compact "up next" chips without queue-management actions
    - Auto-advances when song ends
   - Receives queue/control updates via WebSocket (`/api/queue/ws`) without periodic polling

4. **Settings Page** (Mobile/Desktop): Open `http://<server-ip>:8000/settings`
       - Requires an admin session created by the server-managed admin login flow; settings management APIs are also admin-only
       - View current runtime settings
       - Log out of the active admin session from the settings page
       - Update Demucs URL, direct-media cutoff, Demucs poll interval, FFmpeg preset/CRF, media/cache paths, tool paths, outbound proxy URL, and WhisperX alignment defaults
       - Enable/disable concurrent yt-dlp search mode
       - Enable/disable concurrent lyrics providers (NetEase, LRCLib)
       - Configure WhisperX transcription model, alignment language, language detection, synced-lyrics mode, and preload list for Demucs-side lyric alignment
       - Use the WhisperX preload button to ask the remote Demucs host to download/cache the listed models on demand
       - Trigger a remote Demucs garbage-collection pass from the settings page when you want to reclaim GPU memory without shell access
       - Configure **Stage Lobby Media URL** (`/media/...` or `/cache/...`) for empty-queue loop playback
       - Check current yt-dlp version and run in-place update (`yt-dlp -U`) from UI
      - Apply settings immediately without restarting the app (for processing/runtime behavior)
       - Persist changes to the database so settings survive app reloads and restarts
       - View real-time Demucs engine health (online/offline with detail)

5. **Media Library Page** (Mobile/Desktop): Open `http://<server-ip>:8000/media`
         - Browse existing database-backed media entries in responsive card/table layouts
         - View title, artist, and capability badges (multi-track, lyrics)
          - Local audio files reuse embedded album art as the thumbnail when cached cover art is available
          - Use **Add to Queue** to enqueue a local media row through the existing queue API
          - Guests can browse and queue items only; edit, scan, upload, and delete controls are admin-only
          - Admin users can use **Rename** to update title/artist in the database and optionally rename on-disk media/sidecar files
          - The edit modal can enable **AI Karaoke** for single-track media when Demucs is online; saving creates a monitored media-processing task
          - Existing multi-track items show AI Karaoke as enabled but locked, preventing duplicate separation work
          - Admin users can use **Refresh Sidecars** in the edit modal to rescan just one item's vocals and lyrics sidecars
          - Admin users can open **Lossless Trim** from the edit modal to retain an intro/outro interval without re-encoding; video boundaries snap outward to I-frames and attached vocals/lyrics are shifted to the same interval
          - Admin users can use **Delete** to remove the media row and any on-disk media/sidecar files; guest users do not see delete actions
          - Admin users can trigger **Scan Library** to reconcile DB with filesystem on demand
          - App also performs one media-library scan on startup/restart

See [docs/lossless-trim-editor.md](docs/lossless-trim-editor.md) for supported
sidecars, FFmpeg behavior, and the destructive replacement contract.

6. **Upload Page** (Mobile/Desktop): Open `http://<server-ip>:8000/upload`
        - Upload MP3, MP4, WebM, MKV, MOV, AVI, or M4V files into the media library with title and artist metadata
        - Optionally search, paste, edit, or upload lyrics; saved lyrics are persisted as sidecars for later stage overlay use
        - **AI Karaoke** is available only while Demucs is online and can process uploads whether or not **Add to queue** is enabled
        - Queued AI uploads use the queue preparation task; non-queued AI uploads create a media-library karaoke task
        - If Demucs becomes unavailable during submission, the upload is still saved and optionally queued without karaoke processing
        - Keep the default checked **Add to queue** toggle enabled to enqueue the new media item after upload
        - Uploaded audio files generate cached cover thumbnails immediately when embedded album art is present
        - Successful uploads redirect to the media management page

7. **Access Restricted Page**: Open `http://<server-ip>:8000/access-restricted`
        - Static reverse-proxy gate page for users who are outside the approved home network
        - Explains the Wi-Fi / WAN IP check and common masking tools like iCloud Private Relay, Clash, and V2Ray

8. **Login Page**: Open `http://<server-ip>:8000/login`
        - Guest identification happens inline on the queue page.
        - Admins sign in with a server-created account stored in the local database.
        - Admin credentials cannot be created from the web UI.

### Language switching

The shared page header includes a language selector. The app currently supports English (`en`) and
Simplified Chinese (`zh-CN`) for frontend UI labels only. Song titles, artists, lyrics, filenames,
provider responses, and other backend content are shown as-is. The selected language is stored in a
`karaoke_locale` cookie and applies to server-rendered templates and dynamic frontend messages.

See [docs/internationalization.md](docs/internationalization.md) for adding another locale.

### Frontend i18n Development

When adding or modifying UI text in templates or JavaScript:

1. **Add strings to the English catalog** (`locales/en.json`):
   ```json
   {
     "action.queue_song": "Add to Queue",
     "status.loading": "Loading...",
     "error.upload_failed": "Upload failed"
   }
   ```

2. **Translate to all supported locales** (currently `zh-CN`):
   - Keep the same keys and placeholder format (`{key}`, `{count}`)
   - Only translate the value, never the key

3. **Use in templates** (Jinja2):
   ```html
   <button>{{ t("action.queue_song") }}</button>
   ```

4. **Use in JavaScript**:
   ```javascript
   const message = window.KaraokeI18n.t("status.loading", {item: title});
   ```

5. **Test before commit**:
   ```bash
   uv run pytest
   ```
   Tests verify that all keys exist in all locales, so missing translations will fail the build.

When concurrent yt-dlp search is enabled:
- Query without `karaoke` triggers two parallel searches: `<query>` and `<query> karaoke`
- Query containing `karaoke` uses single-search mode
- Combined results are staggered/interleaved and de-duplicated by video id

When karaoke mode is enabled:
- App removes vocals with Demucs and remuxes the output media into the media library root (no subtitle burn path).
- When lyrics are provided for karaoke processing, the Demucs sidecar flow can optionally run WhisperX forced alignment and stores an `aligned_lyrics.json` sidecar alongside the separated stems.
- Karaoke prep uses the direct-media cutoff to decide whether small video files go straight to Demucs or get converted to audio first; set it to `0` to always extract/download audio for video files, or raise it on a fast LAN to send more media files directly.
- Karaoke remuxes and vocals sidecars are served from `/media`, not `/cache`.
- Lyrics workflow remains available from the queue modal (provider resolve/manual upload), and lyrics are stored as sidecars for stage overlay display.
- If Demucs is offline/unhealthy, karaoke processing fails fast and queue UI disables karaoke toggles.

Lyrics lookup behavior:
- Musixmatch is tried first when configured.
- If Musixmatch misses, the remaining providers run concurrently and the highest-scoring result wins.
- Debug output shows the selected provider score plus provider-specific diagnostics for troubleshooting.
- The queue modal can pre-resolve lyrics, let users replace them with manual synced text, and persist those lyrics as sidecars when the item is queued.

## API Endpoints

See [docs/API.md](docs/API.md) for full API documentation.

### Real-time endpoint

- WebSocket: `/api/queue/ws`
  - Server heartbeat: `ping`
  - Client response: `pong`
  - Queue events: `queue_item_added`, `queue_item_updated`, `queue_item_progress`, `queue_item_removed`, `queue_cleared`, `current_item_changed`, `queue_item_failed`
  - Stage control events: `stage_control_command`, `stage_state_update`
  - Client command message: `stage_command` (`play`, `pause`, `skip`, `seek`, `resync`, vocals, lyrics)
  - Stage commands require an admin session unless the current queue item belongs to the guest sending the command

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for system design details.

## Development

### Running tests
```bash
uv run pytest
```

The route and service suites are split into focused modules so changes stay local:

- `tests/routes/` holds route/API groups
- `tests/services/` holds service groups
- `tests/test_routes.py` and `tests/test_services.py` are import shims for pytest discovery
- shared fixtures live in `tests/conftest.py`, `tests/routes/common.py`, and `tests/services/common.py`

Use `uv run` for Python commands in this workspace; bare `python` is not guaranteed to be on PATH.
See [docs/testing.md](docs/testing.md) for the module map.

### Debug logging
Set `LOG_LEVEL=DEBUG` in your local `.env` when you want to see `logger.debug(...)` output during
agent-assisted debugging. Switch it back to `INFO` when you're done.

### Test title inference from CLI
```bash
# Run against sample titles in lyrics/karaoke_titles.py
uv run scripts/lyrics_inference_cli.py --samples
# or: uv run python scripts/lyrics_inference_cli.py --samples

# Add custom titles
uv run scripts/lyrics_inference_cli.py --title "JAY CHOU (周杰伦) - PIAO YI (飄移)"

# Interactive mode
uv run scripts/lyrics_inference_cli.py --interactive
```
Set `LASTFM_API_KEY` in `.env` to enable online Last.fm-assisted inference; otherwise the CLI uses regex-only local inference.

### Lyrics provider debug CLI
```bash
uv run scripts/lyrics_debug_cli.py
```
Use this menu-driven helper to step through the bundled karaoke titles or paste a custom YouTube title, then inspect the inferred metadata, provider, and editable lyrics box.

NetEase implementation notes:
- Adapted from `cqjjjzr/MusicBee-NeteaseLyrics` (search + lyric flow) and `Gaohaoyang/netease-music-downloader` (lyrics retrieval endpoint behavior).
- Keeps a Python-native runtime path (no Node dependency in production provider flow).

### With coverage
```bash
uv run pytest --cov=. --cov-report=html
```

### Logging
The app uses centralized Python logging with:
- Console output
- Rotating file logs

Root logging is configured once at startup, and `LOG_LEVEL` controls whether debug calls are
emitted.

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
 │   ├── lyrics_inference.py
 │   ├── lyrics_providers.py
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
The downloader uses explicit audio-only selectors first for karaoke audio downloads, so yt-dlp does not silently fall back to a video-only stream under the audio filename. It still uses progressive fallback for unavailable video formats and logs expected format-unavailable fallbacks at `INFO` level to reduce warning noise. When you set a video resolution cap in Settings, the app adds yt-dlp's resolution sort flag, for example `-S "res:720"`, so downloads stay at or below the chosen height. Leave the setting at `Default` to keep the current behavior unchanged.
Runtime proxy is supported through settings (`yt-dlp Proxy URL`) and applied to:
- yt-dlp search/download commands
- lyrics provider requests (Musixmatch, NetEase, LRCLib, and Last.fm metadata lookup)
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
  -f "bestaudio[ext=m4a]/bestaudio" \
  --extractor-args "youtube:player_client=web" \
  --no-playlist \
  -o "/tmp/karaoke_media/VIDEO_ID.%(ext)s"

# Non-karaoke mode: single progressive file (video+audio)
yt-dlp "https://www.youtube.com/watch?v=VIDEO_ID" \
  -S "res:720" \
  -f "best[ext=mp4]/best" \
  --extractor-args "youtube:player_client=web" \
  --no-playlist \
  -o "/tmp/karaoke_media/VIDEO_ID.%(ext)s"

# Last-resort default selection (lets yt-dlp choose)
yt-dlp "https://www.youtube.com/watch?v=VIDEO_ID" \
  --no-playlist \
  -o "/tmp/karaoke_media/VIDEO_ID.%(ext)s"
```

To cap downloads from the UI, set **yt-dlp Video Resolution** to `360p`, `480p`, `720p`, `1080p`, or `2160p`. `Default` keeps the old behavior.

If you want to manually test via proxy, add:

```bash
--proxy "socks5://127.0.0.1:1080"
```

### ffmpeg issues
```bash
# Check ffmpeg installation
ffmpeg -version
```
`ffmpeg` is still required for karaoke media extraction/remux operations.

### Demucs service not available
Karaoke mode requires Demucs service running. Configure `DEMUCS_API_URL` for the main app and `UPSTREAM_DEMUCS_API_URL` for the stub in `.env`.

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
curl http://10.10.120.191:8001/metrics
```

If you run the local stub proxy on `localhost:8002`, keep `DEMUCS_API_URL=http://localhost:8002` for the main app and set `UPSTREAM_DEMUCS_API_URL=http://10.10.120.191:8001` for the stub.

## License

MIT
