# Separation Backends

The standalone `demucs_svc` worker supports two interchangeable two-stem vocal separation backends:

- `demucs`: the default, higher-quality backend with CPU and CUDA support.
- `sherpa_spleeter`: a faster CPU-only backend using sherpa-onnx and modified Spleeter models.

The main app selects the backend for new jobs from `/settings`. Both backends return the same ZIP
shape with `no_vocals` and `vocals` stems, and either backend can feed the existing optional
WhisperX alignment stage.

## Install Sherpa+Spleeter

Install the standalone worker dependencies in the worker environment:

```bash
uv pip install -r demucs_svc/requirements.txt
```

FFmpeg must also be installed and available through `SHERPA_SPLEETER_FFMPEG_PATH`.

Download at least one official model bundle explicitly:

```bash
uv run python -m demucs_svc.download_sherpa_models --variant fp16
```

Available variants are `fp16`, `int8`, and `fp32`. Use `--variant all` to install all three. The
command validates the expected vocals/accompaniment pair before installing the bundle under
`SHERPA_SPLEETER_MODEL_ROOT`.

## Worker Configuration

`demucs_svc/.env` controls worker-local paths and CPU tuning:

```dotenv
SEPARATION_BACKEND=demucs
SHERPA_SPLEETER_MODEL=fp16
SHERPA_SPLEETER_MODEL_ROOT=./model_data/sherpa_spleeter
SHERPA_SPLEETER_NUM_THREADS=8
SHERPA_SPLEETER_FFMPEG_PATH=ffmpeg
```

`SEPARATION_BACKEND` is the default for direct callers that omit a backend. Main-app requests send
their persisted selection explicitly. Model paths and thread count remain worker-local because they
describe the remote host, not the main app.

Sherpa always runs separation on CPU. If the main app saves `Device=cuda`, a separation-only Sherpa
job still succeeds and reports `effective_device=cpu`. A job that also requests WhisperX continues
to validate CUDA for WhisperX and fails clearly when CUDA is unavailable.

## Input and Output Handling

Sherpa inputs are normalized through FFmpeg to stereo PCM WAV before inference. This makes MP4,
AAC, MP3, WAV, and other FFmpeg-readable inputs behave consistently. Sherpa produces WAV stems;
when MP3 is requested, the worker converts both stems with FFmpeg at the configured bitrate.

Sherpa does not expose meaningful progress callbacks. Its jobs report an indeterminate separation
stage until inference completes. Cancellation terminates the isolated Sherpa child process and uses
the same cleanup contract as Demucs and WhisperX.

## Readiness

Query readiness for the configured backend through the main app or directly:

```bash
curl "http://127.0.0.1:8001/health?separation_backend=sherpa_spleeter&sherpa_spleeter_model=fp16"
```

The response advertises `supported_backends`, reports each backend's checks separately, and derives
overall health from the requested backend. Missing Python packages, FFmpeg, or either ONNX model are
reported before a Sherpa job is accepted. The worker never falls back between backends silently.
