from fastapi.testclient import TestClient
from unittest.mock import patch

from demucs_svc.app import app as demucs_app, job_store
from demucs_svc.jobs import DemucsJobState, utc_now


def _clear_job_store() -> None:
    for job in job_store.all():
        job_store.delete(job.job_id)


def _make_job(job_id: str, *, status: str, job_kind: str = "separation") -> DemucsJobState:
    return DemucsJobState(
        job_id=job_id,
        model="htdemucs",
        device="cuda",
        output_format="wav",
        mp3_bitrate=None,
        original_filename=f"{job_id}.wav",
        job_kind=job_kind,
        status=status,
        created_at=utc_now(),
    )


def test_metrics_reports_running_jobs_and_vram_snapshot():
    _clear_job_store()
    job_store.create(_make_job("job-running", status="running"))
    job_store.create(_make_job("job-queued", status="queued"))

    with patch("demucs_svc.app.preload_models", return_value=[]), patch(
        "demucs_svc.app._cuda_memory_snapshot",
        return_value=(3 * 1024 * 1024 * 1024, 8 * 1024 * 1024 * 1024),
    ):
        with TestClient(demucs_app) as client:
            response = client.get("/metrics")

    assert response.status_code == 200
    data = response.json()
    assert data["active_job_count"] == 2
    assert data["running_job_count"] == 1
    assert data["free_vram_bytes"] == 3 * 1024 * 1024 * 1024
    assert data["total_vram_bytes"] == 8 * 1024 * 1024 * 1024
    assert data["active_job_counts_by_status"] == {"queued": 1, "running": 1}
    assert data["active_job_counts_by_kind"] == {"separation": 2}

    _clear_job_store()


def test_gc_full_unloads_models_when_idle():
    _clear_job_store()

    with patch("demucs_svc.app.preload_models", return_value=[]), patch(
        "demucs_svc.app.unload_models",
        return_value={"transcription_models": 2, "align_models": 1},
    ) as unload_mock, patch(
        "demucs_svc.app.gc.collect",
        return_value=11,
    ) as gc_mock, patch(
        "demucs_svc.app._clear_cuda_memory",
        return_value=(True, True),
    ) as clear_mock, patch(
        "demucs_svc.app._cuda_memory_snapshot",
        return_value=(5 * 1024 * 1024 * 1024, 8 * 1024 * 1024 * 1024),
    ):
        with TestClient(demucs_app) as client:
            response = client.post("/gc", params={"mode": "full"})

    assert response.status_code == 200
    data = response.json()
    assert data["requested_mode"] == "full"
    assert data["executed_mode"] == "full"
    assert data["whisperx_unloaded"] == {"transcription_models": 2, "align_models": 1}
    unload_mock.assert_called_once()
    gc_mock.assert_called()
    clear_mock.assert_called_once()


def test_gc_full_downgrades_when_jobs_are_running():
    _clear_job_store()
    job_store.create(_make_job("job-running", status="running"))

    with patch("demucs_svc.app.preload_models", return_value=[]), patch(
        "demucs_svc.app.unload_models"
    ) as unload_mock, patch(
        "demucs_svc.app.gc.collect",
        return_value=7,
    ) as gc_mock, patch(
        "demucs_svc.app._clear_cuda_memory",
        return_value=(True, True),
    ) as clear_mock, patch(
        "demucs_svc.app._cuda_memory_snapshot",
        return_value=(1 * 1024 * 1024 * 1024, 8 * 1024 * 1024 * 1024),
    ):
        with TestClient(demucs_app) as client:
            response = client.post("/gc", params={"mode": "full"})

    assert response.status_code == 200
    data = response.json()
    assert data["requested_mode"] == "full"
    assert data["executed_mode"] == "cuda"
    unload_mock.assert_not_called()
    gc_mock.assert_called()
    clear_mock.assert_called_once()

    _clear_job_store()
