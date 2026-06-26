from .common import *

import json
from io import BytesIO
from starlette.datastructures import UploadFile

from services.subtitle_workflow_service import SubtitleWorkflowService


def _make_json_payload():
    return {
        "segments": [
            {
                "start": 0.0,
                "end": 2.0,
                "text": "Hello world",
                "words": [
                    {"word": "Hello", "start": 0.0, "end": 1.0},
                    {"word": "world", "start": 1.0, "end": 2.0},
                ],
            },
            {
                "start": 1.5,
                "end": 4.0,
                "text": "Again",
                "words": [
                    {"word": "Again", "start": 1.5, "end": 4.0},
                ],
            },
        ]
    }


def test_export_ass_and_srt_from_json_normalizes_overlap(db_session, tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)

    media_file = media_root / "song.mp4"
    lyrics_file = media_root / "song.json"
    media_file.write_bytes(b"video")
    lyrics_file.write_text(json.dumps(_make_json_payload()), encoding="utf-8")

    media = MediaItem(
        title="Song",
        artist="Artist",
        media_path="/media/song.mp4",
        lyrics_path="/media/song.json",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    db_session.refresh(media)

    service = SubtitleWorkflowService()

    ass_content, ass_filename, ass_preview = service.build_export_text(db_session, media.id, "ass")
    srt_content, srt_filename, srt_preview = service.build_export_text(db_session, media.id, "srt")

    assert ass_filename.endswith(".ass")
    assert srt_filename.endswith(".srt")
    assert ass_preview["warning_count"] == 1
    assert srt_preview["warning_count"] == 1
    assert "{\\k100}Hello" in ass_content
    assert "{\\k50}world" in ass_content
    assert "//wx:0//Hello" in srt_content
    assert "//wx:10//Again" in srt_content


def test_preview_and_replace_uploaded_srt_back_to_json(db_session, tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)

    media_file = media_root / "song.mp4"
    lyrics_file = media_root / "song.json"
    media_file.write_bytes(b"video")
    lyrics_file.write_text(json.dumps(_make_json_payload()), encoding="utf-8")

    media = MediaItem(
        title="Song",
        artist="Artist",
        media_path="/media/song.mp4",
        lyrics_path="/media/song.json",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    db_session.refresh(media)

    srt_text = (
        "1\n00:00:00,000 --> 00:00:01,000\n//wx:0//Hello\n\n"
        "2\n00:00:01,000 --> 00:00:02,000\nworld\n\n"
        "3\n00:00:03,000 --> 00:00:04,000\n//wx:10//Again\n\n"
    )

    service = SubtitleWorkflowService()
    preview = service.preview_upload(
        db_session,
        media.id,
        UploadFile(file=BytesIO(srt_text.encode("utf-8")), filename="edited.srt"),
    )
    result = service.replace_from_upload(
        db_session,
        media.id,
        UploadFile(file=BytesIO(srt_text.encode("utf-8")), filename="edited.srt"),
    )

    assert preview["preview"]["warning_count"] == 0
    assert result["source_format"] == "srt"
    assert result["lyrics_path"] == "/media/song.json"
    saved_payload = json.loads(lyrics_file.read_text(encoding="utf-8"))
    assert saved_payload["segments"][0]["text"] == "Hello world"
    assert saved_payload["segments"][1]["text"] == "Again"


def test_replace_uploaded_raw_lyrics_overwrites_file_without_processing(db_session, tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)

    media_file = media_root / "song.mp4"
    original_lyrics_file = media_root / "song.json"
    media_file.write_bytes(b"video")
    original_lyrics_file.write_text(json.dumps(_make_json_payload()), encoding="utf-8")

    media = MediaItem(
        title="Song",
        artist="Artist",
        media_path="/media/song.mp4",
        lyrics_path="/media/song.json",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    db_session.refresh(media)

    raw_text = "Line one\nLine two\n"

    result = SubtitleWorkflowService().replace_raw_upload(
        db_session,
        media.id,
        UploadFile(file=BytesIO(raw_text.encode("utf-8")), filename="edited.lrc"),
    )

    assert result["replacement_kind"] == "raw"
    assert result["source_format"] == "lrc"
    assert result["lyrics_path"] == "/media/song.lrc"
    assert (media_root / "song.lrc").read_text(encoding="utf-8") == raw_text
    assert not original_lyrics_file.exists()


def test_preview_reports_overlap_warnings_for_ass(db_session, tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)

    media_file = media_root / "song.mp4"
    lyrics_file = media_root / "song.json"
    media_file.write_bytes(b"video")
    lyrics_file.write_text(json.dumps(_make_json_payload()), encoding="utf-8")

    media = MediaItem(
        title="Song",
        artist="Artist",
        media_path="/media/song.mp4",
        lyrics_path="/media/song.json",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    db_session.refresh(media)

    ass_text = (
        "[Script Info]\nTitle: Song\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
        "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,{\\k100}Hello {\\k100}world\n"
        "Dialogue: 0,0:00:01.50,0:00:03.00,Default,,0,0,0,,{\\k150}Again\n"
    )

    preview = SubtitleWorkflowService().preview_upload(
        db_session,
        media.id,
        UploadFile(file=BytesIO(ass_text.encode("utf-8")), filename="edited.ass"),
    )

    assert preview["preview"]["warning_count"] == 1
    assert preview["preview"]["warnings"][0]["type"] == "overlap"
