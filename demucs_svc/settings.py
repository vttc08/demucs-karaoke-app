from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parent
IO_ROOT = WORKSPACE_ROOT / "io"
INCOMING_ROOT = IO_ROOT / "incoming"
OUTPUT_ROOT = IO_ROOT / "output"

DEMUCS_MODEL = "htdemucs"
DEMUCS_DEVICE = "cuda"

INCOMING_ROOT.mkdir(parents=True, exist_ok=True)
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
