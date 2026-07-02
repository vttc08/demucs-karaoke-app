from .common import *



def test_media_library_sync_service_reconciles_rows_and_sidecars(db_session, tmp_path):
    """Library scan should mark missing rows, create new rows, and refresh sidecars."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        existing_file = settings.media_path / "existing.mp4"
        existing_vocals = settings.media_path / "existing.vocals.mp3"
        existing_lyrics = settings.media_path / "existing.lrc"
        existing_file.write_text("video", encoding="utf-8")
        existing_vocals.write_text("vocals", encoding="utf-8")
        existing_lyrics.write_text("[00:01.00]lyrics", encoding="utf-8")

        new_nested_file = settings.media_path / "nested" / "new-track.mp4"
        new_nested_file.parent.mkdir(parents=True, exist_ok=True)
        new_nested_file.write_text("video", encoding="utf-8")

        db_session.add_all(
            [
                MediaItem(
                    title="Missing Row",
                    media_path="/media/missing.mp4",
                    missing=False,
                ),
                MediaItem(
                    title="Existing Row",
                    media_path="/media/existing.mp4",
                    vocals_path=None,
                    lyrics_path="/media/old-value.lrc",
                    missing=True,
                ),
            ]
        )
        db_session.commit()

        service = MediaLibrarySyncService()
        summary = service.scan_library(db_session)

        assert summary["scanned_files"] == 2
        assert summary["created"] == 1
        assert summary["marked_missing"] == 1
        assert summary["restored"] == 1

        missing_row = db_session.query(MediaItem).filter(MediaItem.media_path == "/media/missing.mp4").first()
        assert missing_row is not None
        assert missing_row.missing is True
        assert missing_row.last_scanned_at is not None

        existing_row = db_session.query(MediaItem).filter(MediaItem.media_path == "/media/existing.mp4").first()
        assert existing_row is not None
        assert existing_row.missing is False
        assert existing_row.vocals_path == "/media/existing.vocals.mp3"
        assert existing_row.lyrics_path == "/media/existing.lrc"

        new_row = db_session.query(MediaItem).filter(MediaItem.media_path == "/media/nested/new-track.mp4").first()
        assert new_row is not None
        assert new_row.title == "new-track"
        assert new_row.artist is None
        assert new_row.file_stem == "new-track"
        assert new_row.missing is False
    finally:
        settings.media_path = original_media

def test_media_library_sync_service_scans_one_item_sidecars(db_session, tmp_path, monkeypatch):
    """Single-item scans should refresh vocals and lyrics sidecar paths."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "single-item.mp4"
        vocals_file = settings.media_path / "single-item.vocals.wav"
        lyrics_file = settings.media_path / "single-item.lrc"
        media_file.write_text("video", encoding="utf-8")
        vocals_file.write_text("vocals", encoding="utf-8")
        lyrics_file.write_text("[00:01.00]lyrics", encoding="utf-8")

        media = MediaItem(
            title="Single Item",
            media_path="/media/single-item.mp4",
            missing=True,
        )
        db_session.add(media)
        db_session.commit()

        service = MediaLibrarySyncService()
        monkeypatch.setattr(
            service.thumbnail_service,
            "ensure_thumbnail_for_media_file",
            lambda path: False,
        )

        summary = service.scan_media_item(db_session, media.id)

        assert summary["scanned_files"] == 1
        assert summary["restored"] == 1
        assert summary["sidecars_updated"] == 1

        stored = db_session.query(MediaItem).filter(MediaItem.id == media.id).first()
        assert stored is not None
        assert stored.missing is False
        assert stored.vocals_path == "/media/single-item.vocals.wav"
        assert stored.lyrics_path == "/media/single-item.lrc"
        assert stored.last_scanned_at is not None
    finally:
        settings.media_path = original_media

