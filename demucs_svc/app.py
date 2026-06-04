import json
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response, UploadFile, File, Form
from pydantic import ValidationError

try:
    from .demucs_runner import (
        _build_command,
        build_expected_output_paths,
        parse_progress_line,
        prepare_job_input,
        run_demucs_on_file,
    )
    from .jobs import DemucsJobState, DemucsJobStore, utc_now
    from .models import (
        DemucsJobCreateResponse,
        DemucsJobStatusResponse,
        SeparateConfig,
        SeparateMetaResponse,
    )
    from .settings import (
        DEFAULT_DEMUCS_DEVICE,
        DEFAULT_DEMUCS_MODEL,
        DEFAULT_OUTPUT_FORMAT,
        INCOMING_ROOT,
        JOB_OUTPUT_TAIL_LINES,
        JOB_RETENTION_SECONDS,
        OUTPUT_ROOT,
    )
except ImportError:
    from demucs_runner import (
        _build_command,
        build_expected_output_paths,
        parse_progress_line,
        prepare_job_input,
        run_demucs_on_file,
    )
    from jobs import DemucsJobState, DemucsJobStore, utc_now
    from models import (
        DemucsJobCreateResponse,
        DemucsJobStatusResponse,
        SeparateConfig,
        SeparateMetaResponse,
    )
    from settings import (
        DEFAULT_DEMUCS_DEVICE,
        DEFAULT_DEMUCS_MODEL,
        DEFAULT_OUTPUT_FORMAT,
        INCOMING_ROOT,
        JOB_OUTPUT_TAIL_LINES,
        JOB_RETENTION_SECONDS,
        OUTPUT_ROOT,
    )

app = FastAPI(title="Demucs Service", version="0.2.0")
job_store = DemucsJobStore(tail_limit=JOB_OUTPUT_TAIL_LINES)


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


def _build_stems_zip(result) -> bytes:
    stem_ext = "mp3" if result.output_format == "mp3" else "wav"
    metadata = {
        "job_id": result.job_id,
        "model": result.model,
        "device": result.device,
        "output_format": result.output_format,
        "mp3_bitrate": result.mp3_bitrate,
        "duration_ms": result.duration_ms,
        "files": {
            "no_vocals": f"no_vocals.{stem_ext}",
            "vocals": f"vocals.{stem_ext}",
        },
    }

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(result.no_vocals_path, arcname=f"no_vocals.{stem_ext}")
        archive.write(result.vocals_path, arcname=f"vocals.{stem_ext}")
        archive.writestr("metadata.json", json.dumps(metadata, separators=(",", ":")))
    return buffer.getvalue()


def _job_to_status_response(job: DemucsJobState) -> DemucsJobStatusResponse:
    data = job.to_dict()
    for key in ("created_at", "started_at", "finished_at"):
        value = data[key]
        data[key] = value.isoformat() if value is not None else None
    return DemucsJobStatusResponse(**data)


def _job_paths(job_id: str) -> tuple[Path, Path]:
    return INCOMING_ROOT / job_id, OUTPUT_ROOT / job_id


def _cleanup_job_files(job_id: str) -> None:
    incoming_dir, output_dir = _job_paths(job_id)
    for path in (incoming_dir, output_dir):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


def _cleanup_expired_jobs() -> None:
    cutoff = time.time() - JOB_RETENTION_SECONDS
    for job in job_store.all():
        if job.status in {"queued", "running"}:
            continue
        finished_at = job.finished_at.timestamp() if job.finished_at is not None else None
        if finished_at is None or finished_at > cutoff:
            continue
        job_store.delete(job.job_id)
        _cleanup_job_files(job.job_id)


def _update_job_progress(job_id: str, *, percent: int | None = None, message: str | None = None) -> None:
    changes = {}
    if percent is not None:
        changes["progress_percent"] = max(0, min(99, percent))
    if message:
        changes["progress_message"] = message
    if changes:
        job_store.update(job_id, **changes)


