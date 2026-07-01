"""Tests for demucs_svc advanced request-scoped configuration and async jobs."""

from __future__ import annotations

import asyncio
import json
import importlib
import logging
import time
import threading
import zipfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(REPO_ROOT))

demucs_app = importlib.import_module("demucs_svc.app")
demucs_models = importlib.import_module("demucs_svc.models")
demucs_runner = importlib.import_module("demucs_svc.demucs_runner")
demucs_settings = importlib.import_module("demucs_svc.settings")


def _clear_job_store() -> None:
    for job in demucs_app.job_store.all():
        demucs_app.job_store.delete(job.job_id)


def test_separate_config_defaults_and_mp3_bitrate():
    config = demucs_models.SeparateConfig(output_format="mp3")
    assert config.model == "htdemucs"
    assert config.device == "cuda"
    assert config.output_format == "mp3"
    assert config.mp3_bitrate == 320
    assert config.transcription_model == "tiny"
    assert config.align_language == "en"
    assert config.detect_language is False
    assert config.use_synced_lyrics is False
    assert config.whisperx_preload_models == "transcription=tiny,align=en"


def test_demucs_settings_uses_default_io_root():
    assert demucs_settings.IO_ROOT == demucs_settings.DEFAULT_IO_ROOT
    assert demucs_settings.INCOMING_ROOT == demucs_settings.IO_ROOT / "incoming"
    assert demucs_settings.OUTPUT_ROOT == demucs_settings.IO_ROOT / "output"


def test_demucs_settings_accepts_env_var_override_for_io_root(tmp_path, monkeypatch):
    custom_root = tmp_path / "custom-io"
    monkeypatch.setenv("DEMUCS_IO_ROOT", str(custom_root))

    config = demucs_settings.DemucsSettings()

    assert config.io_root == custom_root


def test_demucs_settings_accepts_env_file_override_for_io_root(tmp_path):
    custom_root = tmp_path / "custom-io-from-file"
    env_file = tmp_path / "demucs.env"
    env_file.write_text(f"DEMUCS_IO_ROOT={custom_root}\n", encoding="utf-8")

    config = demucs_settings.DemucsSettings(_env_file=env_file)

    assert config.io_root == custom_root


def test_separate_config_accepts_srt_lyrics_format():
    config = demucs_models.SeparateConfig(lyrics_format="srt")
    assert config.lyrics_format == "srt"


def test_whisperx_preload_parser_keeps_bare_entries_on_previous_type(monkeypatch):
    whisperx_pipeline = importlib.import_module("demucs_svc.whisperx_pipeline")

    calls: list[tuple[str, str, dict[str, object] | str]] = []

    class FakeWhisperX:
        @staticmethod
        def load_model(model_name, **kwargs):
            calls.append(("transcription", model_name, kwargs))
            return {"model_name": model_name, "kwargs": kwargs}

        @staticmethod
        def load_align_model(language_code, device):
            calls.append(("align", language_code, device))
            return {"language_code": language_code}, {"language_code": language_code}

    monkeypatch.setattr(whisperx_pipeline, "whisperx", FakeWhisperX)
    whisperx_pipeline._TRANSCRIPTION_MODEL_CACHE.clear()
    whisperx_pipeline._ALIGN_MODEL_CACHE.clear()

    entries = whisperx_pipeline._parse_preload_entries("transcription=tiny,align=en,fr,zh")
    assert entries == [
        ("transcription", "tiny"),
        ("align", "en"),
        ("align", "fr"),
        ("align", "zh"),
    ]

    whisperx_pipeline.preload_models("transcription=tiny,align=en,fr", device="cpu")
    assert calls == [
        ("transcription", "tiny", {"device": "cpu", "compute_type": "float32"}),
        ("align", "en", "cpu"),
        ("align", "fr", "cpu"),
    ]


def test_parse_srt_lyrics_uses_library_entries(monkeypatch):
    whisperx_pipeline = importlib.import_module("demucs_svc.whisperx_pipeline")

    class FakeDelta:
        def __init__(self, seconds):
            self._seconds = seconds

        def total_seconds(self):
            return self._seconds

    monkeypatch.setattr(
        whisperx_pipeline,
        "srt",
        SimpleNamespace(
            parse=lambda text: [
                SimpleNamespace(content="Hello\nworld", start=FakeDelta(1.25), end=FakeDelta(2.75)),
                SimpleNamespace(content="Second line", start=FakeDelta(2.75), end=FakeDelta(4.0)),
            ]
        ),
    )

    segments, is_synced = whisperx_pipeline._parse_srt("ignored")

    assert is_synced is True
    assert [(segment.text, segment.start, segment.end) for segment in segments] == [
        ("Hello world", 1.25, 2.75),
        ("Second line", 2.75, 4.0),
    ]


def test_parse_lrc_lyrics_uses_library_entries_and_falls_back_to_text(monkeypatch):
    whisperx_pipeline = importlib.import_module("demucs_svc.whisperx_pipeline")

    monkeypatch.setattr(
        whisperx_pipeline,
        "pylrc",
        SimpleNamespace(
            parse=lambda text: [
                SimpleNamespace(text="Hello / 你好", time=1.0),
                SimpleNamespace(text="World", time=3.0),
            ]
        ),
    )

    segments, is_synced = whisperx_pipeline._parse_lrc("ignored")

    assert is_synced is True
    assert [(segment.text, segment.start, segment.end) for segment in segments] == [
        ("Hello", 1.0, 3.0),
        ("World", 3.0, 8.0),
    ]

    monkeypatch.setattr(whisperx_pipeline, "pylrc", SimpleNamespace(parse=lambda text: []))
    fallback_segments, fallback_is_synced = whisperx_pipeline._parse_lrc("line one\nline two")

    assert fallback_is_synced is False
    assert [(segment.text, segment.start, segment.end) for segment in fallback_segments] == [
        ("line one", 0.0, 0.0),
        ("line two", 0.0, 0.0),
    ]


