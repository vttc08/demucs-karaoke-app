# 环境变量 { #environment-variables }

DMKaraoke 会从 `.env` 文件、操作系统环境或 Docker 的 `environment:` 配置块中读取环境变量。可以使用环境变量配置部署相关的值，例如路径、服务 URL、可执行文件路径和密钥。

完整的起点是 [`.env.example` 文件](https://raw.githubusercontent.com/vttc08/demucs-karaoke-app/main/.env.example)。

!!! warning "保护秘密"

    不要将 API token 或服务密钥提交到公开代码库。请将密钥保存在受保护的 `.env` 文件、权限受限的 systemd 环境文件或容器的密钥管理系统中。

## 配置工作方式 { #how-configuration-works }

主应用按以下顺序加载配置值：

1. 进程、Docker 或 systemd 提供的环境变量。
2. 本地 `.env` 文件中的值。
3. 应用运行时设置数据库中保存的值。
4. 应用内置的默认值。

明确提供的环境变量在重启后仍优先于设置页面保存的值。当部署必须固定某个路径、服务 URL、可执行文件或其他配置时，这种方式很有用。如果希望由设置页面和数据库中的值控制配置，请不要设置对应的环境变量。

大多数布尔变量接受 `true`、`false`、`1`、`0`、`yes` 或 `no` 等值。除非另有说明，路径可以是绝对路径，也可以是相对于应用目录的路径。大小限制使用字节，超时和间隔使用秒。

Docker Compose 文件会通过其中的 `environment:` 部分直接提供一些应用默认值。在 Linux 或 Windows 安装中，如果需要在启动前设置这些值，请取消 `.env` 中对应变量的注释。

## 主应用 { #main-application }

以下变量用于配置主应用的 FastAPI 服务。

### 服务器和路由 { #server-and-routing }

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | 应用监听的网络地址。`0.0.0.0` 表示监听所有网络接口，通常是 Docker 和局域网访问所需的设置。 |
| `PORT` | `8000` | 应用监听的端口。 |
| `KARAOKE_BASE_PATH` | 空 | 可选的反向代理 URL 前缀，例如 `/karaoke`。如果应用直接部署在 `/`，请留空。代理转发请求时必须保留此前缀。 |
| `ENABLED_LOCALES` | `en` | 用户界面可用的语言代码列表，使用逗号分隔，例如 `en,zh-CN`。简体中文使用 `zh-CN`，单独使用 `zh` 不够。 |

### 数据库和存储 { #database-and-storage }

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./karaoke.db` | SQLAlchemy 数据库 URL。默认会将 SQLite 数据库存储在应用目录中。Docker 通常会将其设置为 `/data` 下的路径。 |
| `MEDIA_PATH` | `/tmp/karaoke_media` | 存放下载、上传和处理后媒体的目录。应用会在需要时创建该目录，运行应用的用户必须具有读写权限。 |
| `CACHE_PATH` | `/tmp/karaoke_cache` | 存放临时下载、处理输出、缩略图和其他缓存文件的目录。 |
| `KARAOKE_PROCESSING_MAX_WORKERS` | `2` | 主应用可以同时运行的处理任务数量上限。 |
| `KARAOKE_MAX_UPLOAD_BYTES` | `2147483648`（2 GiB） | 上传文件或解压后 ZIP 导入的大小上限。 |
| `KARAOKE_UPLOAD_MIN_FREE_BYTES` | `1073741824`（1 GiB） | 接受上传前所需的最小可用空间。 |

### 歌词提供商和语言 { #lyrics-providers-and-languages }

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MUSIXMATCH_TOKEN` | 空 | 歌词提供商使用的 Musixmatch token。 |
| `LASTFM_API_KEY` | 空 | Last.fm API key，用于改善标题和艺人信息的推断。 |
| `LRCLIB_API_URL` | `https://lrclib.net` | LRCLIB 歌词提供商的基础 URL。 |
| `LYRICS_TTML_STORAGE_URL` | `https://lyrics-storage.binimum.org` | 用于为受支持的同步歌词执行可选 TTML 升级的服务 URL。 |
| `LYRICS_TTML_UPGRADE_TIMEOUT_SECONDS` | `3.0` | 等待 TTML 升级的最长时间。如果超时，原始歌词结果仍然可用。 |
| `LYRICS_PROVIDER_CUSTOM_PATHS` | 空 | 可选的 Python 文件或目录列表，使用逗号分隔，其中包含自定义歌词提供商模块。应用会扫描目录顶层的 `.py` 文件。 |
| `LYRICS_PROVIDER_NETEASE_ENABLED` | `true` | 启用 NetEase 歌词提供商。 |
| `LYRICS_PROVIDER_LRCLIB_ENABLED` | `true` | 启用 LRCLIB 歌词提供商。 |

### Demucs 和卡拉 OK 处理 { #demucs-and-karaoke-processing }

这些变量控制主应用如何连接到独立的 Demucs 服务并向其请求处理任务。Demucs 服务本身还有其他配置变量，详见下文。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DEMUCS_API_URL` | `http://localhost:8001` | Demucs 服务的 URL。在 Docker Compose 中通常为 `http://demucs:8001`；远程服务则应填写可以访问的 HTTP URL。 |
| `DEMUCS_API_KEY` | 空 | 可选的共享 API key。当 Demucs 服务暴露在不完全可信的网络之外时，应在主应用和 Demucs 服务中设置相同的值。 |
| `DEMUCS_MODEL` | `htdemucs` | Demucs 用于人声分离的模型。 |
| `DEMUCS_DEVICE` | `cuda` | 请求 Demucs 使用的处理设备。CUDA 不可用时使用 `cpu`。 |
| `DEMUCS_OUTPUT_FORMAT` | `mp3` | 请求 Demucs 使用的输出格式。支持 `mp3` 和 `wav`。 |
| `DEMUCS_MP3_BITRATE` | `320` | 输出格式为 MP3 时使用的比特率，单位为 kbps。 |
| `SEPARATION_BACKEND` | `demucs` | 请求 Demucs 使用的分离后端。支持 `demucs` 和 `sherpa_spleeter`。 |
| `SHERPA_SPLEETER_MODEL` | `fp16` | `SEPARATION_BACKEND=sherpa_spleeter` 时使用的 Sherpa+Spleeter 模型变体。支持 `fp16`、`int8` 和 `fp32`。 |
| `DEMUCS_DIRECT_MEDIA_MAX_MB` | `500` | 允许直接处理的媒体大小上限，单位为 MB；直接处理时不会先将媒体复制到常规工作流目录。 |
| `DEMUCS_POLL_INTERVAL_SECONDS` | `1.0` | 等待远程 Demucs 任务时，两次轮询之间的间隔。 |
| `WHISPERX_TRANSCRIPTION_MODEL` | `tiny` | 请求 WhisperX 用于歌词对齐的转录模型。 |
| `WHISPERX_ALIGN_LANGUAGE` | `en` | 传递给 WhisperX 对齐步骤的语言。 |
| `WHISPERX_DETECT_LANGUAGE` | `false` | 允许 WhisperX 检测转录语言，而不是使用配置的语言。 |
| `WHISPERX_USE_SYNCED_LYRICS` | `false` | 如果工作流支持，请求在 WhisperX 处理过程中使用同步歌词。 |
| `WHISPERX_PRELOAD_MODELS` | `transcription=tiny,align=en` | 发送给 Demucs 服务的 WhisperX 模型预加载配置，多个项目使用逗号分隔。 |

### 下载和外部工具 { #downloads-and-external-tools }

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `YTDLP_PATH` | `yt-dlp` | yt-dlp 的路径或可执行文件名。应用会先检查当前虚拟环境，然后检查系统的 `PATH`。 |
| `YTDLP_DENO_PATH` | 空 | Deno 的可选路径，用于 yt-dlp 执行外部 JavaScript。除非某个视频需要，否则请留空。 |
| `YTDLP_PROXY_URL` | 空 | yt-dlp 和相关出站请求使用的可选 HTTP、HTTPS、SOCKS4 或 SOCKS5 代理 URL。 |
| `YTDLP_VIDEO_RESOLUTION` | `default` | 首选视频分辨率。支持 `default`、`360`、`480`、`720`、`1080` 和 `2160`。 |
| `YTDLP_VIDEO_CODEC` | 空 | 可选的视频编码器偏好。留空表示使用默认选择；需要指定编码器时支持 `avc`。 |
| `CONCURRENT_YTDLP_SEARCH_ENABLED` | `false` | 启用并发 yt-dlp 搜索。这可能增加出站请求和资源使用量。 |
| `FFMPEG_PATH` | `ffmpeg` | FFmpeg 的路径或可执行文件名。 |
| `FFMPEG_AUDIO_CODEC` | 空 | 可选的音频编码器偏好。留空表示使用默认选择；需要指定编码器时支持 `aac`。 |

### 日志 { #logging }

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | 根日志级别，例如 `DEBUG`、`INFO`、`WARNING` 或 `ERROR`。 |
| `LOG_DIR` | `./logs` | 应用日志文件所在的目录。 |
| `LOG_FILE_NAME` | `karaoke.log` | `LOG_DIR` 中的日志文件名。 |
| `LOG_MAX_BYTES` | `5242880`（5 MB） | 日志轮换前单个日志文件的大小上限。 |
| `LOG_BACKUP_COUNT` | `5` | 保留的轮换日志文件数量。 |
| `LOG_FORMAT` | <code>%(asctime)s &#124; %(levelname)s &#124; %(name)s &#124; %(message)s</code> | Python 日志格式字符串。 |
| `LOG_TO_FILE_IN_RELOAD` | `false` | 在 reload 模式下运行时启用文件日志。正常开发时请保持禁用，以免日志写入触发 reload 循环。 |

### 舞台和 WebSocket 行为 { #stage-and-websocket-behavior }

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `STAGE_QR_URL` | 空 | 编码到舞台 QR 覆盖层中的 URL。 |
| `STAGE_LOBBY_MEDIA_PATH` | 空 | 队列为空时用于大厅循环的可选 `/media/...` 或 `/cache/...` 路径。 |
| `STAGE_VOCALS_VOLUME_DEFAULT` | `1.0` | 舞台或队列页面加载时使用的默认人声音量。取值范围为 `0.0` 到 `1.0`。 |
| `WS_HEARTBEAT_INTERVAL` | `30` | WebSocket 心跳间隔，单位为秒。服务器使用它检测失效的浏览器连接。 |

## Demucs 服务 { #demucs-service }

Demucs 服务读取自己的环境文件。默认情况下，它会在 `demucs_svc/` 中查找 `.env`。如果服务配置位于其他路径，请设置 `DEMUCS_ENV_FILE`。

以下变量用于配置独立的 GPU 或 CPU 处理服务。与主应用共享的变量通常应使用相同的值。

### 服务路径和访问 { #service-paths-and-access }

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DEMUCS_ENV_FILE` | `demucs_svc/.env` | Demucs 服务环境文件的路径。服务加载其他设置前会先读取此变量。 |
| `DEMUCS_IO_ROOT` | `demucs_svc/io` | 存放传入任务和处理后输出的根目录。相对路径以 `demucs_svc` 目录为基准解析。 |
| `DEMUCS_API_KEY` | 空 | 可选的共享 API key。请使用与主应用 `DEMUCS_API_KEY` 相同的值。 |

### 处理和模型设置 { #processing-and-model-settings }

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DEMUCS_MODEL` | `htdemucs` | 服务加载的 Demucs 模型。 |
| `DEMUCS_DEVICE` | `cuda` | 服务使用的设备。仅使用 CPU 处理时使用 `cpu`。 |
| `DEMUCS_OUTPUT_FORMAT` | `wav` | 服务默认生成的输出格式。 |
| `DEMUCS_MP3_BITRATE` | `320` | 选择 MP3 输出时使用的比特率，单位为 kbps。 |
| `SEPARATION_BACKEND` | `demucs` | 默认的人声分离后端。支持 `demucs` 和 `sherpa_spleeter`。 |
| `SHERPA_SPLEETER_MODEL` | `fp16` | Sherpa+Spleeter 模型变体。支持 `fp16`、`int8` 和 `fp32`。 |
| `SHERPA_SPLEETER_MODEL_ROOT` | `demucs_svc/model_data/sherpa_spleeter` | Sherpa+Spleeter 模型的存储目录。相对路径以 `demucs_svc` 为基准解析。 |
| `SHERPA_SPLEETER_NUM_THREADS` | 最多 `8` 个 | Sherpa+Spleeter 使用的 CPU 线程数。默认值受主机 CPU 数量限制。 |
| `SHERPA_SPLEETER_FFMPEG_PATH` | `ffmpeg` | Sherpa+Spleeter 使用的 FFmpeg 路径或可执行文件名。 |
| `WHISPERX_TRANSCRIPTION_MODEL` | `tiny` | 服务使用的 WhisperX 转录模型。 |
| `WHISPERX_ALIGN_LANGUAGE` | `en` | WhisperX 对齐使用的默认语言。 |
| `WHISPERX_DETECT_LANGUAGE` | `false` | 为 WhisperX 转录启用语言检测。 |
| `WHISPERX_USE_SYNCED_LYRICS` | `false` | 运行对齐工作流时使用所提供的同步歌词。 |
| `WHISPERX_PRELOAD_MODELS` | `transcription=tiny,align=en` | 服务启动时预加载的模型配置。 |

### 资源限制和清理 { #resource-limits-and-cleanup }

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DEMUCS_MAX_CONCURRENT_JOBS` | `1` | 同时处理的最大人声分离任务数。保持为 `1` 有助于避免 GPU 内存竞争。 |
| `DEMUCS_MAX_UPLOAD_BYTES` | `2147483648`（2 GiB） | 服务接受的上传大小上限。 |
| `DEMUCS_MIN_FREE_BYTES` | `1073741824`（1 GiB） | 接受下一个上传前所需的最小可用空间。 |
| `DEMUCS_GC_INTERVAL_SECONDS` | `600` | 定期检查 GPU 内存并执行清理的时间间隔。 |
| `DEMUCS_GC_LOW_FREE_VRAM_BYTES` | `2147483648`（2 GiB） | 触发额外清理的可用显存阈值。 |

## 示例配置 { #example-configurations }

### 最小本地应用配置 { #minimal-local-application }

```dotenv
HOST=0.0.0.0
PORT=8000
MEDIA_PATH=/srv/karaoke/media
CACHE_PATH=/srv/karaoke/cache
DATABASE_URL=sqlite:////srv/karaoke/karaoke.db
```

### 主应用连接到远程 Demucs 服务 { #main-application-connected-to-a-remote-demucs-service }

```dotenv
DEMUCS_API_URL=http://demucs-host:8001
DEMUCS_API_KEY=replace-with-a-shared-secret
DEMUCS_DEVICE=cuda
YTDLP_DENO_PATH=/usr/local/bin/deno
```

### Docker Compose 存储和日志 { #docker-compose-storage-and-logging }

```dotenv
PUID=1000
PGID=1000
```

随附的 Compose 文件会将主机上的 `data` 目录映射到容器中的 `/data`，并在那里定义应用路径。`PUID` 和 `PGID` 控制容器用于绑定挂载所有权的数字用户和组；它们是 Compose 变量，不是应用设置。
