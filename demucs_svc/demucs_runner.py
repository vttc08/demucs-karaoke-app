import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from settings import INCOMING_ROOT, OUTPUT_ROOT, DEMUCS_MODEL, DEMUCS_DEVICE


class DemucsRunResult:
    def __init__(self, job_id: str, no_vocals_path: Path, vocals_path: Path, duration_ms: int):
        self.job_id = job_id
        self.no_vocals_path = no_vocals_path
        self.vocals_path = vocals_path
        self.duration_ms = duration_ms


def run_demucs_on_file(input_bytes: bytes, original_filename: str) -> DemucsRunResult:
    job_id = uuid4().hex
    incoming_dir = INCOMING_ROOT / job_id
    output_dir = OUTPUT_ROOT / job_id
    incoming_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    input_suffix = Path(original_filename).suffix or ".wav"
    input_path = incoming_dir / f"input{input_suffix}"
    input_path.write_bytes(input_bytes)

    start = time.time()
    cmd = [
        sys.executable,
        "-m",
        "demucs.separate",
        "-n",
        DEMUCS_MODEL,
        "--two-stems=vocals",
        "-d",
        DEMUCS_DEVICE,
        "-o",
        str(output_dir),
        str(input_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    duration_ms = int((time.time() - start) * 1000)

    # Expected layout: output/<job>/<model>/<track-stem>/{vocals.wav,no_vocals.wav}
    stem_folder = output_dir / DEMUCS_MODEL / input_path.stem
    no_vocals_path = stem_folder / "no_vocals.wav"
    vocals_path = stem_folder / "vocals.wav"

    if not no_vocals_path.exists() or not vocals_path.exists():
        raise RuntimeError(f"Demucs output not found in expected path: {stem_folder}")

    return DemucsRunResult(
        job_id=job_id,
        no_vocals_path=no_vocals_path,
        vocals_path=vocals_path,
        duration_ms=duration_ms,
    )
