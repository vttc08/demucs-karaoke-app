# 媒体管理

本指南介绍如何管理导入的媒体、修复歌词时间、编辑视频文件，以及转换 CD+G 卡拉 OK 格式。

## 目录

- [导入和导出媒体](#import-and-export-media)
- [重新同步不准确的 WhisperX 歌词](#resynchronize-inaccurate-whisperx-lyrics)
- [调整视频时长和元数据](#adjust-video-duration-and-metadata)
- [更新 CD+G 格式](#modernize-cdg-formats)

## 导入和导出媒体 { #import-and-export-media }

您可以下载应用为卡拉 OK 创建的所有文件，包括分离的人声和逐词同步的 JSON 歌词。

1. 前往 `/media`，点击**编辑**。
2. 展开**文件管理**。
3. 点击**下载 ZIP**下载所有文件，或下载单个文件。
4. 不再需要时，可以删除人声和歌词等旁车文件。

**下载 ZIP**选项会将媒体文件打包成归档文件。您可以通过 `/upload` 上传该归档，以备份和恢复卡拉 OK 媒体。

对于由外部管理的媒体，应用预期使用以下旁车文件命名约定：

- `<song>.mp4`：主视频文件。导入已分离人声的视频时，视频中应只包含伴奏音频。
- `<song>.vocals.mp3`：分离出的人声音频。
- `<song>.json` 或 `<song>.lrc`：逐词同步歌词或普通歌词。JSON 文件应由 WhisperX 生成。

WhisperX JSON 示例：

```json
{"segments":[{"start":0.0,"end":5.0,"text":"Hello, world!","words":[{"start":0.0,"end":2.5,"word":"Hello"},{"start":2.5,"end":5.0,"word":"world"}]}]}
```

??? note "非 WhisperX JSON 文件"

    如果 JSON 文件不符合 WhisperX 格式，或文件本身格式错误，应用不会处理它，歌词也无法正常使用。

将文件复制到 `media` 文件夹，然后扫描媒体库以发现新曲目。

## 重新同步不准确的 WhisperX 歌词 { #resynchronize-inaccurate-whisperx-lyrics }

??? note "严重的同步问题"

    如果歌词快速移动并且明显不同步，WhisperX 可能检测到了错误的语言，或使用了不适合对齐的模型。请删除现有的 JSON 歌词，然后手动指定语言覆盖，再次运行 WhisperX 对齐。

    1. 在媒体编辑器页面展开**文件管理**，删除 JSON 歌词。
    2. 再次启用**歌词同步**，并打开 **WhisperX 对齐**。
    3. 在**WhisperX 语言覆盖**中手动指定语言代码。

对于较小的同步问题，例如某个词结束得太早，或一直显示到下一段副歌，可以使用第三方工具微调时间。请下载 `.vocals.mp3` 文件作为时间参考。编辑完成后，上传相应的文件，服务器会将其重新处理为 JSON。

![字幕编辑器](../assets/images/subtitleeditor.webp)

### SSA 卡拉 OK 时间轴

应用会导出包含卡拉 OK 时间轴的 `.ass` 字幕文件。您可以使用 [Aegisub](https://aegisub.org/) 微调时间，并导出新的 `.ass` 文件。

- [卡拉 OK 时间轴教程](https://aegisub.org/docs/latest/karaoke_timing_tutorial/)
- [YouTube：Aegisub 第 10 课——如何制作卡拉 OK 视频](https://www.youtube.com/watch?v=4YTIaMeKXts)

![Aegisub](../assets/images/sysadmin/aegisub.gif)

1. 将人声和 `.ass` 文件导入 Aegisub。
2. 启用**卡拉 OK 时间轴**，编辑逐词时间。
3. 禁用该选项，编辑逐行时间。
4. 左键单击设置某行的起点，右键单击设置终点。
5. 按空格键，配合人声预览时间效果。

这不是完整的 Aegisub 教程。

### SRT 逐词编辑

应用还会导出带有时间标记的 `.srt` 字幕文件，其中每个单词都是独立的字幕条目。您可以使用 [Subtitle Edit](https://www.nikse.dk/SubtitleEdit/) 微调时间，并导出新的 `.srt` 文件。

![Subtitle Edit](../assets/images/sysadmin/subtitleedit.gif)

1. 将人声和 `.srt` 文件导入 Subtitle Edit。
2. Subtitle Edit 应会自动生成人声波形。
3. 拖动每个单词的起止时间，修改其时间轴。

??? warning "请勿删除 `//wx:meta` 和 `//wx:time` 行"

    这些行标记是重新生成逐词同步歌词所必需的。

### 拆分和合并歌词行

![较长的歌词](../assets/images/sysadmin/long-lyrics.webp)

有时原始歌词包含无法自然断开的长句，导致卡拉 OK 显示时出现多行。可以调整布局或重新换行歌词，使每行卡拉 OK 歌词的字符数保持一致。

您还可以[减小文本大小或增大最大宽度](stage-and-branding.md#typography-and-layout)来改善显示效果。

有两种修复方式：

1. 在 [创建 AI 卡拉 OK](create-ai-karaoke.md) 页面进行 WhisperX 处理时设置**重新换行歌词**。默认值为英文每行 36 个字符、CJK 每行 12 个字符。请选择最适合歌词预设和自定义样式的上限。
2. 手动拆分和合并。在最自然的单词边界处拆分长行，或合并多个较短的行。

![拆分和合并](../assets/images/sysadmin/merge-split.gif)

1. 在**歌词编辑器**中选择**拆分和合并**，打开拆分和合并编辑器。
2. 使用**自动处理**，并指定**最大行长**，自动拆分超过限制的行。
3. 点击某个单词，在该单词后拆分歌词行。
4. 点击**合并下方**，将当前行与下一行合并。
5. 如有需要，可以撤销更改。

## 调整视频时长和元数据 { #adjust-video-duration-and-metadata }

下载 YouTube 视频时，应用会保留默认元数据：标题使用视频标题，艺人为空，文件名为 `<video_title>.mp4`。这可能不利于媒体库整理。视频也会按原样下载，而许多卡拉 OK 视频包含不适合无缝播放的片头和片尾。

有关调整视频元数据的信息，请参阅[修改现有视频](create-ai-karaoke.md)。

### 无损裁剪 { #lossless-trim }

??? note "无损裁剪无法做到完全精确"

    应用使用 I 帧裁剪视频，不会重新编码。因此，裁剪只能发生在 I 帧处，无法精确裁剪到指定时间；应用会选择距离指定时间最近的 I 帧。

??? warning "裁剪不可逆"

    裁剪操作不可逆。视频裁剪后，原始视频将丢失。

![无损裁剪](../assets/images/videotrimmer.webp)

编辑器会显示所有可以执行裁剪的 I 帧时间点。

- 拖动手柄调整起止时间。每个手柄都会吸附到最近的 I 帧。
- 在输入框中指定起止时间。应用会选择包含各指定时间的 I 帧。
- 播放视频，使用 **:material-rewind: 设置**和 **:material-fast-forward: 设置**按钮设置起止点。
- 使用 **:material-rewind:** 和 **:material-fast-forward:** 按钮跳转到上一个或下一个 I 帧。
- 使用 **:material-rewind: 跳转**和 **:material-fast-forward: 跳转**按钮，预览起止点之间的裁剪结果。

??? tip "使用键盘快捷键加快预览"

    - ++i++ / ++o++：设置裁剪的起点和终点
    - ++bracket-left++ / ++bracket-right++：在检测到的关键帧之间移动
    - ++comma++ / ++period++：将播放头移动一帧
    - ++home++ / ++end++：跳转到开头或结尾

## 更新 CD+G 格式 { #modernize-cdg-formats }

CD+G 是一种传统卡拉 OK 格式，以图形形式显示歌词，通常与 MP3 文件一起作为 MP3+G 使用。舞台可以播放 CD+G 图形，但除非先转换为视频，否则不支持[裁剪](#lossless-trim) CD+G 文件。

对 CD+G 文件打开编辑器时，应用会提示您打开**转码为 MP4**，而不是打开无损裁剪编辑器。

- 在编辑器中，将 CD+G 图形和 MP3 音频转码为 MP4 视频。
- 选择**创建 MP4 后替换原始 CD+G 文件**，创建新的媒体项目，同时保留原始 CD+G 项目。