def test_whisperx_preload_endpoint_uses_remote_models(monkeypatch):
    monkeypatch.setattr(demucs_app, "whisperx_available", lambda: True)
    seen = {}

    def fake_preload_models(preload_models, *, device, compute_type=None):
        seen["preload_models"] = preload_models
        seen["device"] = device
        seen["compute_type"] = compute_type
        return ["transcription=tiny", "align=en", "align=fr"]

    monkeypatch.setattr(demucs_app, "preload_models", fake_preload_models)

    client = TestClient(demucs_app.app)
    response = client.post(
        "/whisperx/preload",
        data={
            "whisperx_preload_models": "transcription=tiny,align=en,fr",
            "device": "cpu",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["requested_models"] == "transcription=tiny,align=en,fr"
    assert data["device"] == "cpu"
    assert data["loaded_entries"] == ["transcription=tiny", "align=en", "align=fr"]
    assert seen == {
        "preload_models": "transcription=tiny,align=en,fr",
        "device": "cpu",
        "compute_type": None,
    }


def test_startup_logs_degraded_health_when_demucs_cli_unavailable(monkeypatch, caplog):
    monkeypatch.setattr(demucs_app, "preload_models", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        demucs_app.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
    )
    caplog.set_level(logging.INFO, logger=demucs_app.logger.name)

    with TestClient(demucs_app.app):
        pass

    assert "Demucs startup degraded" in caplog.text
    assert "demucs_cli_available" in caplog.text


def test_startup_logs_whisperx_preload_failure(monkeypatch, caplog):
    def fail_preload(*args, **kwargs):
        raise RuntimeError("No Demucs in this virtualenv")

    monkeypatch.setattr(demucs_app, "preload_models", fail_preload)
    monkeypatch.setattr(
        demucs_app.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )
    caplog.set_level(logging.INFO, logger=demucs_app.logger.name)

    with TestClient(demucs_app.app):
        pass

    assert "WhisperX preload failed during Demucs startup" in caplog.text
    assert "No Demucs in this virtualenv" in caplog.text
    assert "Demucs startup healthy" in caplog.text


def test_align_lyrics_supports_srt_format(monkeypatch):
    whisperx_pipeline = importlib.import_module("demucs_svc.whisperx_pipeline")

    class FakeDelta:
        def __init__(self, seconds):
            self._seconds = seconds

        def total_seconds(self):
            return self._seconds

    monkeypatch.setattr(
        whisperx_pipeline,
        "srt",
        SimpleNamespace(
            parse=lambda text: [
                SimpleNamespace(content="Hello\nworld", start=FakeDelta(1.0), end=FakeDelta(2.0)),
                SimpleNamespace(content="Second line", start=FakeDelta(2.0), end=FakeDelta(3.0)),
            ]
        ),
    )
    monkeypatch.setattr(
        whisperx_pipeline,
        "whisperx",
        SimpleNamespace(
            load_audio=lambda path: [0.0] * 16000,
            load_align_model=lambda language_code, device: ({"language_code": language_code}, {"language_code": language_code}),
            align=lambda transcript, *args, **kwargs: {"segments": transcript},
        ),
    )

    aligned = whisperx_pipeline.align_lyrics(
        Path("input.wav"),
        "ignored",
        lyrics_format="srt",
        transcription_model="tiny",
        align_language="en",
        detect_language=False,
        use_synced_lyrics=True,
        process_lyrics_lines=False,
        max_line_length=36,
        max_line_length_cjk=12,
        device="cpu",
        compute_type=None,
    )

    assert [(segment["text"], segment["start"], segment["end"]) for segment in aligned] == [
        ("Hello world", 1.0, 2.0),
        ("Second line", 2.0, 3.0),
    ]


def test_align_lyrics_rebuilds_synced_lrc_lines_with_filtered_tokens(monkeypatch):
    whisperx_pipeline = importlib.import_module("demucs_svc.whisperx_pipeline")

    monkeypatch.setattr(
        whisperx_pipeline,
        "pylrc",
        SimpleNamespace(
            parse=lambda text: [
                SimpleNamespace(text="Now he's thinkin' 'bout me every night, oh", time=8.83),
                SimpleNamespace(text="My give-a-fucks are on vacation", time=33.32),
                SimpleNamespace(text="♪", time=50.28),
            ]
        ),
    )
    monkeypatch.setattr(
        whisperx_pipeline,
        "whisperx",
        SimpleNamespace(
            load_audio=lambda path: [0.0] * 16000,
            load_align_model=lambda language_code, device: (
                {"language_code": language_code},
                {"language_code": language_code},
            ),
            align=lambda transcript, *args, **kwargs: {
                "segments": [
                    {
                        "start": 22.661,
                        "end": 51.422,
                        "text": "flattened",
                        "words": [
                            {"word": "Now", "start": 22.661, "end": 22.921, "score": 0.47},
                            {"word": "he's", "start": 23.161, "end": 23.281, "score": 0.18},
                            {"word": "thinkin'", "start": 23.781, "end": 24.061, "score": 0.30},
                            {"word": "'bout", "start": 24.081, "end": 24.361, "score": 0.45},
                            {"word": "me", "start": 24.401, "end": 25.001, "score": 0.70},
                            {"word": "every", "start": 25.061, "end": 25.241, "score": 0.28},
                            {"word": "night,", "start": 25.281, "end": 25.581, "score": 0.42},
                            {"word": "oh", "start": 25.821, "end": 26.101, "score": 0.72},
                            {"word": "My", "start": 47.182, "end": 47.422, "score": 0.62},
                            {"word": "give", "start": 47.442, "end": 47.782, "score": 0.51},
                            {"word": "a", "start": 47.822, "end": 47.982, "score": 0.63},
                            {"word": "fucks", "start": 48.022, "end": 48.522, "score": 0.61},
                            {"word": "are", "start": 48.562, "end": 48.862, "score": 0.58},
                            {"word": "on", "start": 49.002, "end": 49.262, "score": 0.60},
                            {"word": "vacation", "start": 49.302, "end": 51.422, "score": 0.66},
                            {"word": "♪", "start": 51.500, "end": 51.600, "score": 0.01},
                        ],
                    }
                ]
            },
        ),
    )

    aligned = whisperx_pipeline.align_lyrics(
        Path("input.wav"),
        "ignored",
        lyrics_format="lrc",
        transcription_model="tiny",
        align_language="en",
        detect_language=False,
        use_synced_lyrics=False,
        process_lyrics_lines=False,
        max_line_length=36,
        max_line_length_cjk=12,
        device="cpu",
        compute_type=None,
    )

    assert [(segment["start"], segment["end"], segment["text"]) for segment in aligned] == [
        (22.661, 26.101, "Now he's thinkin' 'bout me every night, oh"),
        (47.182, 51.422, "My give a fucks are on vacation"),
    ]


def test_align_lyrics_rebuilds_unsynced_plain_text_lines(monkeypatch):
    whisperx_pipeline = importlib.import_module("demucs_svc.whisperx_pipeline")

    seen_transcript = {}

    def fake_align(transcript, *args, **kwargs):
        seen_transcript["transcript"] = transcript
        return {
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "flattened",
                    "words": [
                        {"word": "Hello", "start": 0.0, "end": 0.2, "score": 0.91},
                        {"word": "world", "start": 0.2, "end": 0.5, "score": 0.87},
                        {"word": "Second", "start": 0.5, "end": 0.7, "score": 0.86},
                        {"word": "line", "start": 0.7, "end": 1.0, "score": 0.84},
                    ],
                }
            ]
        }

    monkeypatch.setattr(whisperx_pipeline, "pylrc", SimpleNamespace(parse=lambda text: []))
    monkeypatch.setattr(
        whisperx_pipeline,
        "whisperx",
        SimpleNamespace(
            load_audio=lambda path: [0.0] * 16000,
            load_align_model=lambda language_code, device: (
                {"language_code": language_code},
                {"language_code": language_code},
            ),
            align=fake_align,
        ),
    )

    aligned = whisperx_pipeline.align_lyrics(
        Path("input.wav"),
        "Hello world\nSecond line",
        lyrics_format="txt",
        transcription_model="tiny",
        align_language="en",
        detect_language=False,
        use_synced_lyrics=False,
        process_lyrics_lines=False,
        max_line_length=36,
        max_line_length_cjk=12,
        device="cpu",
        compute_type=None,
    )

    assert seen_transcript["transcript"] == [{"text": "Hello world Second line", "start": 0.0, "end": 1.0}]
    assert [(segment["start"], segment["end"], segment["text"]) for segment in aligned] == [
        (0.0, 0.5, "Hello world"),
        (0.5, 1.0, "Second line"),
    ]


