# 创建 AI 卡拉 OK { #create-ai-karaoke }

应用支持多种创建卡拉 OK 的方式，从下载音乐视频到处理自己的文件。请选择最符合源材料和处理需求的工作流程。

## 目录

- [从音乐视频创建卡拉 OK](#create-karaoke-from-a-music-video)
- [从歌词视频创建卡拉 OK](#create-karaoke-from-a-lyrics-video)
- [从上传文件创建卡拉 OK](#create-karaoke-from-uploaded-files)
- [修改现有视频](#modify-existing-video)
- [为现成的卡拉 OK 视频添加人声](#add-vocals-to-a-premade-karaoke-video)
- [最快或效果最佳的卡拉 OK](#fastest-or-best-case-karaoke)

## 从音乐视频创建卡拉 OK { #create-karaoke-from-a-music-video }

从音乐视频创建卡拉 OK 可以带来最沉浸式的体验，并支持自定义歌词样式。这也是处理量最大的一种方式。若要加快处理速度，请在支持 GPU 的设备上运行 Demucs 服务。

![AI 卡拉 OK 完整流程](../assets/images/tasks/ai-karaoke-fullflow.webp){ width="800" }

### 1. 选择音乐视频 { #1-select-a-music-video }

1. 搜索歌曲，并从搜索结果中选择一个音乐视频。
2. 应用不会自动判断视频是否包含歌词或卡拉 OK 内容，因此会同时启用人声分离和歌词处理。

### 2. 配置卡拉 OK 选项 { #2-configure-karaoke-options }

排队前页面提供以下选项：

- **WhisperX 单词对齐**：为卡拉 OK 创建逐词同步的歌词。
- **重新换行歌词**：设置每行的最大字符数，超过后换到下一行。
    - 对于中文、日文和韩文等东亚语言（CJK），请改为调整 `Max CJK Chars`。
- **语言覆盖**：指定 [WhisperX 对齐](../configuration/whisperx-lyrics.md#whisperx-alignment-language)所使用的语言。设置后会跳过自动语言检测，也不会使用已配置的默认语言。

### 3. 添加歌词 { #3-add-lyrics }

WhisperX 需要歌词才能创建卡拉 OK 时间轴。应用会搜索已配置的歌词提供商。

- 应用首先使用 Last.fm，根据视频标题推断歌曲名和艺人。如果结果不正确，请在搜索前手动输入歌曲名和艺人。
- **Google** 按钮会打开新标签页，并搜索 `Artist - Title lyrics`。请将搜索结果复制到**歌词编辑器**中。
- 也可以上传 `.lrc` 或 `.txt` 歌词文件。
- 将歌曲加入卡拉 OK 队列前，请按需编辑歌词。

??? tip "升级 LRC 歌词"

    部分歌词可以升级为 TTML（Timed Text Markup Language，定时文本标记语言），通常来源于 Apple Music。TTML 已经包含逐词同步信息，可以提供更准确的卡拉 OK 时间轴，并跳过 WhisperX 处理。

    如果升级失败或返回了错误的歌词，请改用标准歌词结果。

### 4. 处理歌曲 { #4-process-the-song }

歌曲加入队列后，应用会下载源文件、分离人声、对齐歌词，并准备好用于舞台播放的卡拉 OK 媒体。

!!! note "处理失败时"

    如果下载失败，请参阅 [yt-dlp 故障排除指南](../troubleshooting/index.md#yt-dlp-fails-to-download)。如果人声分离出现问题，请参阅[人声分离速度很慢](../troubleshooting/index.md#vocal-separation-is-very-slow)。如果歌词对齐失败或同步不正确，请参阅 [WhisperX 对齐故障排除](../troubleshooting/index.md#whisperx-alignment-fails-or-takes-too-long)和 [WhisperX 同步故障排除](../troubleshooting/index.md#whisperx-lyrics-are-poorly-synchronized)。

## 从歌词视频创建卡拉 OK { #create-karaoke-from-a-lyrics-video }

![歌词视频示例](../assets/images/tasks/lyricsvideo.webp)

YouTube 上有大量歌词视频。它们通常不包含逐词同步的歌词，但可能提供一些用户喜欢的视觉样式和背景。歌词视频还可以跳过 WhisperX 对齐，在仅使用 CPU 的设备上减少处理时间。

### 1. 选择歌词视频 { #1-select-a-lyrics-video }

1. 搜索歌曲，并从搜索结果中选择一个歌词视频。
2. 应用会识别歌词视频，只启用人声分离并跳过歌词处理。

### 2. 等待人声分离 { #2-wait-for-vocal-separation }

歌曲需要进行人声分离。处理完成后，歌曲会显示在舞台上。

??? note "歌词视频的同步效果不一定理想"

    歌词视频通常是逐行同步，而不是逐词同步。它们也经常优先考虑视觉效果和动画，因此行与行之间的切换可能无法与音乐精确匹配。不过，熟悉歌曲后通常不太容易注意到这一点。

!!! note "处理失败时"

    如果下载失败，请参阅 [yt-dlp 故障排除指南](../troubleshooting/index.md#yt-dlp-fails-to-download)。如果人声分离失败或耗时过长，请参阅[人声分离速度很慢](../troubleshooting/index.md#vocal-separation-is-very-slow)。

## 从上传文件创建卡拉 OK { #create-karaoke-from-uploaded-files }

从带有专辑封面的 MP3 文件创建卡拉 OK，可以获得沉浸式且可自定义的体验。当应用无法下载视频、其他设备或网络更适合下载，或者您想使用个人媒体库中的文件时，上传也很有用。

![上传自动化](../assets/images/media/autopilot.gif)

### 1. 上传文件 { #1-upload-a-file }

点击上传区域，或将文件拖放到上传区域中。

??? tip "上传自动化"

    自动化功能只需点击一次，就会准备默认的卡拉 OK 选项：

    - 从文件名推断曲目信息。
    - 搜索并下载歌词。
    - 填写歌曲名、艺人和卡拉 OK 处理选项。
    - 在提交前创建经过优化的卡拉 OK 处理设置。

### 2. 配置上传的歌曲 { #2-configure-the-uploaded-song }

可用的歌词选项请参阅[从音乐视频创建卡拉 OK](#create-karaoke-from-a-music-video)。上传流程提供相同的选项。

### 3. 选择歌曲的添加位置 { #3-choose-where-to-add-the-song }

启用**添加到队列**后，歌曲会加入队列，并在处理完成后显示在舞台上。关闭此选项后，处理完成的歌曲会添加到媒体库，供日后使用。

!!! note "处理失败时"

    如果人声分离失败或耗时过长，请参阅[人声分离速度很慢](../troubleshooting/index.md#vocal-separation-is-very-slow)。如果歌词对齐失败、耗时过长或同步不正确，请参阅 [WhisperX 对齐故障排除](../troubleshooting/index.md#whisperx-alignment-fails-or-takes-too-long)和 [WhisperX 同步故障排除](../troubleshooting/index.md#whisperx-lyrics-are-poorly-synchronized)。

## 修改现有视频 { #modify-existing-video }

应用可以对媒体库中的现有媒体执行人声分离和歌词对齐。

![从现有媒体创建 AI 卡拉 OK](../assets/images/media/create.gif)

### 1. 打开媒体编辑器 { #1-open-the-media-editor }

1. 打开媒体页面，点击媒体项目的**编辑**。
2. 在**编辑媒体详情**页面中修改歌曲名、艺人或卡拉 OK 处理选项。
3. 使用**自动**通过 Last.fm 根据文件名推断歌曲名和艺人。
    - 这会修改媒体库中的名称。如果还要修改文件名，请启用**在磁盘上重命名**。

??? note "在磁盘上重命名"

    只有点击**重命名**后，文件才会被重命名。如果只想修改歌曲名、艺人或文件名，而不处理媒体，请不要修改**AI 卡拉 OK**或**歌词同步**选项。

### 2. 配置歌词和处理 { #2-configure-lyrics-and-processing }

可用的歌词选项请参阅[从音乐视频创建卡拉 OK](#create-karaoke-from-a-music-video)。

??? note "歌词同步和 WhisperX"

    仅启用**歌词同步**并提供歌词时，应用会保存歌词文件，但不会运行 WhisperX。若要创建同步歌词，请再次编辑媒体并启用 **WhisperX 对齐**。

!!! note "处理失败时"

    如果人声分离失败或耗时过长，请参阅[人声分离速度很慢](../troubleshooting/index.md#vocal-separation-is-very-slow)。如果歌词对齐失败、耗时过长或同步不正确，请参阅 [WhisperX 对齐故障排除](../troubleshooting/index.md#whisperx-alignment-fails-or-takes-too-long)和 [WhisperX 同步故障排除](../troubleshooting/index.md#whisperx-lyrics-are-poorly-synchronized)。

## 为现成的卡拉 OK 视频添加人声 { #add-vocals-to-a-premade-karaoke-video }

如果您喜欢现成卡拉 OK 视频（例如 Sing King 视频）的歌词样式，但希望在练习时听到人声，可以使用应用为该视频添加人声。

??? tip "自动人声对齐需要 vocal-sync"

    满足条件时，应用可以自动将原始卡拉 OK 伴奏与原音乐视频中分离出的伴奏对齐。请安装 [vocal-sync extra](../getting-started/linux.md#1-prepare-the-application-and-dependencies)，或使用 [vocal-sync Docker 镜像](../getting-started/docker.md#3-configure-the-environment)，以启用自动人声对齐。

### 1. 打开 Vocal Sync { #1-open-vocal-sync }

1. 打开媒体页面，点击**编辑**。
2. 选择**添加人声**，打开 Vocal Sync 页面。

![添加人声](../assets/images/addvocals.webp)

### 2. 准备并对齐人声 { #2-prepare-and-align-the-vocals }

1. 搜索 YouTube，或上传自己的文件，然后点击**准备**。
2. 应用会分离人声和伴奏，并准备预览。
    - 如果 `vocal-sync` 可用，偏移量会自动计算。
3. 使用 **+** 和 **-** 按钮调整偏移量，然后点击**预览**检查结果。
    - **+** 值会延后人声。如果人声早于伴奏开始，请增大该值。
    - **-** 值会提前人声。如果人声晚于伴奏开始，请减小该值。

??? note "使用“预览”检查播放效果"

    请勿使用媒体播放器控件进行检查，因为它们只播放原始视频。请改用**预览**和**停止**。

### 3. 提交结果 { #3-commit-the-result }

对齐效果满意后，点击**提交**。

## 最快或效果最佳的卡拉 OK { #fastest-or-best-case-karaoke }

如果 Demucs 服务没有支持 CUDA 的 GPU，仍然可以使用 CPU 运行 AI 功能。

### CPU 处理 { #cpu-processing }

使用 [Sherpa+Spleeter](../configuration/karaoke-processing.md#separation-backend) 进行人声分离。

- Demucs 服务会根据您的[配置](../configuration/environments.md#processing-and-model-settings)下载模型。
- Sherpa+Spleeter 在 CPU 上运行良好，速度明显快于 Demucs。
- 分离质量不如 Demucs。

### TTML 歌词升级 { #ttml-lyrics-upgrade }

WhisperX 没有简单的纯 CPU 替代方案。一首典型的三分钟歌曲可能需要一到两分钟才能完成分离。不过，部分歌曲可以升级到 TTML 歌词。TTML 已包含逐词同步信息，可以跳过 WhisperX 处理。

TTML 时间轴是官方音乐歌词时间轴，通常与原歌曲发行版本匹配，而不是与某个具体的视频剪辑匹配。如果音乐视频包含片头、片尾或其他剪辑，歌词可能会与视频错开，因此 TTML 不适合这类视频。对于使用原歌曲时间轴的非音乐视频或上传的 MP3 文件，可以使用 TTML；如果视频包含额外或改动的片段，则应使用 WhisperX。

在仅使用 CPU 的设备上，`Sherpa+Spleeter` 配合 TTML 升级可以提供最快且效果最佳的卡拉 OK 体验。
