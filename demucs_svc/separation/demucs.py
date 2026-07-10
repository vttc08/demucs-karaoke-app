from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from .base import (
    SeparationCanceled,
    SeparationRequest,
    SeparationResult,
    SeparationRuntime,
)


_PERCENT_RE = re.compile(r"(?P<percent>\d{1,3})(?:\.\d+)?%")


def parse_progress_line(line: str) -> tuple[int | None, str | None]:
    cleaned = " ".join(line.replace("\r", "\n").split()).strip()
    if not cleaned:
        return None, None

    match = _PERCENT_RE.search(cleaned)
    percent = None
    if match:
        percent = max(0, min(99, int(float(match.group("percent")))))
    return percent, cleaned


def build_command(request: SeparationRequest) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "demucs.separate",
        "-n",
        request.model,
        "--two-stems=vocals",
        "-d",
        request.requested_device,
        "-o",
        str(request.output_dir),
    ]
    if request.output_format == "mp3":
        command.extend(["--mp3", "--mp3-bitrate", str(request.mp3_bitrate)])
    command.append(str(request.input_path))
    return command


def expected_output_paths(request: SeparationRequest) -> tuple[Path, Path]:
    extension = "mp3" if request.output_format == "mp3" else "wav"
    stem_dir = request.output_dir / request.model / request.input_path.stem
    return stem_dir / f"no_vocals.{extension}", stem_dir / f"vocals.{extension}"


class DemucsProvider:
    name = "demucs"

    def readiness(self, model: str) -> dict[str, object]:
        try:
            probe = subprocess.run(
                [sys.executable, "-m", "demucs.separate", "--help"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            available = probe.returncode == 0
        except Exception:
            available = False
        return {
            "ready": available,
            "model": model,
            "checks": {"demucs_cli_available": available},
        }

    def separate(
        self,
        request: SeparationRequest,
        runtime: SeparationRuntime,
    ) -> SeparationResult:
        process = subprocess.Popen(
            build_command(request),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        runtime.set_process(process)
        runtime.emit_progress(0, "Starting Demucs", "demucs", "determinate")

        try:
            assert process.stdout is not None
            for raw_line in process.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                runtime.append_output(line)
                percent, message = parse_progress_line(line)
                mapped_percent = (percent * 9 + 9) // 10 if percent is not None else None
                runtime.emit_progress(mapped_percent, message, "demucs", "determinate")
                if runtime.is_canceled():
                    runtime.terminate_process(process)
                    raise SeparationCanceled()

            return_code = process.wait()
            if runtime.is_canceled():
                raise SeparationCanceled()
            if return_code != 0:
                raise RuntimeError(f"Demucs exited with status {return_code}")

            no_vocals_path, vocals_path = expected_output_paths(request)
            if not no_vocals_path.exists() or not vocals_path.exists():
                raise RuntimeError("Demucs output files were not created")
            return SeparationResult(
                no_vocals_path=no_vocals_path,
                vocals_path=vocals_path,
                separation_backend=self.name,
                separation_model=request.model,
                effective_device=request.requested_device,
            )
        finally:
            runtime.set_process(None)