def test_align_lyrics_processes_plain_text_lines_before_alignment(monkeypatch):
    whisperx_pipeline = importlib.import_module("demucs_svc.whisperx_pipeline")

    seen_transcript = {}

    def fake_align(transcript, *args, **kwargs):
        seen_transcript["transcript"] = transcript
        return {
            "segments": [
                {
                    "start": 0.0,
                    "end": 2.0,
                    "text": "flattened",
                    "words": [
                        {"word": "Hello", "start": 0.0, "end": 0.2, "score": 0.9},
                        {"word": "there", "start": 0.2, "end": 0.4, "score": 0.9},
                        {"word": "friend", "start": 0.4, "end": 0.6, "score": 0.9},
                        {"word": "this", "start": 0.6, "end": 0.8, "score": 0.9},
                        {"word": "line", "start": 0.8, "end": 1.0, "score": 0.9},
                        {"word": "should", "start": 1.0, "end": 1.2, "score": 0.9},
                        {"word": "split", "start": 1.2, "end": 1.4, "score": 0.9},
                    ],
                }
            ]
        }

    monkeypatch.setattr(whisperx_pipeline, "pylrc", SimpleNamespace(parse=lambda text: []))
    monkeypatch.setattr(
        whisperx_pipeline,
        "whisperx",
        SimpleNamespace(
            load_audio=lambda path: [0.0] * 32000,
            load_align_model=lambda language_code, device: (
                {"language_code": language_code},
                {"language_code": language_code},
            ),
            align=fake_align,
        ),
    )

    aligned = whisperx_pipeline.align_lyrics(
        Path("input.wav"),
        "Hello there friend this line should split",
        lyrics_format="txt",
        transcription_model="tiny",
        align_language="en",
        detect_language=False,
        use_synced_lyrics=False,
        process_lyrics_lines=True,
        max_line_length=18,
        max_line_length_cjk=12,
        device="cpu",
        compute_type=None,
    )

    assert seen_transcript["transcript"] == [{"text": "Hello there friend this line should split", "start": 0.0, "end": 2.0}]
    assert [segment["text"] for segment in aligned] == [
        "Hello there friend",
        "this line",
        "should split",
    ]


def test_align_lyrics_processes_cjk_lines(monkeypatch):
    whisperx_pipeline = importlib.import_module("demucs_svc.whisperx_pipeline")

    monkeypatch.setattr(whisperx_pipeline, "pylrc", SimpleNamespace(parse=lambda text: []))
    monkeypatch.setattr(
        whisperx_pipeline,
        "whisperx",
        SimpleNamespace(
            load_audio=lambda path: [0.0] * 32000,
            load_align_model=lambda language_code, device: (
                {"language_code": language_code},
                {"language_code": language_code},
            ),
            align=lambda transcript, *args, **kwargs: {
                "segments": [
                    {
                        "start": 0.0,
                        "end": 1.0,
                        "text": "flattened",
                        "words": [
                            {"word": "當", "start": 0.0, "end": 0.1, "score": 0.9},
                            {"word": "夢", "start": 0.1, "end": 0.2, "score": 0.9},
                            {"word": "被", "start": 0.2, "end": 0.3, "score": 0.9},
                            {"word": "埋", "start": 0.3, "end": 0.4, "score": 0.9},
                            {"word": "在", "start": 0.4, "end": 0.5, "score": 0.9},
                            {"word": "江", "start": 0.5, "end": 0.6, "score": 0.9},
                            {"word": "南", "start": 0.6, "end": 0.7, "score": 0.9},
                            {"word": "煙", "start": 0.7, "end": 0.8, "score": 0.9},
                            {"word": "雨", "start": 0.8, "end": 0.9, "score": 0.9},
                            {"word": "中", "start": 0.9, "end": 1.0, "score": 0.9},
                        ],
                    }
                ]
            },
        ),
    )

    aligned = whisperx_pipeline.align_lyrics(
        Path("input.wav"),
        "當夢被埋在江南煙雨中",
        lyrics_format="txt",
        transcription_model="tiny",
        align_language="zh",
        detect_language=False,
        use_synced_lyrics=False,
        process_lyrics_lines=True,
        max_line_length=36,
        max_line_length_cjk=5,
        device="cpu",
        compute_type=None,
    )

    assert [segment["text"] for segment in aligned] == ["當夢被埋在", "江南煙雨中"]


