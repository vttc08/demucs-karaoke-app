# Demucs Service on Windows (Remote GPU)
This document defines the **real Demucs API service** contract for the Windows GPU machine and how Linux backend connects to it.

```powershell
(.venv) PS C:\Users\hubcc\Documents> demucs
usage: demucs.separate [-h] [-s SIG | -n NAME] [--repo REPO] [-v] [-o OUT] [--filename FILENAME] [-d DEVICE] [--shifts SHIFTS] [--overlap OVERLAP]
                       [--no-split | --segment SEGMENT] [--two-stems STEM] [--int24 | --float32] [--clip-mode {rescale,clamp}] [--flac | --mp3]
                       [--mp3-bitrate MP3_BITRATE] [--mp3-preset {2,3,4,5,6,7}] [-j JOBS]
                       tracks [tracks ...]
demucs.separate: error: the following arguments are required: tracks
```

Demucs is installed inside the Windows project virtual environment:

- `C:\Users\hubcc\Documents\Projects\karaoke\.venv`
- Service folder: `C:\Users\hubcc\Documents\Projects\karaoke\demucs_svc`

### Basic Usage
```powershell
demucs -n htdemucs --two-stems=vocals "song.mp3"
```
This command will separate the vocals from the rest of the track in `song.mp3` using the `htdemucs` model. The output will be saved in a folder named `separated/htdemucs/<song_name>/vocals.wav` and `separated/htdemucs/<song_name>/no_vocals.wav`.

```powershell
demucs -n htdemucs --two-stems=vocals "song.mp3" -o ./output
```
- this specifiy the output folder to be `./output` 
- however, the output will still be in the same structure `output/htdemucs/<song_name>/vocals.wav` ...

## API Contract (Implemented)

### `GET /health`
Returns service status and runtime config.

### `POST /separate`
Input: multipart file upload (`file` field, audio input from Linux backend).  
Behavior: runs Demucs and returns **`no_vocals.wav` as binary file response**.  
Important: this avoids Linux/Windows shared path issues.

Response headers include:
- `X-Job-Id`
- `X-Model`
- `X-Duration-Ms`
- `X-Vocals-Path` (Windows-side debug path)

### `POST /separate-meta` (optional debug)
Runs the same process but returns JSON metadata with Windows output paths.

## Runbook (Windows)

```powershell
cd C:\Users\hubcc\Documents\Projects\karaoke\demucs_svc
C:\Users\hubcc\Documents\Projects\karaoke\.venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8001
```

## Connectivity Notes
- Linux backend should use `DEMUCS_API_URL=http://10.10.120.191:8001`.
- Do **not** return Windows file paths for consumption by Linux pipeline.
- Return file content and save locally on Linux side.
