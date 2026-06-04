"""Tests for demucs_svc advanced request-scoped configuration and async jobs."""

from __future__ import annotations

import importlib
import time
import zipfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(REPO_ROOT))

demucs_app = importlib.import_module("demucs_svc.app")
demucs_models = importlib.import_module("demucs_svc.models")
demucs_runner = importlib.import_module("demucs_svc.demucs_runner")


def test_separate_config_defaults_and_mp3_bitrate():
    config = demucs_models.SeparateConfig(output_format="mp3")
    assert config.model == "htdemucs"
    assert config.device == "cuda"
    assert config.output_format == "mp3"
    assert config.mp3_bitrate == 320


def test_separate_config_clears_mp3_bitrate_for_wav():
    config = demucs_models.SeparateConfig(output_format="wav", mp3_bitrate=256)
    assert config.output_format == "wav"
    assert config.mp3_bitrate is None


def test_parse_progress_line_extracts_percent_and_message():
    percent, message = demucs_runner.parse_progress_line(" 45%|#####     | 9/20 [00:01<00:01] ")
    assert percent == 45
    assert "45%" in message


def test_run_demucs_on_file_mp3_builds_expected_command_and_paths(tmp_path, monkeypatch):
    incoming = tmp_path / "incoming"
    output = tmp_path / "output"
    incoming.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(demucs_runner, "INCOMING_ROOT", incoming)
    monkeypatch.setattr(demucs_runner, "OUTPUT_ROOT", output)
    monkeypatch.setattr(
        demucs_runner,
        "uuid4",
        lambda: SimpleNamespace(hex="job123"),
    )

    seen_cmd = {}

    def fake_run(cmd, check, capture_output, text):
        seen_cmd["cmd"] = cmd
        out_dir = Path(cmd[cmd.index("-o") + 1])
        model = cmd[cmd.index("-n") + 1]
        input_path = Path(cmd[-1])
        stem = out_dir / model / input_path.stem
        stem.mkdir(parents=True, exist_ok=True)
        (stem / "no_vocals.mp3").write_bytes(b"no-vocals")
        (stem / "vocals.mp3").write_bytes(b"vocals")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(demucs_runner.subprocess, "run", fake_run)

    config = demucs_models.SeparateConfig(
        model="htdemucs_ft",
        device="cpu",
        output_format="mp3",
        mp3_bitrate=256,
    )
    result = demucs_runner.run_demucs_on_file(
        b"audio-bytes",
        "track.wav",
        config,
    )

    cmd = seen_cmd["cmd"]
    assert "-n" in cmd and "htdemucs_ft" in cmd
    assert "-d" in cmd and "cpu" in cmd
    assert "--mp3" in cmd
    assert "--mp3-bitrate" in cmd and "256" in cmd
    assert result.no_vocals_path.name.endswith(".mp3")
    assert result.vocals_path.name.endswith(".mp3")
    assert result.output_format == "mp3"