def test_align_lyrics_processes_mixed_script_lines_without_cjk_over_split(monkeypatch):
    whisperx_pipeline = importlib.import_module("demucs_svc.whisperx_pipeline")

    monkeypatch.setattr(whisperx_pipeline, "pylrc", SimpleNamespace(parse=lambda text: []))
    monkeypatch.setattr(
        whisperx_pipeline,
        "whisperx",
        SimpleNamespace(
            load_audio=lambda path: [0.0] * 32000,
            load_align_model=lambda language_code, device: (
                {"language_code": language_code},
                {"language_code": language_code},
            ),
            align=lambda transcript, *args, **kwargs: {
                "segments": [
                    {
                        "start": 0.0,
                        "end": 1.0,
                        "text": "flattened",
                        "words": [
                            {"word": "hello", "start": 0.0, "end": 0.1, "score": 0.9},
                            {"word": "中文", "start": 0.1, "end": 0.2, "score": 0.9},
                            {"word": "friend", "start": 0.2, "end": 0.3, "score": 0.9},
                            {"word": "again", "start": 0.3, "end": 0.4, "score": 0.9},
                        ],
                    }
                ]
            },
        ),
    )

    aligned = whisperx_pipeline.align_lyrics(
        Path("input.wav"),
        "hello 中文 friend again",
        lyrics_format="txt",
        transcription_model="tiny",
        align_language="zh",
        detect_language=False,
        use_synced_lyrics=False,
        process_lyrics_lines=True,
        max_line_length=12,
        max_line_length_cjk=4,
        device="cpu",
        compute_type=None,
    )

    assert [segment["text"] for segment in aligned] == ["hello 中文", "friend again"]


def test_process_lyric_lines_wraps_long_english_lines():
    lyric_processor = importlib.import_module("demucs_svc.lyrics_line_processor")

    processed = lyric_processor.process_lyric_lines(
        [
            "I can get 'em both, I don't wanna choose",
            "I don't dance now, I make money moves",
            "Look, I might just chill in some BAPE",
            "Turns out, I'm rich, I'm rich, I'm rich",
            "you can't fuck with me if you wanted to\"",
        ],
        max_line_length=36,
        max_line_length_cjk=12,
    )

    assert processed[:2] == ["I can get 'em both,", "I don't wanna choose"]
    assert all(len(line) <= 36 for line in processed)
    assert len(processed) > 5


def test_align_lyrics_processing_disables_synced_lrc_mode(monkeypatch):
    whisperx_pipeline = importlib.import_module("demucs_svc.whisperx_pipeline")

    seen_transcript = {}

    def fake_align(transcript, *args, **kwargs):
        seen_transcript["transcript"] = transcript
        return {
            "segments": [
                {
                    "start": 0.0,
                    "end": 2.0,
                    "text": "flattened",
                    "words": [
                        {"word": "Hello", "start": 0.0, "end": 0.2, "score": 0.9},
                        {"word": "there", "start": 0.2, "end": 0.4, "score": 0.9},
                        {"word": "friend", "start": 0.4, "end": 0.6, "score": 0.9},
                        {"word": "Second", "start": 0.6, "end": 0.8, "score": 0.9},
                        {"word": "synced", "start": 0.8, "end": 1.0, "score": 0.9},
                        {"word": "line", "start": 1.0, "end": 1.2, "score": 0.9},
                    ],
                }
            ]
        }

    monkeypatch.setattr(
        whisperx_pipeline,
        "pylrc",
        SimpleNamespace(
            parse=lambda text: [
                SimpleNamespace(text="Hello there friend", time=1.0),
                SimpleNamespace(text="Second synced line", time=2.0),
            ]
        ),
    )
    monkeypatch.setattr(
        whisperx_pipeline,
        "whisperx",
        SimpleNamespace(
            load_audio=lambda path: [0.0] * 32000,
            load_align_model=lambda language_code, device: (
                {"language_code": language_code},
                {"language_code": language_code},
            ),
            align=fake_align,
        ),
    )

    aligned = whisperx_pipeline.align_lyrics(
        Path("input.wav"),
        "ignored",
        lyrics_format="lrc",
        transcription_model="tiny",
        align_language="en",
        detect_language=False,
        use_synced_lyrics=True,
        process_lyrics_lines=True,
        max_line_length=12,
        max_line_length_cjk=12,
        device="cpu",
        compute_type=None,
    )

    assert seen_transcript["transcript"] == [{"text": "Hello there friend Second synced line", "start": 0.0, "end": 2.0}]
    assert [segment["text"] for segment in aligned] == ["Hello", "there friend", "Second", "synced line"]


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


