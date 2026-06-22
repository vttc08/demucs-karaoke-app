from .common import *



def test_queue_service_add_to_queue(db_session):
    """Test adding item to queue via service."""
    service = QueueService()
    item = QueueItemCreate(
        youtube_id="test123",
        title="Test Song",
        artist="Test Artist",
        is_karaoke=True,
    )

    result = service.add_to_queue(db_session, item)

    assert result.youtube_id == "test123"
    assert result.title == "Test Song"
    assert result.is_karaoke is True
    assert result.status == QueueStatus.PENDING

def test_queue_service_add_to_queue_includes_thumbnail_for_local_media(db_session, tmp_path, monkeypatch):
    """Queue responses should include cached thumbnails for local media items."""
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    media_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)

    media_file = media_root / "local-track.mp4"
    media_file.write_bytes(b"media")
    thumbnail_path = MediaThumbnailService.thumbnail_path_for_media_file(media_file)
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    thumbnail_path.write_bytes(b"thumbnail")

    db_session.add(
        MediaItem(
            youtube_id=None,
            title="Local Thumb",
            artist="Artist",
            media_path="/media/local-track.mp4",
            missing=False,
        )
    )
    db_session.commit()

    service = QueueService()
    result = service.add_to_queue(
        db_session,
        QueueItemCreate(
            media_item_id=db_session.query(MediaItem).filter(MediaItem.title == "Local Thumb").first().id,
            title="Local Thumb",
            artist="Artist",
            is_karaoke=False,
        ),
    )

    assert result.thumbnail == MediaThumbnailService.thumbnail_url_for_media_file(media_file)

def test_queue_service_prefers_adjacent_thumbnail_for_local_media(db_session, tmp_path, monkeypatch):
    """Queue responses should prefer adjacent thumbnail sidecars over cached thumbs."""
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    media_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)

    media_file = media_root / "adjacent-track.mp4"
    media_file.write_bytes(b"media")
    cache_thumb = MediaThumbnailService.thumbnail_path_for_media_file(media_file)
    cache_thumb.parent.mkdir(parents=True, exist_ok=True)
    cache_thumb.write_bytes(b"thumbnail")
    adjacent_thumb = media_file.with_suffix(".jpg")
    adjacent_thumb.write_bytes(b"adjacent")

    db_session.add(
        MediaItem(
            youtube_id=None,
            title="Adjacent Thumb",
            artist="Artist",
            media_path="/media/adjacent-track.mp4",
            missing=False,
        )
    )
    db_session.commit()

    service = QueueService()
    result = service.add_to_queue(
        db_session,
        QueueItemCreate(
            media_item_id=db_session.query(MediaItem).filter(MediaItem.title == "Adjacent Thumb").first().id,
            title="Adjacent Thumb",
            artist="Artist",
            is_karaoke=False,
        ),
    )

    assert result.thumbnail == MediaThumbnailService.thumbnail_url_for_media_file(media_file)
    assert result.thumbnail == MediaThumbnailService.public_url_for_path(adjacent_thumb)

def test_queue_service_prefers_local_thumbnail_over_youtube_fallback(db_session, tmp_path, monkeypatch):
    """Queue responses should prefer local thumbnail sidecars over YouTube thumbs."""
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    media_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)

    media_file = media_root / "blank-space.mp4"
    media_file.write_bytes(b"media")
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

    service = QueueService()
    result = service.add_to_queue(
        db_session,
        QueueItemCreate(
            media_item_id=db_session.query(MediaItem).filter(MediaItem.title == "Blank Space").first().id,
            title="Blank Space",
            artist="Taylor Swift",
            is_karaoke=False,
        ),
    )

    assert result.thumbnail == MediaThumbnailService.public_url_for_path(adjacent_thumb)

def test_queue_service_add_to_queue_stores_requester_metadata(db_session):
    """Queue items should preserve requester identity and display name."""
    service = QueueService()

    result = service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="requester123",
            title="Requester Song",
            is_karaoke=False,
        ),
        requester_id="guest-123",
        requester_session_id="tab-123",
        requester_name="Alex",
    )

    stored = db_session.query(QueueItem).filter(QueueItem.id == result.id).first()
    assert stored is not None
    assert stored.user_id == "guest-123"
    assert stored.session_id == "tab-123"
    assert stored.requester_name == "Alex"
    assert result.requested_by_name == "Alex"

