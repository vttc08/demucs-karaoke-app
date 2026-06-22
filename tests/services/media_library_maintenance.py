from .common import *



def test_media_library_maintenance_service_deletes_files_and_queue_rows(db_session, tmp_path):
    """Deleting a media item should remove its DB row, queue rows, and local files."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        (settings.cache_path / "lyrics").mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "delete-me.mp4"
        vocals_file = settings.media_path / "delete-me.vocals.wav"
        lyrics_file = settings.cache_path / "lyrics" / "delete-me.lrc"
        thumb_file = MediaThumbnailService.thumbnail_path_for_media_file(media_file)
        adjacent_thumb = media_file.with_suffix(".jpg")
        media_file.write_text("video", encoding="utf-8")
        vocals_file.write_text("vocals", encoding="utf-8")
        thumb_file.parent.mkdir(parents=True, exist_ok=True)
        thumb_file.write_bytes(b"thumb")
        adjacent_thumb.write_bytes(b"adjacent")

        media = MediaItem(
            title="Delete Me",
            artist="Singer",
            media_path="/media/delete-me.mp4",
            vocals_path="/media/delete-me.vocals.wav",
            lyrics_path="/cache/lyrics/delete-me.lrc",
            missing=False,
        )
        db_session.add(media)
        db_session.flush()
        db_session.add(
            QueueItem(
                media_id=media.id,
                position=1000,
                status=QueueStatus.PENDING,
            )
        )
        db_session.commit()

        service = MediaLibraryMaintenanceService()
        summary = service.delete_media_item(db_session, media.id)

        assert summary["deleted_files"] == 4
        assert summary["missing_files"] == 1
        assert summary["removed_queue_items"] == 1
        assert not media_file.exists()
        assert not vocals_file.exists()
        assert not lyrics_file.exists()
        assert not thumb_file.exists()
        assert not adjacent_thumb.exists()
        assert db_session.query(MediaItem).filter(MediaItem.id == media.id).first() is None
        assert db_session.query(QueueItem).filter(QueueItem.media_id == media.id).count() == 0
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache

def test_media_library_maintenance_service_rejects_missing_item(db_session):
    """Deleting a missing media item should raise a not-found error."""
    service = MediaLibraryMaintenanceService()

    with pytest.raises(MediaItemNotFoundError):
        service.delete_media_item(db_session, 9999)

def test_media_library_maintenance_service_rejects_playing_queue_item(db_session):
    """Deleting a currently playing media item should be blocked."""
    media = MediaItem(
        title="Playing Track",
        media_path="/media/playing-track.mp4",
        missing=False,
    )
    db_session.add(media)
    db_session.flush()
    db_session.add(
        QueueItem(
            media_id=media.id,
            position=1000,
            status=QueueStatus.PLAYING,
        )
    )
    db_session.commit()

    service = MediaLibraryMaintenanceService()

    with pytest.raises(MediaItemDeleteConflictError):
        service.delete_media_item(db_session, media.id)


def test_media_library_maintenance_service_builds_file_manifest(db_session, tmp_path):
    """File manifests should include the main file and tracked sidecars."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        (settings.cache_path / "lyrics").mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "manifest-song.mp4"
        vocals_file = settings.media_path / "manifest-song.vocals.wav"
        lyrics_file = settings.cache_path / "lyrics" / "manifest-song.json"
        media_file.write_bytes(b"video")
        vocals_file.write_bytes(b"vocals")
        lyrics_file.write_text("{}", encoding="utf-8")

        media = MediaItem(
            title="Manifest Song",
            artist="Manifest Artist",
            media_path="/media/manifest-song.mp4",
            vocals_path="/media/manifest-song.vocals.wav",
            lyrics_path="/cache/lyrics/manifest-song.json",
            missing=False,
        )
        db_session.add(media)
        db_session.commit()

        service = MediaLibraryMaintenanceService()
        manifest = service.get_media_file_manifest(db_session, media.id)

        assert manifest["media_id"] == media.id
        assert manifest["has_multi_track"] is True
        assert manifest["has_lyrics"] is True
        assert manifest["lyrics_kind"] == "json"
        assert manifest["download_name"] == "manifest-song.zip"
        assert [entry["kind"] for entry in manifest["files"]] == ["main", "vocals", "lyrics"]
        assert manifest["files"][0]["filename"] == "manifest-song.mp4"
        assert manifest["files"][0]["exists"] is True
        assert manifest["files"][1]["filename"] == "manifest-song.vocals.wav"
        assert manifest["files"][2]["filename"] == "manifest-song.json"
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache


