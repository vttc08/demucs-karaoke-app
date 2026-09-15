# 媒体编辑 { #media-editing }

管理员可以在媒体库的编辑控件中使用媒体编辑工具。

## 无损裁剪 { #lossless-trimmer }

![无损裁剪工具](../assets/images/videotrimmer.webp){ width="600" }

有些卡拉 OK 歌曲可能带有很长的片头、品牌画面或片尾提醒，音乐视频也可能包含没有音乐的片段。为了获得更好的卡拉 OK 体验，请使用**无损裁剪**删除这些部分。

使用无损裁剪时，歌词、人声等附属文件会自动裁剪到相同范围。该工具使用 I 帧（关键帧）快速裁剪视频，无需重新编码，也不会降低画质。

## 歌词编辑器 { #lyrics-editor }

![歌词编辑器](../assets/images/subtitleeditor.webp){ width="600" }

WhisperX 的输出可能不够完美，你可能需要对歌词进行小幅调整。**歌词编辑器**会将 WhisperX 的输出转换为标准卡拉 OK 字幕格式，让你可以使用外部程序调整时间。支持 ASS 和 SRT 两种格式。

<div class="grid cards" markdown>

-   :material-subtitles:{ .lg .middle } __ASS 格式__

    ---

    ASS 支持卡拉 OK 时间轴。每一行都会转换为带有 `\k` 标记和时间码的标准格式。

    使用 [Aegisub](https://aegisub.org/) 编辑 ASS 文件。

-   :material-subtitles-outline:{ .lg .middle } __SRT 格式__

    ---

    SRT 是广泛使用的字幕格式。每个词都会转换为一行字幕。

    使用 [Subtitle Edit](https://www.nikse.dk/SubtitleEdit/) 编辑 SRT 文件。

</div>

## 添加人声 { #add-vocals }

![添加人声](../assets/images/addvocals.webp){ width="600" }

在预先制作的卡拉 OK 视频中加入伴唱人声有助于练习。**添加人声**功能允许你搜索 YouTube 或上传完整歌曲，然后使用 Demucs 提取其中的人声。

安装支持的[人声同步额外依赖](../tasks/create-ai-karaoke.md)后，可以自动将提取的人声与原卡拉 OK 视频同步。完整流程请参阅“在预先制作的卡拉 OK 视频中添加人声”部分。你也可以手动调整人声轨道的时间，增加或减少延迟。
