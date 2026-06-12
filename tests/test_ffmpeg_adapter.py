"""Tests for ffmpeg adapter command construction."""
import asyncio
from pathlib import Path
import threading
import subprocess

import pytest

from adapters.ffmpeg import FFmpegAdapter


def test_combine_audio_video_uses_stream_copy(monkeypatch, tmp_path):
    """Final karaoke combine should be remux-only without re-encoding."""
    adapter = FFmpegAdapter(ffmpeg_path="/bin/ffmpeg")
    captured_cmd = {}

    def fake_run(cmd, check, capture_output):
        captured_cmd["cmd"] = cmd
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    video_path = tmp_path / "in.mp4"
    audio_path = tmp_path / "in.wav"
    output_path = tmp_path / "out.mp4"
    video_path.write_bytes(b"v")
    audio_path.write_bytes(b"a")

    adapter.combine_audio_video(video_path=video_path, audio_path=audio_path, output_path=output_path)

    cmd = captured_cmd["cmd"]
    assert "-c:v" in cmd
    assert cmd[cmd.index("-c:v") + 1] == "copy"
    assert "-c:a" in cmd
    assert cmd[cmd.index("-c:a") + 1] == "copy"


def test_extract_audio_uses_stream_copy(monkeypatch, tmp_path):
    """Audio extraction for Demucs input should avoid transcoding."""
    adapter = FFmpegAdapter(ffmpeg_path="/bin/ffmpeg")
    captured_cmd = {}

    def fake_run(cmd, check, capture_output):
        captured_cmd["cmd"] = cmd
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(adapter, "_probe_audio_codec", lambda _path: "aac")

    source_path = tmp_path / "in.mp4"
    output_path = tmp_path / "audio.mka"
    source_path.write_bytes(b"v")

    adapter.extract_audio(source_path=source_path, output_path=output_path)

    cmd = captured_cmd["cmd"]
    assert "-vn" in cmd
    assert "-c:a" in cmd
    assert cmd[cmd.index("-c:a") + 1] == "copy"


def test_extract_audio_transcodes_unsupported_streams(monkeypatch, tmp_path):
    """WebM/Opus inputs should transcode to a Demucs-friendly m4a."""
    adapter = FFmpegAdapter(ffmpeg_path="/bin/ffmpeg")
    captured_cmd = {}

    def fake_run(cmd, check, capture_output):
        captured_cmd["cmd"] = cmd
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(adapter, "_probe_audio_codec", lambda _path: "opus")

    source_path = tmp_path / "in.webm"
    output_path = tmp_path / "audio.m4a"
    source_path.write_bytes(b"v")

    adapter.extract_audio(source_path=source_path, output_path=output_path)

    cmd = captured_cmd["cmd"]
    assert "-vn" in cmd
    assert "-c:a" in cmd
    assert cmd[cmd.index("-c:a") + 1] == "aac"


def test_extract_audio_terminates_child_on_cancel(monkeypatch, tmp_path):
    """Cancellation should terminate the ffmpeg child process."""
    adapter = FFmpegAdapter(ffmpeg_path="/bin/ffmpeg")
    cancel_event = threading.Event()
    cancel_event.set()

    class FakeProcess:
        def __init__(self):
            self.returncode = None
            self.terminated = False
            self.killed = False

        def poll(self):
            return self.returncode

        def terminate(self):
            self.terminated = True
            self.returncode = -15

        def kill(self):
            self.killed = True
            self.returncode = -9

        def wait(self, timeout=None):
            return 0 if self.returncode is None else self.returncode

    fake_process = FakeProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: fake_process)
    monkeypatch.setattr(adapter, "_probe_audio_codec", lambda _path: "aac")

    source_path = tmp_path / "in.mp4"
    output_path = tmp_path / "audio.mka"
    source_path.write_bytes(b"v")

    with pytest.raises(asyncio.CancelledError):
        adapter.extract_audio(source_path=source_path, output_path=output_path, cancel_event=cancel_event)

    assert fake_process.terminated is True
    assert fake_process.killed is False
