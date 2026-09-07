## Windows

This doc covers the installation of main karaoke application on Windows, for Demucs service, refer to [Demucs service](demucs-service.md).

### 1. Download Python/UV and dependencies

- [Python](https://www.python.org/downloads/windows/) 3.11 or later, make sure to check "Add Python to PATH" during installation.
- [UV](https://docs.astral.sh/uv/getting-started/installation/)
- [ffmpeg](https://ffmpeg.org/download.html) 6.0 or later, add to PATH.
- [Deno](https://docs.deno.com/runtime/getting_started/installation/) add to PATH, only if needed.

### 2. Add binary to PATH

Open "Edit the system environment variables" and add the following to PATH:

- `C:\Tools\ffmpeg\bin` (or wherever you installed ffmpeg, ffprobe, and ffplay.exe)
- Deno path if needed, for example `C:\Tools\deno`

Verify on the command line:

```powershell
ffmpeg -version
uv --version
deno --version  # only if needed
python --version
```

### 3. Download and setup the application

```powershell
git clone https://github.com/vttc08/demucs-karaoke-app.git
cd demucs-karaoke-app
uv venv
uv pip install -e .
```

!!! tip
    If git is not available, you can download the zip from GitHub and extract it.

!!! note
    The default installation do not include `numpy` and `scipy`, which are required for [vocal sync](link to be added later). If you need vocal sync, install the `vocal-sync` extra:

    ```powershell
    uv pip install -e .[vocal-sync]
    ```

### 4. Build documentation

For non-Docker setup, the static documentation is not included. It's fine to run the application without it and use the [online documentation](https://vttc08.github.io/demucs-karaoke-app/). To build the documentation, install `mkdocs` and `mkdocs-material`:

```bash
uv pip install mkdocs mkdocs-material mkdocs-minify-plugin mkdocs-static-i18n
uv run scripts/build_docs.py
```

### 5. Configure the environment

```powershell
cp .env.example .env
```

The default environment configuration which should work for most use cases. You can review the detailed configuration in the [configuration section](../configuration/index.md).

### 6. Running the application

```powershell
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

For unattended startup, use Task Scheduler or a service wrapper such as NSSM. Store media, cache, logs, and the SQLite database under a directory that the service account can read and write.

### 7. Configure the admin user and default presets

While the application is running, open another PowerShell window in the application directory. Create the first admin user and install the default stage presets:

```powershell
uv run python scripts/admin_user.py create --username admin
uv run python scripts/default_presets.py
```

Once the application is running, open `http://<your-server-ip>:8000/login` and log in with the admin user you just created.

## Next Steps

- [Configuring the application](../configuration/index.md)
- [Deploy Demucs service (optional)](demucs-service.md)
- [Clients](clients.md)
- [Explore features](../features/index.md)
