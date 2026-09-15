# 设置页面 { #settings-page }

!!! note "设置页面仅限管理员使用"

    只有以管理员身份登录后，才能访问设置页面。请在初始设置过程中创建管理员账户。

![设置页面](../assets/images/settings.webp){ width="800" }

请先使用[建议设置](#recommended-settings)作为起点，然后阅读各个章节的指南以了解详细信息。

<div class="grid cards" markdown>

-   __[卡拉 OK 处理](karaoke-processing.md)__

    ---

    配置分离引擎、输出格式和处理限制。

-   __[WhisperX 歌词](whisperx-lyrics.md)__

    ---

    配置转录、对齐、同步时间轴和模型预加载。

-   __[应用程序路径](application-paths.md)__

    ---

    选择媒体、缓存和可执行文件的位置。

-   __[下载](downloads.md)__

    ---

    调整 yt-dlp 下载、代理路由、并发搜索和歌词提供商。

-   __[舞台](stage.md)__

    ---

    配置舞台链接、大厅播放和默认人声混音。

-   __[工具](tools.md)__

    ---

    检查连接和存储、更新 yt-dlp，或释放远程 Demucs 服务的内存。

</div>

## 建议设置 { #recommended-settings }

以下设置值适合作为流畅卡拉 OK 体验的起点。请根据你的硬件、网络和工作流程进行调整。

### 卡拉 OK 处理 { #karaoke-processing }

- **分离引擎：** `demucs`。如果 Demucs 后端无法使用 GPU，请改用 `Sherpa+Spleeter`。
- **直接处理媒体大小上限（MB）：** `500`。如果连接 Demucs 的网络速度较慢，可以调低此值，例如设置为 `20–50`。
- **MP3 音轨比特率：** `320`。如果连接 Demucs 的网络速度较慢，可以调低此值，例如设置为 `128–160`。

### WhisperX 歌词 { #whisperx-lyrics }

- **对齐前检测语言：** 已启用。
- **使用同步歌词时间轴：** 已禁用。

### 下载 { #downloads }

- **并发 YouTube 搜索：** 已启用。

### 舞台 { #stage }

- **舞台 QR URL：** 配置你自己的队列页面 URL。
- **舞台大厅媒体 URL：** 配置媒体或缓存路径，用于队列为空时显示的大厅页面。

这些建议适用于各种硬件和部署环境，但你可以随时在设置页面中调整它们。
