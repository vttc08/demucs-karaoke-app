# Create AI Karaoke

The application supports several ways to create karaoke, from downloading a music video to processing your own files. Choose the workflow that best matches your source material and the amount of processing you want to use.

## Contents

- [Create karaoke from a music video](#create-karaoke-from-a-music-video)
- [Create karaoke from a lyrics video](#create-karaoke-from-a-lyrics-video)
- [Create karaoke from uploaded files](#create-karaoke-from-uploaded-files)
- [Modify existing video](#modify-existing-video)
- [Add vocals to a premade karaoke video](#add-vocals-to-a-premade-karaoke-video)
- [Fastest or best-case karaoke](#fastest-or-best-case-karaoke)

## Create karaoke from a music video

Creating karaoke from a music video provides the most immersive experience and supports customizable lyrics styles. It is also the most processing-intensive option. For faster processing, use the Demucs service on a GPU-capable device.

![AI Karaoke full flow](../assets/images/tasks/ai-karaoke-fullflow.webp){ width="800" }

### 1. Select a music video

1. Search for a song and choose a music video from the search results.
2. The application does not automatically identify whether the video contains lyrics or karaoke. It therefore enables both vocal separation and lyrics processing.

### 2. Configure karaoke options

The pre-queue page provides the following options:

- **WhisperX word alignment** creates word-synchronized lyrics for karaoke.
- **Rewrap lyric lines** changes the maximum number of characters per line before wrapping to the next line.
    - For Asian languages, especially Chinese, Japanese, and Korean (CJK), adjust `Max CJK Chars` instead.
- **Language override** specifies the language for [WhisperX alignment](../configuration/whisperx-lyrics.md#whisperx-alignment-language). Setting this skips automatic language detection and any configured default language.

### 3. Add lyrics

WhisperX requires lyrics to create karaoke timing. The application searches the configured lyrics providers.

- It first uses Last.fm to infer the title and artist from the video title. If the result is incorrect, enter the title and artist manually before searching.
- The **Google** button opens a new tab and searches for `Artist - Title lyrics`. Copy the result into the **lyrics editor**.
- You can also upload an `.lrc` or `.txt` lyrics file.
- Edit the lyrics as needed before adding the song to the karaoke queue.

??? tip "Upgrade LRC lyrics"

    Some lyrics can be upgraded to TTML (Timed Text Markup Language), typically sourced from Apple Music. TTML already contains word-synchronized lyrics, which can provide precise karaoke timing and skip WhisperX processing.

    If the upgrade fails or returns the wrong lyrics, fall back to the standard lyrics result.

### 4. Process the song

After the song is queued, the application downloads the source, separates the vocals, aligns the lyrics, and prepares the karaoke media for the stage.

!!! note "If processing fails"

    If downloading fails, see the [yt-dlp troubleshooting guide](../troubleshooting/index.md#yt-dlp-fails-to-download). For vocal separation problems, see [Vocal separation is very slow](../troubleshooting/index.md#vocal-separation-is-very-slow). For lyrics alignment problems or incorrect synchronization, see [WhisperX alignment troubleshooting](../troubleshooting/index.md#whisperx-alignment-fails-or-takes-too-long) and [WhisperX synchronization troubleshooting](../troubleshooting/index.md#whisperx-lyrics-are-poorly-synchronized).

## Create karaoke from a lyrics video

![Example lyrics video](../assets/images/tasks/lyricsvideo.webp)

Lyrics videos are widely available on YouTube. They usually do not contain word-synchronized lyrics, but they may provide visual styles and backgrounds that some users prefer. They also skip WhisperX alignment, which reduces processing time on CPU-only devices.

### 1. Select a lyrics video

1. Search for a song and choose a lyrics video from the search results.
2. The application detects the lyrics video and enables only vocal separation, skipping lyrics processing.

### 2. Wait for vocal separation

The song requires vocal-separation processing. It appears on the stage after processing is complete.

??? note "Lyrics videos are not always well synchronized"

    Lyrics videos usually contain line-synchronized rather than word-synchronized lyrics. They also often prioritize visual effects and animation, so transitions between lines may not match the music precisely. This is less noticeable when you are familiar with the song.

!!! note "If processing fails"

    If downloading fails, see the [yt-dlp troubleshooting guide](../troubleshooting/index.md#yt-dlp-fails-to-download). If vocal separation fails or takes too long, see [Vocal separation is very slow](../troubleshooting/index.md#vocal-separation-is-very-slow).

## Create karaoke from uploaded files

Creating karaoke from an uploaded MP3 file with album art can provide an immersive and customizable experience. Uploading is also useful when the application cannot download a video, when another device or network is better suited for downloading, or when you want to use a file from your own library.

![Upload Autopilot](../assets/images/media/autopilot.gif)

### 1. Upload a file

Click the upload area or drag and drop a file into it.

??? tip "Upload Autopilot"

    Autopilot prepares the default karaoke options with one click:

    - Infers track information from the filename.
    - Searches for and downloads lyrics.
    - Fills in the title, artist, and karaoke processing options.
    - Creates optimized karaoke processing settings before submission.

### 2. Configure the uploaded song

Refer to [Create karaoke from a music video](#create-karaoke-from-a-music-video) for the available lyrics options. The same options are available in the upload flow.

### 3. Choose where to add the song

Enable **Add to queue** to add the song to the queue and show it on the stage after processing is complete. Leave it disabled to add the processed song to the library for later use.

!!! note "If processing fails"

    If vocal separation fails or takes too long, see [Vocal separation is very slow](../troubleshooting/index.md#vocal-separation-is-very-slow). If lyrics alignment fails, takes too long, or produces incorrect synchronization, see [WhisperX alignment troubleshooting](../troubleshooting/index.md#whisperx-alignment-fails-or-takes-too-long) and [WhisperX synchronization troubleshooting](../troubleshooting/index.md#whisperx-lyrics-are-poorly-synchronized).

## Modify existing video

The application can run vocal separation and lyrics alignment on existing media in the library.

![Create AI karaoke from existing media](../assets/images/media/create.gif)

### 1. Open the media editor

1. Open the Media page and click **Edit** for the media item.
2. On the **Edit Media Details** page, modify the title, artist, or karaoke processing options.
3. Use **Auto** to infer the title and artist from the filename using Last.fm.
    - This changes the name in the library. Enable **Rename on disk** if the filename should also change.

??? note "Rename on disk"

    The file is renamed only after you click **Rename**. If you only want to change the title, artist, or filename without processing the media, do not modify **AI Karaoke** or **Lyrics Sync**.

### 2. Configure lyrics and processing

Refer to [Create karaoke from a music video](#create-karaoke-from-a-music-video) for the available lyrics options.

??? note "Lyrics Sync and WhisperX"

    When only **Lyrics Sync** is enabled and lyrics are provided, the application saves the lyrics file without running WhisperX. Edit the media again and enable **WhisperX Align** when you want to create synchronized lyrics.

!!! note "If processing fails"

    If vocal separation fails or takes too long, see [Vocal separation is very slow](../troubleshooting/index.md#vocal-separation-is-very-slow). If lyrics alignment fails, takes too long, or produces incorrect synchronization, see [WhisperX alignment troubleshooting](../troubleshooting/index.md#whisperx-alignment-fails-or-takes-too-long) and [WhisperX synchronization troubleshooting](../troubleshooting/index.md#whisperx-lyrics-are-poorly-synchronized).

## Add vocals to a premade karaoke video

If you prefer the lyrics styles of a premade karaoke video, such as one from Sing King, but want backing vocals for practice, you can use the application to add vocals to the video.

??? tip "Automatic vocal alignment requires vocal-sync"

    The application can automatically align the original karaoke instrumental with the separated instrumental from the original music video when the requirements are met. Install the [vocal-sync extra](../getting-started/linux.md#1-prepare-the-application-and-dependencies), or use the [vocal-sync Docker image](../getting-started/docker.md#3-configure-the-environment), to enable automatic vocal alignment.

### 1. Open Vocal Sync

1. Open the Media page and click **Edit**.
2. Select **Add Vocals** to open the Vocal Sync page.

![Add vocals](../assets/images/addvocals.webp)

### 2. Prepare and align the vocals

1. Search YouTube or upload your own files, then click **Prepare**.
2. The application separates the vocals and instrumental and prepares a preview.
    - When `vocal-sync` is available, the offset is calculated automatically.
3. Use the **+** and **-** buttons to adjust the offset, then click **Preview** to check the result.
    - A **+** value delays the vocals. Increase it if the vocals begin before the instrumental.
    - A **-** value moves the vocals earlier. Decrease it if the vocals begin after the instrumental.

??? note "Use Preview for playback"

    Do not use the media player controls for this check; they play only the original video. Use **Preview** and **Stop** instead.

### 3. Commit the result

Click **Commit** when the alignment is satisfactory.

## Fastest or best-case karaoke

If you do not have a CUDA-capable GPU for the Demucs service, you can still use the AI features with a CPU.

### CPU processing

Use [Sherpa+Spleeter](../configuration/karaoke-processing.md#separation-backend) for vocal separation.

- The Demucs service downloads the models according to your [configuration](../configuration/environments.md#processing-and-model-settings).
- Sherpa+Spleeter runs well on a CPU and is significantly faster than Demucs.
- Separation quality is not as good as Demucs.

### TTML lyrics upgrade

There is no easy CPU-only alternative to WhisperX. A typical three-minute song may take one to two minutes to separate. However, some songs have a TTML lyrics upgrade available. TTML already contains word-synchronized lyrics and skips WhisperX processing.

Using `Sherpa+Spleeter` with a TTML upgrade provides the fastest and best-case karaoke experience on CPU-only devices.