def test_job_creation_passes_whisperx_request_fields(monkeypatch, tmp_path):
    monkeypatch.setattr(demucs_app, "_cuda_available", lambda: True)
    monkeypatch.setattr(demucs_app, "INCOMING_ROOT", tmp_path / "incoming")
    monkeypatch.setattr(demucs_app, "OUTPUT_ROOT", tmp_path / "output")
    demucs_app.INCOMING_ROOT.mkdir(parents=True, exist_ok=True)
    demucs_app.OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    seen = {}

    def fake_start_job(payload, original_filename, config):
        seen["config"] = config
        return demucs_app.job_store.create(
            demucs_app.DemucsJobState(
                job_id="job-whisperx",
                model=config.model,
                device=config.device,
                output_format=config.output_format,
                mp3_bitrate=config.mp3_bitrate,
                original_filename=original_filename,
                status="queued",
            )
        )

    monkeypatch.setattr(demucs_app, "_start_job", fake_start_job)

    client = TestClient(demucs_app.app)
    response = client.post(
        "/jobs",
        data={
            "lyrics_text": "[00:01.00]hello world",
            "lyrics_format": "lrc",
            "transcription_model": "base",
            "align_language": "en",
            "detect_language": "true",
            "use_synced_lyrics": "true",
            "whisperx_preload_models": "transcription=base,align=en",
            "process_lyrics_lines": "true",
            "max_line_length": "40",
            "max_line_length_cjk": "14",
        },
        files={"file": ("input.wav", b"audio", "audio/wav")},
    )

    assert response.status_code == 202
    config = seen["config"]
    assert config.lyrics_text == "[00:01.00]hello world"
    assert config.lyrics_format == "lrc"
    assert config.transcription_model == "base"
    assert config.align_language == "en"
    assert config.detect_language is True
    assert config.use_synced_lyrics is True
    assert config.whisperx_preload_models == "transcription=base,align=en"
    assert config.process_lyrics_lines is True
    assert config.max_line_length == 40
    assert config.max_line_length_cjk == 14


