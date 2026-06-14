from pathlib import Path
from datetime import timedelta


WORKSPACE_ROOT = Path(__file__).resolve().parent
IO_ROOT = WORKSPACE_ROOT / "io"
INCOMING_ROOT = IO_ROOT / "incoming"
OUTPUT_ROOT = IO_ROOT / "output"

DEFAULT_DEMUCS_MODEL = "htdemucs"
DEFAULT_DEMUCS_DEVICE = "cuda"
DEFAULT_OUTPUT_FORMAT = "wav"
DEFAULT_MP3_BITRATE = 320
DEFAULT_WHISPERX_TRANSCRIPTION_MODEL = "tiny"
DEFAULT_WHISPERX_ALIGN_LANGUAGE = "en"
DEFAULT_WHISPERX_DETECT_LANGUAGE = False
DEFAULT_WHISPERX_USE_SYNCED_LYRICS = False
DEFAULT_WHISPERX_PRELOAD_MODELS = "transcription=tiny,align=en"
JOB_RETENTION_SECONDS = int(timedelta(minutes=30).total_seconds())
JOB_OUTPUT_TAIL_LINES = 120

INCOMING_ROOT.mkdir(parents=True, exist_ok=True)
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
