# 下载 { #downloads }

![下载设置](../assets/images/settings/downloads.webp){ width="400" }

使用此区域控制 yt-dlp 下载偏好、代理路由、并发搜索和歌词提供商。部署需要固定值时，也可以通过[环境变量](environments.md)配置这些设置。

### yt-dlp 视频编码 { #yt-dlp-video-codec }

yt-dlp 的可选视频编码偏好。留空表示使用 yt-dlp 的默认选择。

Apple 设备上的浏览器支持的编码器有限。如果出现视频播放问题，可以将此项设置为 `avc`。

### yt-dlp 视频分辨率 { #yt-dlp-video-resolution }

首选视频分辨率上限。选择 `Default` 以保持当前行为，或选择 `360p`、`480p`、`720p`、`1080p` 或 `2160p`，将视频下载限制在该分辨率或更低。

### yt-dlp 代理 URL { #yt-dlp-proxy-url }

yt-dlp 和相关出站请求使用的可选代理 URL。支持 HTTP、HTTPS、SOCKS4 和 SOCKS5 代理 URL。留空可直接连接。

### yt-dlp 版本 { #yt-dlp-version }

使用**检查版本**查看已安装的 yt-dlp 版本。**更新 yt-dlp**会安装稳定版，**安装 yt-dlp Nightly**会安装 nightly 版。当提供商发生变化，或当前版本不再适用于某个视频来源时，请更新 yt-dlp。

### 并行 YouTube 搜索 { #parallel-youtube-search }

同时搜索原始查询和卡拉 OK 版本。这样可能返回更有用的结果，但会产生额外的出站请求。

### 歌词提供者 { #lyrics-providers }

启用或禁用内置歌词提供商：

- **NetEase 歌词**
- **LRCLIB 歌词**

如果某个提供商不可用，或你不希望在歌词搜索中使用它，可以将其禁用。
