# 卡拉 OK 处理 { #karaoke-processing }

进行卡拉 OK 处理时，主应用会将音频或适用的完整视频发送到 Demucs 服务进行分离。服务会生成伴奏轨道和人声轨道，并将两者返回给主应用。主应用使用 FFmpeg 将伴奏轨道与原视频合并，同时单独保存人声轨道，并通过 SSE（服务器发送事件）接收 Demucs 的处理进度。

本页用于配置分离引擎、输出格式和处理限制。部署需要固定值时，也可以通过[环境变量](environments.md)配置这些设置。

![卡拉 OK 处理设置](../assets/images/settings/karaoke-processing.webp){ width="400" }

## Demucs 服务 { #demucs-service }

### 分离服务 URL { #separation-service-url }

用于连接 Demucs 服务的 URL。

### 分离服务 API 密钥 { #separation-service-api-key }

Demucs 服务使用的可选 API 密钥。

??? warning "公开 Demucs 服务时强烈建议使用 API 密钥"

    如果用户位于 CG-NAT 后方，并希望与朋友或家人共享 Demucs 服务，可以使用 Cloudflare Tunnel 或类似服务让主应用访问 Demucs。不过，Demucs 服务一旦公开，任何人都可能使用它，因此强烈建议配置 API 密钥。设置方法请参阅 [Demucs 服务环境变量](environments.md#demucs-service)。

## 分离选项 { #separation-options }

### 分离后端 { #separation-backend }

选择 `Demucs` 或 `Sherpa+Spleeter`。

### Demucs 模型 { #demucs-model }

用于音轨分离的模型。默认值为 `htdemucs`，其他模型包括：

- `htdemucs`：Hybrid Transformer Demucs 的第一个版本，在 MusDB 和另外 800 首歌曲上训练。默认模型。
- `htdemucs_ft`：`htdemucs` 的微调版本。分离所需时间约为 4 倍，但效果可能略好；训练数据集与 `htdemucs` 相同。
- `htdemucs_6s`：`htdemucs` 的六源版本，增加了钢琴和吉他音轨。请注意，目前钢琴音轨的效果不太理想。
- `hdemucs_mmi`：Hybrid Demucs v3，在 MusDB 和另外 800 首歌曲上重新训练。
- `mdx`：仅使用 MusDB HQ 训练，在 MDX 挑战赛 A 赛道中获胜的模型。
- `mdx_extra`：使用额外训练数据（包括 MusDB 测试集）训练，在 MDX 挑战赛 B 赛道中排名第二。
- `mdx_q`、`mdx_extra_q`：上述模型的量化版本，下载和存储空间更小，但质量可能略低。
- `SIG`：来自模型库的单一模型。

### Sherpa+Spleeter 模型 { #sherpaspleeter-model }

默认值为 `fp16`。可选择 `int8`、`fp16` 或 `fp32`。`int8` 模型速度最快、体积最小，但质量可能低于 `fp16` 和 `fp32`。

### 设备 { #device }

用于分离的计算设备。请根据 Demucs 服务的能力选择 `cuda` 或 `cpu`。

- 如果选择了 `cuda`，但 Demucs 服务不支持 CUDA，或者使用仅支持 CPU 的 Sherpa+Spleeter 后端，处理会回退到 CPU。

## 输出选项 { #output-options }

### 音轨输出格式 { #stem-output-format }

选择 `mp3` 或 `wav`。建议使用 `mp3`，以缩短网络传输时间并减少存储占用。

### MP3 音轨比特率 { #mp3-stem-bitrate }

MP3 音轨输出的比特率，默认值为 `320`。如果连接 Demucs 的网络较慢，可以降至 `128–160`。

### FFmpeg 音频编码 { #ffmpeg-audio-codec }

FFmpeg 将伴奏音轨与原视频合并时使用的音频编码器。默认留空并使用流复制。只有舞台客户端无法播放合并后的视频时才需要设置；例如，iOS 设备支持 `aac`。

## 处理限制 { #processing-limits }

### 分离服务直接处理媒体的上限（MB） { #separation-direct-media-cutoff-mb }

媒体文件小于此值时，主应用会将视频直接发送给 Demucs，无需先提取音频。默认值为 `500`。如果连接 Demucs 的网络较慢，可将其降至 `20–50`。

### 分离服务回退轮询间隔（秒） { #separation-fallback-poll-interval-seconds }

SSE 连接失败时，主应用轮询 Demucs 进度的间隔，默认值为 `1.0` 秒。
