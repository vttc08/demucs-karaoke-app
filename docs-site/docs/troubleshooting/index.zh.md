# 故障排除 { #troubleshooting }

本页面介绍主应用和 Demucs 服务的常见问题及可能的解决方法。如需了解特定任务的操作步骤，请参阅[用户任务指南](../tasks/for-users.md)。

## 目录

- [无法访问应用或 Demucs](#application-or-demucs-is-not-accessible)
    - [Demucs 连接失败](#demucs-connection-fails)
- [yt-dlp 下载失败](#yt-dlp-fails-to-download)
- [找不到歌词或歌词不正确](#lyrics-cannot-be-found-or-are-incorrect)
- [人声分离速度很慢](#vocal-separation-is-very-slow)
- [WhisperX 对齐失败或耗时过长](#whisperx-alignment-fails-or-takes-too-long)
- [WhisperX 歌词同步效果差](#whisperx-lyrics-are-poorly-synchronized)
- [iOS 播放问题](#ios-playback-issues)

## 无法访问应用或 Demucs { #application-or-demucs-is-not-accessible }

如果无法访问主应用，请检查以下项目。

检查 [HOST 设置](../configuration/environments.md#server-and-routing)。如果监听 `localhost` 或 `127.0.0.1`，应用只能从运行它的主机访问。要让局域网中的其他设备访问，请使用主机的局域网 IP 地址。在 Docker 中运行时，请监听 `0.0.0.0`，因为容器使用独立的网络和 NAT 层。

检查 Docker 端口映射。对于 `-p 8000:8000`，左侧是主机端口，右侧是容器端口。主机端口可以使用机器上的任意空闲端口，但容器端口必须与 [PORT 设置](../configuration/environments.md#server-and-routing)一致。

例如，如果容器仍配置为 `PORT=8000`，则 `-p 8001:8001` 不会生效。此时应使用 `-p 8001:8000`，或者将容器内的 `PORT` 改为 8001。

还要确认主机防火墙允许该主机端口的入站流量。

### 允许应用通过 Windows 防火墙 { #allow-the-application-through-windows-firewall }

在 Windows 上，可以通过**具有高级安全性的 Windows Defender 防火墙**创建入站规则：

1. 打开**具有高级安全性的 Windows Defender 防火墙**。
2. 选择**入站规则**，然后选择**新建规则**。
3. 选择**端口**，选择 **TCP**，并输入主机端口，例如 8000。
4. 选择**允许连接**。
5. 将规则应用到适当的配置文件。对于可信的家庭网络，通常应选择**专用**。
6. 为规则输入名称，例如 Karaoke Application，然后选择**完成**。

??? note "也可以在管理员 PowerShell 终端中创建规则"

    ```powershell
    New-NetFirewallRule `
      -DisplayName "Karaoke Application" `
      -Direction Inbound `
      -Protocol TCP `
      -LocalPort 8000 `
      -Action Allow `
      -Profile Private
    ```

在 Windows 计算机上，请确保网络配置文件设置为**专用**。

??? note "在管理员 PowerShell 终端中检查或修改配置文件"

    ```powershell
    Get-NetConnectionProfile |
      Where-Object { $_.NetworkCategory -ne 'Private' } |
      ForEach-Object {
        $_
        Set-NetConnectionProfile -InterfaceIndex $_.InterfaceIndex -NetworkCategory Private -Confirm:$false
      }
    ```

### Demucs 连接失败 { #demucs-connection-fails }

如果 Demucs 报告连接超时或无法访问主机，请检查 Demucs 服务的主机地址和端口是否填写正确。

- 在 Docker 中，`localhost` 指向当前容器。如果两个服务位于同一个 Docker 网络，请使用 Demucs 容器名称。
- 如果 Demucs 在同一局域网的另一台计算机上运行，请使用该计算机的局域网 IP 地址。
- 如果 Demucs 服务要求 API 密钥，请确认配置的密钥正确。
- 检查 Demucs 服务日志，查看 Demucs 或 WhisperX 错误。

服务成功启动时，应包含以下内容：

```text
INFO   Application startup complete.
```

您可以[验证 Demucs 服务是否正常](../getting-started/demucs-service.md#5-verify-application-health)。

有时，虚拟环境没有激活，或者启动 Demucs 服务时使用了错误的环境。启动服务前，请激活正确的虚拟环境。

如果 Demucs 通过互联网运行，请参阅[公开远程 Demucs 服务](../tasks/server-administration.md#expose-a-remote-demucs-service)。

## yt-dlp 下载失败 { #yt-dlp-fails-to-download }

YouTube 可能会屏蔽或限制 VPS 提供商使用的 IP 地址。即使是家庭网络，也可能暂时受到速率限制或被屏蔽。

如果问题是暂时的，最快的解决方法是在失败的任务上选择**重试**。

如果下载仍然失败，请[为 yt-dlp 下载配置代理服务器](../tasks/server-administration.md#use-a-proxy-server-for-downloads)。

最后，可以使用手机上的 [Seal](https://f-droid.org/en/packages/com.junkfood.seal/) 下载视频，或在另一台计算机或网络上使用 yt-dlp。然后将[视频上传](../tasks/create-ai-karaoke.md#create-karaoke-from-uploaded-files)到应用。

## 找不到歌词或歌词不正确 { #lyrics-cannot-be-found-or-are-incorrect }

请确保主卡拉 OK 应用是最新版本。请参阅[升级](../getting-started/backup-and-restore.md#upgrade)。

要使用歌词功能，您**必须**配置 [Last.fm 和 Musixmatch API 密钥](../getting-started/docker.md#3-configure-the-environment)。

应用目前会搜索 Musixmatch、LRCLIB 和 Netease。如果这些提供商都没有相应歌词，应用就无法找到歌词。

[Google 歌词选项](../tasks/create-ai-karaoke.md#3-add-lyrics)会搜索 `Artist - Title lyrics`。您可以复制搜索结果并将歌词粘贴到文本框中。歌词不需要预先同步，普通歌词也可以使用。

如果应用找到的歌词不正确，可能是 Last.fm 推断出了错误的歌曲名或艺人。请输入正确的歌曲名和艺人，然后再次搜索。

如果内置提供商都无法使用，而您想使用自己的提供商，请按照[自定义歌词提供商说明](../configuration/custom-lyrics-provider.md)操作。

欢迎提交拉取请求，以添加新的提供商或修复现有提供商的实现。

## 人声分离速度很慢 { #vocal-separation-is-very-slow }

!!! note "Demucs 的进度可能会在接近 90% 时暂停"

    如果 Demucs 在 90% 附近停留几秒，这是正常现象。Demucs 只报告人声分离的进度，不包括其他准备和清理工作，而应用无法捕获这些额外工作的进度。

Demucs 使用 NVIDIA CUDA GPU 时效果最佳。如果有支持 CUDA 的 GPU，请检查 [Demucs 服务状态](../getting-started/demucs-service.md#5-verify-application-health)，确认后端已识别该 GPU。

仅使用 CPU 时，[Sherpa+Spleeter](../tasks/create-ai-karaoke.md#cpu-processing) 的速度明显快于 Demucs，但质量较低。您可以改用它，并查看[卡拉 OK 处理配置](../configuration/karaoke-processing.md#separation-options)。

## WhisperX 对齐失败或耗时过长 { #whisperx-alignment-fails-or-takes-too-long }

WhisperX 会使用大量 VRAM，因此应用会在每次人声分离后自动卸载模型并运行垃圾回收。这样会略微增加对齐时间，但有助于防止 WhisperX 卡住。

如果 WhisperX 在使用 GPU 时仍然卡住，请取消任务。运行 [Demucs GC](../configuration/tools.md#run-demucs-gc) 释放 GPU 显存，然后重试。

如果歌词不准确或检测到了错误的语言，WhisperX 对齐也可能耗时更长。如果知道音频所用的语言，请重试并[指定语言覆盖](../tasks/media-administration.md#resynchronize-inaccurate-whisperx-lyrics)。

??? tip "在日志中检查检测到的语言"

    查看 Demucs 服务日志。对齐异常时，WhisperX 很可能检测到了错误的语言。

    ```text
    2026-09-13 20:34:28 - whisperx.asr - INFO -
    Detected language: ja (0.68) in first 30s of audio
    ```

处理歌曲期间，您可以将另一首歌曲加入队列。对齐通常需要一到两分钟，比一首标准的三分钟歌曲短。您也可以在卡拉 OK 活动之前或之后预先处理自己或嘉宾喜欢的曲目，此时处理速度不那么重要。

如果朋友有支持 CUDA 的计算机，可以请他们运行 Demucs 服务，具体请参阅[通过互联网公开服务的说明](../tasks/server-administration.md#expose-a-remote-demucs-service)。

## WhisperX 歌词同步效果差 { #whisperx-lyrics-are-poorly-synchronized }

没有任何模型是完美的，因此出现轻微同步问题是正常的。出现严重问题时，通常是 WhisperX 检测到了错误的语言。如果知道音频所用的语言，请重试并[指定语言覆盖](../tasks/media-administration.md#resynchronize-inaccurate-whisperx-lyrics)。

如需了解如何修复轻微和严重的同步问题，请参阅[重新同步不准确的 WhisperX 歌词](../tasks/media-administration.md#resynchronize-inaccurate-whisperx-lyrics)。

## iOS 播放问题 { #ios-playback-issues }

在 iOS 设备上，可能会遇到视频无法播放、视频冻结、播放按钮无响应或视频卡顿等问题。

有关已知限制和解决方法，请参阅[使用 iPhone 或 iPad 作为舞台显示](../tasks/stage-and-branding.md#use-an-iphone-or-ipad-as-a-stage-display)。