def test_media_library_sync_service_scans_one_item_cdg_sidecar(db_session, tmp_path, monkeypatch):
    """Single-item scans should treat adjacent CDG graphics as a lyrics sidecar."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "cdg-item.mp3"
        cdg_file = settings.media_path / "cdg-item.cdg"
        media_file.write_text("audio", encoding="utf-8")
        cdg_file.write_bytes(b"cdg-bytes")

        media = MediaItem(
            title="CDG Item",
            media_path="/media/cdg-item.mp3",
            missing=True,
        )
        db_session.add(media)
        db_session.commit()

        service = MediaLibrarySyncService()
        monkeypatch.setattr(
            service.thumbnail_service,
            "ensure_thumbnail_for_media_file",
            lambda path: False,
        )

        summary = service.scan_media_item(db_session, media.id)

        assert summary["scanned_files"] == 1
        stored = db_session.query(MediaItem).filter(MediaItem.id == media.id).first()
        assert stored is not None
        assert stored.lyrics_path == "/media/cdg-item.cdg"
    finally:
        settings.media_path = original_media

def test_media_library_sync_service_detects_json_lyrics_sidecar(db_session, tmp_path, monkeypatch):
    """Single-item scans should treat adjacent JSON lyrics as a valid sidecar."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "json-sidecar.mp4"
        lyrics_file = settings.media_path / "json-sidecar.json"
        media_file.write_text("video", encoding="utf-8")
        lyrics_file.write_text('[{"start":1.0,"text":"Hello"}]', encoding="utf-8")

        media = MediaItem(
            title="JSON Sidecar",
            media_path="/media/json-sidecar.mp4",
            missing=True,
        )
        db_session.add(media)
        db_session.commit()

        service = MediaLibrarySyncService()
        monkeypatch.setattr(
            service.thumbnail_service,
            "ensure_thumbnail_for_media_file",
            lambda path: False,
        )

        summary = service.scan_media_item(db_session, media.id)

        assert summary["scanned_files"] == 1
        stored = db_session.query(MediaItem).filter(MediaItem.id == media.id).first()
        assert stored is not None
        assert stored.lyrics_path == "/media/json-sidecar.json"
    finally:
        settings.media_path = original_media

def test_media_library_sync_service_preserves_adjacent_thumbnail_sidecar(
    db_session, tmp_path
):
    """Single-item scans should keep adjacent thumbnails available after refresh."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "thumb-refresh.mp4"
        media_file.write_text("video", encoding="utf-8")
        adjacent_thumb = media_file.with_suffix(".jpg")
        adjacent_thumb.write_bytes(b"thumb")

        media = MediaItem(
            title="Thumb Refresh",
            media_path="/media/thumb-refresh.mp4",
            missing=True,
        )
        db_session.add(media)
        db_session.commit()

        summary = MediaLibrarySyncService().scan_media_item(db_session, media.id)
        stored = db_session.query(MediaItem).filter(MediaItem.id == media.id).first()
        assert stored is not None
        assert summary["thumbnails_updated"] == 1
        assert stored.missing is False
        assert MediaLibraryService._thumbnail_for(stored) == MediaThumbnailService.public_url_for_path(adjacent_thumb)
    finally:
        settings.media_path = original_media

def test_media_library_sync_service_skips_thumbnail_regen_for_youtube_rows_without_override(
    db_session, tmp_path
):
    """YouTube-backed scans should not recreate cache thumbnails when no override exists."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "blank-space.mp4"
        media_file.write_text("video", encoding="utf-8")
        thumb_path = MediaThumbnailService.thumbnail_path_for_media_file(media_file)

        media = MediaItem(
            title="Blank Space",
            artist="Taylor Swift",
            youtube_id="abc123",
            media_path="/media/blank-space.mp4",
            missing=True,
        )
        db_session.add(media)
        db_session.commit()

        summary = MediaLibrarySyncService().scan_media_item(db_session, media.id)
        stored = db_session.query(MediaItem).filter(MediaItem.id == media.id).first()
        assert stored is not None
        assert summary["thumbnails_updated"] == 0
        assert not thumb_path.exists()
        assert MediaLibraryService._thumbnail_for(stored) == "https://i.ytimg.com/vi/abc123/hqdefault.jpg"
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache

