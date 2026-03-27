import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

try:
    from .models import SeparateConfig
    from .settings import INCOMING_ROOT, OUTPUT_ROOT
except ImportError:
    from models import SeparateConfig
    from settings import INCOMING_ROOT, OUTPUT_ROOT


class DemucsRunResult:
    def __init__(
        self,
        job_id: str,
        no_vocals_path: Path,
        vocals_path: Path,
        duration_ms: int,
        model: str,
        device: str,
        output_format: str,
        mp3_bitrate: int | None,
    ):
        self.job_id = job_id
        self.no_vocals_path = no_vocals_path
        self.vocals_path = vocals_path
        self.duration_ms = duration_ms
        self.model = model
        self.device = device
        self.output_format = output_format
        self.mp3_bitrate = mp3_bitrate


def run_demucs_on_file(
    input_bytes: bytes, original_filename: str, config: SeparateConfig
) -> DemucsRunResult:
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
        config.model,
        "--two-stems=vocals",
        "-d",
        config.device,
        "-o",
        str(output_dir),
    ]
    if config.output_format == "mp3":
        cmd.extend(["--mp3", "--mp3-bitrate", str(config.mp3_bitrate)])
    cmd.append(
        str(input_path),
    )
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    duration_ms = int((time.time() - start) * 1000)

    # Expected layout: output/<job>/<model>/<track-stem>/{vocals.*,no_vocals.*}
    stem_folder = output_dir / config.model / input_path.stem
    extension = "mp3" if config.output_format == "mp3" else "wav"
    no_vocals_path = stem_folder / f"no_vocals.{extension}"
    vocals_path = stem_folder / f"vocals.{extension}"

    if not no_vocals_path.exists() or not vocals_path.exists():
        raise RuntimeError(f"Demucs output not found in expected path: {stem_folder}")

    return DemucsRunResult(
        job_id=job_id,
        no_vocals_path=no_vocals_path,
        vocals_path=vocals_path,
        duration_ms=duration_ms,
        model=config.model,
        device=config.device,
        output_format=config.output_format,
        mp3_bitrate=config.mp3_bitrate,
    )
