# 自定义歌词提供商 { #custom-lyrics-providers }

应用可以在运行时从本地 Python 文件或目录加载你自己的备用歌词提供商。

![自定义歌词提供商](../assets/images/custom.webp)

## 配置 { #configuration }

将 `LYRICS_PROVIDER_CUSTOM_PATHS` 设置为以逗号分隔的目录或 Python 文件列表：

```bash
LYRICS_PROVIDER_CUSTOM_PATHS=/app/custom_lyrics,/mnt/shared/lyrics_provider.py
```

### Docker { #docker }

使用 Docker 时，必须将自定义提供商文件挂载到容器中，并使用容器内的路径设置 `LYRICS_PROVIDER_CUSTOM_PATHS`。

```yaml
      LYRICS_PROVIDER_CUSTOM_PATHS: /app/custom_lyrics
    volumes:
      - ./custom_lyrics:/app/custom_lyrics
```

## 接口约定 { #contract }

使用 AI 编写自定义歌词提供商时，可以复制下面的提示词模板：
```
I want you to help me write a custom lyrics provider plugin based on the specifications. Please fetch this URL https://raw.githubusercontent.com/vttc08/demucs-karaoke-app/refs/heads/main/custom_lyrics_providers.md for which explains the requirements and structure of a custom lyrics provider, including the InferredSong input and the LyricsPayload output. I will include information about the lyrics provider I want to create, and you will generate the code for it. Please ensure that the generated code adheres to the requirements and structure outlined in the provided documentation.
```

每个提供商模块应定义一个提供商类，通常命名为 `LyricsProvider` 或 `CustomLyricsProvider`。

基本结构如下：

```python
from services.lyrics_types import InferredSong, LyricsPayload


class LyricsProvider:
    name = "hello-world"

    async def fetch(self, inferred_song: InferredSong, **kwargs):
        # Implement your lyrics lookup, proxy rotation, caching, etc. here.
        return LyricsPayload()
```

必须满足以下要求：

- 类必须可以无参数实例化。
- `name` 必须是非空字符串。
- `fetch(...)` 必须是 `async` 函数（同步函数可以通过 `asyncio.to_thread` 包装）。
- `fetch(...)` 会接收规范化的歌曲元数据 `inferred_song`。
- 加载器还会传入 `title`、`artist` 等关键字提示，因此自定义实现应接受 `**kwargs`，即使不使用这些参数。
- 如果提供商找不到匹配结果，必须返回 `None`。

## 函数输入：`InferredSong` { #function-input-inferredsong }

`InferredSong` 是应用根据现有信息整理出的最佳歌曲描述。歌词查询最重要的字段包括：

- `title`：规范化后的歌曲标题。
- `artist`：规范化后的艺人名称（应用能够推断时才有值）。
- `source`：元数据来源，例如 YouTube 或其他输入路径。


## 返回类型：`LyricsPayload` 或 `None` { #return-type-lyricspayload-or-none }


对于需要返回更多结构化信息的提供商，`LyricsPayload` 是其标准返回类型。

它包含以下字段：

- `lyrics`：歌词文本本身（多行字符串）。
- `is_synced`：歌词是否包含时间戳。
- `provider`：简短的提供商名称，例如 `hello-world`。
- `inferred_song`：本次查询使用的 `InferredSong`。
- `provider_score`：应用比较多个备用匹配结果时使用的内部置信度分数。
    - 取值范围为 0 到 250，分数越高越优先。
- `provider_details`：用于调试或未来扩展的可选额外元数据。
- `alternatives`：可选的 `LyricsAlternative` 元组。当提供商可以提供同一结果的其他格式时，可以使用此字段。基础歌词仍然是处理时的安全默认值；界面可以选择 TTML 替代版本，同时保留基础 LRC，以便需要时降级。

带有可选 TTML 升级的提供商示例：

```python
from services.lyrics_types import InferredSong, LyricsAlternative, LyricsPayload


class LyricsProvider:
    name = "example"

    async def fetch(self, inferred_song: InferredSong, **kwargs):
        lrc = "[00:01.00]Original synced lyrics"
        ttml = "<tt>...valid timed TTML...</tt>"
        return LyricsPayload(
            lyrics=lrc,
            is_synced=True,
            provider=self.name,
            inferred_song=inferred_song,
            alternatives=(
                LyricsAlternative(
                    lyrics=ttml,
                    format="ttml",
                    provider=self.name,
                    is_synced=True,
                ),
            ),
        )
```

内置的 Musixmatch 提供商使用此接口实现可选的 TTML 升级。如果升级失败，应用会将其视为缺少替代版本，因此基础歌词结果仍然可用。

## 实现说明 { #implementation-notes }

- 如果提供商调用 HTTP API，请使用 `httpx` 发起网络请求。
- 如果提供商需要调用其他程序，请使用 `subprocess`。
- 自定义提供商也可以代理到专用的歌词 Web 服务器。

## Hello World 示例 { #helloworld-example }

```python
from services.lyrics_types import InferredSong, LyricsPayload
# import other libraries such as httpx, subprocess, etc. if needed

class LyricsProvider:
    name = "hello-world"

    async def fetch(self, inferred_song: InferredSong, **kwargs):
        # support both inferred_song and kwargs for title/artist hints
        title = inferred_song.title or kwargs.get("title")
        artist = inferred_song.artist or kwargs.get("artist")
        
        # Your custom logic goes here
        # lyrics = find_lyrics(title, artist)
        # is_synced = check_if_synced(lyrics)
        # score = calculate_provider_score(lyrics)

        return LyricsPayload(
            lyrics="""[00:00.00]Hello world
[00:02.00]From a custom provider
[00:04.00]This is just an example""",
            is_synced=is_synced,
            provider="hello-world",
            inferred_song=inferred_song,
            provider_score=250
        )
```

- 必须从 `services.lyrics_types` 导入相关类型，否则加载器无法识别你的提供商。
- 认证信息、代理设置等其他变量，可以在类构造函数或类属性中声明。
- `lyrics` 必须是多行字符串，不能是文件、路径或 URL 引用。
- `is_synced` 为 `False` 时表示纯文本歌词，为 `True` 时表示歌词包含时间戳。
- 不要返回歌词为空的 `LyricsPayload`；这种情况下应返回 `None`。
- 如果希望应用将你的提供商作为备用来源考虑，请不要返回空分数或 0 分，使用 1 分或更高分数。
- 可以使用最高分 250，这样应用会始终优先选择你的提供商，而不是其他提供商。