def test_queue_service_add_to_queue_stores_whisperx_language_override(db_session):
    """Queue items should persist a per-item WhisperX language override."""
    service = QueueService()

    result = service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="language-override",
            title="Language Override Song",
            artist="Artist",
            is_karaoke=True,
            whisperx_align_language_override="ZH",
        ),
    )

    stored = db_session.query(QueueItem).filter(QueueItem.id == result.id).first()
    assert stored is not None
    assert stored.whisperx_align_language_override == "zh"
    assert result.whisperx_align_language_override == "zh"

def test_queue_service_get_queue_sets_can_remove_for_owner_and_admin(db_session):
    """Queue responses should expose remove permissions for the current viewer."""
    service = QueueService()
    owner_result = service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="owned-queue-item",
            title="Owned Song",
            is_karaoke=False,
        ),
        requester_id="guest-123",
    )
    other_result = service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="other-queue-item",
            title="Other Song",
            is_karaoke=False,
        ),
        requester_id="guest-999",
    )

    items_for_owner = service.get_queue(db_session, requester_id="guest-123")
    permission_by_id = {item.id: item.can_remove for item in items_for_owner}

    assert permission_by_id[owner_result.id] is True
    assert permission_by_id[other_result.id] is False
    control_by_id = {item.id: item.can_control_stage for item in items_for_owner}
    assert control_by_id[owner_result.id] is True
    assert control_by_id[other_result.id] is False

    items_for_admin = service.get_queue(db_session, is_admin=True)
    assert all(item.can_remove is True for item in items_for_admin)
    assert all(item.can_control_stage is True for item in items_for_admin)

def test_queue_service_response_includes_step_progress_metadata(db_session):
    """Queue responses should expose the current step metadata for active task progress."""
    service = QueueService()
    created = service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="step-progress",
            title="Step Progress",
            is_karaoke=True,
        ),
    )
    task = ProcessingTask(
        task_type="queue_prepare",
        source_kind="youtube",
        target_queue_item_id=created.id,
        target_media_item_id=created.media_id,
        status=ProcessingTaskStatus.DOWNLOADING.value,
        stage="download",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    asyncio.run(
        processing_task_service.emit_progress(
            task.id,
            queue_item_id=created.id,
            progress_percent=32,
            progress_label="Downloading video",
            progress_label_key="task.downloading_video",
            progress_step_index=1,
            progress_step_total=4,
            status=ProcessingTaskStatus.DOWNLOADING.value,
            stage="download",
        )
    )

    queue_items = service.get_queue(db_session)
    item = next(entry for entry in queue_items if entry.id == created.id)
    assert item.processing_progress == 32
    assert item.processing_label == "Downloading video"
    assert item.processing_label_key == "task.downloading_video"
    assert item.processing_step_index == 1
    assert item.processing_step_total == 4
    asyncio.run(task_stream_manager.clear_task(task.id))

def test_queue_service_add_to_queue_can_delegate_owner_guest_id(db_session):
    """Queue items may be owned by a delegated guest while showing a delegated label."""
    service = QueueService()

    result = service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="delegated-owner",
            title="Delegated Owner Song",
            is_karaoke=False,
            queue_as_name="Taylor",
            queue_as_guest_id="guest-target",
        ),
        requester_id="guest-admin-device",
        requester_session_id="tab-admin-device",
        requester_name="Taylor",
        owner_guest_id="guest-target",
    )

    stored = db_session.query(QueueItem).filter(QueueItem.id == result.id).first()
    assert stored is not None
    assert stored.user_id == "guest-target"
    assert stored.session_id == "tab-admin-device"
    assert stored.requester_name == "Taylor"
    assert result.requested_by_name == "Taylor"

