"""Tests for yt-dlp adapter command construction and output selection."""
from pathlib import Path
import subprocess
import threading

import pytest

from adapters.ytdlp import YtDlpAdapter
from config import settings


def test_download_audio_uses_direct_audio_format_without_extract(monkeypatch, tmp_path):
    """Audio download should avoid yt-dlp postprocessing to not require local ffmpeg."""
    adapter = YtDlpAdapter(ytdlp_path="/bin/yt-dlp")
    youtube_id = "abc123"
    expected_output = tmp_path / f"{youtube_id}.audio.m4a"
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


def test_streaming_download_adds_newline_for_live_progress(monkeypatch, tmp_path):
    """Streaming downloads should force line-delimited yt-dlp progress output."""
    adapter = YtDlpAdapter(ytdlp_path="/bin/yt-dlp")
    youtube_id = "stream123"
    expected_output = tmp_path / f"{youtube_id}.mp4"
    captured_cmd = {}

    def fake_streaming_download(cmd, *, progress_callback=None, log_callback=None):
        captured_cmd["cmd"] = cmd
        expected_output.write_bytes(b"video")
        if progress_callback:
            progress_callback(42, "[download] 42.0%")

    monkeypatch.setattr(adapter, "_run_streaming_download", fake_streaming_download)

    progress_events = []
    result = adapter.download_video_with_progress(
        youtube_id,
        tmp_path,
        progress_callback=lambda percent, line: progress_events.append((percent, line)),
    )

    assert result == expected_output
    assert "--newline" in captured_cmd["cmd"]
    assert "--progress" in captured_cmd["cmd"]
    assert "--no-colors" in captured_cmd["cmd"]
    assert "--progress-template" in captured_cmd["cmd"]
    assert "[download][karaoke-progress]" in captured_cmd["cmd"][captured_cmd["cmd"].index("--progress-template") + 1]
    assert progress_events == [(42, "[download] 42.0%")]


def test_parse_progress_line_prefers_structured_marker():
    """Structured yt-dlp progress lines should parse into bounded integer percentages."""
    assert YtDlpAdapter._parse_progress_line("[download][karaoke-progress] 42.500000") == 42
    assert YtDlpAdapter._parse_progress_line("[download] 87.1% of 12.3MiB") == 87
    assert YtDlpAdapter._parse_progress_line("some unrelated output") is None


def test_run_streaming_download_terminates_child_when_callback_raises(monkeypatch):
    """Callback failures should not leak the yt-dlp child process."""
    adapter = YtDlpAdapter(ytdlp_path="/bin/yt-dlp")

    class FakeStdout:
        def __init__(self):
            self.closed = False
            self._lines = ["[download] 5.0%\n", ""]

        def readline(self):
            return self._lines.pop(0)

        def close(self):
            self.closed = True

    class FakeProcess:
        def __init__(self):
            self.stdout = FakeStdout()
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

    with pytest.raises(RuntimeError, match="callback failed"):
        adapter._run_streaming_download(
            ["/bin/yt-dlp", "https://example.test/video"],
            progress_callback=lambda percent, line: (_ for _ in ()).throw(RuntimeError("callback failed")),
            timeout_seconds=1,
        )

    assert fake_process.terminated is True
    assert fake_process.killed is False
    assert fake_process.stdout.closed is True


def test_run_streaming_download_terminates_child_on_timeout(monkeypatch):
    """Streaming timeout should terminate the child before surfacing the timeout."""
    adapter = YtDlpAdapter(ytdlp_path="/bin/yt-dlp")
    release_event = threading.Event()

    class FakeStdout:
        def __init__(self):
            self.closed = False

        def readline(self):
            release_event.wait(timeout=1)
            return ""

        def close(self):
            self.closed = True

    class FakeProcess:
        def __init__(self):
            self.stdout = FakeStdout()
            self.returncode = None
            self.terminated = False
            self.killed = False

        def poll(self):
            return self.returncode

        def terminate(self):
            self.terminated = True
            self.returncode = -15
            release_event.set()

        def kill(self):
            self.killed = True
            self.returncode = -9
            release_event.set()

        def wait(self, timeout=None):
            return 0 if self.returncode is None else self.returncode

    fake_process = FakeProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: fake_process)

    with pytest.raises(subprocess.TimeoutExpired):
        adapter._run_streaming_download(
            ["/bin/yt-dlp", "https://example.test/video"],
            timeout_seconds=0.01,
        )

    assert fake_process.terminated is True
    assert fake_process.killed is False
    assert fake_process.stdout.closed is True


def test_download_audio_default_fallback_can_return_mp4(monkeypatch, tmp_path):
    """Audio fallback should accept container outputs when yt-dlp default picks mp4."""
    adapter = YtDlpAdapter(ytdlp_path="/bin/yt-dlp")
    youtube_id = "aud123"
    expected_output = tmp_path / f"{youtube_id}.audio.mp4"
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
    expected_output = tmp_path / f"{youtube_id}.audio.m4a"
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
