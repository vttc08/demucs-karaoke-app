from .common import *
from sqlalchemy import event

def test_media_library_service_batches_latest_eligible_tasks(db_session):
    first = MediaItem(title="First", media_path="/media/first.mp4", missing=False)
    second = MediaItem(title="Second", media_path="/media/second.mp4", missing=False)
    third = MediaItem(title="Third", media_path="/media/third.mp4", missing=False)
    db_session.add_all([first, second, third])
    db_session.flush()

    older = ProcessingTask(
        task_type="media_karaoke",
        source_kind="library_media",
        target_media_item_id=first.id,
        status=ProcessingTaskStatus.PROCESSING.value,
        stage="separating",
    )
    db_session.add(older)
    db_session.flush()
    latest = ProcessingTask(
        task_type="media_karaoke",
        source_kind="library_media",
        target_media_item_id=first.id,
        status=ProcessingTaskStatus.FAILED.value,
        stage="failed",
    )
    db_session.add_all(
        [
            latest,
            ProcessingTask(
                task_type="media_karaoke",
                source_kind="library_media",
                target_media_item_id=second.id,
                status=ProcessingTaskStatus.DONE.value,
            ),
            ProcessingTask(
                task_type="media_karaoke",
                source_kind="library_media",
                target_media_item_id=second.id,
                status=ProcessingTaskStatus.CANCELED.value,
            ),
            ProcessingTask(
                task_type="media_karaoke_align",
                source_kind="library_media",
                target_media_item_id=third.id,
                status=ProcessingTaskStatus.PROCESSING.value,
            ),
        ]
    )
    db_session.commit()

    asyncio.run(
        task_stream_manager.publish(
            latest.id,
            event_type="progress",
            status=latest.status,
            stage=latest.stage,
            progress_percent=63,
            progress_label="Almost there",
        )
    )
    statements: list[str] = []

    def track_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(db_session.bind, "before_cursor_execute", track_statement)
    try:
        items = MediaLibraryService().list_media_items(db_session)
    finally:
        event.remove(db_session.bind, "before_cursor_execute", track_statement)
        asyncio.run(task_stream_manager.clear_task(latest.id))

    by_title = {item["title"]: item for item in items}
    assert by_title["First"]["task_id"] == latest.id
    assert by_title["First"]["task_status"] == ProcessingTaskStatus.FAILED.value
    assert by_title["First"]["task_progress"] == 63
    assert by_title["First"]["task_label"] == "Almost there"
    assert by_title["Second"]["task_id"] is None
    assert by_title["Third"]["task_id"] is None
    assert len(statements) == 2
    assert sum("FROM media_items" in statement for statement in statements) == 1
    assert sum("processing_tasks" in statement for statement in statements) == 1


def test_media_library_stats_use_one_query_and_preserve_counts(db_session):
    db_session.add_all(
        [
            MediaItem(
                title="Complete",
                media_path="/media/complete.mp4",
                vocals_path="/media/complete.vocals.wav",
                lyrics_path="/media/complete.json",
                missing=False,
            ),
            MediaItem(
                title="Missing",
                media_path="/media/missing.mp4",
                missing=True,
            ),
        ]
    )
    db_session.commit()
    statements: list[str] = []

    def track_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(db_session.bind, "before_cursor_execute", track_statement)
    try:
        stats = MediaLibraryService().get_media_stats(db_session)
    finally:
        event.remove(db_session.bind, "before_cursor_execute", track_statement)

    assert stats == {
        "total": 2,
        "with_multi_track": 1,
        "with_lyrics": 1,
        "missing": 1,
    }
    assert len(statements) == 1


def test_media_library_stats_are_zero_for_empty_library(db_session):
    assert MediaLibraryService().get_media_stats(db_session) == {
        "total": 0,
        "with_multi_track": 0,
        "with_lyrics": 0,
        "missing": 0,
    }




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

def test_media_library_service_prefers_youtube_thumbnail_over_cache(db_session, tmp_path):
    """YouTube-backed media should fall back to YouTube art instead of a bad cache frame."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "blank-space.mp4"
        media_file.write_text("video", encoding="utf-8")
        cache_thumb = MediaThumbnailService.thumbnail_path_for_media_file(media_file)
        cache_thumb.parent.mkdir(parents=True, exist_ok=True)
        cache_thumb.write_bytes(b"black")

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
        assert items[0]["thumbnail"] == "https://i.ytimg.com/vi/abc123/hqdefault.jpg"
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

def test_media_library_service_marks_cdg_lyrics_kind(db_session, tmp_path):
    """Media page rows should expose CDG lyrics as a distinct lyrics kind."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "cdg-song.mp3"
        media_file.write_text("audio", encoding="utf-8")

        db_session.add(
            MediaItem(
                title="CDG Song",
                media_path="/media/cdg-song.mp3",
                lyrics_path="/media/cdg-song.cdg",
                missing=False,
            )
        )
        db_session.commit()

        service = MediaLibraryService()
        items = service.list_media_items(db_session)

        assert len(items) == 1
        assert items[0]["has_lyrics"] is True
        assert items[0]["lyrics_path"] == "/media/cdg-song.cdg"
        assert items[0]["lyrics_kind"] == "cdg"
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
