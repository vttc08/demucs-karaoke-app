# Troubleshooting

Use this page to find common problems and possible solutions for the application and Demucs service. For task-specific instructions, see the [user task guides](../tasks/for-users.md).

## Contents

- [Application or Demucs is not accessible](#application-or-demucs-is-not-accessible)
    - [Demucs connection fails](#demucs-connection-fails)
- [yt-dlp fails to download](#yt-dlp-fails-to-download)
- [Lyrics cannot be found or are incorrect](#lyrics-cannot-be-found-or-are-incorrect)
- [Vocal separation is very slow](#vocal-separation-is-very-slow)
- [WhisperX alignment fails or takes too long](#whisperx-alignment-fails-or-takes-too-long)
- [WhisperX lyrics are poorly synchronized](#whisperx-lyrics-are-poorly-synchronized)
- [iOS playback issues](#ios-playback-issues)

## Application or Demucs is not accessible

If the main application is not reachable, check the following items.

Check the [HOST setting](../configuration/environments.md#server-and-routing). Listening on localhost or 127.0.0.1 makes the application accessible only from the host machine. To access it from other devices on your LAN, use the host's LAN IP address. When running in Docker, listen on 0.0.0.0 because the container uses a separate network and NAT layer.

Check the Docker port mapping. For `-p 8000:8000`, the left side is the host port and the right side is the container port. The host port can be any free port on the machine, but the container port must match the [PORT setting](../configuration/environments.md#server-and-routing).

For example, `-p 8001:8001` will not work if the container is still configured with `PORT=8000`. In that case, use `-p 8001:8000`, or change the `PORT` value to 8001 inside the container.

Also confirm that the host firewall allows inbound traffic on the host port.

### Allow the application through Windows Firewall

On Windows, you can create an inbound rule from **Windows Defender Firewall with Advanced Security**:

1. Open **Windows Defender Firewall with Advanced Security**.
2. Select **Inbound Rules**, then choose **New Rule**.
3. Select **Port**, choose **TCP**, and enter the host port, such as 8000.
4. Select **Allow the connection**.
5. Apply the rule to the appropriate profiles. **Private** is usually the correct profile for a trusted home network.
6. Give the rule a name such as Karaoke Application, then select **Finish**.

??? note "You can also create the rule from an Administrator PowerShell terminal"
    ```powershell
    New-NetFirewallRule `
      -DisplayName "Karaoke Application" `
      -Direction Inbound `
      -Protocol TCP `
      -LocalPort 8000 `
      -Action Allow `
      -Profile Private
    ```

On a Windows computer, make sure the network is set to **Private**. 

??? note "To check or change the profile from an Administrator PowerShell terminal"

    ```powershell
    Get-NetConnectionProfile |
      Where-Object { $_.NetworkCategory -ne 'Private' } |
      ForEach-Object {
        $_
        Set-NetConnectionProfile -InterfaceIndex $_.InterfaceIndex -NetworkCategory Private -Confirm:$false
      }
    ```

### Demucs connection fails

If Demucs reports connection timed out or no route to host, check that the Demucs service host and port are entered correctly.

- In Docker, localhost refers to the current container. Use the Demucs container name when both services are on the same Docker network.
- If Demucs runs on another computer on the same LAN, use that computer's LAN IP address.
- Confirm the API key if the Demucs service requires one.
- Check the Demucs service logs for Demucs or WhisperX errors.

A successful service startup should include:

```text
INFO   Application startup complete.
```

You can [verify that the Demucs service is healthy](../getting-started/demucs-service.md#5-verify-application-health).

In some cases, the virtual environment is not activated, or the wrong environment is used when starting the Demucs service. Activate the correct virtual environment before starting it.

If Demucs is running over the internet, see [Expose a remote Demucs service](../tasks/server-administration.md#expose-a-remote-demucs-service).

## yt-dlp fails to download

YouTube may block or rate-limit IP addresses used by VPS providers. Even a home connection can be temporarily rate-limited or blocked.

If the problem is temporary, the fastest solution is to select **Retry** on the failed task.

If the download continues to fail, [configure a proxy server for yt-dlp downloads](../tasks/server-administration.md#use-a-proxy-server-for-downloads).

As a last resort, download the video on your phone with [Seal](https://f-droid.org/en/packages/com.junkfood.seal/), or use yt-dlp from another computer or network. Then [upload the video](../tasks/create-ai-karaoke.md#create-karaoke-from-uploaded-files) to the application.

## Lyrics cannot be found or are incorrect

Make sure the main karaoke application is up to date. See [Upgrade](../getting-started/backup-and-restore.md#upgrade).

You **must** configure the [Last.fm and Musixmatch API keys](../getting-started/docker.md#3-configure-the-environment) for lyrics functionality.

The application currently searches Musixmatch, LRCLIB, and Netease. If none of these providers contain the lyrics, the application cannot find them.

The [Google lyrics option](../tasks/create-ai-karaoke.md#3-add-lyrics) searches for Artist - Title lyrics. You can copy the results and paste the lyrics into the text box. The lyrics do not need to be synchronized; plain lyrics work as well.

If the application finds incorrect lyrics, Last.fm may have inferred the wrong song title or artist. Enter the correct title and artist, then search again.

If none of the built-in providers work and you want to use your own provider, follow the [custom lyrics provider instructions](../configuration/custom-lyrics-provider.md).

Feel free to make a pull request to add your provider or fix the current provider implementations.

## Vocal separation is very slow

!!! note "Demucs progress can pause near 90%"

    If Demucs appears stuck at 90% for a few seconds, this is normal. Demucs reports only vocal-separation progress, not all setup and teardown work, and the application cannot capture that additional progress.

Demucs vocal separation works best with an NVIDIA CUDA GPU. If you have a CUDA-capable GPU, check the [Demucs service health](../getting-started/demucs-service.md#5-verify-application-health) and confirm that the backend recognizes the GPU.

For CPU-only processing, [Sherpa+Spleeter](../tasks/create-ai-karaoke.md#cpu-processing) is significantly faster than Demucs, although the quality is lower. Consider using it instead and review the [karaoke processing configuration](../configuration/karaoke-processing.md#separation-options).

## WhisperX alignment fails or takes too long

Because WhisperX uses a large amount of VRAM, the application automatically unloads models and runs garbage collection after each vocal separation. This slightly increases the alignment time, but helps prevent WhisperX from hanging.

If WhisperX still hangs while using a GPU, cancel the task. Run [Demucs GC](../configuration/tools.md#run-demucs-gc) to free GPU memory, then try again.

WhisperX alignment can also take longer when the lyrics are inaccurate or the wrong language is detected. If you know the language of the audio, try again and [specify the language override](../tasks/media-administration.md#resynchronize-inaccurate-whisperx-lyrics).

??? tip "Check the detected language in the logs"

    Inspect the Demucs service logs. During a bad alignment, there is a good chance that WhisperX detected the wrong language.

    ```text
    2026-09-13 20:34:28 - whisperx.asr - INFO -
    Detected language: ja (0.68) in first 30s of audio
    ```

While WhisperX processes a song, you can queue another song. Typical alignment takes one to two minutes, which is shorter than a standard three-minute song. You can also preprocess tracks that you or your guests like before or after the karaoke session, when processing speed is less critical.

If your friend has a CUDA-capable computer, ask them to run the Demucs service, here are the [instructions for exposing it over the internet](../tasks/server-administration.md#expose-a-remote-demucs-service).

## WhisperX lyrics are poorly synchronized

No model is perfect, so minor synchronization issues are expected. For major issues, the language detected by WhisperX is often incorrect. If you know the language of the audio, try again and [specify the language override](../tasks/media-administration.md#resynchronize-inaccurate-whisperx-lyrics).

For instructions on fixing both minor and major synchronization issues, see [Resynchronize Inaccurate WhisperX Lyrics](../tasks/media-administration.md#resynchronize-inaccurate-whisperx-lyrics).

## iOS playback issues

On iOS devices, you may encounter issues such as video not playing, video freezing, the play button not responding, or video lag.

See [Use an iPhone or iPad as a stage display](../tasks/stage-and-branding.md#use-an-iphone-or-ipad-as-a-stage-display) for the known limitations and workarounds.
