# 舞台 { #stage }

![舞台设置](../assets/images/settings/stage.webp){ width="400" }

使用此区域配置舞台视图的二维码目标地址、空队列大厅媒体和默认人声音量。部署需要固定值时，也可以通过[环境变量](environments.md)配置这些设置。

### 舞台二维码 URL { #stage-qr-url }

此可选 URL 会编码为舞台视图中显示的二维码。留空时，应用会使用当前主机名生成目标地址。

### 舞台大厅媒体 URL { #stage-lobby-media-url }

此可选媒体 URL 用于队列为空时循环播放大厅内容。请使用相对于媒体目录的 `/media/...` URL，例如 `/media/stage-lobby.mp4`。

### 默认人声音量 { #default-vocals-volume }

应用重启后，舞台或点歌页面加载时会采用此音量。请输入 `0` 到 `100` 之间的百分比。运行期间仍可从舞台页面调整人声音量。

对应的 `STAGE_VOCALS_VOLUME_DEFAULT` 环境变量使用 `0.0` 到 `1.0` 之间的小数值；例如，`0.46` 表示 `46%`。
