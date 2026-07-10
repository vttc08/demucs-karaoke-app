from __future__ import annotations

import importlib.util
import multiprocessing
import shutil
import subprocess
import time
from pathlib import Path

from .base import (
    SeparationCanceled,
    SeparationRequest,
    SeparationResult,
    SeparationRuntime,
)


MODEL_FILES = {
    "fp16": ("vocals.fp16.onnx", "accompaniment.fp16.onnx"),
    "int8": ("vocals.int8.onnx", "accompaniment.int8.onnx"),
    "fp32": ("vocals.onnx", "accompaniment.onnx"),
}
MODEL_DIRECTORIES = {
    "fp16": "sherpa-onnx-spleeter-2stems-fp16",
    "int8": "sherpa-onnx-spleeter-2stems-int8",
    "fp32": "sherpa-onnx-spleeter-2stems",
}


def resolve_model_paths(model_root: Path, variant: str) -> tuple[Path, Path]:
    if variant not in MODEL_FILES:
        raise ValueError(f"Unsupported Sherpa+Spleeter model: {variant}")
    model_dir = model_root / MODEL_DIRECTORIES[variant]
    vocals_name, accompaniment_name = MODEL_FILES[variant]
    return model_dir / vocals_name, model_dir / accompaniment_name


def _run_ffmpeg(command: list[str], *, operation: str) -> None:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "unknown error").strip()
        raise RuntimeError(f"FFmpeg {operation} failed: {detail}")


def _sherpa_child_entry(
    request: SeparationRequest,
    model_root_raw: str,
    num_threads: int,
    ffmpeg_path: str,
    error_path_raw: str,
) -> None:
    error_path = Path(error_path_raw)
    try:
        import numpy as np
        import sherpa_onnx
        import soundfile as sf

        model_root = Path(model_root_raw)
        vocals_model, accompaniment_model = resolve_model_paths(model_root, request.model)
        work_dir = request.output_dir / "sherpa_spleeter" / request.input_path.stem
        work_dir.mkdir(parents=True, exist_ok=True)
        normalized_path = work_dir / "input.normalized.wav"
        _run_ffmpeg(
            [
                ffmpeg_path,
                "-y",
                "-i",
                str(request.input_path),
                "-vn",
                "-ac",
                "2",
                "-c:a",
                "pcm_s16le",
                str(normalized_path),
            ],
            operation="input normalization",
        )

        config = sherpa_onnx.OfflineSourceSeparationConfig(
            model=sherpa_onnx.OfflineSourceSeparationModelConfig(
                spleeter=sherpa_onnx.OfflineSourceSeparationSpleeterModelConfig(
                    vocals=str(vocals_model),
                    accompaniment=str(accompaniment_model),
                ),
                num_threads=num_threads,
                debug=False,
                provider="cpu",
            )
        )
        if not config.validate():
            raise RuntimeError("Sherpa+Spleeter model configuration is invalid")

        samples, sample_rate = sf.read(
            str(normalized_path), dtype="float32", always_2d=True
        )
        samples = np.ascontiguousarray(np.transpose(samples))
        separator = sherpa_onnx.OfflineSourceSeparation(config)
        output = separator.process(sample_rate=sample_rate, samples=samples)
        if len(output.stems) != 2:
            raise RuntimeError(f"Sherpa+Spleeter returned {len(output.stems)} stems; expected 2")

        vocals_wav = work_dir / "vocals.wav"
        no_vocals_wav = work_dir / "no_vocals.wav"
        sf.write(str(vocals_wav), np.transpose(output.stems[0].data), output.sample_rate)
        sf.write(str(no_vocals_wav), np.transpose(output.stems[1].data), output.sample_rate)

        if request.output_format == "mp3":
            bitrate = request.mp3_bitrate or 320
            for source in (vocals_wav, no_vocals_wav):
                target = source.with_suffix(".mp3")
                _run_ffmpeg(
                    [
                        ffmpeg_path,
                        "-y",
                        "-i",
                        str(source),
                        "-vn",
                        "-b:a",
                        f"{bitrate}k",
                        str(target),
                    ],
                    operation=f"{source.stem} MP3 conversion",
                )
                source.unlink(missing_ok=True)
        normalized_path.unlink(missing_ok=True)
    except Exception as error:
        error_path.write_text(str(error), encoding="utf-8")
        raise