def test_media_library_sync_service_skips_sidecars_as_primary_media(db_session, tmp_path):
    """Sidecar-only files should not be inserted as standalone media rows."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        (settings.media_path / "track.vocals.mp3").write_text("vocals", encoding="utf-8")
        (settings.media_path / "track.lrc").write_text("[00:00.00]line", encoding="utf-8")
        (settings.media_path / "track.cdg").write_bytes(b"cdg")

        service = MediaLibrarySyncService()
        summary = service.scan_library(db_session)

        assert summary["scanned_files"] == 0
        assert summary["created"] == 0
        assert db_session.query(MediaItem).count() == 0
    finally:
        settings.media_path = original_media

def test_media_library_sync_service_skips_audio_scratch_files_as_primary_media(
    db_session, tmp_path
):
    """Transient *.audio.* files should not be inserted as standalone media rows."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        (settings.media_path / "track.mp4").write_text("video", encoding="utf-8")
        (settings.media_path / "track.audio.webm").write_text("audio", encoding="utf-8")
        (settings.media_path / "track.vocals.mp3").write_text("vocals", encoding="utf-8")

        service = MediaLibrarySyncService()
        summary = service.scan_library(db_session)

        assert summary["scanned_files"] == 1
        assert summary["created"] == 1
        rows = db_session.query(MediaItem).all()
        assert len(rows) == 1
        assert rows[0].media_path == "/media/track.mp4"
        assert rows[0].vocals_path == "/media/track.vocals.mp3"
    finally:
        settings.media_path = original_media

def test_media_library_sync_service_skips_legacy_karaoke_duplicate_when_canonical_exists(
    db_session, tmp_path
):
    """Legacy *.karaoke.mp4 should not become a duplicate row if canonical media exists."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        (settings.media_path / "track.mp4").write_text("video", encoding="utf-8")
        (settings.media_path / "track.karaoke.mp4").write_text("legacy-video", encoding="utf-8")
        (settings.media_path / "track.vocals.mp3").write_text("vocals", encoding="utf-8")

        service = MediaLibrarySyncService()
        summary = service.scan_library(db_session)

        assert summary["scanned_files"] == 1
        assert summary["created"] == 1
        rows = db_session.query(MediaItem).all()
        assert len(rows) == 1
        assert rows[0].media_path == "/media/track.mp4"
        assert rows[0].vocals_path == "/media/track.vocals.mp3"
    finally:
        settings.media_path = original_media

def test_media_library_sync_service_keeps_legacy_karaoke_file_when_no_canonical_exists(
    db_session, tmp_path
):
    """Legacy *.karaoke.mp4 remains importable when it is the only playable media file."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        (settings.media_path / "track.karaoke.mp4").write_text("legacy-video", encoding="utf-8")
        (settings.media_path / "track.vocals.mp3").write_text("vocals", encoding="utf-8")

        service = MediaLibrarySyncService()
        summary = service.scan_library(db_session)

        assert summary["scanned_files"] == 1
        assert summary["created"] == 1
        row = db_session.query(MediaItem).one()
        assert row.media_path == "/media/track.karaoke.mp4"
        assert row.vocals_path == "/media/track.vocals.mp3"
    finally:
        settings.media_path = original_media

def test_media_library_sync_service_generates_thumbnails_for_videos(db_session, tmp_path, monkeypatch):
    """Library scans should request thumbnail generation for local video files."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "scan-me.mp4"
        media_file.write_text("video", encoding="utf-8")

        service = MediaLibrarySyncService()
        calls: list[Path] = []

        def fake_generate(path: Path):
            calls.append(path)
            thumb_path = MediaThumbnailService.thumbnail_path_for_media_file(path)
            thumb_path.parent.mkdir(parents=True, exist_ok=True)
            thumb_path.write_bytes(b"thumb")
            return thumb_path

        monkeypatch.setattr(service.thumbnail_service, "ensure_thumbnail_for_media_file", fake_generate)

        summary = service.scan_library(db_session)

        assert summary["scanned_files"] == 1
        assert summary["created"] == 1
        assert summary["thumbnails_updated"] == 1
        assert calls == [media_file]
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache

def test_media_library_sync_service_generates_thumbnails_for_audio_files(db_session, tmp_path, monkeypatch):
    """Library scans should request thumbnail generation for local audio files too."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "scan-me.mp3"
        media_file.write_text("audio", encoding="utf-8")

        service = MediaLibrarySyncService()
        calls: list[Path] = []

        def fake_generate(path: Path):
            calls.append(path)
            thumb_path = MediaThumbnailService.thumbnail_path_for_media_file(path)
            thumb_path.parent.mkdir(parents=True, exist_ok=True)
            thumb_path.write_bytes(b"thumb")
            return thumb_path

        monkeypatch.setattr(service.thumbnail_service, "ensure_thumbnail_for_media_file", fake_generate)

        summary = service.scan_library(db_session)

        assert summary["scanned_files"] == 1
        assert summary["created"] == 1
        assert summary["thumbnails_updated"] == 1
        assert calls == [media_file]
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache
