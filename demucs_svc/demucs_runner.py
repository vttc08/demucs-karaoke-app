import subprocess
import time
from pathlib import Path
from uuid import uuid4

try:
    from .models import SeparateConfig
    from .settings import INCOMING_ROOT, OUTPUT_ROOT
    from .separation.base import SeparationRequest
    from .separation.demucs import (
        build_command as _provider_build_command,
        expected_output_paths,
        parse_progress_line,
    )
except ImportError:
    from models import SeparateConfig
    from settings import INCOMING_ROOT, OUTPUT_ROOT
    from separation.base import SeparationRequest
    from separation.demucs import (
        build_command as _provider_build_command,
        expected_output_paths,
        parse_progress_line,
    )


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


def _build_command(input_path: Path, output_dir: Path, config: SeparateConfig) -> list[str]:
    return _provider_build_command(
        SeparationRequest(
            job_id="",
            input_path=input_path,
            output_dir=output_dir,
            model=config.model,
            requested_device=config.device,
            output_format=config.output_format,
            mp3_bitrate=config.mp3_bitrate,
        )
    )


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
    return expected_output_paths(
        SeparationRequest(
            job_id=job_id,
            input_path=input_path,
            output_dir=OUTPUT_ROOT / job_id,
            model=config.model,
            requested_device=config.device,
            output_format=config.output_format,
            mp3_bitrate=config.mp3_bitrate,
        )
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
