"""Tests for yt-dlp adapter command construction and output selection."""
from pathlib import Path
import subprocess

import pytest

from adapters.ytdlp import YtDlpAdapter
from config import settings


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
    assert "youtube:player_client=web" not in calls[0]
    assert "-f" in calls[0]
    assert "bestvideo/best" in calls[0]
    assert any("youtube:player_client=web" in call for call in calls[1:])
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


def test_search_includes_proxy_when_configured(monkeypatch):
    """Search command should include --proxy when ytdlp_proxy_url is set."""
    adapter = YtDlpAdapter(ytdlp_path="/bin/yt-dlp")
    original_proxy = settings.ytdlp_proxy_url
    settings.ytdlp_proxy_url = "socks5://127.0.0.1:1080"
    captured_cmd = {}

    def fake_run(cmd, capture_output, text, check, timeout):
        captured_cmd["cmd"] = cmd
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    try:
        adapter.search("proxy test")
    finally:
        settings.ytdlp_proxy_url = original_proxy

    cmd = captured_cmd["cmd"]
    assert "--proxy" in cmd
    assert "socks5://127.0.0.1:1080" in cmd


def test_download_includes_proxy_when_configured(monkeypatch, tmp_path):
    """Download command should include --proxy when ytdlp_proxy_url is set."""
    adapter = YtDlpAdapter(ytdlp_path="/bin/yt-dlp")
    youtube_id = "proxydl123"
    expected_output = tmp_path / f"{youtube_id}.m4a"
    expected_output.write_bytes(b"audio")
    original_proxy = settings.ytdlp_proxy_url
    settings.ytdlp_proxy_url = "http://127.0.0.1:3128"
    captured_cmd = {}

    def fake_run(cmd, check, capture_output, timeout):
        captured_cmd["cmd"] = cmd
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    try:
        adapter.download_audio(youtube_id, tmp_path)
    finally:
        settings.ytdlp_proxy_url = original_proxy

    cmd = captured_cmd["cmd"]
    assert "--proxy" in cmd
    assert "http://127.0.0.1:3128" in cmd


def test_get_video_info_parses_single_json(monkeypatch):
    """Single video info fetch should parse --dump-single-json response."""
    adapter = YtDlpAdapter(ytdlp_path="/bin/yt-dlp")
    captured_cmd = {}

    def fake_run(cmd, capture_output, text, check, timeout):
        captured_cmd["cmd"] = cmd
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout='{"id":"dQw4w9WgXcQ","title":"Song","uploader":"Channel","duration_string":"3:33","thumbnail":"https://i.ytimg.com/x.jpg"}',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = adapter.get_video_info("https://youtu.be/dQw4w9WgXcQ")
    assert result["video_id"] == "dQw4w9WgXcQ"
    assert result["title"] == "Song"
    assert "--dump-single-json" in captured_cmd["cmd"]


def test_get_video_info_fallback_without_extractor_args(monkeypatch):
    """Metadata fetch should fallback to default client when web client fails."""
    adapter = YtDlpAdapter(ytdlp_path="/bin/yt-dlp")
    calls = []

    def fake_run(cmd, capture_output, text, check, timeout):
        calls.append(cmd)
        if len(calls) == 1:
            raise subprocess.CalledProcessError(
                returncode=1,
                cmd=cmd,
                stderr=b"ERROR: [youtube] FQUTyz0WfOM: Requested format is not available.",
            )
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout='{"id":"FQUTyz0WfOM","title":"Song","uploader":"Channel"}',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = adapter.get_video_info("https://www.youtube.com/watch?v=FQUTyz0WfOM")
    assert result["video_id"] == "FQUTyz0WfOM"
    assert len(calls) == 2
    assert "--extractor-args" in calls[0]
    assert "--extractor-args" not in calls[1]
