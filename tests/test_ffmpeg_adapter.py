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


def test_probe_media_reads_duration_and_stream_types(monkeypatch, tmp_path):
    adapter = FFmpegAdapter(ffmpeg_path="/opt/bin/ffmpeg")

    def fake_run(cmd, check, capture_output, text):
        assert cmd[0] == "/opt/bin/ffprobe"
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout='{"format":{"duration":"12.5","start_time":"1.0"},'
            '"streams":[{"codec_type":"video","avg_frame_rate":"30000/1001"},'
            '{"codec_type":"audio"}]}',
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = adapter.probe_media(tmp_path / "input.mp4")

    assert result == {
        "duration": 12.5,
        "start_time": 1.0,
        "has_video": True,
        "has_audio": True,
        "frame_rate": pytest.approx(30000 / 1001),
    }


def test_has_audio_stream_reads_ffprobe_json(monkeypatch, tmp_path):
    adapter = FFmpegAdapter(ffmpeg_path="/opt/bin/ffmpeg")
    source_path = tmp_path / "input.mp4"
    captured = {}

    def fake_run(cmd, check, capture_output, text):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout='{"streams":[{"codec_type":"audio"}]}',
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert adapter.has_audio_stream(source_path) is True
    assert captured["cmd"] == [
        "/opt/bin/ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        "-select_streams",
        "a",
        str(source_path),
    ]


def test_has_audio_stream_returns_false_without_audio(monkeypatch, tmp_path):
    adapter = FFmpegAdapter(ffmpeg_path="/bin/ffmpeg")

    def fake_run(cmd, check, capture_output, text):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout='{"streams":[]}')

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert adapter.has_audio_stream(tmp_path / "input.mp4") is False


@pytest.mark.parametrize(
    "side_effect,stdout",
    [
        (FileNotFoundError(), ""),
        (subprocess.CalledProcessError(returncode=1, cmd=["ffprobe"]), ""),
        (None, "{not-json"),
    ],
)
def test_has_audio_stream_returns_false_when_probe_fails(
    monkeypatch,
    tmp_path,
    side_effect,
    stdout,
):
    adapter = FFmpegAdapter(ffmpeg_path="/bin/ffmpeg")

    def fake_run(cmd, check, capture_output, text):
        if side_effect is not None:
            raise side_effect
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout)

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert adapter.has_audio_stream(tmp_path / "input.mp4") is False


def test_get_video_keyframes_normalizes_media_start_time(monkeypatch, tmp_path):
    adapter = FFmpegAdapter(ffmpeg_path="/opt/bin/ffmpeg")
    monkeypatch.setattr(
        adapter,
        "probe_media",
        lambda _path: {
            "duration": 10.0,
            "start_time": 2.0,
            "has_video": True,
            "has_audio": True,
        },
    )

    def fake_run(cmd, check, capture_output, text):
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout='{"frames":[{"best_effort_timestamp_time":"2.0"},'
            '{"pts_time":"6.5"},{"best_effort_timestamp_time":"20.0"}]}',
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert adapter.get_video_keyframes(tmp_path / "input.mp4") == [0.0, 4.5, 10.0]


def test_lossless_trim_maps_all_streams_and_uses_copy(monkeypatch, tmp_path):
    adapter = FFmpegAdapter(ffmpeg_path="/bin/ffmpeg")
    captured = {}
    monkeypatch.setattr(adapter, "_run_command", lambda cmd, **_kwargs: captured.setdefault("cmd", cmd))

    adapter.lossless_trim(
        tmp_path / "input.mp4",
        tmp_path / "output.mp4",
        5.0,
        20.0,
    )

    cmd = captured["cmd"]
    assert cmd[cmd.index("-ss") + 1] == "5.000000"
    assert cmd[cmd.index("-t") + 1] == "15.000000"
    assert cmd[cmd.index("-map") + 1] == "0"
    assert cmd[cmd.index("-c") + 1] == "copy"
    assert "-c:v" not in cmd
    assert "-c:a" not in cmd
    assert cmd[cmd.index("-movflags") + 1] == "+faststart"
