import subprocess
import sys
import time
from pathlib import Path
import re
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


_PERCENT_RE = re.compile(r"(?P<percent>\d{1,3})(?:\.\d+)?%")


def parse_progress_line(line: str) -> tuple[int | None, str | None]:
    cleaned = " ".join(line.replace("\r", "\n").split()).strip()
    if not cleaned:
        return None, None

    percent_match = _PERCENT_RE.search(cleaned)
    percent = None
    if percent_match:
        percent = max(0, min(99, int(float(percent_match.group("percent")))))
    return percent, cleaned


def _build_command(input_path: Path, output_dir: Path, config: SeparateConfig) -> list[str]:
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
    cmd.append(str(input_path))
    return cmd


def prepare_job_input(
    input_bytes: bytes,
    original_filename: str,
    *,
    job_id: str | None = None,
) -> tuple[str, Path, Path, Path]:
    resolved_job_id = job_id or uuid4().hex
    incoming_dir = INCOMING_ROOT / resolved_job_id
    output_dir = OUTPUT_ROOT / resolved_job_id
    incoming_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    input_suffix = Path(original_filename).suffix or ".wav"
    input_path = incoming_dir / f"input{input_suffix}"
    input_path.write_bytes(input_bytes)
    return resolved_job_id, incoming_dir, output_dir, input_path


def build_expected_output_paths(
    job_id: str,
    input_path: Path,
    config: SeparateConfig,
) -> tuple[Path, Path]:
    stem_folder = OUTPUT_ROOT / job_id / config.model / input_path.stem
    extension = "mp3" if config.output_format == "mp3" else "wav"
    return (
        stem_folder / f"no_vocals.{extension}",
        stem_folder / f"vocals.{extension}",
    )


def run_demucs_on_file(
    input_bytes: bytes, original_filename: str, config: SeparateConfig
) -> DemucsRunResult:
    job_id, _incoming_dir, output_dir, input_path = prepare_job_input(
        input_bytes,
        original_filename,
    )

    start = time.time()
    cmd = _build_command(input_path, output_dir, config)
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    duration_ms = int((time.time() - start) * 1000)

    no_vocals_path, vocals_path = build_expected_output_paths(job_id, input_path, config)

    if not no_vocals_path.exists() or not vocals_path.exists():
        raise RuntimeError(
            f"Demucs output not found in expected path: {output_dir / config.model / input_path.stem}"
        )

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
