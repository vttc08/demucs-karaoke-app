from .common import *

from services.media_trim_service import (
    MediaTrimConflictError,
    MediaTrimService,
    MediaTrimUnsupportedError,
)


class FakeFFmpeg:
    def __init__(self):
        self.trim_calls = []

    def probe_media(self, path):
        return {
            "duration": 15.0 if ".trim-" in path.name else 30.0,
            "start_time": 0.0,
            "has_video": path.suffix == ".mp4",
            "has_audio": True,
            "frame_rate": 25.0,
        }

    def get_video_keyframes(self, _path):
        return [0.0, 5.0, 10.0, 20.0, 30.0]

    def lossless_trim(self, source, output, start, end):
        self.trim_calls.append((source, output, start, end))
        output.write_bytes(b"trimmed:" + source.read_bytes())


def test_resolve_video_bounds_snaps_outward_to_keyframes():
    assert MediaTrimService._resolve_bounds(
        6.0,
        18.0,
        30.0,
        [0.0, 5.0, 10.0, 20.0],
        has_video=True,
    ) == (5.0, 20.0)


def test_get_trim_info_includes_frame_rate(db_session, tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)

    media_file = media_root / "song.mp4"
    media_file.write_bytes(b"video")
    media = MediaItem(
        title="Song",
        artist="Artist",
        media_path="/media/song.mp4",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    db_session.refresh(media)

    result = MediaTrimService(ffmpeg=FakeFFmpeg()).get_trim_info(db_session, media.id)

    assert result["frame_rate"] == 25.0
    assert result["lyrics_kind"] is None


def test_get_trim_info_infers_cdg_sidecar_without_db_lyrics_path(
    db_session, tmp_path, monkeypatch
):
    media_root = tmp_path / "media"
    media_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)

    media_file = media_root / "song.mp3"
    cdg_file = media_root / "song.cdg"
    media_file.write_bytes(b"audio")
    cdg_file.write_bytes(b"cdg")
    media = MediaItem(
        title="Song",
        artist="Artist",
        media_path="/media/song.mp3",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    db_session.refresh(media)

    result = MediaTrimService(ffmpeg=FakeFFmpeg()).get_trim_info(db_session, media.id)

    assert result["lyrics_path"] == "/media/song.cdg"
    assert result["lyrics_kind"] == "cdg"
    assert result["lyrics_format"] == "cdg"


def test_shift_timed_lyrics_formats():
    lrc = MediaTrimService._shift_lrc(
        "[ar:Artist]\n[00:03.00]Before\n[00:08.00]Keep\n[00:22.00]After\n",
        5.0,
        20.0,
    )
    assert "[ar:Artist]" in lrc
    assert "[00:03.00]Keep" in lrc
    assert "Before" not in lrc
    assert "After" not in lrc

    srt_payload = (
        "1\n00:00:04,000 --> 00:00:07,000\nOpening\n\n"
        "2\n00:00:18,000 --> 00:00:22,000\nClosing\n\n"
    )
    shifted_srt = MediaTrimService._shift_srt(srt_payload, 5.0, 20.0)
    assert "00:00:00,000 --> 00:00:02,000" in shifted_srt
    assert "00:00:13,000 --> 00:00:15,000" in shifted_srt

    shifted_json = json.loads(
        MediaTrimService._shift_json(
            json.dumps(
                {
                    "segments": [
                        {
                            "start": 6.0,
                            "end": 9.0,
                            "text": "Hello world",
                            "words": [
                                {"start": 6.0, "end": 7.0, "word": "Hello"},
                                {"start": 8.0, "end": 9.0, "word": "world"},
                            ],
                        }
                    ]
                }
            ),
            5.0,
            20.0,
        )
    )
    assert shifted_json["segments"][0]["start"] == 1.0
    assert shifted_json["segments"][0]["end"] == 4.0
    assert shifted_json["segments"][0]["text"] == "Hello world"


def test_trim_media_item_replaces_media_vocals_and_lyrics_together(
    db_session, tmp_path, monkeypatch
):
    media_root = tmp_path / "media"
    media_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", tmp_path / "cache")

    media_file = media_root / "song.mp4"
    vocals_file = media_root / "song.vocals.wav"
    lyrics_file = media_root / "song.lrc"
    media_file.write_bytes(b"video")
    vocals_file.write_bytes(b"vocals")
    lyrics_file.write_text(
        "[ar:Artist]\n[00:03.00]Intro\n[00:08.00]Verse\n[00:24.00]Outro\n",
        encoding="utf-8",
    )
    media = MediaItem(
        title="Song",
        artist="Artist",
        media_path="/media/song.mp4",
        vocals_path="/media/song.vocals.wav",
        lyrics_path="/media/song.lrc",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    db_session.refresh(media)
    previous_updated_at = media.updated_at

    fake_ffmpeg = FakeFFmpeg()
    service = MediaTrimService(ffmpeg=fake_ffmpeg)
    monkeypatch.setattr(
        service.thumbnail_service, "remove_thumbnail_for_media_file", lambda _path: None
    )
    monkeypatch.setattr(
        service.thumbnail_service, "ensure_thumbnail_for_media_file", lambda _path: None
    )

    result = service.trim_media_item(db_session, media.id, 5.0, 20.0)

    assert result["resolved_start"] == 5.0
    assert result["resolved_end"] == 20.0
    assert result["trimmed_sidecars"] == ["vocals", "lyrics"]
    assert media_file.read_bytes() == b"trimmed:video"
    assert vocals_file.read_bytes() == b"trimmed:vocals"
    shifted_lyrics = lyrics_file.read_text(encoding="utf-8")
    assert "[00:03.00]Verse" in shifted_lyrics
    assert "Intro" not in shifted_lyrics
    assert "Outro" not in shifted_lyrics
    assert len(fake_ffmpeg.trim_calls) == 2
    db_session.refresh(media)
    assert media.updated_at >= previous_updated_at
    assert not list(media_root.glob(".*.trim-*"))


def test_trim_media_item_rejects_cdg_sidecars(
    db_session, tmp_path, monkeypatch
):
    media_root = tmp_path / "media"
    media_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", tmp_path / "cache")

    media_file = media_root / "song.mp3"
    cdg_file = media_root / "song.cdg"
    media_file.write_bytes(b"audio")
    cdg_file.write_bytes(b"cdg-bytes")
    media = MediaItem(
        title="Song",
        artist="Artist",
        media_path="/media/song.mp3",
        lyrics_path="/media/song.cdg",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    db_session.refresh(media)

    fake_ffmpeg = FakeFFmpeg()
    service = MediaTrimService(ffmpeg=fake_ffmpeg)
    monkeypatch.setattr(
        service.thumbnail_service, "remove_thumbnail_for_media_file", lambda _path: None
    )
    monkeypatch.setattr(
        service.thumbnail_service, "ensure_thumbnail_for_media_file", lambda _path: None
    )

    with pytest.raises(MediaTrimUnsupportedError, match="CDG lyrics sidecars"):
        service.trim_media_item(db_session, media.id, 5.0, 20.0)


def test_trim_rejects_media_that_is_currently_playing(
    db_session, tmp_path, monkeypatch
):
    media_root = tmp_path / "media"
    media_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    (media_root / "playing.mp4").write_bytes(b"video")
    media = MediaItem(
        title="Playing",
        media_path="/media/playing.mp4",
        missing=False,
    )
    db_session.add(media)
    db_session.flush()
    db_session.add(
        QueueItem(
            media_id=media.id,
            position=1,
            status=QueueStatus.PLAYING.value,
        )
    )
    db_session.commit()

    with pytest.raises(MediaTrimConflictError, match="currently playing"):
        MediaTrimService(ffmpeg=FakeFFmpeg()).trim_media_item(
            db_session, media.id, 0.0, 10.0
        )