def test_media_library_maintenance_service_omits_missing_sidecars_from_manifest(
    db_session, tmp_path
):
    """Missing sidecars should not be exposed to the edit modal."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        (settings.cache_path / "lyrics").mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "hidden-missing-song.mp4"
        vocals_file = settings.media_path / "hidden-missing-song.vocals.wav"
        media_file.write_bytes(b"video")
        vocals_file.write_bytes(b"vocals")

        media = MediaItem(
            title="Hidden Missing Song",
            artist="Hidden Artist",
            media_path="/media/hidden-missing-song.mp4",
            vocals_path="/media/hidden-missing-song.vocals.wav",
            lyrics_path="/cache/lyrics/hidden-missing-song.lrc",
            missing=False,
        )
        db_session.add(media)
        db_session.commit()

        service = MediaLibraryMaintenanceService()
        manifest = service.get_media_file_manifest(db_session, media.id)

        assert [entry["kind"] for entry in manifest["files"]] == ["main", "vocals"]
        assert manifest["has_multi_track"] is True
        assert manifest["has_lyrics"] is False
        assert manifest["lyrics_kind"] is None
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache


def test_media_library_maintenance_service_deletes_sidecar_and_clears_db_field(
    db_session, tmp_path
):
    """Deleting a sidecar should remove the file and clear the matching DB field."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        vocals_file = settings.media_path / "delete-sidecar.vocals.wav"
        vocals_file.write_bytes(b"vocals")

        media = MediaItem(
            title="Delete Sidecar",
            media_path="/media/delete-sidecar.mp4",
            vocals_path="/media/delete-sidecar.vocals.wav",
            missing=False,
        )
        db_session.add(media)
        db_session.commit()

        service = MediaLibraryMaintenanceService()
        summary = service.delete_media_file(db_session, media.id, "vocals")

        assert summary["kind"] == "vocals"
        assert summary["deleted"] is True
        assert not vocals_file.exists()

        stored = db_session.query(MediaItem).filter(MediaItem.id == media.id).first()
        assert stored is not None
        assert stored.vocals_path is None
    finally:
        settings.media_path = original_media


def test_media_library_maintenance_service_allows_missing_sidecar_cleanup(
    db_session, tmp_path
):
    """Missing sidecars should still be cleared from the DB when deleted."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        media = MediaItem(
            title="Missing Sidecar",
            media_path="/media/missing-sidecar.mp4",
            lyrics_path="/media/missing-sidecar.lrc",
            missing=False,
        )
        db_session.add(media)
        db_session.commit()

        service = MediaLibraryMaintenanceService()
        summary = service.delete_media_file(db_session, media.id, "lyrics")

        assert summary["kind"] == "lyrics"
        assert summary["deleted"] is False

        stored = db_session.query(MediaItem).filter(MediaItem.id == media.id).first()
        assert stored is not None
        assert stored.lyrics_path is None
    finally:
        settings.media_path = original_media


def test_media_library_maintenance_service_rejects_main_file_delete(db_session):
    """The main media file should not be deletable through the modal service."""
    media = MediaItem(
        title="Main Delete",
        media_path="/media/main-delete.mp4",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()

    service = MediaLibraryMaintenanceService()

    with pytest.raises(MediaFileDeleteConflictError):
        service.delete_media_file(db_session, media.id, "main")


def test_media_library_maintenance_service_builds_zip_package(db_session, tmp_path):
    """ZIP packages should include available media files without compression."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        (settings.cache_path / "lyrics").mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "zip-song.mp4"
        vocals_file = settings.media_path / "zip-song.vocals.wav"
        lyrics_file = settings.cache_path / "lyrics" / "zip-song.lrc"
        media_file.write_bytes(b"video-bytes")
        vocals_file.write_bytes(b"vocals-bytes")
        lyrics_file.write_text("[00:01.00]zip", encoding="utf-8")

        media = MediaItem(
            title="Zip Song",
            artist="Zip Artist",
            media_path="/media/zip-song.mp4",
            vocals_path="/media/zip-song.vocals.wav",
            lyrics_path="/cache/lyrics/zip-song.lrc",
            missing=False,
        )
        db_session.add(media)
        db_session.commit()

        service = MediaLibraryMaintenanceService()
        archive_bytes, archive_name = service.build_media_zip(db_session, media.id)

        assert archive_name == "zip-song.zip"
        with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
            assert archive.namelist() == ["zip-song.mp4", "zip-song.vocals.wav", "zip-song.lrc"]
            assert archive.getinfo("zip-song.mp4").compress_type == zipfile.ZIP_STORED
            assert archive.read("zip-song.mp4") == b"video-bytes"
            assert archive.read("zip-song.vocals.wav") == b"vocals-bytes"
            assert archive.read("zip-song.lrc") == b"[00:01.00]zip"
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache

