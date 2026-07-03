from .common import *

from services.cdg_transcode_service import CdgTranscodeService


class FakeFFmpeg:
    def __init__(self):
        self.calls = []

    def transcode_cdg_to_mp4(self, cdg_path, audio_path, output_path, **kwargs):
        self.calls.append((cdg_path, audio_path, output_path, kwargs))
        output_path.write_bytes(b"mp4-bytes")

    def probe_media(self, path):
        return {
            "duration": 12.0,
            "start_time": 0.0,
            "has_video": True,
            "has_audio": True,
            "frame_rate": 30.0,
        }


def build_media_item(db_session, *, media_root, stem="song", suffix=".mp3"):
    media_file = media_root / f"{stem}{suffix}"
    lyrics_file = media_root / f"{stem}.cdg"
    media_file.write_bytes(b"audio-bytes")
    lyrics_file.write_bytes(b"cdg-bytes")
    item = MediaItem(
        title="Song",
        artist="Artist",
        media_path=f"/media/{media_file.name}",
        lyrics_path=f"/media/{lyrics_file.name}",
        file_stem=stem,
        missing=False,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item, media_file, lyrics_file


def test_cdg_transcode_creates_new_media_row(db_session, tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    media_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)

    media_item, media_file, lyrics_file = build_media_item(db_session, media_root=media_root)
    fake_ffmpeg = FakeFFmpeg()
    service = CdgTranscodeService(ffmpeg=fake_ffmpeg)
    monkeypatch.setattr(
        service.thumbnail_service, "ensure_thumbnail_for_media_file", lambda _path: None
    )

    result = service.transcode_media_item(db_session, media_item.id)

    assert result["overwrite_original"] is False
    assert result["output_media_path"] == "/media/song - CDG.mp4"
    assert media_file.exists()
    assert lyrics_file.exists()
    output_file = media_root / "song - CDG.mp4"
    assert output_file.read_bytes() == b"mp4-bytes"
    assert len(fake_ffmpeg.calls) == 1
    assert db_session.query(MediaItem).count() == 2
    created = db_session.query(MediaItem).filter(MediaItem.id != media_item.id).one()
    assert created.media_path == "/media/song - CDG.mp4"
    assert created.lyrics_path is None


def test_cdg_transcode_can_overwrite_original_item(db_session, tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    media_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)

    media_item, media_file, lyrics_file = build_media_item(db_session, media_root=media_root)
    fake_ffmpeg = FakeFFmpeg()
    service = CdgTranscodeService(ffmpeg=fake_ffmpeg)
    monkeypatch.setattr(
        service.thumbnail_service, "ensure_thumbnail_for_media_file", lambda _path: None
    )
    monkeypatch.setattr(
        service.thumbnail_service, "remove_thumbnail_for_media_file", lambda _path: None
    )
    monkeypatch.setattr(
        service.thumbnail_service,
        "remove_thumbnail_sidecars_for_media_file",
        lambda _path: None,
    )

    result = service.transcode_media_item(
        db_session,
        media_item.id,
        overwrite_original=True,
    )

    assert result["overwrite_original"] is True
    db_session.refresh(media_item)
    assert media_item.media_path == "/media/song.mp4"
    assert media_item.lyrics_path is None
    assert not media_file.exists()
    assert not lyrics_file.exists()
    assert (media_root / "song.mp4").exists()
