"""Tests for demucs_svc advanced request-scoped configuration."""

from __future__ import annotations

import importlib
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


def test_separate_endpoint_defaults_to_wav(monkeypatch, tmp_path):
    monkeypatch.setattr(demucs_app, "_cuda_available", lambda: True)

    output_file = tmp_path / "no_vocals.wav"
    vocals_file = tmp_path / "vocals.wav"
    output_file.write_bytes(b"wav-audio")
    vocals_file.write_bytes(b"wav-vocals")

    def fake_run(payload, original_filename, config):
        assert config.output_format == "wav"
        return SimpleNamespace(
            job_id="job-default",
            no_vocals_path=output_file,
            vocals_path=vocals_file,
            duration_ms=1000,
            model=config.model,
            device=config.device,
            output_format=config.output_format,
            mp3_bitrate=config.mp3_bitrate,
        )

    monkeypatch.setattr(demucs_app, "run_demucs_on_file", fake_run)

    client = TestClient(demucs_app.app)
    response = client.post(
        "/separate",
        files={"file": ("input.wav", b"audio", "audio/wav")},
    )

    assert response.status_code == 200
    assert response.headers["x-output-format"] == "wav"
    assert response.headers["content-type"].startswith("audio/wav")


def test_separate_endpoint_mp3_request_sets_headers(monkeypatch, tmp_path):
    monkeypatch.setattr(demucs_app, "_cuda_available", lambda: True)

    output_file = tmp_path / "no_vocals.mp3"
    vocals_file = tmp_path / "vocals.mp3"
    output_file.write_bytes(b"mp3-audio")
    vocals_file.write_bytes(b"mp3-vocals")

    def fake_run(payload, original_filename, config):
        assert config.output_format == "mp3"
        assert config.mp3_bitrate == 256
        return SimpleNamespace(
            job_id="job-mp3",
            no_vocals_path=output_file,
            vocals_path=vocals_file,
            duration_ms=900,
            model=config.model,
            device=config.device,
            output_format=config.output_format,
            mp3_bitrate=config.mp3_bitrate,
        )

    monkeypatch.setattr(demucs_app, "run_demucs_on_file", fake_run)

    client = TestClient(demucs_app.app)
    response = client.post(
        "/separate",
        data={"output_format": "mp3", "mp3_bitrate": "256", "device": "cpu"},
        files={"file": ("input.wav", b"audio", "audio/wav")},
    )

    assert response.status_code == 200
    assert response.headers["x-output-format"] == "mp3"
    assert response.headers["x-mp3-bitrate"] == "256"
    assert response.headers["content-type"].startswith("audio/mpeg")


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
