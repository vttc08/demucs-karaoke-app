# Linux

The Linux deployment uses systemd to manage the main application. This setup is suitable for bare-metal and LXC installations.

## Installation

### 1. Prepare the application and dependencies

Clone the application:

```bash
git clone https://github.com/vttc08/demucs-karaoke-app.git /opt/karaoke/app
```

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then install the system and application dependencies:

```bash
sudo apt-get install ffmpeg
cd /opt/karaoke/app
uv venv
uv pip install -e .
```

!!! note

    The default installation does not include `numpy` and `scipy`, which are required for [vocal sync](../tasks/create-ai-karaoke.md). If you need vocal sync, install the `vocal-sync` extra:

```bash
uv pip install -e ".[vocal-sync]"
```

### 2. Install Deno if needed

Some videos require yt-dlp's external JavaScript execution support. Install [Deno](https://docs.deno.com/runtime/getting_started/installation/) only if needed. The npm package is acceptable on hosts that already have npm:

```bash
npm install -g deno
which deno
```

### 3. Build the documentation

For a non-Docker setup, the static documentation is not included in the application by default. You can run the application without it and use the [online documentation](https://vttc08.github.io/demucs-karaoke-app/). To build the documentation locally, install the documentation dependencies and run the build script:

```bash
uv pip install mkdocs mkdocs-material mkdocs-minify-plugin mkdocs-static-i18n pymdown-extensions
uv run scripts/build_docs.py
```

### 4. Configure the environment

Store the environment in `/etc/karaoke.env`:

The following configuration should work for most use cases. Replace the example paths and service URL with values for your host. You can review the detailed configuration in the [configuration section](../configuration/settings.md).

```env
HOST=0.0.0.0
PORT=8000
DATABASE_URL=sqlite:////opt/karaoke/data/karaoke.db
MEDIA_PATH=/your/media/path
CACHE_PATH=/opt/karaoke/data/cache
LOG_DIR=/opt/karaoke/data/logs
YTDLP_PATH=yt-dlp
YTDLP_DENO_PATH=/usr/local/bin/deno
DEMUCS_API_URL=http://demucs-host:8001
```

!!! note

    The `MEDIA_PATH` must be writable by the user running the application and have enough space for your media files. SMB/NFS shares are supported.

### 5. Create the systemd service

Create `/etc/systemd/system/karaoke.service` with the following contents:

```ini
[Unit]
Description=Karaoke main app
After=network-online.target
Wants=network-online.target

[Service]
User=<your-user>
Group=<your-group>
WorkingDirectory=/opt/karaoke/app
EnvironmentFile=/etc/karaoke.env
ExecStart=/usr/bin/env uv run uvicorn main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 6. Enable and start the service

```bash
sudo systemctl daemon-reload
sudo systemctl enable karaoke.service
sudo systemctl start karaoke.service
sudo systemctl status karaoke.service
```

After changing tool paths or storage paths in `/settings`, restart the service if the setting affects startup-time mounts or the process environment.

### 7. Configure the admin user and default presets

From the application directory, create the first admin user and install the default stage presets:

```bash
cd /opt/karaoke/app
uv run python scripts/admin_user.py create --username admin
uv run python scripts/default_presets.py
```

Once the application is running, open `http://<your-server-ip>:8000/login` and log in with the admin user you just created.

## Next Steps

- [Backup, restore, and upgrade](backup-and-restore.md)
- [Deploy the Demucs service (optional)](demucs-service.md)
- [Connect clients](clients.md)
- [Queue page](../features/queue-page.md)
- [Create AI Karaoke](../tasks/create-ai-karaoke.md)
