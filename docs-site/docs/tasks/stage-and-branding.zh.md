# 舞台与品牌

本页面介绍如何为嘉宾配置舞台、自定义歌词显示，以及管理品牌媒体和预设。

## 目录

- [配置舞台](#configure-the-stage)
- [自定义舞台显示](#customize-the-stage-display)
- [自定义品牌](#custom-branding)
- [歌词预设](#lyric-presets)
- [从队列控制修改歌词](#modify-lyrics-from-queue-control)
- [使用 iPhone 或 iPad 作为舞台显示](#use-an-iphone-or-ipad-as-a-stage-display)

## 配置舞台 { #configure-the-stage }

### 1. 配置舞台二维码

为了让嘉宾使用顺畅，请配置一个设备可以访问的二维码 URL。当队列不应公开时，[带访问控制的反向代理](server-administration.md#restrict-access-to-guest-wi-fi-users)会很有用。

![舞台显示](../assets/images/stage.webp)

1. 在设置中配置[二维码 URL](../configuration/stage.md#stage-qr-url)。
2. 在 `/stage` 页面按键盘上的 ++q++，在舞台屏幕上显示二维码。
3. 按 **+** 或 **-** 调整二维码大小。

### 2. 配置舞台大厅

队列为空时，应用会显示默认的卡拉 OK 大厅，其中包含循环播放的视频和提示音。换成自己的大厅媒体，可以让舞台更符合个人风格。

![默认大厅](../assets/images/tasks/stage-lobby.webp)

在设置中配置[舞台大厅媒体 URL](../configuration/stage.md#stage-lobby-media-url)。

创建或选择大厅媒体有以下两种方式：

<div class="grid cards" markdown>

-   **从 YouTube 下载视频**

    ---

    按照[将现成的卡拉 OK 视频加入队列](karaoke-tasks.md#queue-a-premade-karaoke-video)中的说明，将视频下载到媒体库。

    - 可以[重命名视频](create-ai-karaoke.md)，例如改为 `stage-lobby.mp4`，方便识别。

-   **使用 Remotion 创建视频**

    ---

    [Remotion](https://www.remotion.dev/) 是一个用于以编程方式创建视频的框架。与专业视频编辑器相比，它易于设置，也便于 AI 代理使用。

</div>

## 自定义舞台显示 { #customize-the-stage-display }

舞台显示提供丰富的歌词自定义选项。安装默认预设后，可以选择一个作为起点，再根据场地进行调整。

![歌词预设](../assets/images/presets.webp)

!!! note "舞台歌词需要全屏模式"

    为避免舞台上的控件造成干扰，只有舞台处于全屏模式时才会显示歌词。

您可以让 AI 助手生成自定义预设 JSON 文件。以下提示词可作为起点：

??? tip "复制并粘贴 AI 提示词"

    ```text
    You are a creative designer for a karaoke stage display. Generate one complete,
    valid JSON object for a custom lyrics preset. The design brief is:

    [Describe the venue, mood, audience, colors to use or avoid, and whether the
    lyrics will often be Chinese, Latin-script, or mixed.]

    Prioritize visual aesthetics and projected-screen legibility: choose a cohesive
    font, color scheme, typography weight, spacing, line hierarchy, and outline
    that still read clearly over a moving music video. Make the active lyric color
    visually distinct without using low-contrast combinations. Use restrained
    neighbor-line opacity and scale so the current line is obvious from a distance.

    Include the JSON with the following keys and values:
    fontPreset, customFontFamily, customFontWeight, sizeVw, lineWidthPct,
    lineGapVw, neighborLineScalePct, neighborLineOpacityPct, textColor,
    activeColor, outlineColor, outlineWidth, previousLines, nextLines,
    lineBehavior, animation, backgroundMediaEnabled, backgroundMediaPath,
    backgroundMediaOpacityPct.

    Rules:
    - Use one of fontPreset: custom, karaoke_cjk, readable_cjk, system_cjk, serif_cjk.
    - For custom fonts, choose a real Google Fonts family and one supported
      weight from 300, 400, 500, or 700. Otherwise set customFontFamily to an empty
      string and customFontWeight to 700.
    - Use #RRGGBB colors only.
    - Keep values within: sizeVw 3.2-8.8; lineWidthPct 60-100; lineGapVw 0.2-2;
      neighborLineScalePct and neighborLineOpacityPct 30-100; outlineWidth 2-14;
      previousLines and nextLines 0-3; backgroundMediaOpacityPct 10-100.
    - Use rolling, rolling_scroll, or fixed_group for lineBehavior; use slide,
      crop, fade, or none for animation.
    - The crop animation is preferred for classic karaoke scrolling.
    - Do not use a background image or video in this generated design: set
      backgroundMediaEnabled to false and backgroundMediaPath to an empty string.
    - If the user has specified a JSON object with backgroundMediaEnabled, keep
      that value and change the other values to match the design brief.
    ```

如需更多技术细节，请参阅 [`custom_presets.md`](https://raw.githubusercontent.com/vttc08/demucs-karaoke-app/main/custom_presets.md)。

### 字体和布局 { #typography-and-layout }

**字体**是歌词使用的字体。您可以通过 [Google Fonts](https://fonts.google.com/) 选择数百种字体。

**自定义字体栈**是要加载的 Google Fonts 字体系列名称。字体名称区分大小写。

??? warning "字体名称区分大小写"

    `Roboto` 和 `roboto` 是不同的字体名称。拼写错误或大小写错误都会导致字体无法加载。加载 Google Fonts 还需要互联网连接。

**自定义字体粗细**控制字体的粗细。可用选项包括 Light、Regular、Medium 和 Bold。

![歌词布局](../assets/images/lyrics-layout.webp){ width="700" }

**文本大小**以视口宽度单位控制主歌词文本的大小。

**最大宽度**设置歌词行宽度占舞台宽度的最大百分比。

**行间距**以视口宽度单位控制可见歌词行之间的间距。

**文本颜色**是当前未高亮歌词的颜色。

**高亮颜色**是当前歌词文本或当前单词的颜色。

**描边颜色**是用于提高文本可读性的描边颜色。

**描边**控制歌词文本描边的宽度。

![相邻歌词行](../assets/images/lyrics-neighbor.webp){ width="700" }

**前置行数**控制当前行之前显示多少行歌词。使用 `fixed_group` 时会忽略此设置。

**后置行数**控制当前行之后显示多少行歌词。使用 `fixed_group` 时，可见分组包含 `1 + nextLines` 个提示。

**相邻行大小**控制前后歌词行相对于当前行的大小。

**相邻行不透明度**控制前后歌词行的不透明度。

### 动画和行行为

![歌词动画](../assets/images/tasks/lyricsanimation.gif)

**动画**控制文本的过渡效果。`crop` 最接近经典卡拉 OK 的滚动效果。

- `slide`：当前单词会放大突出显示，然后在过渡时恢复正常大小。
- `crop`：当前单词从左向右显示，就像文本正在滚动。
- `fade`：当前单词通过改变不透明度逐渐显示。
- `none`：新单词直接改变颜色，不使用过渡效果。

![行行为](../assets/images/tasks/lyricsbehavior.gif){ width="700" }

**行行为**控制可见歌词窗口的推进方式。

- `rolling`：将当前提示保持在由 `previousLines` 和 `nextLines` 定义的窗口中，当前行保持在同一位置。
- `rolling_scroll`：使用相同的窗口，但随着歌词推进向上滚动。
- `fixed_group`：忽略 `previousLines`，显示包含 `1 + nextLines` 个提示的固定分组，只有当前提示离开该分组后才会推进。

### 背景媒体

**背景媒体**是显示在视频上方、歌词后方的背景图片或视频的相对路径。请参阅[自定义品牌](#custom-branding)。

**启用背景媒体**控制是否在歌词后方显示背景媒体。

**背景不透明度**控制背景图片或视频的不透明度，可用于压暗明亮背景或调整深色图片的显示效果。

## 自定义品牌 { #custom-branding }

对于使用 WhisperX 对齐歌词的卡拉 OK，可以添加背景图片或视频。这样可以压暗背景以提高歌词可读性、遮挡敏感内容，或添加自己的水印和徽标。透明图片（例如 `.png` 文件）可以作为视频上的叠加层。请从舞台歌词设置中配置背景。

![自定义品牌](../assets/images/branding.webp)

??? note "仅在舞台页面可用"

    必须从舞台页面更改背景源。队列控制只能启用或禁用已配置的背景。您可以将不同的品牌图片保存到预设中，需要时在预设之间切换。

默认预设包含两张背景图片：

- `black.png`：纯黑背景。
- `branding1.png`：带有品牌文字和徽标的通用背景，仅用于演示。

## 歌词预设 { #lyric-presets }

所有歌词自定义设置都会保存为 JSON 文件。您可以导入或导出该文件，也可以将其作为预设与他人分享。

在**预设**中选择默认预设，然后点击**应用**或**删除**。要将当前设置保存为预设，请点击**创建**并输入名称。使用**更新**覆盖现有预设。

在**高级传输**中，可以将当前设置导入或导出为 JSON 文件：

- **下载**：将当前设置导出为 JSON 文件。
- **应用**：应用文本框中 JSON 内容的设置。
- **上传**：导入 JSON 文件并覆盖当前设置。

## 从队列控制修改歌词 { #modify-lyrics-from-queue-control }

您可以从队列控制远程控制舞台显示，但可自定义的选项比较有限。

![队列控制中的歌词](../assets/images/queue/queuelyrics.webp)

- **歌词**：显示或隐藏歌词。
- **背景**：显示或隐藏舞台设置中配置的背景图片或视频。
- **目标屏幕**：连接多个屏幕时，选择要控制的舞台显示。
- **预设**：选择要应用的预设。此操作会覆盖当前设置。
- **文本大小**和**最大宽度**：从队列控制快速调整这两个设置。

??? note "应用与覆盖"

    **应用**只会应用预设，不会修改**文本大小**或**最大宽度**。如果要在预设或当前设置的基础上修改这些设置，请使用**覆盖**。

## 使用 iPhone 或 iPad 作为舞台显示 { #use-an-iphone-or-ipad-as-a-stage-display }

Apple 设备可以显示卡拉 OK 舞台，但 iOS 和 iPadOS 浏览器存在一些会影响播放的限制。

### 音频播放限制

iOS 和 iPadOS 无法可靠地同时播放两个媒体源。因此，舞台显示会播放卡拉 OK 视频或伴奏，同时禁用人声轨道，以避免播放不稳定。

- 目前没有可用的解决方法。当应用检测到 iOS 或 iPadOS 用户代理时，会禁用人声轨道。

### 视频和音频兼容性

YouTube 下载通常使用 VP9，而 Demucs 输出轨道使用 MP3。为提高卡拉 OK 处理效率，应用在合并视频和处理后音频时使用流复制，不会重新编码 MP3 容器。Apple 设备可能不支持 VP9 视频、MP3 音频或其他格式。

如需提高兼容性：

- 将 [yt-dlp 视频编码](../configuration/downloads.md#yt-dlp-video-codec)设置为 `avc`，强制下载 H.264 视频。
- 将 [FFmpeg 音频编码](../configuration/karaoke-processing.md#ffmpeg-audio-codec)设置为 `aac`，在合并时重新编码音频。
- 对于自定义品牌或舞台循环播放，请使用 H.264 视频搭配 AAC 音频等兼容媒体。

这些设置只适用于新下载或新处理的歌曲。对于已有歌曲，请先将其转码为 H.264 视频和 AAC 音频，再在 Apple 设备浏览器上使用。
