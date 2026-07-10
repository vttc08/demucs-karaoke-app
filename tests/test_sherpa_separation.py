from __future__ import annotations

import io
import tarfile

import pytest

from demucs_svc import download_sherpa_models
from demucs_svc.separation.base import (
    SeparationCanceled,
    SeparationRequest,
    SeparationRuntime,
)
from demucs_svc.separation.sherpa_spleeter import SherpaSpleeterProvider


def _model_archive(variant: str) -> bytes:
    directory = download_sherpa_models.MODEL_DIRECTORIES[variant]
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:bz2") as archive:
        for filename in download_sherpa_models.MODEL_FILES[variant]:
            payload = f"model:{filename}".encode()
            member = tarfile.TarInfo(f"{directory}/{filename}")
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
    return buffer.getvalue()


def test_model_downloader_installs_validated_variant(tmp_path, monkeypatch):
    archive_bytes = _model_archive("fp16")
    monkeypatch.setattr(
        download_sherpa_models,
        "urlopen",
        lambda *args, **kwargs: io.BytesIO(archive_bytes),
    )

    installed = download_sherpa_models.install_variant("fp16", tmp_path)

    assert installed.name == "sherpa-onnx-spleeter-2stems-fp16"
    assert (installed / "vocals.fp16.onnx").is_file()
    assert (installed / "accompaniment.fp16.onnx").is_file()


def test_sherpa_provider_cancellation_terminates_child(tmp_path, monkeypatch):
    provider = SherpaSpleeterProvider(
        model_root=tmp_path,
        num_threads=4,
        ffmpeg_path="ffmpeg",
    )
    monkeypatch.setattr(
        provider,
        "readiness",
        lambda model: {"ready": True, "checks": {}},
    )

    class FakeProcess:
        exitcode = None

        def __init__(self, *args, **kwargs):
            self.alive = False

        def start(self):
            self.alive = True

        def is_alive(self):
            return self.alive

    process = FakeProcess()
    monkeypatch.setattr(
        "demucs_svc.separation.sherpa_spleeter.multiprocessing.Process",
        lambda *args, **kwargs: process,
    )
    process_updates = []
    runtime = SeparationRuntime(
        set_process=process_updates.append,
        append_output=lambda line: None,
        emit_progress=lambda *args: None,
        is_canceled=lambda: True,
        terminate_process=lambda child: setattr(child, "alive", False),
    )
    request = SeparationRequest(
        job_id="job",
        input_path=tmp_path / "input.mp4",
        output_dir=tmp_path / "output",
        model="fp16",
        requested_device="cuda",
        output_format="wav",
        mp3_bitrate=None,
    )

    with pytest.raises(SeparationCanceled):
        provider.separate(request, runtime)

    assert process_updates == [process, None]
    assert process.alive is False