def test_queue_service_updates_youtube_metadata_from_payload(db_session):
    """YouTube-backed media rows should store the submitted title and artist."""
    db_session.add(
        MediaItem(
            youtube_id="resolve123",
            title="Original Video Title",
            artist="Original Uploader",
            media_path="/media/resolve123.mp4",
            missing=False,
        )
    )
    db_session.commit()

    service = QueueService()
    result = service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="resolve123",
            title="Resolved Track Title",
            artist="Resolved Artist",
            is_karaoke=True,
        ),
    )

    stored = (
        db_session.query(MediaItem)
        .filter(MediaItem.youtube_id == "resolve123")
        .first()
    )
    assert stored is not None
    assert stored.title == "Resolved Track Title"
    assert stored.artist == "Resolved Artist"
    assert result.title == "Resolved Track Title"
    assert result.artist == "Resolved Artist"

def test_queue_service_moves_item_up_with_sparse_positions(db_session):
    """Moving an item up should keep sparse ordering stable."""
    service = QueueService()
    first = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="move-up-1", title="First", is_karaoke=False),
    )
    second = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="move-up-2", title="Second", is_karaoke=False),
    )
    third = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="move-up-3", title="Third", is_karaoke=False),
    )
    fourth = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="move-up-4", title="Fourth", is_karaoke=False),
    )

    first_row = db_session.query(QueueItem).filter(QueueItem.id == first.id).first()
    first_row.status = QueueStatus.PLAYING
    db_session.commit()

    moved = service.move_queue_item(db_session, third.id, "up")
    ordered_titles = [item.title for item in service.get_queue(db_session)]

    assert moved.id == third.id
    assert ordered_titles == ["First", "Third", "Second", "Fourth"]
    assert moved.position < second.position
    assert moved.position > first.position

def test_queue_service_moves_item_down_to_queue_tail(db_session):
    """Moving an item down should append it after the next movable item."""
    service = QueueService()
    first = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="move-down-1", title="First", is_karaoke=False),
    )
    second = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="move-down-2", title="Second", is_karaoke=False),
    )
    third = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="move-down-3", title="Third", is_karaoke=False),
    )

    first_row = db_session.query(QueueItem).filter(QueueItem.id == first.id).first()
    first_row.status = QueueStatus.PLAYING
    db_session.commit()

    moved = service.move_queue_item(db_session, second.id, "down")
    ordered_titles = [item.title for item in service.get_queue(db_session)]

    assert moved.id == second.id
    assert ordered_titles == ["First", "Third", "Second"]
    assert moved.position > third.position

def test_queue_service_renumbers_before_reordering_when_gap_is_exhausted(db_session):
    """Dense positions should be renumbered before the move succeeds."""
    service = QueueService()
    first = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="dense-1", title="First", is_karaoke=False),
    )
    second = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="dense-2", title="Second", is_karaoke=False),
    )
    third = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="dense-3", title="Third", is_karaoke=False),
    )
    fourth = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="dense-4", title="Fourth", is_karaoke=False),
    )

    for index, item in enumerate((first, second, third, fourth), start=1):
        row = db_session.query(QueueItem).filter(QueueItem.id == item.id).first()
        row.position = 1000 + (index - 1)
    first_row = db_session.query(QueueItem).filter(QueueItem.id == first.id).first()
    first_row.status = QueueStatus.PLAYING
    db_session.commit()

    moved = service.move_queue_item(db_session, third.id, "up")
    refreshed = service.get_queue(db_session)

    assert moved.id == third.id
    assert [item.title for item in refreshed] == ["First", "Third", "Second", "Fourth"]
    assert [item.position for item in refreshed] == [1000, 1500, 2000, 4000]

def test_media_items_has_youtube_id_index(db_session):
    """Media item youtube_id lookups should be backed by an index."""
    indexes = inspect(db_session.get_bind()).get_indexes("media_items")
    assert any("youtube_id" in index["name"] for index in indexes)

def test_queue_service_get_queue(db_session):
    """Test getting queue via service."""
    service = QueueService()

    # Add items
    item1 = QueueItemCreate(
        youtube_id="test1", title="Song 1", is_karaoke=False
    )
    item2 = QueueItemCreate(
        youtube_id="test2", title="Song 2", is_karaoke=True
    )
    service.add_to_queue(db_session, item1)
    service.add_to_queue(db_session, item2)

    # Get queue
    queue = service.get_queue(db_session)

    assert len(queue) == 2
    assert queue[0].title == "Song 1"
    assert queue[0].is_karaoke is False
    assert queue[1].title == "Song 2"
    assert queue[1].is_karaoke is True

