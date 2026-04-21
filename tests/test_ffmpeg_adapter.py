"""Tests for ffmpeg adapter command construction."""
from pathlib import Path
import subprocess

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

    source_path = tmp_path / "in.mp4"
    output_path = tmp_path / "audio.mka"
    source_path.write_bytes(b"v")

    adapter.extract_audio(source_path=source_path, output_path=output_path)

    cmd = captured_cmd["cmd"]
    assert "-vn" in cmd
    assert "-c:a" in cmd
    assert cmd[cmd.index("-c:a") + 1] == "copy"