def test_media_library_maintenance_service_renames_metadata_and_files(db_session, tmp_path):
    """Renaming a media item should update DB fields and disk assets."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        (settings.cache_path / "lyrics").mkdir(parents=True, exist_ok=True)

        old_media = settings.media_path / "old-title.mp4"
        old_vocals = settings.media_path / "old-title.vocals.wav"
        old_lyrics = settings.cache_path / "lyrics" / "old-title.lrc"
        old_thumb = MediaThumbnailService.thumbnail_path_for_media_file(old_media)
        old_adjacent_thumb = old_media.with_suffix(".png")
        old_media.write_text("video", encoding="utf-8")
        old_vocals.write_text("vocals", encoding="utf-8")
        old_lyrics.write_text("[00:01.00]lyrics", encoding="utf-8")
        old_thumb.parent.mkdir(parents=True, exist_ok=True)
        old_thumb.write_bytes(b"thumb")
        old_adjacent_thumb.write_bytes(b"adjacent")

        media = MediaItem(
            title="Old Title",
            artist="Old Artist",
            media_path="/media/old-title.mp4",
            vocals_path="/media/old-title.vocals.wav",
            lyrics_path="/cache/lyrics/old-title.lrc",
            missing=False,
        )
        db_session.add(media)
        db_session.commit()

        service = MediaLibraryMaintenanceService()
        summary = service.rename_media_item(
            db_session,
            media.id,
            title="New Title",
            artist="New Artist",
            rename_on_disk=True,
        )

        expected_stem = build_media_stem("New Title", "New Artist", fallback=media.youtube_id)
        assert summary["renamed_files"] == 3
        assert summary["target_stem"] == expected_stem
        assert not old_media.exists()
        assert not old_vocals.exists()
        assert not old_lyrics.exists()

        renamed_media = settings.media_path / f"{expected_stem}.mp4"
        renamed_vocals = settings.media_path / f"{expected_stem}.vocals.wav"
        renamed_lyrics = settings.cache_path / "lyrics" / f"{expected_stem}.lrc"
        renamed_thumb = MediaThumbnailService.thumbnail_path_for_media_file(renamed_media)
        renamed_adjacent_thumb = renamed_media.with_suffix(".png")
        assert renamed_media.exists()
        assert renamed_vocals.exists()
        assert renamed_lyrics.exists()
        assert not old_thumb.exists()
        assert renamed_thumb.exists()
        assert not old_adjacent_thumb.exists()
        assert renamed_adjacent_thumb.exists()

        stored = db_session.query(MediaItem).filter(MediaItem.id == media.id).first()
        assert stored is not None
        assert stored.title == "New Title"
        assert stored.artist == "New Artist"
        assert stored.file_stem == expected_stem
        assert stored.media_path == f"/media/{expected_stem}.mp4"
        assert stored.vocals_path == f"/media/{expected_stem}.vocals.wav"
        assert stored.lyrics_path == f"/cache/lyrics/{expected_stem}.lrc"
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache

def test_media_library_maintenance_service_renames_metadata_without_disk_changes(db_session, tmp_path):
    """Renaming without disk changes should only update database fields."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        media_file = settings.media_path / "unchanged.mp4"
        media_file.write_text("video", encoding="utf-8")

        media = MediaItem(
            title="Unchanged",
            artist="Artist",
            media_path="/media/unchanged.mp4",
            missing=False,
        )
        db_session.add(media)
        db_session.commit()

        service = MediaLibraryMaintenanceService()
        summary = service.rename_media_item(
            db_session,
            media.id,
            title="Only DB Rename",
            artist="Artist Two",
            rename_on_disk=False,
        )

        assert summary["renamed_files"] == 0
        stored = db_session.query(MediaItem).filter(MediaItem.id == media.id).first()
        assert stored is not None
        assert stored.title == "Only DB Rename"
        assert stored.artist == "Artist Two"
        assert stored.media_path == "/media/unchanged.mp4"
        assert media_file.exists()
    finally:
        settings.media_path = original_media

