"""Tests for yt-dlp adapter command construction and output selection."""
from pathlib import Path
import subprocess

import pytest

from adapters.ytdlp import YtDlpAdapter


def test_download_audio_uses_direct_audio_format_without_extract(monkeypatch, tmp_path):
    """Audio download should avoid yt-dlp postprocessing to not require local ffmpeg."""
    adapter = YtDlpAdapter(ytdlp_path="/bin/yt-dlp")
    youtube_id = "abc123"
    expected_output = tmp_path / f"{youtube_id}.m4a"
    expected_output.write_bytes(b"audio")

    captured_cmd = {}

    def fake_run(cmd, check, capture_output, timeout):
        captured_cmd["cmd"] = cmd
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = adapter.download_audio(youtube_id, tmp_path)

    cmd = captured_cmd["cmd"]
    assert "-x" not in cmd
    assert "--audio-format" not in cmd
    assert "-f" in cmd
    assert "bestaudio[ext=m4a]/bestaudio/best" in cmd
    assert "--extractor-args" in cmd
    assert "youtube:player_client=web" in cmd
    assert result == expected_output


def test_download_audio_raises_when_file_missing(monkeypatch, tmp_path):
    """Audio download should fail clearly when yt-dlp returns success but no file exists."""
    adapter = YtDlpAdapter(ytdlp_path="/bin/yt-dlp")

    def fake_run(cmd, check, capture_output, timeout):
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="file not found"):
        adapter.download_audio("missing123", tmp_path)


def test_download_video_retries_without_ios_client(monkeypatch, tmp_path):
    """Video download should retry fallback formats without ios client attempts."""
    adapter = YtDlpAdapter(ytdlp_path="/bin/yt-dlp")
    youtube_id = "vid123"
    expected_output = tmp_path / f"{youtube_id}.mp4"
    calls = []

    def fake_run(cmd, check, capture_output, timeout):
        calls.append(cmd)
        if len(calls) == 1:
            raise subprocess.CalledProcessError(
                returncode=1, cmd=cmd, stderr=b"Signature solving failed"
            )
        expected_output.write_bytes(b"video")
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = adapter.download_video(youtube_id, tmp_path)

    assert result == expected_output
    assert len(calls) >= 2
    assert "youtube:player_client=web" in calls[0]
    assert all("youtube:player_client=ios" not in call for call in calls)


def test_download_video_with_audio_falls_back_to_best(monkeypatch, tmp_path):
    """Progressive download should fall back from strict format to yt-dlp default."""
    adapter = YtDlpAdapter(ytdlp_path="/bin/yt-dlp")
    youtube_id = "prog123"
    expected_output = tmp_path / f"{youtube_id}.webm"
    calls = []

    def fake_run(cmd, check, capture_output, timeout):
        calls.append(cmd)
        if "-f" in cmd:
            raise subprocess.CalledProcessError(
                returncode=1, cmd=cmd, stderr=b"Requested format is not available"
            )
        expected_output.write_bytes(b"video-audio")
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = adapter.download_video_with_audio(youtube_id, tmp_path)

    assert result == expected_output
    attempted_formats = [cmd[cmd.index("-f") + 1] for cmd in calls if "-f" in cmd]
    assert "best[ext=mp4]/best" in attempted_formats
    assert "-f" not in calls[-1]


def test_download_audio_default_fallback_can_return_mp4(monkeypatch, tmp_path):
    """Audio fallback should accept container outputs when yt-dlp default picks mp4."""
    adapter = YtDlpAdapter(ytdlp_path="/bin/yt-dlp")
    youtube_id = "aud123"
    expected_output = tmp_path / f"{youtube_id}.mp4"
    calls = []

    def fake_run(cmd, check, capture_output, timeout):
        calls.append(cmd)
        if "-f" in cmd:
            raise subprocess.CalledProcessError(
                returncode=1, cmd=cmd, stderr=b"Requested format is not available"
            )
        expected_output.write_bytes(b"container-audio")
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = adapter.download_audio(youtube_id, tmp_path)

    assert result == expected_output
    assert "-f" not in calls[-1]