def test_create_job_and_fetch_result(monkeypatch, tmp_path):
    monkeypatch.setattr(demucs_app, "_cuda_available", lambda: True)
    monkeypatch.setattr(demucs_app, "INCOMING_ROOT", tmp_path / "incoming")
    monkeypatch.setattr(demucs_app, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(demucs_runner, "INCOMING_ROOT", tmp_path / "incoming")
    monkeypatch.setattr(demucs_runner, "OUTPUT_ROOT", tmp_path / "output")
    demucs_app.INCOMING_ROOT.mkdir(parents=True, exist_ok=True)
    demucs_app.OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    def fake_run_job(job_id, input_path, config):
        demucs_app.job_store.update(
            job_id,
            status="running",
            progress_percent=33,
            progress_message="Separating vocals",
            started_at=demucs_app.utc_now(),
        )
        no_vocals_path, vocals_path = demucs_runner.build_expected_output_paths(job_id, input_path, config)
        no_vocals_path.parent.mkdir(parents=True, exist_ok=True)
        no_vocals_path.write_bytes(b"no-vocals")
        vocals_path.write_bytes(b"vocals")
        demucs_app.job_store.update(
            job_id,
            status="completed",
            progress_percent=100,
            progress_message="Completed",
            finished_at=demucs_app.utc_now(),
            duration_ms=12,
            no_vocals_path=str(no_vocals_path),
            vocals_path=str(vocals_path),
            process=None,
        )

    monkeypatch.setattr(demucs_app, "_run_job", fake_run_job)

    client = TestClient(demucs_app.app)
    response = client.post(
        "/jobs",
        files={"file": ("input.wav", b"audio", "audio/wav")},
    )
    assert response.status_code == 202
    payload = response.json()
    job_id = payload["job_id"]

    status_response = client.get(f"/jobs/{job_id}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed"

    result_response = client.get(f"/jobs/{job_id}/result")
    assert result_response.status_code == 200
    assert result_response.headers["x-response-format"] == "zip"
    with zipfile.ZipFile(BytesIO(result_response.content)) as archive:
        names = set(archive.namelist())
        assert "no_vocals.wav" in names
        assert "vocals.wav" in names


def test_cancel_job_marks_terminal(monkeypatch, tmp_path):
    monkeypatch.setattr(demucs_app, "_cuda_available", lambda: True)
    monkeypatch.setattr(demucs_app, "INCOMING_ROOT", tmp_path / "incoming")
    monkeypatch.setattr(demucs_app, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(demucs_runner, "INCOMING_ROOT", tmp_path / "incoming")
    monkeypatch.setattr(demucs_runner, "OUTPUT_ROOT", tmp_path / "output")
    demucs_app.INCOMING_ROOT.mkdir(parents=True, exist_ok=True)
    demucs_app.OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    class FakeProcess:
        def __init__(self):
            self.terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

    process = FakeProcess()

    def fake_start_job(payload, original_filename, config):
        job_id, _incoming_dir, _output_dir, _input_path = demucs_runner.prepare_job_input(payload, original_filename)
        return demucs_app.job_store.create(
            demucs_app.DemucsJobState(
                job_id=job_id,
                model=config.model,
                device=config.device,
                output_format=config.output_format,
                mp3_bitrate=config.mp3_bitrate,
                original_filename=original_filename,
                status="running",
                process=process,
            )
        )

    monkeypatch.setattr(demucs_app, "_start_job", fake_start_job)

    client = TestClient(demucs_app.app)
    created = client.post(
        "/jobs",
        files={"file": ("input.wav", b"audio", "audio/wav")},
    )
    job_id = created.json()["job_id"]
    cancel_response = client.delete(f"/jobs/{job_id}")
    assert cancel_response.status_code == 202
    assert process.terminated is True
    status_payload = client.get(f"/jobs/{job_id}").json()
    assert status_payload["progress_message"] == "Cancel requested"


def test_separate_endpoint_defaults_to_wav(monkeypatch, tmp_path):
    monkeypatch.setattr(demucs_app, "_cuda_available", lambda: True)

    output_file = tmp_path / "no_vocals.wav"
    vocals_file = tmp_path / "vocals.wav"
    output_file.write_bytes(b"wav-audio")
    vocals_file.write_bytes(b"wav-vocals")

    def fake_start_job(payload, original_filename, config):
        job = demucs_app.DemucsJobState(
            job_id="job-default",
            model=config.model,
            device=config.device,
            output_format=config.output_format,
            mp3_bitrate=config.mp3_bitrate,
            original_filename=original_filename,
            status="completed",
            progress_percent=100,
            progress_message="Completed",
            created_at=demucs_app.utc_now(),
            started_at=demucs_app.utc_now(),
            finished_at=demucs_app.utc_now(),
            duration_ms=1000,
            no_vocals_path=str(output_file),
            vocals_path=str(vocals_file),
        )
        demucs_app.job_store.create(job)
        return job

    monkeypatch.setattr(demucs_app, "_start_job", fake_start_job)
    monkeypatch.setattr(demucs_app, "_wait_for_terminal_job", lambda job_id, timeout_seconds=600.0: demucs_app.job_store.require(job_id))

    client = TestClient(demucs_app.app)
    response = client.post(
        "/separate",
        files={"file": ("input.wav", b"audio", "audio/wav")},
    )

    assert response.status_code == 200
    assert response.headers["x-output-format"] == "wav"
    assert response.headers["x-response-format"] == "zip"
    assert response.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert "no_vocals.wav" in names
        assert "vocals.wav" in names
        assert "metadata.json" in names


def test_separate_endpoint_mp3_request_sets_headers(monkeypatch, tmp_path):
    monkeypatch.setattr(demucs_app, "_cuda_available", lambda: True)

    output_file = tmp_path / "no_vocals.mp3"
    vocals_file = tmp_path / "vocals.mp3"
    output_file.write_bytes(b"mp3-audio")
    vocals_file.write_bytes(b"mp3-vocals")

    def fake_start_job(payload, original_filename, config):
        job = demucs_app.DemucsJobState(
            job_id="job-mp3",
            model=config.model,
            device=config.device,
            output_format=config.output_format,
            mp3_bitrate=config.mp3_bitrate,
            original_filename=original_filename,
            status="completed",
            progress_percent=100,
            progress_message="Completed",
            created_at=demucs_app.utc_now(),
            started_at=demucs_app.utc_now(),
            finished_at=demucs_app.utc_now(),
            duration_ms=900,
            no_vocals_path=str(output_file),
            vocals_path=str(vocals_file),
        )
        demucs_app.job_store.create(job)
        return job

    monkeypatch.setattr(demucs_app, "_start_job", fake_start_job)
    monkeypatch.setattr(demucs_app, "_wait_for_terminal_job", lambda job_id, timeout_seconds=600.0: demucs_app.job_store.require(job_id))

    client = TestClient(demucs_app.app)
    response = client.post(
        "/separate",
        data={"output_format": "mp3", "mp3_bitrate": "256", "device": "cpu"},
        files={"file": ("input.wav", b"audio", "audio/wav")},
    )

    assert response.status_code == 200
    assert response.headers["x-output-format"] == "mp3"
    assert response.headers["x-mp3-bitrate"] == "256"
    assert response.headers["x-response-format"] == "zip"
    assert response.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert "no_vocals.mp3" in names
        assert "vocals.mp3" in names


def test_separate_endpoint_cuda_unavailable_fails_fast(monkeypatch):
    monkeypatch.setattr(demucs_app, "_cuda_available", lambda: False)
    client = TestClient(demucs_app.app)
    response = client.post(
        "/separate",
        data={"device": "cuda"},
        files={"file": ("input.wav", b"audio", "audio/wav")},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "CUDA requested but unavailable on Demucs host"
