import subprocess
import sys
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from demucs_runner import run_demucs_on_file
from models import SeparateMetaResponse
from settings import IO_ROOT, INCOMING_ROOT, OUTPUT_ROOT, DEMUCS_MODEL, DEMUCS_DEVICE

app = FastAPI(title="Demucs Service", version="0.1.0")


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
        "model": DEMUCS_MODEL,
        "device": DEMUCS_DEVICE,
        "detail": detail,
        "checks": checks,
    }


@app.post("/separate")
async def separate(file: UploadFile = File(...)):
    try:
        payload = await file.read()
        result = run_demucs_on_file(payload, file.filename or "input.wav")
    except subprocess.CalledProcessError as e:  # type: ignore[name-defined]
        raise HTTPException(status_code=500, detail=f"Demucs failed: {e.stderr}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    headers = {
        "X-Job-Id": result.job_id,
        "X-Model": DEMUCS_MODEL,
        "X-Duration-Ms": str(result.duration_ms),
        "X-Vocals-Path": str(result.vocals_path),
    }
    return FileResponse(
        path=result.no_vocals_path,
        media_type="audio/wav",
        filename=f"{result.job_id}_no_vocals.wav",
        headers=headers,
    )


@app.post("/separate-meta", response_model=SeparateMetaResponse)
async def separate_meta(file: UploadFile = File(...)):
    try:
        payload = await file.read()
        result = run_demucs_on_file(payload, file.filename or "input.wav")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return SeparateMetaResponse(
        job_id=result.job_id,
        no_vocals_path=str(result.no_vocals_path),
        vocals_path=str(result.vocals_path),
        model=DEMUCS_MODEL,
        duration_ms=result.duration_ms,
        status="completed",
    )
