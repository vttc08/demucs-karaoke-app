from .common import *



def test_media_library_service_uses_cached_local_thumbnail(db_session, tmp_path):
    """Media page rows should use cached thumbnails for local media files."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "local-song.mp4"
        media_file.write_text("video", encoding="utf-8")
        thumb_path = MediaThumbnailService.thumbnail_path_for_media_file(media_file)
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        thumb_path.write_bytes(b"thumb")

        db_session.add(
            MediaItem(
                title="Local Song",
                media_path="/media/local-song.mp4",
                missing=False,
            )
        )
        db_session.commit()

        service = MediaLibraryService()
        items = service.list_media_items(db_session)

        assert len(items) == 1
        assert items[0]["thumbnail"] == MediaThumbnailService.thumbnail_url_for_media_file(media_file)
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache

def test_media_library_service_prefers_adjacent_local_thumbnail(db_session, tmp_path):
    """Media page rows should prefer adjacent thumbnail sidecars over cache."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "local-song.mp4"
        media_file.write_text("video", encoding="utf-8")
        cache_thumb = MediaThumbnailService.thumbnail_path_for_media_file(media_file)
        cache_thumb.parent.mkdir(parents=True, exist_ok=True)
        cache_thumb.write_bytes(b"thumb")
        adjacent_thumb = media_file.with_suffix(".webp")
        adjacent_thumb.write_bytes(b"adjacent")

        db_session.add(
            MediaItem(
                title="Local Song",
                media_path="/media/local-song.mp4",
                missing=False,
            )
        )
        db_session.commit()

        service = MediaLibraryService()
        items = service.list_media_items(db_session)

        assert len(items) == 1
        assert items[0]["thumbnail"] == MediaThumbnailService.public_url_for_path(adjacent_thumb)
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache

def test_media_library_service_prefers_local_thumbnail_over_youtube_fallback(db_session, tmp_path):
    """Local thumbnail sidecars should override the YouTube fallback for saved media."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "blank-space.mp4"
        media_file.write_text("video", encoding="utf-8")
        adjacent_thumb = media_file.with_suffix(".jpg")
        adjacent_thumb.write_bytes(b"adjacent")

        db_session.add(
            MediaItem(
                youtube_id="abc123",
                title="Blank Space",
                artist="Taylor Swift",
                media_path="/media/blank-space.mp4",
                missing=False,
            )
        )
        db_session.commit()

        service = MediaLibraryService()
        items = service.list_media_items(db_session)

        assert len(items) == 1
        assert items[0]["thumbnail"] == MediaThumbnailService.public_url_for_path(adjacent_thumb)
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache

def test_media_thumbnail_service_prefers_adjacent_thumbnail_over_cache(tmp_path):
    """Adjacent thumbnail sidecars should win over cached thumbnails."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)
        media_file = settings.media_path / "song.mp4"
        media_file.write_bytes(b"video")

        cache_thumb = MediaThumbnailService.thumbnail_path_for_media_file(media_file)
        cache_thumb.parent.mkdir(parents=True, exist_ok=True)
        cache_thumb.write_bytes(b"cache-thumb")

        adjacent_thumb = media_file.with_suffix(".png")
        adjacent_thumb.write_bytes(b"adjacent-thumb")

        service = MediaThumbnailService()

        assert service.best_thumbnail_path_for_media_file(media_file) == adjacent_thumb
        assert service.thumbnail_url_for_media_file(media_file) == MediaThumbnailService.public_url_for_path(adjacent_thumb)
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache

def test_media_library_service_marks_json_lyrics_kind(db_session, tmp_path):
    """Media page rows should expose WhisperX JSON as a distinct lyrics kind."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "json-song.mp4"
        media_file.write_text("video", encoding="utf-8")

        db_session.add(
            MediaItem(
                title="JSON Song",
                media_path="/media/json-song.mp4",
                lyrics_path="/media/json-song.json",
                missing=False,
            )
        )
        db_session.commit()

        service = MediaLibraryService()
        items = service.list_media_items(db_session)

        assert len(items) == 1
        assert items[0]["has_lyrics"] is True
        assert items[0]["lyrics_path"] == "/media/json-song.json"
        assert items[0]["lyrics_kind"] == "json"
    finally:
        settings.media_path = original_media

def test_media_thumbnail_service_uses_embedded_art_extraction_for_audio(tmp_path, monkeypatch):
    """Audio thumbnails should use embedded-art extraction instead of video frame capture."""
    original_cache = settings.cache_path
    try:
        settings.cache_path = tmp_path / "cache"
        settings.cache_path.mkdir(parents=True, exist_ok=True)
        media_file = tmp_path / "album-track.mp3"
        media_file.write_bytes(b"audio")
        service = MediaThumbnailService()
        called: list[str] = []

        def fake_extract_embedded(source_path: Path, output_path: Path):
            called.append(f"embedded:{source_path.name}")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"thumb")
            return output_path

        def fail_extract_video(source_path: Path, output_path: Path):
            raise AssertionError("video extraction should not run for audio files")

        monkeypatch.setattr(service.ffmpeg, "extract_embedded_thumbnail", fake_extract_embedded)
        monkeypatch.setattr(service.ffmpeg, "extract_video_thumbnail", fail_extract_video)

        result = service.ensure_thumbnail_for_media_file(media_file)

        assert result == media_file.with_suffix(".jpg")
        assert result.exists()
        assert called == ["embedded:album-track.mp3"]
    finally:
        settings.cache_path = original_cache
