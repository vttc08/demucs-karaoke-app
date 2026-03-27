import subprocess
import sys
from typing import Literal
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from pydantic import ValidationError

try:
    from .demucs_runner import run_demucs_on_file
    from .models import SeparateConfig, SeparateMetaResponse
    from .settings import (
        DEFAULT_DEMUCS_DEVICE,
        DEFAULT_DEMUCS_MODEL,
        DEFAULT_OUTPUT_FORMAT,
        IO_ROOT,
        INCOMING_ROOT,
        OUTPUT_ROOT,
    )
except ImportError:
    from demucs_runner import run_demucs_on_file
    from models import SeparateConfig, SeparateMetaResponse
    from settings import (
        DEFAULT_DEMUCS_DEVICE,
        DEFAULT_DEMUCS_MODEL,
        DEFAULT_OUTPUT_FORMAT,
        IO_ROOT,
        INCOMING_ROOT,
        OUTPUT_ROOT,
    )

app = FastAPI(title="Demucs Service", version="0.1.0")


def _cuda_available() -> bool:
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import torch;print('1' if torch.cuda.is_available() else '0')",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return probe.returncode == 0 and probe.stdout.strip() == "1"


@app.get("/health")
def health():
    checks = {}

    checks["incoming_writable"] = INCOMING_ROOT.exists() and INCOMING_ROOT.is_dir()
    checks["output_writable"] = OUTPUT_ROOT.exists() and OUTPUT_ROOT.is_dir()

    try:
        probe = subprocess.run(
            [sys.executable, "-m", "demucs.separate", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        checks["demucs_cli_available"] = probe.returncode == 0
    except Exception:
        checks["demucs_cli_available"] = False

    healthy = all(checks.values())
    detail = "ready" if healthy else "One or more readiness checks failed"

    return {
        "status": "ok" if healthy else "degraded",
        "service": "demucs",
        "model": DEFAULT_DEMUCS_MODEL,
        "device": DEFAULT_DEMUCS_DEVICE,
        "detail": detail,
        "checks": checks,
    }


@app.post("/separate")
async def separate(
    file: UploadFile = File(...),
    model: str = Form(DEFAULT_DEMUCS_MODEL),
    device: Literal["cuda", "cpu"] = Form(DEFAULT_DEMUCS_DEVICE),
    output_format: Literal["wav", "mp3"] = Form(DEFAULT_OUTPUT_FORMAT),
    mp3_bitrate: int | None = Form(None),
):
    try:
        config = SeparateConfig(
            model=model,
            device=device,
            output_format=output_format,
            mp3_bitrate=mp3_bitrate,
        )
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors()) from error

    if config.device == "cuda" and not _cuda_available():
        raise HTTPException(
            status_code=503,
            detail="CUDA requested but unavailable on Demucs host",
        )

    try:
        payload = await file.read()
        result = run_demucs_on_file(payload, file.filename or "input.wav", config)
    except subprocess.CalledProcessError as error:
        raise HTTPException(
            status_code=500,
            detail=f"Demucs failed: {error.stderr}",
        ) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    headers = {
        "X-Job-Id": result.job_id,
        "X-Model": result.model,
        "X-Device": result.device,
        "X-Output-Format": result.output_format,
        "X-Duration-Ms": str(result.duration_ms),
        "X-Vocals-Path": str(result.vocals_path),
    }
    if result.mp3_bitrate is not None:
        headers["X-Mp3-Bitrate"] = str(result.mp3_bitrate)

    media_type = "audio/mpeg" if result.output_format == "mp3" else "audio/wav"
    filename = f"{result.job_id}_no_vocals.{result.output_format}"
    return FileResponse(
        path=result.no_vocals_path,
        media_type=media_type,
        filename=filename,
        headers=headers,
    )


@app.post("/separate-meta", response_model=SeparateMetaResponse)
async def separate_meta(
    file: UploadFile = File(...),
    model: str = Form(DEFAULT_DEMUCS_MODEL),
    device: Literal["cuda", "cpu"] = Form(DEFAULT_DEMUCS_DEVICE),
    output_format: Literal["wav", "mp3"] = Form(DEFAULT_OUTPUT_FORMAT),
    mp3_bitrate: int | None = Form(None),
):
    try:
        config = SeparateConfig(
            model=model,
            device=device,
            output_format=output_format,
            mp3_bitrate=mp3_bitrate,
        )
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors()) from error

    if config.device == "cuda" and not _cuda_available():
        raise HTTPException(
            status_code=503,
            detail="CUDA requested but unavailable on Demucs host",
        )

    try:
        payload = await file.read()
        result = run_demucs_on_file(payload, file.filename or "input.wav", config)
    except subprocess.CalledProcessError as error:
        raise HTTPException(
            status_code=500,
            detail=f"Demucs failed: {error.stderr}",
        ) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    return SeparateMetaResponse(
        job_id=result.job_id,
        no_vocals_path=str(result.no_vocals_path),
        vocals_path=str(result.vocals_path),
        model=result.model,
        device=result.device,
        output_format=result.output_format,
        mp3_bitrate=result.mp3_bitrate,
        duration_ms=result.duration_ms,
        status="completed",
    )