class SherpaSpleeterProvider:
    name = "sherpa_spleeter"

    def __init__(self, *, model_root: Path, num_threads: int, ffmpeg_path: str):
        self.model_root = model_root
        self.num_threads = max(1, num_threads)
        self.ffmpeg_path = ffmpeg_path

    def readiness(self, model: str) -> dict[str, object]:
        checks: dict[str, bool] = {
            "sherpa_onnx_available": importlib.util.find_spec("sherpa_onnx") is not None,
            "numpy_available": importlib.util.find_spec("numpy") is not None,
            "soundfile_available": importlib.util.find_spec("soundfile") is not None,
            "ffmpeg_available": shutil.which(self.ffmpeg_path) is not None
            or Path(self.ffmpeg_path).is_file(),
        }
        try:
            vocals_model, accompaniment_model = resolve_model_paths(self.model_root, model)
            checks["vocals_model_available"] = vocals_model.is_file()
            checks["accompaniment_model_available"] = accompaniment_model.is_file()
        except ValueError:
            checks["model_variant_valid"] = False
        return {"ready": all(checks.values()), "model": model, "checks": checks}

    def separate(
        self,
        request: SeparationRequest,
        runtime: SeparationRuntime,
    ) -> SeparationResult:
        readiness = self.readiness(request.model)
        if not readiness["ready"]:
            failed = [name for name, ok in readiness["checks"].items() if not ok]
            raise RuntimeError(
                "Sherpa+Spleeter is not ready: " + ", ".join(failed)
            )

        error_path = request.output_dir / "sherpa_spleeter_error.txt"
        error_path.unlink(missing_ok=True)
        process = multiprocessing.Process(
            target=_sherpa_child_entry,
            args=(
                request,
                str(self.model_root),
                self.num_threads,
                self.ffmpeg_path,
                str(error_path),
            ),
            daemon=True,
            name=f"sherpa-spleeter-{request.job_id}",
        )
        process.start()
        runtime.set_process(process)
        runtime.emit_progress(
            0,
            "Running Sherpa+Spleeter",
            "separation",
            "indeterminate",
        )
        runtime.append_output(
            f"Sherpa+Spleeter model={request.model} threads={self.num_threads} device=cpu"
        )

        try:
            while process.is_alive():
                if runtime.is_canceled():
                    runtime.terminate_process(process)
                    raise SeparationCanceled()
                time.sleep(0.25)
            process.join()
            if runtime.is_canceled():
                raise SeparationCanceled()
            if process.exitcode not in (0, None):
                detail = (
                    error_path.read_text(encoding="utf-8").strip()
                    if error_path.exists()
                    else f"Sherpa+Spleeter exited with status {process.exitcode}"
                )
                raise RuntimeError(detail)

            extension = "mp3" if request.output_format == "mp3" else "wav"
            stem_dir = request.output_dir / "sherpa_spleeter" / request.input_path.stem
            no_vocals_path = stem_dir / f"no_vocals.{extension}"
            vocals_path = stem_dir / f"vocals.{extension}"
            if not no_vocals_path.exists() or not vocals_path.exists():
                raise RuntimeError("Sherpa+Spleeter output files were not created")
            return SeparationResult(
                no_vocals_path=no_vocals_path,
                vocals_path=vocals_path,
                separation_backend=self.name,
                separation_model=request.model,
                effective_device="cpu",
            )
        finally:
            runtime.set_process(None)
