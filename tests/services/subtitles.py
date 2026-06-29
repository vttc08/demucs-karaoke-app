from .common import *

import json
from io import BytesIO
from starlette.datastructures import UploadFile

from services.subtitle_workflow_service import SubtitleWorkflowService
from services.subtitle_editor_service import subtitle_editor_service


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


def test_subtitle_editor_service_split_and_merge_segments():
    segments = [
        {
            "start": 0.0,
            "end": 1.0,
            "text": "Hello world again",
            "words": [
                {"word": "Hello", "start": 0.0, "end": 0.3},
                {"word": "world", "start": 0.3, "end": 0.6},
                {"word": "again", "start": 0.6, "end": 1.0},
            ],
        },
        {
            "start": 1.0,
            "end": 2.0,
            "text": "Next line",
            "words": [
                {"word": "Next", "start": 1.0, "end": 1.5},
                {"word": "line", "start": 1.5, "end": 2.0},
            ],
        },
    ]

    split_segments = subtitle_editor_service.split_segment(segments, 0, 2)
    merged_segments = subtitle_editor_service.merge_segment(split_segments, 0)

    assert [segment["text"] for segment in split_segments] == [
        "Hello world",
        "again",
        "Next line",
    ]
    assert [segment["text"] for segment in merged_segments] == [
        "Hello world again",
        "Next line",
    ]


def test_subtitle_editor_service_process_segments_wraps_english_cjk_and_mixed_lines():
    segments = [
        {
            "start": 0.0,
            "end": 1.0,
            "text": "I can get em both I dont wanna choose",
            "words": [
                {"word": "I", "start": 0.0, "end": 0.1},
                {"word": "can", "start": 0.1, "end": 0.2},
                {"word": "get", "start": 0.2, "end": 0.3},
                {"word": "em", "start": 0.3, "end": 0.4},
                {"word": "both", "start": 0.4, "end": 0.5},
                {"word": "I", "start": 0.5, "end": 0.6},
                {"word": "dont", "start": 0.6, "end": 0.7},
                {"word": "wanna", "start": 0.7, "end": 0.8},
                {"word": "choose", "start": 0.8, "end": 0.9},
            ],
        },
        {
            "start": 1.0,
            "end": 2.0,
            "text": "hello 世界 friend again",
            "words": [
                {"word": "hello", "start": 1.0, "end": 1.1},
                {"word": "世界", "start": 1.1, "end": 1.2},
                {"word": "friend", "start": 1.2, "end": 1.3},
                {"word": "again", "start": 1.3, "end": 1.4},
            ],
        },
        {
            "start": 2.0,
            "end": 3.0,
            "text": "你好世界再见",
            "words": [
                {"word": "你", "start": 2.0, "end": 2.1},
                {"word": "好", "start": 2.1, "end": 2.2},
                {"word": "世", "start": 2.2, "end": 2.3},
                {"word": "界", "start": 2.3, "end": 2.4},
                {"word": "再", "start": 2.4, "end": 2.5},
                {"word": "见", "start": 2.5, "end": 2.6},
            ],
        },
    ]

    processed = subtitle_editor_service.process_segments(
        segments,
        max_line_length=12,
        max_line_length_cjk=4,
    )

    assert [segment["text"] for segment in processed[:4]] == [
        "I can get em",
        "both I",
        "dont",
        "wanna choose",
    ]
    assert [segment["text"] for segment in processed[4:6]] == [
        "hello 世界",
        "friend again",
    ]
    assert [segment["text"] for segment in processed[6:]] == [
        "你好世界",
        "再见",
    ]
    assert all(len(segment["text"]) <= 12 or any("\u4e00" <= char <= "\u9fff" for char in segment["text"]) for segment in processed)


def test_subtitle_editor_service_process_saved_segments_rewraps_disk_state(db_session, tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)

    media_file = media_root / "song.mp4"
    lyrics_file = media_root / "song.json"
    media_file.write_bytes(b"video")
    lyrics_file.write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "start": 0.0,
                        "end": 1.0,
                        "text": "I can get em both I dont wanna choose",
                        "words": [
                            {"word": "I", "start": 0.0, "end": 0.1},
                            {"word": "can", "start": 0.1, "end": 0.2},
                            {"word": "get", "start": 0.2, "end": 0.3},
                            {"word": "em", "start": 0.3, "end": 0.4},
                            {"word": "both", "start": 0.4, "end": 0.5},
                            {"word": "I", "start": 0.5, "end": 0.6},
                            {"word": "dont", "start": 0.6, "end": 0.7},
                            {"word": "wanna", "start": 0.7, "end": 0.8},
                            {"word": "choose", "start": 0.8, "end": 0.9},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

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

    processed = subtitle_editor_service.process_saved_segments(
        db_session,
        media.id,
        max_line_length=12,
        max_line_length_cjk=4,
    )

    assert [segment["text"] for segment in processed] == [
        "I can get em",
        "both I",
        "dont",
        "wanna choose",
    ]
