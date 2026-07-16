# Main App Deployment Notes

This guide covers the lightweight karaoke main app only. Keep `demucs_svc/` on its own GPU-capable host and connect to it through `DEMUCS_API_URL`.

## Home Server Checklist

- Run the app behind a LAN-only address or a reverse proxy with explicit access rules.
- Persist the database, media, cache, and logs outside the app process or container.
- Install `ffmpeg` and keep `yt-dlp` current.
- Create the admin account from the server shell:

```bash
uv run python scripts/admin_user.py create --username admin
```

- Set `KARAOKE_BASE_PATH=/karaoke` only when the reverse proxy preserves that prefix upstream.
- Back up the SQLite database and media directory together, especially before large library scans or cleanup.

The app can run without Deno. Leave `YTDLP_DENO_PATH` blank until a video needs yt-dlp external JavaScript execution. When Deno is configured, the app adds:

```bash
--js-runtimes "deno:/path/to/deno"
```

to yt-dlp search, metadata, and download commands.

## Docker

No main-app Dockerfile is currently checked in. If you add one, keep the final image small and persist runtime data with volumes or bind mounts.

Example runtime environment:

```env
HOST=0.0.0.0
PORT=8000
DATABASE_URL=sqlite:////data/karaoke.db
MEDIA_PATH=/data/media
CACHE_PATH=/data/cache
LOG_DIR=/data/logs
YTDLP_PATH=yt-dlp
YTDLP_DENO_PATH=/usr/local/bin/deno
FFMPEG_PATH=ffmpeg
DEMUCS_API_URL=http://demucs-host:8001
DEMUCS_API_KEY=
KARAOKE_PROCESSING_MAX_WORKERS=2
KARAOKE_MAX_UPLOAD_BYTES=2147483648
KARAOKE_UPLOAD_MIN_FREE_BYTES=1073741824
```

If the Demucs host is protected, set the same key on both sides so the main app sends `X-API-Key`
on every request. Leave the value blank when the service is intentionally open on a trusted LAN.

Frontend CSS is generated and committed, so Node is not needed on the production host. After changing templates, JavaScript class strings, or `tailwind.config.js`, rebuild it in the development checkout:

```bash
npm ci
npm run build:css
```

The Demucs host has separate worker-local resource controls:

```dotenv
DEMUCS_MAX_CONCURRENT_JOBS=1
DEMUCS_MAX_UPLOAD_BYTES=2147483648
DEMUCS_MIN_FREE_BYTES=1073741824
```

### Bundle Deno In The Image

Use a multi-stage build and copy the Deno binary from a pinned official `denoland/deno:bin-*` image:

```dockerfile
# syntax=docker/dockerfile:1
FROM denoland/deno:bin-2.8.0 AS deno

FROM python:3.12-slim AS app
ENV UV_LINK_MODE=copy
ENV YTDLP_DENO_PATH=/usr/local/bin/deno
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=deno /deno /usr/local/bin/deno
WORKDIR /app
COPY . .
RUN pip install uv && uv sync --frozen --no-dev
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Pin the Deno tag so rebuilds are predictable. Update the tag deliberately after testing yt-dlp downloads.

### Bind Mount Host Deno

If you prefer to keep Deno outside the image, mount the host binary read-only and point the app at the container path:

```yaml
services:
  karaoke:
    image: your-karaoke-image
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: sqlite:////data/karaoke.db
      MEDIA_PATH: /data/media
      CACHE_PATH: /data/cache
      LOG_DIR: /data/logs
      YTDLP_DENO_PATH: /usr/local/bin/deno
      DEMUCS_API_URL: http://demucs-host:8001
    volumes:
      - ./data:/data
      - type: bind
        source: /home/karaoke/.deno/bin/deno
        target: /usr/local/bin/deno
        read_only: true
        bind:
          create_host_path: false
```

Use a host Deno binary that matches the container CPU architecture. If the source path is wrong, `create_host_path: false` prevents Docker Compose from creating an empty directory in its place.

### No Deno

Leave `YTDLP_DENO_PATH` unset or blank. The app behaves as before, but videos that require external JavaScript execution may fail with yt-dlp errors such as unavailable video or signature extraction failures.

## Linux With systemd

Install the app and tools under a dedicated user:

```bash
sudo useradd --system --create-home --home-dir /opt/karaoke karaoke
sudo apt-get install ffmpeg
sudo -u karaoke -H bash
cd /opt/karaoke/app
uv venv
uv pip install -e .
```

Install Deno only if needed. The npm package is acceptable on hosts that already have npm:

```bash
npm install -g deno
which deno
```

Store environment in `/etc/karaoke.env`:

```env
HOST=0.0.0.0
PORT=8000
DATABASE_URL=sqlite:////opt/karaoke/data/karaoke.db
MEDIA_PATH=/opt/karaoke/data/media
CACHE_PATH=/opt/karaoke/data/cache
LOG_DIR=/opt/karaoke/data/logs
YTDLP_PATH=yt-dlp
YTDLP_DENO_PATH=/usr/local/bin/deno
DEMUCS_API_URL=http://demucs-host:8001
```

Example service:

```ini
[Unit]
Description=Karaoke main app
After=network-online.target
Wants=network-online.target

[Service]
User=karaoke
Group=karaoke
WorkingDirectory=/opt/karaoke/app
EnvironmentFile=/etc/karaoke.env
ExecStart=/usr/bin/env uv run uvicorn main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

After changing tool paths or storage paths in `/settings`, restart the service if the value affects startup-time mounts or process environment.

## Windows

Use `uv` and the project virtual environment. Keep `ffmpeg.exe`, `yt-dlp.exe`, and optionally `deno.exe` in predictable paths.

Common options:

- Put tool directories on `PATH`, then keep `/settings` values as `yt-dlp`, `ffmpeg`, and blank Deno until needed.
- Or set explicit paths in `/settings`, for example `C:\Tools\deno\deno.exe`.
- Run the app from PowerShell for small home setups:

```powershell
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

For unattended startup, use Task Scheduler or a service wrapper such as NSSM. Store media, cache, logs, and the SQLite database under a directory that the service account can read and write.

## Security And Operations

- Do not expose `/settings`, `/media`, or admin APIs directly to the public internet without a trusted reverse proxy and access policy.
- If you expose `demucs_svc` beyond the LAN, set `DEMUCS_API_KEY` there and in the main app so
  remote requests carry `X-API-Key`.
- Keep admin credentials out of environment files and logs.
- Do not log proxy credentials or full external tool payloads.
- Keep `yt-dlp` current from `/settings` or with `uv pip install --upgrade yt-dlp`.
- Test the real problem video after changing Deno or yt-dlp:

```bash
uv run yt-dlp --js-runtimes "deno:/usr/local/bin/deno" "https://www.youtube.com/watch?v=ryFUW_pab4w"
```

## References

- yt-dlp EJS: <https://github.com/yt-dlp/yt-dlp/wiki/EJS>
- yt-dlp options: <https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/options.py>
- Deno installation: <https://docs.deno.com/runtime/getting_started/installation/>
- Deno and Docker: <https://docs.deno.com/runtime/reference/docker/>
- Docker multi-stage builds: <https://docs.docker.com/build/building/multi-stage/>
- Docker Compose volumes: <https://docs.docker.com/reference/compose-file/services/#volumes>
