# Karaoke App

Lightweight AI-powered karaoke application for home use.

## Features

- **Mobile Queue Page**: Search YouTube, add songs to queue
- **TV Playback Page**: Auto-play queue with karaoke mode
- **Karaoke Mode**: Vocal removal + burned-in lyrics
- **Non-Karaoke Mode**: Play original videos

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
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Production mode
```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

## Usage

1. **Queue Page** (Mobile): Open `http://<server-ip>:8000/queue`
   - Search for songs
   - Toggle "Karaoke mode" checkbox
   - Optionally toggle "Burn lyrics" (enabled only in karaoke mode)
   - Add to queue
   
2. **Playback Page** (TV): Open `http://<server-ip>:8000/playback`
   - Auto-plays current song
   - Shows upcoming queue
    - Auto-advances when song ends

3. **Settings Page** (Mobile/Desktop): Open `http://<server-ip>:8000/settings`
    - View current runtime settings
    - Update Demucs URL, FFmpeg preset/CRF, media/cache paths, and tool paths
    - Apply settings immediately without restarting the app (for processing/runtime behavior)
    - If media/cache paths are changed, restart the app so static file mounts use the new paths
    - View real-time Demucs engine health (online/offline with detail)

When karaoke mode is enabled:
- `Burn lyrics` ON: app fetches real lyrics from LRCLIB and burns subtitles.
- `Burn lyrics` OFF: app skips lyric burn and uses faster remux with vocals-removed audio.
- If Demucs is offline/unhealthy, karaoke processing fails fast and queue UI disables karaoke toggles.

## API Endpoints

See [docs/API.md](docs/API.md) for full API documentation.

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

For karaoke mode, this app now downloads source audio directly from yt-dlp formats (instead of yt-dlp ffmpeg postprocessing), which avoids `ffprobe/ffmpeg not found` during the audio-download step.
The downloader also retries with alternate YouTube clients (`web` then `ios`) and broader format fallbacks when strict formats are unavailable.

### ffmpeg issues
```bash
# Check ffmpeg installation
ffmpeg -version
```
`ffmpeg` is still required for karaoke subtitle burn and final video rendering.

### Demucs service not available
Karaoke mode requires Demucs service running. Configure `DEMUCS_API_URL` in `.env`.

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
