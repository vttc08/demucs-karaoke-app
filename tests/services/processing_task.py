from .common import *



def test_processing_task_cancel_cleans_up_partial_artifacts_and_resets_rows(db_session, tmp_path, monkeypatch):
    """Cancel should remove partial files and reset queue/media rows for retry."""
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    media_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)

    media = MediaItem(
        youtube_id="cancel-me",
        file_stem="cancel-song",
        title="Cancel Song",
        artist="Artist",
        media_path="/media/cancel-song.mp4",
        vocals_path="/media/cancel-song.vocals.wav",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    db_session.refresh(media)

    queue_item = QueueItem(
        media_id=media.id,
        position=1,
        requested_karaoke=False,
        user_id="guest-123",
        status=QueueStatus.DOWNLOADING.value,
        error="temporary failure",
    )
    db_session.add(queue_item)
    db_session.commit()
    db_session.refresh(queue_item)

    task = ProcessingTask(
        task_type="queue_prepare",
        source_kind="youtube",
        target_queue_item_id=queue_item.id,
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.DOWNLOADING.value,
        stage="download",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    media_file = media_root / "cancel-song.mp4"
    vocals_file = media_root / "cancel-song.vocals.wav"
    media_file.write_bytes(b"video")
    vocals_file.write_bytes(b"vocals")
    thumbnail_path = MediaThumbnailService.thumbnail_path_for_media_file(media_file)
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    thumbnail_path.write_bytes(b"thumbnail")

    for root_name in ("ytdlp", "audio", "processed", "demucs_outputs"):
        artifact_root = cache_root / root_name
        artifact_root.mkdir(parents=True, exist_ok=True)
        (artifact_root / "cancel-song.partial").write_bytes(b"partial")

    asyncio.run(processing_task_service.cancel_task(db_session, task.id))
    asyncio.run(task_stream_manager.clear_task(task.id))

    db_session.refresh(task)
    db_session.refresh(queue_item)
    db_session.refresh(media)

    assert task.status == ProcessingTaskStatus.CANCELED.value
    assert task.last_error_summary is None
    assert task.last_error_detail is None
    assert queue_item.status == QueueStatus.PENDING.value
    assert queue_item.error is None
    assert media.missing is True
    assert media.vocals_path is None
    assert not media_file.exists()
    assert not vocals_file.exists()
    assert not thumbnail_path.exists()
    assert not any((cache_root / "ytdlp").glob("cancel-song*"))
    assert not any((cache_root / "audio").glob("cancel-song*"))
    assert not any((cache_root / "processed").glob("cancel-song*"))
    assert not any((cache_root / "demucs_outputs").glob("cancel-song*"))

def test_media_karaoke_cancel_preserves_original_local_media(db_session, tmp_path, monkeypatch):
    """Canceling a local media task should remove scratch files without deleting the upload."""
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    media_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)

    media_file = media_root / "local-cancel.mp4"
    media_file.write_bytes(b"original-video")
    media = MediaItem(
        file_stem="local-cancel",
        title="Local Cancel",
        media_path="/media/local-cancel.mp4",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    db_session.refresh(media)
    task = ProcessingTask(
        task_type="media_karaoke",
        source_kind="library_media",
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.PROCESSING.value,
        stage="demucs",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    scratch_root = cache_root / "audio"
    scratch_root.mkdir(parents=True)
    (scratch_root / "local-cancel.audio.m4a").write_bytes(b"scratch")

    asyncio.run(processing_task_service.cancel_task(db_session, task.id))
    asyncio.run(task_stream_manager.clear_task(task.id))

    db_session.refresh(media)
    assert media_file.read_bytes() == b"original-video"
    assert media.missing is False
    assert media.vocals_path is None
    assert not any(scratch_root.glob("local-cancel*"))

def test_processing_task_cancel_permissions_and_cascade_ids(db_session):
    """Guests should only cancel their own active queue tasks while admins get same-media cascades."""
    service = QueueService()
    owner_queue = service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="cancel-owner",
            title="Owner Song",
            is_karaoke=False,
        ),
        requester_id="guest-owner",
    )
    other_queue = service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="cancel-other",
            title="Other Song",
            is_karaoke=False,
        ),
        requester_id="guest-other",
    )

    owner_task = processing_task_service.get_or_create_queue_task(db_session, owner_queue.id)
    other_task = processing_task_service.get_or_create_queue_task(db_session, other_queue.id)
    asyncio.run(
        processing_task_service.set_stage(
            db_session,
            owner_task.id,
            status=ProcessingTaskStatus.DOWNLOADING,
            stage="download",
        )
    )
    asyncio.run(
        processing_task_service.set_stage(
            db_session,
            other_task.id,
            status=ProcessingTaskStatus.DOWNLOADING,
            stage="download",
        )
    )

    assert processing_task_service.can_cancel_task(
        db_session,
        owner_task,
        requester_id="guest-owner",
    ) is True
    assert processing_task_service.can_cancel_task(
        db_session,
        other_task,
        requester_id="guest-owner",
    ) is False

    media = MediaItem(
        youtube_id="cascade-media",
        file_stem="cascade-media",
        title="Cascade Song",
        media_path="/media/cascade-media.mp4",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    db_session.refresh(media)
    media_queue = QueueItem(
        media_id=media.id,
        position=3,
        requested_karaoke=False,
        status=QueueStatus.DOWNLOADING.value,
    )
    db_session.add(media_queue)
    db_session.commit()
    db_session.refresh(media_queue)
    media_queue_task = ProcessingTask(
        task_type="queue_prepare",
        source_kind="youtube",
        target_queue_item_id=media_queue.id,
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.DOWNLOADING.value,
        stage="download",
    )
    media_follow_on_task = ProcessingTask(
        task_type="media_karaoke",
        source_kind="library_media",
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.PROCESSING.value,
        stage="demucs",
    )
    db_session.add_all([media_queue_task, media_follow_on_task])
    db_session.commit()
    db_session.refresh(media_queue_task)
    db_session.refresh(media_follow_on_task)

    assert processing_task_service.get_cancelable_task_ids(
        db_session,
        media_queue_task,
        is_admin=True,
    ) == [media_queue_task.id, media_follow_on_task.id]

    asyncio.run(processing_task_service.cancel_task(db_session, media_queue_task.id))
    asyncio.run(processing_task_service.cancel_task(db_session, media_follow_on_task.id))
    asyncio.run(task_stream_manager.clear_task(media_queue_task.id))
    asyncio.run(task_stream_manager.clear_task(media_follow_on_task.id))

    db_session.refresh(media_queue_task)
    db_session.refresh(media_follow_on_task)
    db_session.refresh(media_queue)

    assert media_queue_task.status == ProcessingTaskStatus.CANCELED.value
    assert media_follow_on_task.status == ProcessingTaskStatus.CANCELED.value
    assert media_queue.status == QueueStatus.PENDING.value

def test_karaoke_progress_callback_throttles_to_about_once_per_second():
    """yt-dlp progress callbacks should not emit queue updates every tick."""
    service = KaraokeService()
    emitted = []
    fake_future = Mock()
    fake_future.result.return_value = None

    class FakeLoop:
        def __init__(self):
            self.current_time = 0.0

        def time(self):
            return self.current_time

    loop = FakeLoop()

    with patch("services.karaoke_service.asyncio.run_coroutine_threadsafe") as mock_run:
        def capture(coro, target_loop):
            emitted.append(coro)
            coro.close()
            return fake_future

        mock_run.side_effect = capture
        callback = service._progress_callback(
            loop,
            task_id=123,
            label="Downloading media",
            label_key="task.downloading_media",
            step_index=1,
            step_total=2,
            status=ProcessingTaskStatus.DOWNLOADING.value,
            stage="download",
        )

        callback(1, "[download][karaoke-progress] 1.0")
        callback(2, "[download][karaoke-progress] 2.0")
        loop.current_time = 0.5
        callback(3, "[download][karaoke-progress] 3.0")
        loop.current_time = 1.1
        callback(4, "[download][karaoke-progress] 4.0")
        loop.current_time = 1.2
        callback(4, "[download][karaoke-progress] 4.0")
        loop.current_time = 1.3
        callback(100, "[download][karaoke-progress] 100.0")

    assert mock_run.call_count == 3
    assert len(emitted) == 3

def test_karaoke_service_resolves_whisperx_alignment_settings_override():
    """Per-queue-item WhisperX overrides should bypass auto-detect."""
    service = KaraokeService()
    original_align_language = settings.whisperx_align_language
    original_detect_language = settings.whisperx_detect_language
    try:
        settings.whisperx_align_language = "en"
        settings.whisperx_detect_language = True

        override_item = QueueItem(whisperx_align_language_override="JA")
        assert service._resolve_whisperx_alignment_settings(override_item) == ("ja", False)
        assert service._resolve_whisperx_alignment_settings(None) == ("en", True)
    finally:
        settings.whisperx_align_language = original_align_language
        settings.whisperx_detect_language = original_detect_language
