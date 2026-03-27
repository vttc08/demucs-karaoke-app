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

other configurations 
```powershell
-n htdemucs # select the model used
```
- htdemucs: first version of Hybrid Transformer Demucs. Trained on MusDB + 800 songs. Default model.
- htdemucs_ft: fine-tuned version of htdemucs, separation will take 4 times more time but might be a bit better. Same training set as htdemucs.
- htdemucs_6s: 6 sources version of htdemucs, with piano and guitar being added as sources. Note that the piano source is not working great at the moment.
- hdemucs_mmi: Hybrid Demucs v3, retrained on MusDB + 800 songs.
mdx: trained only on MusDB HQ, winning model on track A at the MDX challenge.
- mdx_extra: trained with extra training data (including MusDB test set), ranked 2nd on the track B of the MDX challenge.
- mdx_q, mdx_extra_q: quantized version of the previous models. Smaller download and storage but quality can be slightly worse.
- SIG: where SIG is a single model from the model zoo.

```powershell
-d cuda
```
- default should be CUDA for GPU acceleration, can use `cpu` as well

```powershell
--mp3 --mp3-bitrate 
```
- output as MP3 with specific bitrate e.g. 320, 256, 128

## API Contract (Implemented)

### `GET /health`
Returns service status and runtime config.

### `POST /separate`
Input: multipart file upload (`file` field, audio input from Linux backend).  
Optional multipart form fields for per-request stateless config:
- `model` (string, default `htdemucs`)
- `device` (`cuda|cpu`, default `cuda`)
- `output_format` (`wav|mp3`, default `wav`)
- `mp3_bitrate` (int 64-320, used only when `output_format=mp3`, default `320`)

Behavior: runs Demucs and returns `no_vocals` as binary file response (`wav` by default, `mp3` when requested).  
Important: this avoids Linux/Windows shared path issues.

Compatibility: existing clients that send only `file` continue to work unchanged.

Response headers include:
- `X-Job-Id`
- `X-Model`
- `X-Device`
- `X-Output-Format`
- `X-Mp3-Bitrate` (mp3 only)
- `X-Duration-Ms`
- `X-Vocals-Path` (Windows-side debug path)

### `POST /separate-meta` (optional debug)
Runs the same process but returns JSON metadata with Windows output paths plus effective runtime config (`model`, `device`, `output_format`, `mp3_bitrate`).

#### Example (default WAV, backward-compatible)
```bash
curl -X POST http://<demucs-host>:8001/separate \
  -F "file=@track.wav"
```

#### Example (request MP3 output)
```bash
curl -X POST http://<demucs-host>:8001/separate \
  -F "file=@track.wav" \
  -F "model=htdemucs" \
  -F "device=cpu" \
  -F "output_format=mp3" \
  -F "mp3_bitrate=256"
```

#### CUDA behavior
- If `device=cuda` is requested and CUDA is unavailable on the host, the API fails fast with HTTP `503` and a clear error message.

## Runbook (Windows)

```powershell
cd C:\Users\hubcc\Documents\Projects\karaoke\demucs_svc
C:\Users\hubcc\Documents\Projects\karaoke\.venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8001
```

## Connectivity Notes
- Linux backend should use `DEMUCS_API_URL=http://10.10.120.191:8001`.
- Do **not** return Windows file paths for consumption by Linux pipeline.
- Return file content and save locally on Linux side.