def _run_job(job_id: str, input_path: Path, config: SeparateConfig) -> None:
    start = time.time()
    output_dir = OUTPUT_ROOT / job_id
    cmd = _build_command(input_path, output_dir, config)
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    job_store.update(
        job_id,
        status="running",
        started_at=utc_now(),
        progress_percent=0,
        progress_message="Starting Demucs",
        process=process,
    )

    try:
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            job_store.append_output(job_id, line)
            percent, message = parse_progress_line(line)
            _update_job_progress(job_id, percent=percent, message=message)

            job = job_store.require(job_id)
            if job.cancel_requested:
                process.terminate()
                break

        return_code = process.wait()
        duration_ms = int((time.time() - start) * 1000)
        job = job_store.require(job_id)
        no_vocals_path, vocals_path = build_expected_output_paths(job_id, input_path, config)

        if job.cancel_requested:
            job_store.update(
                job_id,
                status="canceled",
                finished_at=utc_now(),
                duration_ms=duration_ms,
                progress_message="Canceled",
                process=None,
            )
            _cleanup_job_files(job_id)
            return

        if return_code != 0:
            raise RuntimeError(f"Demucs exited with status {return_code}")
        if not no_vocals_path.exists() or not vocals_path.exists():
            raise RuntimeError("Demucs output files were not created")

        job_store.update(
            job_id,
            status="completed",
            finished_at=utc_now(),
            duration_ms=duration_ms,
            progress_percent=100,
            progress_message="Completed",
            no_vocals_path=str(no_vocals_path),
            vocals_path=str(vocals_path),
            process=None,
        )
    except Exception as error:
        duration_ms = int((time.time() - start) * 1000)
        job_store.update(
            job_id,
            status="failed",
            finished_at=utc_now(),
            duration_ms=duration_ms,
            error_detail=str(error),
            progress_message="Failed",
            process=None,
        )
    finally:
        _cleanup_expired_jobs()


def _start_job(payload: bytes, original_filename: str, config: SeparateConfig) -> DemucsJobState:
    _cleanup_expired_jobs()
    job_id, _incoming_dir, _output_dir, input_path = prepare_job_input(payload, original_filename)
    job = job_store.create(
        DemucsJobState(
            job_id=job_id,
            model=config.model,
            device=config.device,
            output_format=config.output_format,
            mp3_bitrate=config.mp3_bitrate,
            original_filename=original_filename,
        )
    )
    worker = threading.Thread(
        target=_run_job,
        args=(job_id, input_path, config),
        daemon=True,
        name=f"demucs-job-{job_id}",
    )
    worker.start()
    return job


def _validated_config(
    model: str,
    device: Literal["cuda", "cpu"],
    output_format: Literal["wav", "mp3"],
    mp3_bitrate: int | None,
) -> SeparateConfig:
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
    return config


def _wait_for_terminal_job(job_id: str, *, timeout_seconds: float = 600.0) -> DemucsJobState:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        job = job_store.require(job_id)
        if job.status in {"completed", "failed", "canceled"}:
            return job
        time.sleep(0.25)
    raise HTTPException(status_code=504, detail="Timed out waiting for Demucs job")


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
        "active_jobs": sum(1 for job in job_store.all() if job.status in {"queued", "running"}),
    }


@app.post("/jobs", response_model=DemucsJobCreateResponse, status_code=202)
async def create_job(
    request: Request,
    file: UploadFile = File(...),
    model: str = Form(DEFAULT_DEMUCS_MODEL),
    device: Literal["cuda", "cpu"] = Form(DEFAULT_DEMUCS_DEVICE),
    output_format: Literal["wav", "mp3"] = Form(DEFAULT_OUTPUT_FORMAT),
    mp3_bitrate: int | None = Form(None),
):
    config = _validated_config(model, device, output_format, mp3_bitrate)
    payload = await file.read()
    job = _start_job(payload, file.filename or "input.wav", config)
    base = str(request.base_url).rstrip("/")
    return DemucsJobCreateResponse(
        job_id=job.job_id,
        status=job.status,
        progress_percent=job.progress_percent,
        progress_message=job.progress_message,
        status_url=f"{base}/jobs/{job.job_id}",
        result_url=f"{base}/jobs/{job.job_id}/result",
        cancel_url=f"{base}/jobs/{job.job_id}",
    )