def test_queue_service_response_includes_vocals_sidecar(db_session):
    """Queue responses should expose existing vocals sidecar paths from media items."""
    media = MediaItem(
        youtube_id="sidecar001",
        title="Sidecar Song",
        artist="Singer",
        media_path="/media/sidecar001.mp4",
        vocals_path="/media/sidecar001.vocals.mp3",
        lyrics_path="/media/sidecar001.lrc",
        missing=False,
    )
    db_session.add(media)
    db_session.flush()

    service = QueueService()
    created = service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="sidecar001",
            title="Sidecar Song",
            artist="Singer",
            is_karaoke=False,
        ),
    )

    assert created.vocals_path == "/media/sidecar001.vocals.mp3"
    assert created.lyrics_path == "/media/sidecar001.lrc"

def test_queue_service_persists_lyrics_sidecar_from_queue_payload(db_session, tmp_path):
    """Lyrics text in the queue payload should be written to a reusable sidecar."""
    original_cache = settings.cache_path
    try:
        settings.cache_path = tmp_path / "cache"
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        media = MediaItem(
            youtube_id="lyrics001",
            title="Lyrics Song",
            artist="Singer",
            media_path="/media/lyrics001.mp4",
            missing=False,
        )
        db_session.add(media)
        db_session.flush()

        service = QueueService()
        created = service.add_to_queue(
            db_session,
            QueueItemCreate(
                youtube_id="lyrics001",
                title="Lyrics Song",
                artist="Singer",
                is_karaoke=True,
                lyrics_text="[00:01.00]Hello lyrics",
            ),
        )

        expected_stem = build_media_stem("Lyrics Song", "Singer", fallback="lyrics001")
        assert created.lyrics_path == f"/cache/lyrics/{expected_stem}.lrc"
        lyrics_file = settings.cache_path / "lyrics" / f"{expected_stem}.lrc"
        assert lyrics_file.read_text(encoding="utf-8") == "[00:01.00]Hello lyrics"
    finally:
        settings.cache_path = original_cache

def test_queue_service_persists_lyrics_sidecar_for_existing_media(db_session, tmp_path):
    """Lyrics sidecar persistence should be reusable outside queue creation."""
    original_cache = settings.cache_path
    try:
        settings.cache_path = tmp_path / "cache"
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        media = MediaItem(
            title="Edited Lyrics",
            artist="Singer",
            file_stem="edited-lyrics",
            media_path="/media/edited-lyrics.mp4",
            missing=False,
        )
        db_session.add(media)
        db_session.flush()

        service = QueueService()
        service.store_lyrics_sidecar(media, "Plain lyrics", lyrics_format="txt")

        assert media.lyrics_path == "/cache/lyrics/edited-lyrics.txt"
        lyrics_file = settings.cache_path / "lyrics" / "edited-lyrics.txt"
        assert lyrics_file.read_text(encoding="utf-8") == "Plain lyrics"
    finally:
        settings.cache_path = original_cache

def test_queue_service_persists_json_lyrics_sidecar(db_session, tmp_path):
    """WhisperX JSON lyrics should persist with a JSON suffix."""
    original_cache = settings.cache_path
    try:
        settings.cache_path = tmp_path / "cache"
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        media = MediaItem(
            title="JSON Lyrics",
            artist="Singer",
            file_stem="json-lyrics",
            media_path="/media/json-lyrics.mp4",
            missing=False,
        )
        db_session.add(media)
        db_session.flush()

        service = QueueService()
        service.store_lyrics_sidecar(
            media,
            '[{"time":1.0,"text":"Hello"}]',
            lyrics_format="json",
        )

        assert media.lyrics_path == "/cache/lyrics/json-lyrics.json"
        lyrics_file = settings.cache_path / "lyrics" / "json-lyrics.json"
        assert lyrics_file.read_text(encoding="utf-8") == '[{"time":1.0,"text":"Hello"}]'
    finally:
        settings.cache_path = original_cache

