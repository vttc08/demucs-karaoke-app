"""Tests for ffmpeg adapter command construction."""
from pathlib import Path
import subprocess

from adapters.ffmpeg import FFmpegAdapter


def test_burn_subtitles_uses_configured_speed_flags(monkeypatch, tmp_path):
    """Subtitle burn command should include preset/crf optimization flags."""
    adapter = FFmpegAdapter(ffmpeg_path="/bin/ffmpeg")
    adapter.ffmpeg_preset = "veryfast"
    adapter.ffmpeg_crf = 24

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

    adapter.burn_subtitles(
        video_path=video_path,
        audio_path=audio_path,
        subtitle_text="Line 1\nLine 2",
        output_path=output_path,
    )

    cmd = captured_cmd["cmd"]
    assert "-preset" in cmd
    assert cmd[cmd.index("-preset") + 1] == "veryfast"
    assert "-crf" in cmd
    assert cmd[cmd.index("-crf") + 1] == "24"


def test_create_srt_file_uses_lrc_timestamps(tmp_path):
    """LRC timestamps should be converted to matching SRT cue timing."""
    adapter = FFmpegAdapter(ffmpeg_path="/bin/ffmpeg")
    srt_path = tmp_path / "lyrics.srt"
    lyrics = "[00:01.82]Line A\n[00:06.87]Line B\n"

    adapter._create_srt_file(lyrics, srt_path)

    content = srt_path.read_text(encoding="utf-8")
    assert "00:00:01,820 --> 00:00:06,870" in content
    assert "Line A" in content
    assert "00:00:06,870 --> 00:00:11,870" in content
    assert "Line B" in content


def test_create_srt_file_plain_text_fallback_starts_at_zero(tmp_path):
    """Plain text fallback should start first subtitle at 0 seconds."""
    adapter = FFmpegAdapter(ffmpeg_path="/bin/ffmpeg")
    srt_path = tmp_path / "plain.srt"

    adapter._create_srt_file("Line 1\nLine 2", srt_path)

    content = srt_path.read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:05,000" in content
