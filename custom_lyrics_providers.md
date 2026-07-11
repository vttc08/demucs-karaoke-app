# Custom Lyrics Providers

The app can load your own fallback lyrics providers at runtime from local Python files or directories.

## Configuration

Set `LYRICS_PROVIDER_CUSTOM_PATHS` to a comma-separated list of:

- Python files, for example `/app/custom_lyrics/hello.py`
- Directories containing top-level `*.py` provider files, for example `/app/custom_lyrics`

Example:

```bash
LYRICS_PROVIDER_CUSTOM_PATHS=/app/custom_lyrics,/mnt/shared/lyrics_provider.py
```

The loader scans directories in sorted file order and ignores non-`.py` files.

## Contract

Use AI to write a custom lyrics provider (copy this template)
```
I want you to help me write a custom lyrics provider plugin based on the specifications. Please fetch this URL https://raw.githubusercontent.com/vttc08/demucs-karaoke-app/refs/heads/main/custom_lyrics_providers.md for which explains the requirements and structure of a custom lyrics provider, including the InferredSong input and the LyricsPayload output. I will include information about the lyrics provider I want to create, and you will generate the code for it. Please ensure that the generated code adheres to the requirements and structure outlined in the provided documentation.
```

Each provider module should define one provider class, usually named `LyricsProvider` or `CustomLyricsProvider`.

Required shape:

```python
from services.lyrics_types import InferredSong, LyricsPayload


class LyricsProvider:
    name = "hello-world"

    async def fetch(self, inferred_song: InferredSong, **kwargs):
        # Implement your lyrics lookup, proxy rotation, caching, etc. here.
        return LyricsPayload()
```

Requirements:

- The class must be constructible with no arguments.
- `name` must be a non-empty string.
- `fetch(...)` must be `async` (synchronous functions can be wrapped with `asyncio.to_thread`).
- `fetch(...)` receives the normalized song metadata as `inferred_song`.
- The loader also passes keyword hints such as `title` and `artist`, so custom implementations should accept `**kwargs` even if they do not use them.
- If a provider cannot find a match, it must return `None`. 

## Function Input (`InferredSong`)

`InferredSong` is the app's best-effort, cleaned-up song description. For lyrics lookups, the important fields are:

- `title`: the normalized song title
- `artist`: the normalized artist name, when the app could infer one
- `source`: where the metadata came from, such as YouTube or another input path


## Return Type (`LyricsPayload` or `None`)


`LyricsPayload` is the structured return type for providers that want to be more explicit.

It contains:

- `lyrics`: the lyrics text itself (multi-line string)
- `is_synced`: whether the lyrics have timestamps
- `provider`: a short provider name, like `hello-world`
- `inferred_song`: the `InferredSong` that was used for the lookup
- `provider_score`: confidence score used internally when the app compares multiple fallback matches
    - range between 0 to 250, where higher is better
- `provider_details`: optional extra metadata for debugging or future use
- `alternatives`: optional tuple of `LyricsAlternative` values when the provider
  can offer another representation of the same result. The first/base lyrics
  remain the safe default for processing; the UI may choose a TTML alternative
  and retain the base LRC for downgrade.

Example provider with an optional TTML upgrade:

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

The built-in Musixmatch provider uses this contract for its optional TTML
upgrade. Upgrade failures are treated as a missing alternative, so the base
lyrics result remains usable.

## Implementation Notes

- Use `httpx` for web requests when your provider talks to an HTTP API.
- Use `subprocess` if your provider shells out to another program.
- A custom provider can also proxy to a dedicated lyrics web server.

## HelloWorld Example

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

- you must import the types from `services.lyrics_types` otherwise the loader will not recognize your provider
- other variables like authentication, proxy etc. can be declared in the class constructor or attributes
- `lyrics` must be a multi-line string, not a file/path/URL reference.
- `is_synced` of `False` indicate it's a plain text lyrics, while `True` indicates it has timestamps.
- do not return a `LyricsPayload` with empty lyrics; return `None` instead.
- do not return an empty or zero score if you want apps to consider your provider as a fallback; use a score of 1 or higher.
- you can use the highest value of 250 so the application will always prefer your provider over others