def test_job_result_includes_aligned_lyrics_zip_entry(monkeypatch, tmp_path):
    monkeypatch.setattr(demucs_app, "_cuda_available", lambda: True)
    monkeypatch.setattr(demucs_app, "INCOMING_ROOT", tmp_path / "incoming")
    monkeypatch.setattr(demucs_app, "OUTPUT_ROOT", tmp_path / "output")
    demucs_app.INCOMING_ROOT.mkdir(parents=True, exist_ok=True)
    demucs_app.OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    def fake_align_lyrics(*args, **kwargs):
        aligned_path = tmp_path / "aligned_lyrics.json"
        aligned_path.write_text(
            json.dumps(
                [
                    {
                        "start": 1.0,
                        "end": 2.0,
                        "text": "hello world",
                        "words": [
                            {"word": "hello", "start": 1.0, "end": 1.5, "score": 0.9},
                            {"word": "world", "start": 1.5, "end": 2.0, "score": 0.8},
                        ],
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return aligned_path

    def fake_start_job(payload, original_filename, config):
        job_id = "job-aligned"
        incoming_dir = demucs_app.INCOMING_ROOT / job_id
        output_dir = demucs_app.OUTPUT_ROOT / job_id
        input_path = incoming_dir / "input.wav"
        incoming_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        input_path.write_bytes(b"audio")
        no_vocals_path = output_dir / config.model / input_path.stem / "no_vocals.wav"
        vocals_path = output_dir / config.model / input_path.stem / "vocals.wav"
        no_vocals_path.parent.mkdir(parents=True, exist_ok=True)
        no_vocals_path.write_bytes(b"no-vocals")
        vocals_path.write_bytes(b"vocals")
        aligned_path = fake_align_lyrics()
        return demucs_app.job_store.create(
            demucs_app.DemucsJobState(
                job_id=job_id,
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
                duration_ms=25,
                no_vocals_path=str(no_vocals_path),
                vocals_path=str(vocals_path),
                aligned_lyrics_path=str(aligned_path),
            )
        )

    monkeypatch.setattr(demucs_app, "_start_job", fake_start_job)

    client = TestClient(demucs_app.app)
    response = client.post(
        "/jobs",
        data={
            "lyrics_text": "[00:01.00]hello world",
            "lyrics_format": "lrc",
            "transcription_model": "base",
        },
        files={"file": ("input.wav", b"audio", "audio/wav")},
    )
    job_id = response.json()["job_id"]

    result_response = client.get(f"/jobs/{job_id}/result")
    assert result_response.status_code == 200
    with zipfile.ZipFile(BytesIO(result_response.content)) as archive:
        names = set(archive.namelist())
        assert "aligned_lyrics.json" in names
        aligned_payload = json.loads(archive.read("aligned_lyrics.json").decode("utf-8"))
        metadata = json.loads(archive.read("metadata.json").decode("utf-8"))
    assert aligned_payload[0]["text"] == "hello world"
    assert "aligned_lyrics" in metadata["files"]


def test_alignment_job_result_returns_json(monkeypatch, tmp_path):
    monkeypatch.setattr(demucs_app, "_cuda_available", lambda: True)
    monkeypatch.setattr(demucs_app, "INCOMING_ROOT", tmp_path / "incoming")
    monkeypatch.setattr(demucs_app, "OUTPUT_ROOT", tmp_path / "output")
    demucs_app.INCOMING_ROOT.mkdir(parents=True, exist_ok=True)
    demucs_app.OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    def fake_start_alignment_job(payload, original_filename, config):
        job_id = "job-align-only"
        output_dir = demucs_app.OUTPUT_ROOT / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        aligned_path = output_dir / "aligned_lyrics.json"
        aligned_path.write_text('[{"start":1.0,"end":2.0,"text":"hello"}]', encoding="utf-8")
        return demucs_app.job_store.create(
            demucs_app.DemucsJobState(
                job_id=job_id,
                model=config.model,
                device=config.device,
                output_format=config.output_format,
                mp3_bitrate=config.mp3_bitrate,
                original_filename=original_filename,
                job_kind="lyrics_alignment",
                status="completed",
                progress_percent=100,
                progress_message="Completed",
                created_at=demucs_app.utc_now(),
                started_at=demucs_app.utc_now(),
                finished_at=demucs_app.utc_now(),
                duration_ms=25,
                aligned_lyrics_path=str(aligned_path),
            )
        )

    monkeypatch.setattr(demucs_app, "_start_alignment_job", fake_start_alignment_job)

    client = TestClient(demucs_app.app)
    response = client.post(
        "/align-jobs",
        data={
            "lyrics_text": "[00:01.00]hello",
            "lyrics_format": "lrc",
            "transcription_model": "base",
        },
        files={"file": ("vocals.wav", b"vocals", "audio/wav")},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["result_url"].endswith("/align-jobs/job-align-only/result")

    result_response = client.get("/align-jobs/job-align-only/result")
    assert result_response.status_code == 200
    assert result_response.json()[0]["text"] == "hello"


def test_alignment_job_requires_lyrics_text(monkeypatch):
    monkeypatch.setattr(demucs_app, "_cuda_available", lambda: True)
    client = TestClient(demucs_app.app)

    response = client.post(
        "/align-jobs",
        data={"lyrics_format": "lrc"},
        files={"file": ("vocals.wav", b"vocals", "audio/wav")},
    )

    assert response.status_code == 422
    assert "lyrics_text is required" in str(response.json()["detail"])


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

    deadline = time.time() + 2
    status_payload = None
    while time.time() < deadline:
        status_response = client.get(f"/jobs/{job_id}")
        assert status_response.status_code == 200
        status_payload = status_response.json()
        if status_payload["status"] == "completed":
            break
        time.sleep(0.01)

    assert status_payload is not None
    assert status_payload["status"] == "completed"

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
            self.killed = False

        def poll(self):
            return None if not self.killed else 1

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            if not self.killed:
                raise demucs_app.subprocess.TimeoutExpired(["fake"], timeout or 0)
            return 1

        def kill(self):
            self.killed = True

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
    monkeypatch.setattr(demucs_app, "_run_garbage_collection", lambda **_: None)

    client = TestClient(demucs_app.app)
    created = client.post(
        "/jobs",
        files={"file": ("input.wav", b"audio", "audio/wav")},
    )
    job_id = created.json()["job_id"]
    cancel_response = client.delete(f"/jobs/{job_id}")
    assert cancel_response.status_code == 202
    assert process.terminated is True
    assert process.killed is True
    status_payload = client.get(f"/jobs/{job_id}").json()
    assert status_payload["status"] == "canceled"
    assert status_payload["progress_message"] == "Canceled"


def test_cancel_alignment_job_terminates_process_and_cleans_io(monkeypatch, tmp_path):
    monkeypatch.setattr(demucs_app, "INCOMING_ROOT", tmp_path / "incoming")
    monkeypatch.setattr(demucs_app, "OUTPUT_ROOT", tmp_path / "output")
    demucs_app.INCOMING_ROOT.mkdir(parents=True, exist_ok=True)
    demucs_app.OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(demucs_runner, "INCOMING_ROOT", tmp_path / "incoming")
    monkeypatch.setattr(demucs_runner, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(demucs_app, "_run_garbage_collection", lambda **_: None)

    class FakeProcess:
        def __init__(self):
            self.terminated = False

        def is_alive(self):
            return not self.terminated

        def terminate(self):
            self.terminated = True

        def join(self, timeout=None):
            return None

    process = FakeProcess()

    def fake_start_alignment_job(payload, original_filename, config):
        job_id, incoming_dir, output_dir, _input_path = demucs_runner.prepare_job_input(payload, original_filename)
        (incoming_dir / "input.wav").write_bytes(b"audio")
        (output_dir / "partial.tmp").write_bytes(b"partial")
        return demucs_app.job_store.create(
            demucs_app.DemucsJobState(
                job_id=job_id,
                model=config.model,
                device=config.device,
                output_format=config.output_format,
                mp3_bitrate=config.mp3_bitrate,
                original_filename=original_filename,
                status="running",
                job_kind="lyrics_alignment",
                process=process,
            )
        )

    monkeypatch.setattr(demucs_app, "_start_alignment_job", fake_start_alignment_job)

    client = TestClient(demucs_app.app)
    created = client.post(
        "/align-jobs",
        data={"lyrics_text": "hello", "device": "cpu"},
        files={"file": ("vocals.wav", b"audio", "audio/wav")},
    )
    job_id = created.json()["job_id"]

    response = client.delete(f"/jobs/{job_id}")

    assert response.status_code == 202
    assert response.json()["status"] == "canceled"
    assert process.terminated is True
    assert not (demucs_app.INCOMING_ROOT / job_id).exists()
    assert not (demucs_app.OUTPUT_ROOT / job_id).exists()


def test_delete_job_artifacts_removes_terminal_job_and_io(monkeypatch, tmp_path):
    monkeypatch.setattr(demucs_app, "INCOMING_ROOT", tmp_path / "incoming")
    monkeypatch.setattr(demucs_app, "OUTPUT_ROOT", tmp_path / "output")
    job_id = "job-delete"
    incoming_dir = demucs_app.INCOMING_ROOT / job_id
    output_dir = demucs_app.OUTPUT_ROOT / job_id
    incoming_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    (incoming_dir / "input.wav").write_bytes(b"audio")
    (output_dir / "stem.wav").write_bytes(b"stem")
    demucs_app.job_store.create(
        demucs_app.DemucsJobState(
            job_id=job_id,
            model="htdemucs",
            device="cpu",
            output_format="wav",
            mp3_bitrate=None,
            original_filename="input.wav",
            status="completed",
            finished_at=demucs_app.utc_now(),
        )
    )

    client = TestClient(demucs_app.app)
    response = client.delete(f"/jobs/{job_id}/artifacts")

    assert response.status_code == 200
    assert response.json()["detail"] == "Deleted Demucs job input/output artifacts"
    assert demucs_app.job_store.get(job_id) is None
    assert incoming_dir.exists() is False
    assert output_dir.exists() is False


def test_delete_job_artifacts_rejects_active_job(tmp_path, monkeypatch):
    monkeypatch.setattr(demucs_app, "INCOMING_ROOT", tmp_path / "incoming")
    monkeypatch.setattr(demucs_app, "OUTPUT_ROOT", tmp_path / "output")
    job_id = "job-active"
    demucs_app.job_store.create(
        demucs_app.DemucsJobState(
            job_id=job_id,
            model="htdemucs",
            device="cpu",
            output_format="wav",
            mp3_bitrate=None,
            original_filename="input.wav",
            status="running",
        )
    )

    client = TestClient(demucs_app.app)
    response = client.delete(f"/jobs/{job_id}/artifacts")

    assert response.status_code == 409
    assert "still active" in response.json()["detail"]
    assert demucs_app.job_store.get(job_id) is not None


def test_job_events_stream_emits_updates_and_closes_on_terminal_state(monkeypatch, tmp_path):
    _clear_job_store()
    monkeypatch.setattr(demucs_app, "INCOMING_ROOT", tmp_path / "incoming")
    monkeypatch.setattr(demucs_app, "OUTPUT_ROOT", tmp_path / "output")
    job_id = "job-stream"
    demucs_app.job_store.create(
        demucs_app.DemucsJobState(
            job_id=job_id,
            model="htdemucs",
            device="cpu",
            output_format="wav",
            mp3_bitrate=None,
            original_filename="input.wav",
            status="queued",
        )
    )

    class FakeRequest:
        headers = {}

        async def is_disconnected(self):
            return False

    async def collect_events():
        agen = demucs_app._stream_job_events(FakeRequest(), job_id)
        try:
            first = await anext(agen)

            def updater():
                time.sleep(0.05)
                demucs_app.job_store.update(
                    job_id,
                    status="running",
                    progress_percent=42,
                    progress_message="Running Demucs",
                )
                demucs_app.job_store.update(
                    job_id,
                    status="completed",
                    progress_percent=100,
                    progress_message="Completed",
                    finished_at=demucs_app.utc_now(),
                )

            thread = threading.Thread(target=updater, daemon=True)
            thread.start()
            second = await anext(agen)
            try:
                await anext(agen)
                raise AssertionError("Expected the stream to close after the terminal event")
            except StopAsyncIteration:
                pass
            thread.join(timeout=1)
            return first, second
        finally:
            await agen.aclose()

    first, second = asyncio.run(collect_events())
    assert "event: job" in first
    assert '"status":"queued"' in first
    assert '"sequence":1' in first
    assert "event: job" in second
    assert '"status":"completed"' in second
    assert '"progress_percent":100' in second


def test_job_events_stream_returns_404_for_unknown_job():
    with TestClient(demucs_app.app) as client:
        response = client.get("/jobs/missing-job/events")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_get_io_usage_reports_current_folder_size_and_counts(monkeypatch, tmp_path):
    _clear_job_store()
    monkeypatch.setattr(demucs_app, "INCOMING_ROOT", tmp_path / "incoming")
    monkeypatch.setattr(demucs_app, "OUTPUT_ROOT", tmp_path / "output")
    incoming_dir = demucs_app.INCOMING_ROOT / "job-one"
    output_dir = demucs_app.OUTPUT_ROOT / "job-one"
    incoming_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    (incoming_dir / "input.wav").write_bytes(b"abcd")
    (output_dir / "stem.wav").write_bytes(b"abcdef")
    demucs_app.job_store.create(
        demucs_app.DemucsJobState(
            job_id="job-one",
            model="htdemucs",
            device="cpu",
            output_format="wav",
            mp3_bitrate=None,
            original_filename="input.wav",
            status="completed",
            finished_at=demucs_app.utc_now(),
        )
    )

    client = TestClient(demucs_app.app)
    response = client.get("/io")

    assert response.status_code == 200
    data = response.json()
    assert data["incoming_bytes"] == 4
    assert data["output_bytes"] == 6
    assert data["total_bytes"] == 10
    assert data["incoming_files"] == 1
    assert data["output_files"] == 1
    assert data["terminal_job_count"] == 1
    assert data["active_job_count"] == 0
    assert data["running_job_count"] == 0
    assert data["detail"] == "Current Demucs IO footprint"


def test_transfer_page_renders_upload_download_and_cli_instructions():
    with patch("demucs_svc.app.preload_models", return_value=[]), patch(
        "demucs_svc.app.subprocess.run",
        return_value=SimpleNamespace(returncode=0),
    ):
        with TestClient(demucs_app.app) as client:
            response = client.get("/transfer")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    assert "/transfer/upload" in body
    assert "/transfer/upload/raw" in body
    assert "/transfer/download/random-25mb" in body
    assert "transfer-commands-block" in body
    assert "buildCliCommands(" in body
    assert "updateCliCommands()" in body
    assert "$DEMUCS_API_KEY" not in body


def test_transfer_upload_multipart_discards_bytes_and_reports_count():
    with patch("demucs_svc.app.preload_models", return_value=[]), patch(
        "demucs_svc.app.subprocess.run",
        return_value=SimpleNamespace(returncode=0),
    ):
        with TestClient(demucs_app.app) as client:
            response = client.post(
                "/transfer/upload",
                files={"file": ("sample.bin", b"abcdef", "application/octet-stream")},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["transfer_mode"] == "multipart"
    assert data["received_bytes"] == 6
    assert data["received_filename"] == "sample.bin"
    assert data["detail"] == "Multipart upload received and discarded"


def test_transfer_upload_raw_discards_bytes_and_reports_count():
    with patch("demucs_svc.app.preload_models", return_value=[]), patch(
        "demucs_svc.app.subprocess.run",
        return_value=SimpleNamespace(returncode=0),
    ):
        with TestClient(demucs_app.app) as client:
            response = client.request(
                "POST",
                "/transfer/upload/raw",
                content=b"raw-transfer-bytes",
                headers={"content-type": "application/octet-stream"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["transfer_mode"] == "raw"
    assert data["received_bytes"] == len(b"raw-transfer-bytes")
    assert data["received_filename"] is None
    assert data["detail"] == "Raw upload received and discarded"


def test_transfer_download_creates_and_reuses_cached_file(monkeypatch, tmp_path):
    monkeypatch.setattr(demucs_app, "TRANSFER_CACHE_ROOT", tmp_path / "transfer-cache")
    monkeypatch.setattr(demucs_app, "TRANSFER_RANDOM_FILE_SIZE_BYTES", 1024)

    create_calls: list[Path] = []
    original_generate = demucs_app._generate_random_transfer_file

    def spy_generate(path):
        create_calls.append(path)
        original_generate(path)

    monkeypatch.setattr(demucs_app, "_generate_random_transfer_file", spy_generate)

    with patch("demucs_svc.app.preload_models", return_value=[]), patch(
        "demucs_svc.app.subprocess.run",
        return_value=SimpleNamespace(returncode=0),
    ):
        with TestClient(demucs_app.app) as client:
            first = client.get("/transfer/download/random-25mb")
            second = client.get("/transfer/download/random-25mb")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.headers["content-type"].startswith("application/octet-stream")
    assert first.headers["content-length"] == "1024"
    assert first.headers["content-disposition"].startswith("attachment;")
    assert "random-25mb.bin" in first.headers["content-disposition"]
    assert len(first.content) == 1024
    assert first.content == second.content
    assert len(create_calls) == 1
    assert create_calls[0] == tmp_path / "transfer-cache" / "random-25mb.bin"


def test_api_key_protected_routes_require_header_when_configured():
    original_api_key = demucs_settings.settings.api_key
    demucs_settings.settings.api_key = "shared-secret"
    try:
        with patch("demucs_svc.app.preload_models", return_value=[]), patch(
            "demucs_svc.app.subprocess.run",
            return_value=SimpleNamespace(returncode=0),
        ):
            with TestClient(demucs_app.app) as client:
                unauthorized = client.get("/metrics")
                transfer_page = client.get("/transfer")
                authorized = client.get(
                    "/metrics",
                    headers={"X-API-Key": "shared-secret"},
                )

        assert unauthorized.status_code == 401
        assert unauthorized.json()["detail"] == "Missing or invalid API key"
        assert transfer_page.status_code == 200
        assert authorized.status_code == 200
    finally:
        demucs_settings.settings.api_key = original_api_key


def test_transfer_upload_requires_api_key_when_configured():
    original_api_key = demucs_settings.settings.api_key
    demucs_settings.settings.api_key = "shared-secret"
    try:
        with patch("demucs_svc.app.preload_models", return_value=[]), patch(
            "demucs_svc.app.subprocess.run",
            return_value=SimpleNamespace(returncode=0),
        ):
            with TestClient(demucs_app.app) as client:
                unauthorized = client.post(
                    "/transfer/upload",
                    files={"file": ("sample.bin", b"abcdef", "application/octet-stream")},
                )
                authorized = client.post(
                    "/transfer/upload",
                    headers={"X-API-Key": "shared-secret"},
                    files={"file": ("sample.bin", b"abcdef", "application/octet-stream")},
                )

        assert unauthorized.status_code == 401
        assert authorized.status_code == 200
        assert authorized.json()["received_bytes"] == 6
    finally:
        demucs_settings.settings.api_key = original_api_key


def test_cleanup_io_deletes_terminal_jobs_and_files(monkeypatch, tmp_path):
    _clear_job_store()
    monkeypatch.setattr(demucs_app, "INCOMING_ROOT", tmp_path / "incoming")
    monkeypatch.setattr(demucs_app, "OUTPUT_ROOT", tmp_path / "output")
    job_id = "job-cleanup"
    incoming_dir = demucs_app.INCOMING_ROOT / job_id
    output_dir = demucs_app.OUTPUT_ROOT / job_id
    incoming_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    (incoming_dir / "input.wav").write_bytes(b"abcd")
    (output_dir / "stem.wav").write_bytes(b"abcdef")
    demucs_app.job_store.create(
        demucs_app.DemucsJobState(
            job_id=job_id,
            model="htdemucs",
            device="cpu",
            output_format="wav",
            mp3_bitrate=None,
            original_filename="input.wav",
            status="completed",
            finished_at=demucs_app.utc_now(),
        )
    )

    client = TestClient(demucs_app.app)
    response = client.delete("/io")

    assert response.status_code == 200
    data = response.json()
    assert data["deleted_bytes"] == 10
    assert data["deleted_files"] == 2
    assert data["deleted_job_count"] == 1
    assert data["active_job_count"] == 0
    assert data["running_job_count"] == 0
    assert demucs_app.job_store.get(job_id) is None
    assert incoming_dir.exists() is False
    assert output_dir.exists() is False
    assert demucs_app.INCOMING_ROOT.exists()
    assert demucs_app.OUTPUT_ROOT.exists()


def test_cleanup_io_rejects_when_jobs_are_active(monkeypatch, tmp_path):
    _clear_job_store()
    monkeypatch.setattr(demucs_app, "INCOMING_ROOT", tmp_path / "incoming")
    monkeypatch.setattr(demucs_app, "OUTPUT_ROOT", tmp_path / "output")
    job_id = "job-active-cleanup"
    incoming_dir = demucs_app.INCOMING_ROOT / job_id
    output_dir = demucs_app.OUTPUT_ROOT / job_id
    incoming_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    (incoming_dir / "input.wav").write_bytes(b"abcd")
    (output_dir / "stem.wav").write_bytes(b"abcdef")
    demucs_app.job_store.create(
        demucs_app.DemucsJobState(
            job_id=job_id,
            model="htdemucs",
            device="cpu",
            output_format="wav",
            mp3_bitrate=None,
            original_filename="input.wav",
            status="running",
        )
    )

    client = TestClient(demucs_app.app)
    response = client.delete("/io")

    assert response.status_code == 409
    assert "still running" in response.json()["detail"]
    assert demucs_app.job_store.get(job_id) is not None
    assert incoming_dir.exists()
    assert output_dir.exists()


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