def test_queue_service_can_persist_media_adjacent_lyrics_sidecar(db_session, tmp_path):
    """Media-library lyrics should be saved next to the media file for scan discovery."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        media_file = settings.media_path / "editable.mp4"
        media_file.write_text("video", encoding="utf-8")

        media = MediaItem(
            title="Editable",
            artist="Singer",
            file_stem="editable",
            media_path="/media/editable.mp4",
            missing=False,
        )
        db_session.add(media)
        db_session.flush()

        service = QueueService()
        service.store_lyrics_sidecar(
            media,
            "[00:01.00]Media lyrics",
            lyrics_format="lrc",
            storage="media",
        )

        assert media.lyrics_path == "/media/editable.lrc"
        assert (settings.media_path / "editable.lrc").read_text(
            encoding="utf-8"
        ) == "[00:01.00]Media lyrics"
    finally:
        settings.media_path = original_media

def test_queue_service_repairs_swapped_vocals_and_infers_sidecar(db_session, tmp_path):
    """If vocals_path stores lyrics, service should recover lyrics and infer *.vocals sidecar."""
    service = QueueService()
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        expected_stem = build_media_stem("Repair Song", "Singer", fallback="repair001")
        media_file = settings.media_path / "repair-song.mp4"
        vocals_file = settings.media_path / "repair-song.vocals.mp3"
        lyrics_file = settings.media_path / "repair-song.lrc"
        media_file.write_text("video", encoding="utf-8")
        vocals_file.write_text("audio", encoding="utf-8")
        lyrics_file.write_text("[00:00.00]hello", encoding="utf-8")

        media = MediaItem(
            youtube_id="repair001",
            title="Repair Song",
            artist="Singer",
            media_path="/media/repair-song.mp4",
            vocals_path="/media/repair-song.lrc",
            lyrics_path=None,
            missing=False,
        )
        db_session.add(media)
        db_session.flush()

        created = service.add_to_queue(
            db_session,
            QueueItemCreate(
                youtube_id="repair001",
                title="Repair Song",
                artist="Singer",
                is_karaoke=False,
            ),
        )

        assert created.vocals_path == f"/media/{expected_stem}.vocals.mp3"
        assert created.lyrics_path == f"/media/{expected_stem}.lrc"
    finally:
        settings.media_path = original_media

def test_queue_service_update_status(db_session):
    """Test updating item status."""
    service = QueueService()
    item = QueueItemCreate(
        youtube_id="test123", title="Test Song", is_karaoke=False
    )
    result = service.add_to_queue(db_session, item)

    # Update status
    service.update_status(db_session, result.id, QueueStatus.READY)

    # Verify
    updated_queue = service.get_queue(db_session)
    assert updated_queue[0].status == QueueStatus.READY

def test_queue_service_skip_current_item_promotes_next_ready(db_session):
    """Test skipping current item promotes next ready item."""
    service = QueueService()
    current = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="play1", title="Current", is_karaoke=False),
    )
    next_item = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="play2", title="Next", is_karaoke=True),
    )

    service.update_status(db_session, current.id, QueueStatus.PLAYING)
    service.update_status(db_session, next_item.id, QueueStatus.READY)

    promoted = service.skip_current_item(db_session)
    assert promoted is not None
    assert promoted.id == next_item.id
    assert promoted.status == QueueStatus.PLAYING

    current_after = (
        db_session.query(QueueItem).filter(QueueItem.id == current.id).first()
    )
    assert current_after is None

def test_queue_service_skip_current_item_without_next_returns_none(db_session):
    """Test skipping current item with no next ready item."""
    service = QueueService()
    current = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="play3", title="Only Song", is_karaoke=False),
    )
    service.update_status(db_session, current.id, QueueStatus.PLAYING)

    promoted = service.skip_current_item(db_session)
    assert promoted is None

    current_after = (
        db_session.query(QueueItem).filter(QueueItem.id == current.id).first()
    )
    assert current_after is None

def test_queue_service_complete_current_promotes_next_ready(db_session):
    """Completing current item should promote next ready item."""
    service = QueueService()
    current = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="c1", title="Current", is_karaoke=False),
    )
    next_item = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="n1", title="Next", is_karaoke=False),
    )

    service.update_status(db_session, current.id, QueueStatus.PLAYING)
    service.update_status(db_session, next_item.id, QueueStatus.READY)

    promoted = service.complete_current_item(db_session)
    assert promoted is not None
    assert promoted.id == next_item.id
    assert promoted.status == QueueStatus.PLAYING

    current_after = (
        db_session.query(QueueItem).filter(QueueItem.id == current.id).first()
    )
    assert current_after is None

def test_queue_service_complete_current_without_next_returns_none(db_session):
    """Completing current item with no ready next item should return none."""
    service = QueueService()
    current = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="only1", title="Only", is_karaoke=False),
    )
    service.update_status(db_session, current.id, QueueStatus.PLAYING)

    promoted = service.complete_current_item(db_session)
    assert promoted is None

    current_after = (
        db_session.query(QueueItem).filter(QueueItem.id == current.id).first()
    )
    assert current_after is None

def test_queue_service_complete_current_promotes_when_none_playing(db_session):
    """If nothing is playing, complete-current still promotes next ready item."""
    service = QueueService()
    next_item = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="r1", title="Ready Next", is_karaoke=False),
    )
    service.update_status(db_session, next_item.id, QueueStatus.READY)

    promoted = service.complete_current_item(db_session)
    assert promoted is not None
    assert promoted.id == next_item.id
    assert promoted.status == QueueStatus.PLAYING

def test_queue_service_add_to_queue_by_media_item_id(db_session):
    """Queue service should support enqueue by existing media_item id."""
    media = MediaItem(
        youtube_id="existing123",
        title="Existing Local",
        artist="Artist",
        media_path="/media/existing123.mp4",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()

    service = QueueService()
    result = service.add_to_queue(
        db_session,
        QueueItemCreate(
            media_item_id=media.id,
            title="Existing Local",
            artist="Artist",
            is_karaoke=False,
        ),
    )

    assert result.media_id == media.id
    assert result.youtube_id == "existing123"

def test_queue_service_ordering_helpers(db_session):
    """Queue ordering helpers should support sparse insertion and renumbering."""
    service = QueueService()
    first = service.add_to_queue(
        db_session, QueueItemCreate(youtube_id="o1", title="One", is_karaoke=False)
    )
    second = service.add_to_queue(
        db_session, QueueItemCreate(youtube_id="o2", title="Two", is_karaoke=False)
    )
    assert first.position == 1000
    assert second.position == 2000

    front_position = service.add_to_front(db_session)
    front_item = QueueItem(
        media_id=(
            db_session.query(QueueItem).filter(QueueItem.id == first.id).first().media_id
        ),
        position=front_position,
        requested_karaoke=False,
        status=QueueStatus.PENDING,
    )
    db_session.add(front_item)
    db_session.commit()
    assert front_item.position < first.position

    between = service.insert_between(db_session, first.position, second.position)
    assert first.position < between < second.position

    first_row = db_session.query(QueueItem).filter(QueueItem.id == first.id).first()
    second_row = db_session.query(QueueItem).filter(QueueItem.id == second.id).first()
    first_row.position = 1000
    second_row.position = 1001
    db_session.commit()
    service.renumber_queue_if_needed(db_session)
    first_row = db_session.query(QueueItem).filter(QueueItem.id == first.id).first()
    second_row = db_session.query(QueueItem).filter(QueueItem.id == second.id).first()
    assert second_row.position - first_row.position == 1000

def test_queue_service_build_media_url_for_media_and_cache(tmp_path):
    """Queue service should map filesystem paths to stable API URLs."""
    service = QueueService()
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.ensure_paths()

        media_file = settings.media_path / "karaoke.webm"
        cache_file = settings.cache_path / "out" / "mix.mp4"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        media_file.write_text("x", encoding="utf-8")
        cache_file.write_text("y", encoding="utf-8")

        assert service.build_media_url(media_file) == "/media/karaoke.webm"
        assert service.build_media_url(cache_file) == "/cache/out/mix.mp4"
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache
