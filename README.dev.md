# Karaoke App

Lightweight AI-powered karaoke application for home use.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Setup](#setup)
- [Running](#running)
  - [Development mode](#development-mode)
  - [Production mode](#production-mode)
  - [Reverse proxy subpath](#reverse-proxy-subpath)
- [Usage](#usage)
  - [Language switching](#language-switching)
  - [Frontend i18n Development](#frontend-i18n-development)
- [API Endpoints](#api-endpoints)
- [Architecture](#architecture)
- [Development](#development)
  - [Running tests](#running-tests)
  - [Debug logging](#debug-logging)
  - [Test title inference from CLI](#test-title-inference-from-cli)
  - [Lyrics provider debug CLI](#lyrics-provider-debug-cli)
  - [With coverage](#with-coverage)
  - [Logging](#logging)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
  - [yt-dlp issues](#yt-dlp-issues)
  - [ffmpeg issues](#ffmpeg-issues)
  - [Separation service not available](#separation-service-not-available)
  - [WebSocket troubleshooting](#websocket-troubleshooting)
  - [Remote Demucs (Windows + NVIDIA)](#remote-demucs-windows--nvidia)
- [License](#license)

## Features

- **Mobile Queue Page**: Search YouTube, add songs to queue
- **Stage Page**: Auto-play queue with karaoke mode
- **Karaoke Mode**: Vocal removal + optional sidecar lyrics overlay
- **Queue Lyrics Viewer**: Phone-friendly lyrics page for the currently playing song (synced + unsynced, line-based cues, aligned JSON preferred when AI karaoke returns it)
- **Subtitle Workflow**: Admin-only ASS/Aegisub, SRT/SubtitleEdit, and TTML-to-JSON import workflow for round-tripping synced JSON lyrics
- **Non-Karaoke Mode**: Play original videos
- **Real-time Queue Updates**: WebSocket push with polling fallback
- **Mobile-Friendly Reconnects**: Lifecycle-aware websocket recovery on queue, lyrics, and stage pages for faster return after backgrounding or screen-off on mobile browsers
- **Live Queue Presence**: Queue page shows active guests and join toasts in real time
- **Frontend Language Switching**: English and Simplified Chinese UI labels with a header selector

## Requirements

- Python 3.11+
- `uv` for dependency management
- `yt-dlp` for YouTube downloads
- Optional: Deno for yt-dlp external JavaScript execution on videos that require it
- `ffmpeg` for video processing
- Separation service with Demucs or CPU-only Sherpa+Spleeter (separate machine or CPU host)

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
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload --reload-exclude '.venv' --reload-exclude 'logs/*' --reload-exclude '*.log' --reload-exclude '*.log.*'
```

### Production mode
```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

For Docker, systemd, and Windows deployment notes, including optional Deno support for yt-dlp external JavaScript execution, see [docs/deployment.md](docs/deployment.md).

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
     - Choose **AI Karaoke Processing** and enable **Lyrics** to reveal the prominent WhisperX word-alignment toggle, title/artist inputs, manual search, a Google search link, an editable lyrics box, lyrics file upload, and an optional WhisperX language override before adding to queue; resolved metadata is saved back into the media entry before queueing
     - Confirm to add to queue
     - Queue items show who requested them
      - Open **Lyrics Viewer** from the queue page to read current-song lyrics on phone/secondary display
     - Admins can use remote stage controls for any current song; guests can use them only while their own queued song is playing
     - Queue remote controls include `play/pause`, `skip`, `resync`, and a `+5` relative forward seek button handled by the active stage player
     - Admin queue controls can target connected stage displays, apply shared lyric presets, and adjust lyric text size/max width without changing each display's browser-local defaults
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
     - Fullscreen zen mode keeps the playbar, song metadata, overlays, and cursor hidden across manual skips and automatic song changes; press `Z` to toggle it
     - Always-on playback shell: queue items switch in-place without full page reload, so fullscreen is preserved during track transitions
     - Audio-only items such as MP3s use embedded album art as the stage background when available, with a branded fallback background otherwise
     - When the queue is empty, stage loops lobby media; when a song becomes playable, stage switches to it automatically and returns to lobby when queue drains
     - Responsive controls overlay: desktop adds a dedicated playback seek bar row, while mobile stays icon-first and moves detailed vocals volume adjustment to `/queue`
     - Toggle the lyrics overlay on or off while playback is running; vocal mix and lyrics visibility persist across song changes, and the centered karaoke-style overlay only appears in fullscreen so it does not block stage controls on mobile
     - Legacy MP3+G/CDG sidecars discovered from the media library render directly in the browser canvas instead of going through the timed-text lyrics pipeline
     - Desktop stage also includes keyboard shortcuts, lyrics-style customization, and a help icon: `←`/`→` seek 5 seconds, `R` resync, `V` vocals, `L` lyrics, `Q` QR, `?` help; the help panel stays open until you close it explicitly
     - Lyrics style settings are stored in the browser for quick per-device JSON download/apply/upload and include CJK-safe font presets, size, color, outline, line-window, animation options, and optional fullscreen background image/video media from `/media/...`, including a crop-style fill for aligned karaoke cues; admins can also manage shared lyric presets from the stage panel, name each stage display locally, receive targeted preset changes from `/queue`, and toggle the background video off directly without going through preset override
     - New `/stage` tabs auto-name themselves from device/platform and screen size with a short local id suffix until you set a custom display name
    - Compact "up next" chips without queue-management actions
    - Auto-advances when song ends
   - Receives queue/control updates via WebSocket (`/api/queue/ws`) without periodic polling

4. **Settings Page** (Mobile/Desktop): Open `http://<server-ip>:8000/settings`
       - Requires an admin session created by the server-managed admin login flow; settings management APIs are also admin-only
       - Settings are organized into collapsible **Karaoke Processing**, **WhisperX Lyrics**, **Application Paths**, **Downloads**, **Stage**, and **Tools** sections; each section links to the documentation homepage
       - View current runtime settings
       - Log out of the active admin session from the settings page
       - Update Demucs URL, direct-media cutoff, Demucs fallback poll interval, media/cache paths, tool paths, outbound proxy URL, and WhisperX alignment defaults
       - Optionally set a Demucs API key for WAN or CG-NAT deployments; when blank, the service stays open as before
       - Check the configured proxy egress IP, org, and city/country from the backend using `ipinfo.io/json`
       - Enable/disable concurrent yt-dlp search mode
       - Enable/disable concurrent lyrics providers (NetEase, LRCLib)
       - Configure WhisperX transcription model, alignment language, language detection, synced-lyrics mode, and preload list for Demucs-side lyric alignment
       - Use the WhisperX preload button to ask the remote Demucs host to download/cache the listed models on demand
       - Trigger a remote Demucs garbage-collection pass from the settings page when you want to reclaim GPU memory without shell access
       - Configure **Stage Lobby Media URL** (`/media/...` or `/cache/...`) for empty-queue loop playback
       - Configure the stage QR overlay URL for the fullscreen stage view; QR size and placement are adjusted per device on `/stage`
       - Configure the default vocals volume used when `/stage` or `/queue` loads after a restart
       - Optionally configure a Deno runtime path for yt-dlp external JavaScript execution
       - Check current yt-dlp version and update from UI; release binaries use `yt-dlp -U`, while pip/uv installs fall back to an in-environment package update
      - Apply settings immediately without restarting the app (for processing/runtime behavior)
       - Persist changes to the database so settings survive app reloads and restarts
       - View real-time Demucs engine health (online/offline with detail)

5. **Media Library Page** (Mobile/Desktop): Open `http://<server-ip>:8000/media`
          - Browse existing database-backed media entries in responsive card/table layouts
          - View title, artist, and capability badges (multi-track, lyrics)
          - Legacy MP3+G/CDG sidecars are discovered as lyrics sidecars and stored in `lyrics_path`
          - Local thumbnails prefer an adjacent same-name image sidecar (`.png`, `.jpg`, `.jpeg`, or `.webp`)
          - Local audio files reuse embedded album art by writing a durable adjacent thumbnail sidecar when cover art is available
          - Use **Add to Queue** to enqueue a local media row through the existing queue API
          - Guests can browse and queue items only; edit, scan, upload, and delete controls are admin-only
          - Admin users can use **Rename** to update title/artist in the database and optionally rename on-disk media/sidecar files
          - The edit modal can enable **AI Karaoke** for single-track media when Demucs is online; saving creates a monitored media-processing task, and WhisperX lyrics alignment can use a per-save language override
          - Existing multi-track items show AI Karaoke as enabled but locked, preventing duplicate separation work
          - Admin users can use **Refresh Sidecars** in the edit modal to rescan just one item's vocals and lyrics sidecars
          - Lyrics sidecars are classified by suffix: `.lrc` and `.txt` stay under the normal lyrics badge, while WhisperX word-aligned `.json` sidecars get a separate badge; legacy `.cdg` sidecars are treated as read-only display assets and do not unlock the text-lyrics editor
          - Admin users can open **Lossless Trim** from the edit modal to retain an intro/outro interval without re-encoding; video boundaries snap outward to I-frames and attached vocals/lyrics are shifted to the same interval, while CDG sidecars relabel the same entry point to **Transcode to MP4** and use the editor's fallback path instead
          - Admin users can open **Add Vocals** from the edit modal to prepare a vocal source from YouTube or upload, review the estimated sync offset, and commit a new guide-vocal sidecar
          - Admin users can open **Lyrics Editor** from the edit modal to export ASS or SRT subtitle files, edit them in Aegisub or SubtitleEdit, and import the result back into the canonical JSON lyrics sidecar; the subtitle workflow page also accepts TTML uploads on the fallback import path and converts them to JSON
          - Admin users can use **Delete** to remove the media row and any on-disk media/sidecar files; guest users do not see delete actions
          - Admin users can open the media edit modal file panel to download the main file or tracked sidecars individually, delete sidecars when they want to re-run processing, or download the whole package as a ZIP; missing tracked sidecars are hidden so the panel only shows real on-disk files
          - Admin users can trigger **Scan Library** to reconcile DB with filesystem on demand
          - App also performs one media-library scan on startup/restart

See [docs/lossless-trim-editor.md](docs/lossless-trim-editor.md) for supported
sidecars, FFmpeg behavior, and the destructive replacement contract.
See [docs/vocal-sync.md](docs/vocal-sync.md) for the Add Vocals workflow and offset semantics.

6. **Upload Page** (Mobile/Desktop): Open `http://<server-ip>:8000/upload`
        - Guest uploads are intentionally allowed so household users can add media without an admin session
        - Uploads are streamed into temporary files and installed atomically; media and selected ZIP contents default to a 2 GiB limit with 1 GiB of disk headroom reserved
        - Upload MP3, MP4, WebM, MKV, MOV, AVI, M4V, or ZIP bundles into the media library with title and artist metadata
        - Optionally search, paste, edit, or upload lyrics; saved lyrics are persisted as sidecars for later stage overlay use, the lyrics file picker accepts `.lrc`, `.txt`, or WhisperX `.json`, and WhisperX alignment can use a per-upload language override
        - Use **Autopilot** after selecting a media file to infer metadata, enable AI karaoke and lyrics sync, search lyrics, then turn on WhisperX alignment; it stops before upload so the result can be reviewed
        - **AI Karaoke** is available only while Demucs is online and can process uploads whether or not **Add to queue** is enabled
        - Queued AI uploads use the queue preparation task; non-queued AI uploads create a media-library karaoke task
        - If Demucs becomes unavailable during submission, the upload is still saved and optionally queued without karaoke processing
        - Keep the default checked **Add to queue** toggle enabled to enqueue the new media item after upload
        - Uploaded audio files write embedded album art to a durable adjacent thumbnail sidecar when present
        - ZIP uploads are treated as imports: the archive must contain one main audio/video file and may include matching `.vocals.*`, `.lrc` / `.json`, and `.png` / `.jpg` / `.jpeg` / `.webp` sidecars; unrelated files are ignored
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
   uv run ruff check adapters config.py database.py demucs_svc lyrics main.py models.py routes scripts services
   uv run python scripts/audit_i18n.py --check
   npm ci && npm run build:css
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
- If Musixmatch misses, NetEase, LRCLib, and any custom providers from `LYRICS_PROVIDER_CUSTOM_PATHS` run concurrently and the highest-scoring result wins.
- When Musixmatch returns synced LRC and a matching ISRC, the app optionally fetches a validated TTML upgrade from `LYRICS_TTML_STORAGE_URL`. The upgrade is bounded by a short timeout and never blocks the original LRC result; LRC remains the default and the lyrics editor shows a compact upgrade/restore toggle before WhisperX processing.
- Debug output shows the selected provider score plus provider-specific diagnostics for troubleshooting.
- The queue modal can pre-resolve lyrics, let users replace them with manual synced text, and persist those lyrics as sidecars when the item is queued. TTML upgrades are normalized to canonical JSON sidecars before persistence so rescans retain timed lyrics.
- See [docs/custom_lyrics_providers.md](docs/custom_lyrics_providers.md) for the runtime custom-provider contract and a HelloWorld example.
- See [custom_presets.md](custom_presets.md) for ready-to-use stage lyric presets, JSON settings, and an AI design prompt.

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
│   ├── lyrics_types.py
│   ├── lyrics_provider_loader.py
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
uv pip install --upgrade yt-dlp
# or, inside the same Python environment
python -m pip install --upgrade yt-dlp
```

For karaoke mode, this app downloads source audio directly from yt-dlp formats (instead of yt-dlp ffmpeg postprocessing), which avoids `ffprobe/ffmpeg not found` during the audio-download step.
The downloader uses explicit audio-only selectors first for karaoke audio downloads, so yt-dlp does not silently fall back to a video-only stream under the audio filename. It still uses progressive fallback for unavailable video formats and logs expected format-unavailable fallbacks at `INFO` level to reduce warning noise. Before the app sends any media file directly to Demucs, it checks for audio streams with ffprobe. If a YouTube-backed yt-dlp video fallback produces a video-only file, the app keeps that video for playback/remuxing but downloads a separate audio-only file for Demucs. Local non-YouTube files with no audio fail before Demucs with a clear no-audio-stream error. When you set a video resolution cap in Settings, the app adds yt-dlp's resolution sort flag, for example `-S "res:720"`, so downloads stay at or below the chosen height. Leave the setting at `Default` to keep the current behavior unchanged.
Some YouTube videos require yt-dlp's external JavaScript execution support. The Python dependency `yt-dlp-ejs` is included in this project, but the JavaScript runtime itself is optional. Install Deno and set **Deno path** in Settings, or set `YTDLP_DENO_PATH=/usr/local/bin/deno` in the environment. Leave it empty to keep the old command shape.
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

# When a video needs external JavaScript execution
yt-dlp --js-runtimes "deno:/usr/local/bin/deno" \
  "https://www.youtube.com/watch?v=VIDEO_ID" \
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

### Separation service not available
Karaoke mode requires `demucs_svc` running. Configure `DEMUCS_API_URL` for the main app and select
Demucs or Sherpa+Spleeter from `/settings`. See [Separation Backends](docs/separation-backends.md)
for CPU-only setup and model installation.
If you expose `demucs_svc` outside a trusted LAN, set the same optional `DEMUCS_API_KEY` on both
the main app and the Demucs service so requests carry `X-API-Key`.

### WebSocket troubleshooting

- If real-time updates are unavailable, the queue page automatically falls back to periodic polling.
- Stage view (`/stage`) is WebSocket-first and reconnects automatically for real-time updates/control.
- Verify reverse proxy/network path allows WebSocket upgrade requests to `/api/queue/ws`.

### Remote Demucs (Windows + NVIDIA)
Use your Windows project venv/service path:

```powershell
cd C:\Users\hubcc\Documents\Projects\karaoke\demucs_svc
C:\Users\hubcc\Documents\Projects\karaoke\.venv\Scripts\python.exe -m pip install -r requirements.txt
C:\Users\hubcc\Documents\Projects\karaoke\.venv\Scripts\python.exe .\download_sherpa_models.py --variant fp16
C:\Users\hubcc\Documents\Projects\karaoke\.venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8001
```

The worker has its own `requirements.txt` and can run independently of the main app's
environment. When launching from the repository root instead, use
`python -m demucs_svc.download_sherpa_models`; when the current directory is already
`demucs_svc`, use `python .\download_sherpa_models.py` as shown above.

Then verify from Linux host:

```bash
auth_header=()
if [ -n "$DEMUCS_API_KEY" ]; then
  auth_header=(-H "X-API-Key: $DEMUCS_API_KEY")
fi

curl "${auth_header[@]}" http://10.10.120.191:8001/health
curl "${auth_header[@]}" http://10.10.120.191:8001/metrics
```

## License

MIT