@app.get("/jobs/{job_id}", response_model=DemucsJobStatusResponse)
def get_job(job_id: str):
    try:
        job = job_store.require(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Job not found") from error
    return _job_to_status_response(job)


@app.get("/jobs/{job_id}/result")
def get_job_result(job_id: str):
    try:
        job = job_store.require(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Job not found") from error

    if job.status == "failed":
        raise HTTPException(status_code=409, detail=job.error_detail or "Job failed")
    if job.status == "canceled":
        raise HTTPException(status_code=409, detail="Job was canceled")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail="Job is not complete")

    no_vocals_path = Path(job.no_vocals_path or "")
    vocals_path = Path(job.vocals_path or "")
    if not no_vocals_path.exists() or not vocals_path.exists():
        raise HTTPException(status_code=500, detail="Job outputs are unavailable")

    result = type(
        "DemucsResult",
        (),
        {
            "job_id": job.job_id,
            "no_vocals_path": no_vocals_path,
            "vocals_path": vocals_path,
            "duration_ms": job.duration_ms,
            "model": job.model,
            "device": job.device,
            "output_format": job.output_format,
            "mp3_bitrate": job.mp3_bitrate,
        },
    )()
    zip_payload = _build_stems_zip(result)
    headers = {
        "X-Job-Id": job.job_id,
        "X-Model": job.model,
        "X-Device": job.device,
        "X-Output-Format": job.output_format,
        "X-Duration-Ms": str(job.duration_ms or 0),
        "X-Vocals-Path": str(vocals_path),
        "X-Response-Format": "zip",
    }
    if job.mp3_bitrate is not None:
        headers["X-Mp3-Bitrate"] = str(job.mp3_bitrate)
    return Response(content=zip_payload, media_type="application/zip", headers=headers)


@app.delete("/jobs/{job_id}", status_code=202)
def cancel_job(job_id: str):
    try:
        job = job_store.require(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Job not found") from error

    if job.status in {"completed", "failed", "canceled"}:
        return {"job_id": job_id, "status": job.status}

    job_store.update(
        job_id,
        cancel_requested=True,
        progress_message="Cancel requested",
    )
    process = job.process
    if process is not None and process.poll() is None:
        process.terminate()
    return {"job_id": job_id, "status": "canceling"}


@app.post("/separate")
async def separate(
    file: UploadFile = File(...),
    model: str = Form(DEFAULT_DEMUCS_MODEL),
    device: Literal["cuda", "cpu"] = Form(DEFAULT_DEMUCS_DEVICE),
    output_format: Literal["wav", "mp3"] = Form(DEFAULT_OUTPUT_FORMAT),
    mp3_bitrate: int | None = Form(None),
):
    config = _validated_config(model, device, output_format, mp3_bitrate)
    payload = await file.read()
    job = _start_job(payload, file.filename or "input.wav", config)
    terminal_job = _wait_for_terminal_job(job.job_id)
    if terminal_job.status == "failed":
        raise HTTPException(status_code=500, detail=f"Demucs failed: {terminal_job.error_detail}")
    if terminal_job.status == "canceled":
        raise HTTPException(status_code=500, detail="Demucs job was canceled")
    return get_job_result(job.job_id)


@app.post("/separate-meta", response_model=SeparateMetaResponse)
async def separate_meta(
    file: UploadFile = File(...),
    model: str = Form(DEFAULT_DEMUCS_MODEL),
    device: Literal["cuda", "cpu"] = Form(DEFAULT_DEMUCS_DEVICE),
    output_format: Literal["wav", "mp3"] = Form(DEFAULT_OUTPUT_FORMAT),
    mp3_bitrate: int | None = Form(None),
):
    config = _validated_config(model, device, output_format, mp3_bitrate)

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