def test_media_library_maintenance_service_rejects_rename_conflicts(db_session, tmp_path):
    """Renaming should fail when the destination asset already exists."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        conflict_stem = build_media_stem("New Title", "Artist", fallback=None)
        conflict_media = settings.media_path / f"{conflict_stem}.mp4"
        conflict_media.write_text("video", encoding="utf-8")
        old_media = settings.media_path / "old-title.mp4"
        old_media.write_text("video", encoding="utf-8")

        media = MediaItem(
            title="Old Title",
            artist="Artist",
            media_path="/media/old-title.mp4",
            missing=False,
        )
        db_session.add(media)
        db_session.commit()

        service = MediaLibraryMaintenanceService()

        with pytest.raises(MediaItemRenameConflictError):
            service.rename_media_item(
                db_session,
                media.id,
                title="New Title",
                artist="Artist",
                rename_on_disk=True,
            )
    finally:
        settings.media_path = original_media

def test_queue_service_renames_existing_media_assets(db_session, tmp_path):
    """Existing media files and sidecars should be renamed to human-readable stems."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)
        (settings.cache_path / "lyrics").mkdir(parents=True, exist_ok=True)

        old_media = settings.media_path / "abc123.mp4"
        old_vocals = settings.cache_path / "abc123.vocals.mp3"
        old_lyrics = settings.cache_path / "lyrics" / "abc123.lrc"
        old_media.write_text("video", encoding="utf-8")
        old_vocals.write_text("vocals", encoding="utf-8")
        old_lyrics.write_text("[00:01.00]lyrics", encoding="utf-8")

        db_session.add(
            MediaItem(
                youtube_id="abc123",
                title="Old Title",
                artist="Old Artist",
                media_path="/media/abc123.mp4",
                vocals_path="/cache/abc123.vocals.mp3",
                lyrics_path="/cache/lyrics/abc123.lrc",
                missing=False,
            )
        )
        db_session.commit()

        service = QueueService()
        result = service.add_to_queue(
            db_session,
            QueueItemCreate(
                youtube_id="abc123",
                title="New Title",
                artist="New Artist",
                is_karaoke=True,
                lyrics_text="[00:01.00]lyrics",
            ),
        )

        expected_stem = build_media_stem("New Title", "New Artist", fallback="abc123")
        stored = (
            db_session.query(MediaItem)
            .filter(MediaItem.youtube_id == "abc123")
            .first()
        )
        assert stored is not None
        assert stored.file_stem == expected_stem
        assert stored.media_path == f"/media/{expected_stem}.mp4"
        assert stored.vocals_path == f"/media/{expected_stem}.vocals.mp3"
        assert stored.lyrics_path == f"/cache/lyrics/{expected_stem}.lrc"
        assert (settings.media_path / f"{expected_stem}.mp4").exists()
        assert (settings.media_path / f"{expected_stem}.vocals.mp3").exists()
        assert (settings.cache_path / "lyrics" / f"{expected_stem}.lrc").exists()
        assert result.title == "New Title"
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache
