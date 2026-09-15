# Variables environnementales { #environment-variables }

DMKaraoke reads environment variables from a `.env` file, the operating-system environment, or a Docker `environment:` block. Use environment variables for deployment-specific values such as paths, service URLs, executable paths, and secrets.

The complete starting point is the [`.env.example` file](https://raw.githubusercontent.com/vttc08/demucs-karaoke-app/main/.env.example).

!!! warning "Protect secrets"

    Do not commit API tokens or service keys to a public repository. Keep secrets in a protected `.env` file, a systemd environment file with restricted permissions, or your container secret-management system.

## Comment fonctionne la configuration { #how-configuration-works }

La principale application charge les valeurs dans cet ordre:

1. Variables d'environnement fournies par le procédé, Docker ou systemd.
2. Les valeurs du fichier `.env` local.
3. Valeurs enregistrées dans la base de données des paramètres d'exécution de l'application.
4. Par défaut d'application intégrée.

Une variable d'environnement fournie explicitement a priorité sur une valeur enregistrée depuis la page Paramètres après un redémarrage. Ceci est utile lorsqu'un déploiement doit maintenir un chemin, une URL de service, exécutable ou une autre valeur fixe. Laissez une variable déréglée lorsque vous voulez que la page Paramètres et la valeur de base de données la contrôlent.

La plupart des variables booléennes acceptent des valeurs telles que `true`, `false`, `1`, `0`, `yes` ou `no`. Sauf indication contraire, les chemins peuvent être absolus ou relatifs au répertoire de l’application. Les limites de taille sont exprimées en octets, tandis que les délais et intervalles sont exprimés en secondes.

Le fichier Docker Compose fournit certaines valeurs par défaut dans sa section `environment:`. Sous Linux ou Windows, décommentez les variables correspondantes dans `.env` si vous devez les définir avant le démarrage.

## Demande principale { #main-application }

Les variables suivantes configurent l'application principale FastAPI.

### Serveur et routage { #server-and-routing }

| Variable | Default | Description |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Network address on which the application listens. `0.0.0.0` listens on all interfaces, which is normally required for Docker and LAN access. |
| `PORT` | `8000` | Port on which the application listens. |
| `KARAOKE_BASE_PATH` | empty | Optional URL prefix for a reverse proxy, such as `/karaoke`. Leave empty when the app is served at `/`. The proxy must preserve the prefix when forwarding requests. |
| `ENABLED_LOCALES` | `en` | Comma-separated locale codes available in the user interface, such as `en,zh-CN`. Use `zh-CN` for Simplified Chinese; `zh` alone is not sufficient. |

### Base de données et stockage { #database-and-storage }

| Variable | Default | Description |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./karaoke.db` | SQLAlchemy database URL. The default stores the SQLite database in the application directory. Docker normally sets this to a path under `/data`. |
| `MEDIA_PATH` | `/tmp/karaoke_media` | Directory for downloaded, uploaded, and processed media. The application creates it when needed, and the running user must be able to read and write it. |
| `CACHE_PATH` | `/tmp/karaoke_cache` | Directory for temporary downloads, processing output, thumbnails, and other cache files. |
| `KARAOKE_PROCESSING_MAX_WORKERS` | `2` | Maximum number of main-application processing tasks that may run at the same time. |
| `KARAOKE_MAX_UPLOAD_BYTES` | `2147483648` (2 GiB) | Maximum size of an uploaded file or expanded ZIP import. |
| `KARAOKE_UPLOAD_MIN_FREE_BYTES` | `1073741824` (1 GiB) | Minimum free space required before accepting an upload. |

### Fournisseurs de lyriques et langues { #lyrics-providers-and-languages }

| Variable | Default | Description |
| --- | --- | --- |
| `MUSIXMATCH_TOKEN` | empty | Musixmatch token used by the lyrics provider. |
| `LASTFM_API_KEY` | empty | Last.fm API key used to improve title and artist metadata inference. |
| `LRCLIB_API_URL` | `https://lrclib.net` | Base URL for the LRCLIB lyrics provider. |
| `LYRICS_TTML_STORAGE_URL` | `https://lyrics-storage.binimum.org` | Service URL used for optional TTML upgrades to supported synced lyrics. |
| `LYRICS_TTML_UPGRADE_TIMEOUT_SECONDS` | `3.0` | Maximum time to wait for a TTML upgrade. The original lyrics result remains available if the upgrade times out. |
| `LYRICS_PROVIDER_CUSTOM_PATHS` | empty | Optional comma-separated list of Python files or directories containing custom lyrics-provider modules. Directories are scanned for top-level `.py` files. |
| `LYRICS_PROVIDER_NETEASE_ENABLED` | `true` | Enables the NetEase lyrics provider. |
| `LYRICS_PROVIDER_LRCLIB_ENABLED` | `true` | Enables the LRCLIB lyrics provider. |

### Démucs et karaokés { #demucs-and-karaoke-processing }

Ces variables contrôlent la façon dont l'application principale se connecte au service Demucs séparé et les demandes de travail. Le service lui-même a des variables supplémentaires documentées ci-dessous.

| Variable | Default | Description |
| --- | --- | --- |
| `DEMUCS_API_URL` | `http://localhost:8001` | URL of the Demucs service. In Docker Compose this is commonly `http://demucs:8001`; for a remote service, use its reachable HTTP URL. |
| `DEMUCS_API_KEY` | empty | Optional shared API key. Set the same value on the main application and Demucs service when the service is exposed beyond a trusted network. |
| `DEMUCS_MODEL` | `htdemucs` | Demucs model requested for vocal separation. |
| `DEMUCS_DEVICE` | `cuda` | Processing device requested from Demucs. Use `cpu` when CUDA is unavailable. |
| `DEMUCS_OUTPUT_FORMAT` | `mp3` | Output format requested from Demucs. Supported values are `mp3` and `wav`. |
| `DEMUCS_MP3_BITRATE` | `320` | MP3 bitrate in kbps when the selected output format is MP3. |
| `SEPARATION_BACKEND` | `demucs` | Separation backend requested from Demucs. Supported values are `demucs` and `sherpa_spleeter`. |
| `SHERPA_SPLEETER_MODEL` | `fp16` | Sherpa+Spleeter model variant when `SEPARATION_BACKEND=sherpa_spleeter`. Supported values are `fp16`, `int8`, and `fp32`. |
| `DEMUCS_DIRECT_MEDIA_MAX_MB` | `500` | Maximum media size, in MB, for direct processing without first copying the media into the normal workflow. |
| `DEMUCS_POLL_INTERVAL_SECONDS` | `1.0` | Interval between polls while waiting for a remote Demucs task. |
| `WHISPERX_TRANSCRIPTION_MODEL` | `tiny` | WhisperX transcription model requested for lyric alignment. |
| `WHISPERX_ALIGN_LANGUAGE` | `en` | Language passed to WhisperX alignment. |
| `WHISPERX_DETECT_LANGUAGE` | `false` | Allows WhisperX to detect the transcription language instead of using the configured language. |
| `WHISPERX_USE_SYNCED_LYRICS` | `false` | Requests synced lyrics as part of WhisperX processing when supported by the workflow. |
| `WHISPERX_PRELOAD_MODELS` | `transcription=tiny,align=en` | Comma-separated WhisperX model preload specification sent to the Demucs service. |

### Téléchargements et outils externes { #downloads-and-external-tools }

| Variable | Default | Description |
| --- | --- | --- |
| `YTDLP_PATH` | `yt-dlp` | Path or executable name for yt-dlp. The application first checks the active virtual environment and then the system `PATH`. |
| `YTDLP_DENO_PATH` | empty | Optional path to Deno for yt-dlp external JavaScript execution. Leave empty unless a video requires it. |
| `YTDLP_PROXY_URL` | empty | Optional HTTP, HTTPS, SOCKS4, or SOCKS5 proxy URL for yt-dlp and related outbound requests. |
| `YTDLP_VIDEO_RESOLUTION` | `default` | Preferred video resolution. Supported values are `default`, `360`, `480`, `720`, `1080`, and `2160`. |
| `YTDLP_VIDEO_CODEC` | empty | Optional video codec preference. Leave empty for the default selection; `avc` is supported when a codec preference is needed. |
| `CONCURRENT_YTDLP_SEARCH_ENABLED` | `false` | Enables concurrent yt-dlp searches. This can increase outbound requests and resource use. |
| `FFMPEG_PATH` | `ffmpeg` | Path or executable name for FFmpeg. |
| `FFMPEG_AUDIO_CODEC` | empty | Optional audio codec preference. Leave empty for the default selection; `aac` is supported when a codec preference is needed. |

### Exploitation forestière { #logging }

| Variable | Default | Description |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | Root logging level, such as `DEBUG`, `INFO`, `WARNING`, or `ERROR`. |
| `LOG_DIR` | `./logs` | Directory for the application log file. |
| `LOG_FILE_NAME` | `karaoke.log` | Log filename inside `LOG_DIR`. |
| `LOG_MAX_BYTES` | `5242880` (5 MB) | Maximum size of one log file before rotation. |
| `LOG_BACKUP_COUNT` | `5` | Number of rotated log files to retain. |
| `LOG_FORMAT` | <code>%(asctime)s &#124; %(levelname)s &#124; %(name)s &#124; %(message)s</code> | Python logging format string. |
| `LOG_TO_FILE_IN_RELOAD` | `false` | Enables file logging while running in reload mode. Leave disabled during normal development to avoid reload loops caused by log writes. |

### Étape et comportement WebSocket { #stage-and-websocket-behavior }

| Variable | Default | Description |
| --- | --- | --- |
| `STAGE_QR_URL` | empty | URL encoded in the QR overlay displayed on the stage. |
| `STAGE_LOBBY_MEDIA_PATH` | empty | Optional `/media/...` or `/cache/...` path used for the lobby loop when the queue is empty. |
| `STAGE_VOCALS_VOLUME_DEFAULT` | `1.0` | Default vocals volume applied when the stage or queue page loads. Use a value from `0.0` to `1.0`. |
| `WS_HEARTBEAT_INTERVAL` | `30` | WebSocket heartbeat interval in seconds. The server uses this to detect stale browser connections. |

## Services aux entreprises { #demucs-service }

The Demucs service reads its own environment file. By default it looks for `.env` inside `demucs_svc/`. Set `DEMUCS_ENV_FILE` when the service configuration should live at another path.

Ces variables configurent le service de traitement GPU ou CPU séparé. Les variables partagées avec l'application principale devraient normalement utiliser des valeurs correspondantes.

### Voies de service et accès { #service-paths-and-access }

| Variable | Default | Description |
| --- | --- | --- |
| `DEMUCS_ENV_FILE` | `demucs_svc/.env` | Path to the Demucs service environment file. This variable is read before the service loads its settings. |
| `DEMUCS_IO_ROOT` | `demucs_svc/io` | Root directory for incoming jobs and processed output. Relative paths are resolved from the `demucs_svc` directory. |
| `DEMUCS_API_KEY` | empty | Optional shared API key required by the main application. Use the same value as the main application's `DEMUCS_API_KEY`. |

### Traitement et réglages du modèle { #processing-and-model-settings }

| Variable | Default | Description |
| --- | --- | --- |
| `DEMUCS_MODEL` | `htdemucs` | Demucs model loaded by the service. |
| `DEMUCS_DEVICE` | `cuda` | Device used by the service. Use `cpu` for CPU-only processing. |
| `DEMUCS_OUTPUT_FORMAT` | `wav` | Default output format produced by the service. |
| `DEMUCS_MP3_BITRATE` | `320` | MP3 bitrate in kbps when MP3 output is selected. |
| `SEPARATION_BACKEND` | `demucs` | Default separation backend. Supported values are `demucs` and `sherpa_spleeter`. |
| `SHERPA_SPLEETER_MODEL` | `fp16` | Sherpa+Spleeter model variant. Supported values are `fp16`, `int8`, and `fp32`. |
| `SHERPA_SPLEETER_MODEL_ROOT` | `demucs_svc/model_data/sherpa_spleeter` | Directory where Sherpa+Spleeter models are stored. Relative paths are resolved from `demucs_svc`. |
| `SHERPA_SPLEETER_NUM_THREADS` | up to `8` | Number of CPU threads used by Sherpa+Spleeter. The default is limited by the host CPU count. |
| `SHERPA_SPLEETER_FFMPEG_PATH` | `ffmpeg` | Path or executable name for FFmpeg used by Sherpa+Spleeter. |
| `WHISPERX_TRANSCRIPTION_MODEL` | `tiny` | WhisperX transcription model used by the service. |
| `WHISPERX_ALIGN_LANGUAGE` | `en` | Default language used for WhisperX alignment. |
| `WHISPERX_DETECT_LANGUAGE` | `false` | Enables language detection for WhisperX transcription. |
| `WHISPERX_USE_SYNCED_LYRICS` | `false` | Uses supplied synced lyrics when running the alignment workflow. |
| `WHISPERX_PRELOAD_MODELS` | `transcription=tiny,align=en` | Models requested during service startup preload. |

### Limites de ressources et nettoyage { #resource-limits-and-cleanup }

| Variable | Default | Description |
| --- | --- | --- |
| `DEMUCS_MAX_CONCURRENT_JOBS` | `1` | Maximum number of separation jobs processed at the same time. Keeping this at `1` helps avoid GPU memory contention. |
| `DEMUCS_MAX_UPLOAD_BYTES` | `2147483648` (2 GiB) | Maximum incoming upload size accepted by the service. |
| `DEMUCS_MIN_FREE_BYTES` | `1073741824` (1 GiB) | Minimum free space required before accepting another upload. |
| `DEMUCS_GC_INTERVAL_SECONDS` | `600` | Interval between scheduled GPU-memory cleanup checks. |
| `DEMUCS_GC_LOW_FREE_VRAM_BYTES` | `2147483648` (2 GiB) | Free-VRAM threshold that triggers additional cleanup. |

## Exemple de configurations { #example-configurations }

### Application locale minimale { #minimal-local-application }

```dotenv
HOST=0.0.0.0
PORT=8000
MEDIA_PATH=/srv/karaoke/media
CACHE_PATH=/srv/karaoke/cache
DATABASE_URL=sqlite:////srv/karaoke/karaoke.db
```

### Application principale connectée à un service Demucs à distance { #main-application-connected-to-a-remote-demucs-service }

```dotenv
DEMUCS_API_URL=http://demucs-host:8001
DEMUCS_API_KEY=replace-with-a-shared-secret
DEMUCS_DEVICE=cuda
YTDLP_DENO_PATH=/usr/local/bin/deno
```

### Docker Composez le stockage et l'enregistrement { #docker-compose-storage-and-logging }

```dotenv
PUID=1000
PGID=1000
```

The included Compose file maps the host `data` directory to `/data` in the container and defines the application paths there. `PUID` and `PGID` control the numeric user and group used by the container for bind-mount ownership; they are Compose variables rather than application settings.
