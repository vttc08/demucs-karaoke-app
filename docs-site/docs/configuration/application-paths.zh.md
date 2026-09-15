# 应用路径 { #application-paths }

![应用路径设置](../assets/images/settings/application-paths.webp){ width="400" }

使用此区域选择应用存储媒体和临时文件的位置，以及应用应使用的外部可执行文件。部署需要固定路径时，也可以通过[环境变量](environments.md)配置这些设置。

### 媒体路径 { #media-path }

用于存放下载、上传和处理后媒体的目录。应用会在需要时创建该目录，运行应用的用户必须具有读写权限。

### 缓存路径 { #cache-path }

用于存放临时下载、处理输出、缩略图和其他缓存文件的目录。不再需要缓存文件时，可以从[工具](tools.md)页面将其删除。

### yt-dlp 路径 { #yt-dlp-path }

用于运行 yt-dlp 的路径或可执行文件名。应用会先检查当前虚拟环境，然后回退到系统 `PATH`。

### Deno 路径 { #deno-path }

Deno 路径在 Docker 安装中默认已配置。强烈建议安装 Deno，以避免使用此应用时遇到 yt-dlp 下载问题。

用于 yt-dlp 外部 JavaScript 执行的可选 Deno 路径。留空可保留 yt-dlp 的默认行为；当视频来源需要外部 JavaScript 运行时环境时再设置此项。

### FFmpeg 路径 { #ffmpeg-path }

用于运行 FFmpeg 的路径或可执行文件名。音频提取、媒体转换和其他处理任务都需要 FFmpeg。
