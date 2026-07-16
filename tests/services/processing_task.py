from .common import *
from types import SimpleNamespace


def _write_task_cache_artifacts(cache_root, task_id):
    artifacts = []
    for category in ("ytdlp", "audio", "processed", "demucs_outputs"):
        task_dir = cache_root / category / str(task_id)
        task_dir.mkdir(parents=True)
        artifact = task_dir / "artifact.tmp"
        artifact.write_bytes(b"scratch")
        artifacts.append(artifact)
    return artifacts


@pytest.mark.parametrize("audio_codec,expected_audio_codec", [("", ""), ("aac", "aac")])
def test_process_karaoke_passes_configured_audio_codec_to_ffmpeg(
    db_session,
    tmp_path,
    monkeypatch,
    audio_codec,
    expected_audio_codec,
):
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    media_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)
    monkeypatch.setattr(settings, "ffmpeg_audio_codec", audio_codec)

    media = MediaItem(
        title="Codec Test",
        file_stem="codec-test",
        media_path="/media/codec-test.mp4",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    task = ProcessingTask(
        task_type="media_karaoke",
        source_kind="youtube",
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.PENDING.value,
        stage="queued",
    )
    db_session.add(task)
    db_session.commit()

    service = KaraokeService()
    video_path = cache_root / "input.mp4"
    audio_path = cache_root / "input.wav"
    no_vocals_path = cache_root / "demucs" / "no_vocals.wav"
    vocals_path = cache_root / "demucs" / "vocals.wav"
    video_path.write_bytes(b"video")
    audio_path.write_bytes(b"audio")
    no_vocals_path.parent.mkdir(parents=True, exist_ok=True)
    no_vocals_path.write_bytes(b"no-vocals")
    vocals_path.write_bytes(b"vocals")

    combine_calls = {}

    async def fake_separate_vocals_with_retry(*_args, **_kwargs):
        return SimpleNamespace(
            job_id="demo-job",
            no_vocals_path=str(no_vocals_path),
            vocals_path=str(vocals_path),
            aligned_lyrics_path=None,
        )

    def fake_combine_audio_video(**kwargs):
        combine_calls["kwargs"] = kwargs
        output_path = kwargs["output_path"]
        output_path.write_bytes(b"combined")
        return output_path

    async def fake_noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(service, "_separate_vocals_with_retry", fake_separate_vocals_with_retry)
    monkeypatch.setattr(service.ffmpeg, "combine_audio_video", fake_combine_audio_video)
    monkeypatch.setattr(service, "_install_karaoke_outputs", lambda **kwargs: (media_root / "codec-test.mp4", media_root / "codec-test.vocals.wav"))
    monkeypatch.setattr(service, "_set_media_item_output_paths", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_cleanup_remote_demucs_job", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_raise_if_canceled", fake_noop)
    monkeypatch.setattr(service, "_is_audio_only_media_path", lambda _path: False)
    monkeypatch.setattr(processing_task_service, "set_stage", AsyncMock())
    monkeypatch.setattr(processing_task_service, "emit_progress", AsyncMock())

    asyncio.run(
        service._process_karaoke(
            db_session,
            task,
            queue_item=None,
            media_item=media,
            video_path=video_path,
            audio_path=audio_path,
        )
    )

    assert combine_calls["kwargs"]["audio_codec"] == expected_audio_codec


def test_successful_processing_task_removes_only_its_cache(db_session, tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    media_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)

    media_file = media_root / "ready.mp4"
    media_file.write_bytes(b"ready")
    media = MediaItem(
        title="Ready",
        file_stem="ready",
        media_path="/media/ready.mp4",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    queue_item = QueueItem(
        media_id=media.id,
        position=1,
        requested_karaoke=False,
        status=QueueStatus.PENDING.value,
    )
    db_session.add(queue_item)
    db_session.commit()
    task = ProcessingTask(
        task_type="queue_prepare",
        source_kind="library_media",
        target_queue_item_id=queue_item.id,
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.PENDING.value,
        stage="queued",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    artifacts = _write_task_cache_artifacts(cache_root, task.id)
    other_artifact = cache_root / "processed" / "9999" / "other.tmp"
    other_artifact.parent.mkdir(parents=True)
    other_artifact.write_bytes(b"other")
    legacy_artifact = cache_root / "processed" / "legacy.mp4"
    legacy_artifact.write_bytes(b"legacy")

    asyncio.run(KaraokeService().process_task(db_session, task.id))

    db_session.refresh(task)
    assert task.status == ProcessingTaskStatus.DONE.value
    assert all(not artifact.exists() for artifact in artifacts)
    assert other_artifact.exists()
    assert legacy_artifact.exists()


def test_failed_processing_task_retains_task_cache(db_session, tmp_path, monkeypatch):
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    monkeypatch.setattr(settings, "cache_path", cache_root)
    task = ProcessingTask(
        task_type="unsupported",
        source_kind="youtube",
        status=ProcessingTaskStatus.PENDING.value,
        stage="queued",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    artifacts = _write_task_cache_artifacts(cache_root, task.id)

    asyncio.run(KaraokeService().process_task(db_session, task.id))

    db_session.refresh(task)
    assert task.status == ProcessingTaskStatus.FAILED.value
    assert all(artifact.exists() for artifact in artifacts)


def test_vocal_sync_success_cleanup_preserves_review_cache(tmp_path, monkeypatch):
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    monkeypatch.setattr(settings, "cache_path", cache_root)
    task = ProcessingTask(id=42, task_type="media_vocal_sync_prepare_youtube")
    artifacts = _write_task_cache_artifacts(cache_root, task.id)
    review_file = cache_root / "vocal_sync" / "session" / "manifest.json"
    review_file.parent.mkdir(parents=True)
    review_file.write_text("{}", encoding="utf-8")
    task_manifest = cache_root / "vocal_sync_tasks" / "42.json"
    task_manifest.parent.mkdir(parents=True)
    task_manifest.write_text("{}", encoding="utf-8")

    KaraokeService().cleanup_successful_task(task)

    assert artifacts[3].exists() is False
    assert all(artifact.exists() for artifact in artifacts[:3])
    assert review_file.exists()
    assert task_manifest.exists()


def test_success_cleanup_error_does_not_fail_completed_task(
    db_session, tmp_path, monkeypatch
):
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    media_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)
    media_file = media_root / "ready.mp4"
    media_file.write_bytes(b"ready")
    media = MediaItem(title="Ready", media_path="/media/ready.mp4", missing=False)
    db_session.add(media)
    db_session.commit()
    queue_item = QueueItem(
        media_id=media.id,
        position=1,
        requested_karaoke=False,
        status=QueueStatus.PENDING.value,
    )
    db_session.add(queue_item)
    db_session.commit()
    task = ProcessingTask(
        task_type="queue_prepare",
        source_kind="library_media",
        target_queue_item_id=queue_item.id,
        status=ProcessingTaskStatus.PENDING.value,
        stage="queued",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    _write_task_cache_artifacts(cache_root, task.id)
    monkeypatch.setattr("services.karaoke_service.shutil.rmtree", Mock(side_effect=OSError("busy")))

    asyncio.run(KaraokeService().process_task(db_session, task.id))

    db_session.refresh(task)
    assert task.status == ProcessingTaskStatus.DONE.value


def test_prepare_karaoke_inputs_downloads_audio_when_fresh_video_has_no_audio(
    db_session,
    tmp_path,
    monkeypatch,
):
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    media_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)

    media = MediaItem(
        youtube_id="videoonly123",
        title="Video Only",
        file_stem="video-only",
        media_path="/media/video-only.mp4",
        missing=True,
    )
    db_session.add(media)
    db_session.commit()
    task = ProcessingTask(
        task_type="media_karaoke",
        source_kind="youtube",
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.PENDING.value,
        stage="queued",
    )
    db_session.add(task)
    db_session.commit()

    service = KaraokeService()
    downloaded_video = cache_root / "ytdlp" / str(task.id) / "videoonly123.mp4"
    downloaded_audio = cache_root / "ytdlp" / str(task.id) / "videoonly123.audio.m4a"

    def fake_download_video(*_args, **_kwargs):
        downloaded_video.parent.mkdir(parents=True, exist_ok=True)
        downloaded_video.write_bytes(b"video")
        return downloaded_video

    def fake_download_audio(*_args, **_kwargs):
        downloaded_audio.parent.mkdir(parents=True, exist_ok=True)
        downloaded_audio.write_bytes(b"audio")
        return downloaded_audio

    monkeypatch.setattr(service, "_download_video_for_task", fake_download_video)
    monkeypatch.setattr(service, "_download_audio_for_task", fake_download_audio)
    monkeypatch.setattr(service.ffmpeg, "has_audio_stream", lambda _path: False)

    video_path, audio_path = asyncio.run(
        service._prepare_karaoke_inputs(
            db_session,
            task,
            media,
            existing_media_path=None,
        )
    )

    assert video_path.name == "video-only.mp4"
    assert audio_path.name == "video-only.audio.m4a"
    assert video_path.exists()
    assert audio_path.exists()


def test_prepare_karaoke_inputs_uses_direct_downloaded_video_when_audio_present(
    db_session,
    tmp_path,
    monkeypatch,
):
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    media_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)
    monkeypatch.setattr(settings, "demucs_direct_media_max_mb", 500)

    media = MediaItem(
        youtube_id="audioyes123",
        title="Audio Yes",
        file_stem="audio-yes",
        media_path="/media/audio-yes.mp4",
        missing=True,
    )
    db_session.add(media)
    db_session.commit()
    task = ProcessingTask(
        task_type="media_karaoke",
        source_kind="youtube",
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.PENDING.value,
        stage="queued",
    )
    db_session.add(task)
    db_session.commit()

    service = KaraokeService()
    downloaded_video = cache_root / "ytdlp" / str(task.id) / "audioyes123.mp4"

    def fake_download_video(*_args, **_kwargs):
        downloaded_video.parent.mkdir(parents=True, exist_ok=True)
        downloaded_video.write_bytes(b"video-with-audio")
        return downloaded_video

    monkeypatch.setattr(service, "_download_video_for_task", fake_download_video)
    monkeypatch.setattr(
        service,
        "_download_audio_for_task",
        Mock(side_effect=AssertionError("audio download should not run")),
    )
    monkeypatch.setattr(service.ffmpeg, "has_audio_stream", lambda _path: True)
    monkeypatch.setattr(service.ffmpeg, "has_video_stream", lambda _path: True)

    video_path, audio_path = asyncio.run(
        service._prepare_karaoke_inputs(
            db_session,
            task,
            media,
            existing_media_path=None,
        )
    )

    assert video_path == audio_path
    assert video_path.name == "audio-yes.mp4"


def test_prepare_karaoke_inputs_downloads_audio_for_existing_youtube_video_without_audio(
    db_session,
    tmp_path,
    monkeypatch,
):
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    media_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)

    existing_video = media_root / "flowers.mp4"
    existing_video.write_bytes(b"video")
    media = MediaItem(
        youtube_id="G7KNmW9a75Y",
        title="Flowers",
        artist="Miley Cyrus",
        file_stem="Miley Cyrus - Flowers",
        media_path="/media/flowers.mp4",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    task = ProcessingTask(
        task_type="media_karaoke",
        source_kind="youtube",
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.PENDING.value,
        stage="queued",
    )
    db_session.add(task)
    db_session.commit()

    service = KaraokeService()
    downloaded_audio = cache_root / "ytdlp" / str(task.id) / "G7KNmW9a75Y.audio.m4a"

    def fake_download_audio(*_args, **_kwargs):
        downloaded_audio.parent.mkdir(parents=True, exist_ok=True)
        downloaded_audio.write_bytes(b"audio")
        return downloaded_audio

    monkeypatch.setattr(service.ffmpeg, "has_audio_stream", lambda _path: False)
    monkeypatch.setattr(
        service.ffmpeg,
        "extract_audio",
        Mock(side_effect=AssertionError("extract_audio should not run")),
    )
    monkeypatch.setattr(service, "_download_audio_for_task", fake_download_audio)

    video_path, audio_path = asyncio.run(
        service._prepare_karaoke_inputs(
            db_session,
            task,
            media,
            existing_media_path=existing_video,
        )
    )

    assert video_path == existing_video
    assert audio_path.name == "Miley Cyrus - Flowers.audio.m4a"
    assert audio_path.exists()


def test_prepare_karaoke_inputs_rejects_local_video_without_audio(
    db_session,
    tmp_path,
    monkeypatch,
):
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    media_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)

    existing_video = media_root / "silent.mp4"
    existing_video.write_bytes(b"video")
    media = MediaItem(
        title="Silent",
        file_stem="silent",
        media_path="/media/silent.mp4",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    task = ProcessingTask(
        task_type="media_karaoke",
        source_kind="library_media",
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.PENDING.value,
        stage="queued",
    )
    db_session.add(task)
    db_session.commit()

    service = KaraokeService()
    monkeypatch.setattr(service.ffmpeg, "has_audio_stream", lambda _path: False)

    with pytest.raises(RuntimeError, match="no audio stream"):
        asyncio.run(
            service._prepare_karaoke_inputs(
                db_session,
                task,
                media,
                existing_media_path=existing_video,
            )
        )



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


def test_processing_task_retry_accepts_failed_and_canceled_tasks(db_session):
    """Retry should move terminal failed/canceled tasks back to pending."""
    media = MediaItem(
        title="Retry Media",
        file_stem="retry-media",
        media_path="/media/retry-media.mp4",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    db_session.refresh(media)

    failed_task = ProcessingTask(
        task_type="media_karaoke",
        source_kind="library_media",
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.FAILED.value,
        stage="demucs",
        last_error_summary="remote failed",
        last_error_detail="remote detail",
        started_at=datetime(2026, 1, 1),
        finished_at=datetime(2026, 1, 2),
    )
    canceled_task = ProcessingTask(
        task_type="media_lyrics_align",
        source_kind="library_media",
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.CANCELED.value,
        stage="demucs",
        last_error_summary="old error",
        last_error_detail="old detail",
        started_at=datetime(2026, 1, 3),
        finished_at=datetime(2026, 1, 4),
    )
    db_session.add_all([failed_task, canceled_task])
    db_session.commit()
    db_session.refresh(failed_task)
    db_session.refresh(canceled_task)

    asyncio.run(
        processing_task_service.emit_progress(
            canceled_task.id,
            progress_percent=95,
            progress_label="Canceled",
            status=ProcessingTaskStatus.CANCELED.value,
            stage="demucs",
        )
    )

    asyncio.run(processing_task_service.retry_task(db_session, failed_task.id))
    asyncio.run(processing_task_service.retry_task(db_session, canceled_task.id))

    db_session.refresh(failed_task)
    db_session.refresh(canceled_task)
    canceled_snapshot = task_stream_manager.snapshot_now(canceled_task.id)

    for task in (failed_task, canceled_task):
        assert task.status == ProcessingTaskStatus.PENDING.value
        assert task.stage == "queued"
        assert task.last_error_summary is None
        assert task.last_error_detail is None
        assert task.started_at is None
        assert task.finished_at is None

    assert canceled_snapshot is not None
    assert canceled_snapshot["status"] == ProcessingTaskStatus.PENDING.value
    assert canceled_snapshot["stage"] == "queued"
    assert canceled_snapshot["progress_percent"] is None

    asyncio.run(task_stream_manager.clear_task(failed_task.id))
    asyncio.run(task_stream_manager.clear_task(canceled_task.id))


def test_processing_task_retry_rejects_active_and_done_tasks_even_for_admin(db_session):
    """Retry is limited to failed/canceled terminal tasks."""
    tasks = [
        ProcessingTask(
            task_type="media_karaoke",
            source_kind="library_media",
            target_media_item_id=1,
            status=status.value,
            stage=status.value,
        )
        for status in (
            ProcessingTaskStatus.PENDING,
            ProcessingTaskStatus.DOWNLOADING,
            ProcessingTaskStatus.PROCESSING,
            ProcessingTaskStatus.DONE,
        )
    ]
    db_session.add_all(tasks)
    db_session.commit()

    for task in tasks:
        db_session.refresh(task)
        assert processing_task_service.can_retry_task(
            db_session,
            task,
            is_admin=True,
        ) is False
        with pytest.raises(ValueError, match="Only failed or canceled tasks can be retried"):
            asyncio.run(processing_task_service.retry_task(db_session, task.id))


def test_processing_task_retry_and_delete_require_owner_for_guests(db_session):
    """Guests should only retry or delete their own failed queue-backed tasks."""
    service = QueueService()
    media = MediaItem(
        title="Guest Managed Task",
        file_stem="guest-managed-task",
        media_path="/media/guest-managed-task.mp4",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    db_session.refresh(media)

    owned_queue = service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="guest-managed-task",
            title="Guest Managed Task",
            is_karaoke=False,
        ),
        requester_id="guest-owner",
    )
    other_queue = service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="guest-managed-task-other",
            title="Guest Managed Task Other",
            is_karaoke=False,
        ),
        requester_id="guest-other",
    )

    owned_task = ProcessingTask(
        task_type="queue_prepare",
        source_kind="youtube",
        target_queue_item_id=owned_queue.id,
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.FAILED.value,
        stage="failed",
    )
    other_task = ProcessingTask(
        task_type="queue_prepare",
        source_kind="youtube",
        target_queue_item_id=other_queue.id,
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.FAILED.value,
        stage="failed",
    )
    db_session.add_all([owned_task, other_task])
    db_session.commit()
    db_session.refresh(owned_task)
    db_session.refresh(other_task)

    assert processing_task_service.can_retry_task(
        db_session,
        owned_task,
        requester_id="guest-owner",
    ) is True
    assert processing_task_service.can_retry_task(
        db_session,
        other_task,
        requester_id="guest-owner",
    ) is False
    assert processing_task_service.can_delete_task(
        db_session,
        owned_task,
        requester_id="guest-owner",
    ) is True
    assert processing_task_service.can_delete_task(
        db_session,
        other_task,
        requester_id="guest-owner",
    ) is False


def test_task_execution_coordinator_cancel_sets_event_without_canceling_async_task():
    """Remote Demucs cleanup relies on cooperative cancel_event handling."""
    from services.processing_task_service import TaskExecutionCoordinator

    coordinator = TaskExecutionCoordinator()
    cancel_event = threading.Event()
    fake_task = Mock()
    fake_task.done.return_value = False
    fake_loop = Mock()
    coordinator._task_contexts[123] = {
        "cancel_event": cancel_event,
        "loop": fake_loop,
        "task": fake_task,
    }

    assert coordinator.cancel(123) is True

    assert cancel_event.is_set() is True
    fake_loop.call_soon_threadsafe.assert_not_called()


def test_task_execution_coordinator_bounds_parallel_workers(monkeypatch):
    from services.processing_task_service import TaskExecutionCoordinator

    coordinator = TaskExecutionCoordinator(max_workers=2)
    release = threading.Event()
    two_started = threading.Event()
    started: list[int] = []
    started_lock = threading.Lock()

    def fake_run(task_id):
        with started_lock:
            started.append(task_id)
            if len(started) == 2:
                two_started.set()
        release.wait(timeout=2)

    monkeypatch.setattr(coordinator, "_run_task", fake_run)
    try:
        coordinator.start(1)
        coordinator.start(2)
        coordinator.start(3)
        assert two_started.wait(timeout=1)
        with started_lock:
            assert len(started) == 2
        release.set()
    finally:
        release.set()
        coordinator.shutdown(wait=True)


@pytest.mark.asyncio
async def test_task_stream_cross_thread_delivery_is_bounded():
    from services.task_stream_service import TaskStreamManager

    stream = TaskStreamManager(subscriber_queue_size=2)
    subscriber = await stream.register_summary_subscriber()

    def publish_from_worker():
        async def publish_all():
            for percent in (10, 20, 30):
                await stream.publish(
                    99,
                    event_type="progress",
                    progress_percent=percent,
                )

        asyncio.run(publish_all())

    await asyncio.to_thread(publish_from_worker)
    await asyncio.sleep(0)
    assert subscriber.qsize() == 2
    assert (await subscriber.get())["progress_percent"] == 20
    assert (await subscriber.get())["progress_percent"] == 30


@pytest.mark.asyncio
async def test_task_stream_summary_omits_log_only_events():
    from services.task_stream_service import TaskStreamManager

    stream = TaskStreamManager()
    subscriber = await stream.register_summary_subscriber()
    await stream.publish(5, event_type="log", message="verbose line")
    await asyncio.sleep(0)
    assert subscriber.empty()


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


def test_demucs_progress_callback_maps_whisperx_checkpoint_mode(monkeypatch):
    service = KaraokeService()
    emitted = []

    async def noop():
        return None

    def fake_emit_progress(*args, **kwargs):
        emitted.append(kwargs)
        return noop()

    def close_coroutine(loop, coroutine):
        coroutine.close()

    monkeypatch.setattr(processing_task_service, "emit_progress", fake_emit_progress)
    monkeypatch.setattr(KaraokeService, "_dispatch_loop_coroutine", staticmethod(close_coroutine))

    class FakeLoop:
        def time(self):
            return 1.0

    callback = service._demucs_progress_callback(
        FakeLoop(),
        task_id=123,
        step_index=3,
        step_total=4,
        status=ProcessingTaskStatus.PROCESSING.value,
        stage="demucs",
        queue_item_id=456,
        has_whisperx=True,
    )

    callback(
        5,
        "whisperx_loading_audio",
        {
            "job_id": "remote-job",
            "progress_stage": "whisperx",
            "progress_mode": "indeterminate",
        },
    )

    assert emitted[-1]["stage"] == "whisperx"
    assert emitted[-1]["progress_label_key"] == "task.whisperx_loading_audio"
    assert emitted[-1]["progress_mode"] == "indeterminate"


def test_demucs_progress_callback_preserves_indeterminate_separation(monkeypatch):
    emitted = []

    async def noop():
        return None

    monkeypatch.setattr(
        processing_task_service,
        "emit_progress",
        lambda *args, **kwargs: (emitted.append(kwargs), noop())[1],
    )
    monkeypatch.setattr(
        KaraokeService,
        "_dispatch_loop_coroutine",
        staticmethod(lambda loop, coroutine: coroutine.close()),
    )

    callback = KaraokeService()._demucs_progress_callback(
        SimpleNamespace(time=lambda: 1.0),
        task_id=123,
        step_index=2,
        step_total=3,
        status=ProcessingTaskStatus.PROCESSING.value,
        stage="demucs",
    )
    callback(
        0,
        "Running Sherpa+Spleeter",
        {
            "job_id": "sherpa-job",
            "progress_stage": "separation",
            "progress_mode": "indeterminate",
        },
    )

    assert emitted[-1]["stage"] == "separation"
    assert emitted[-1]["progress_mode"] == "indeterminate"
    assert emitted[-1]["progress_label_key"] == "task.separating_vocals"


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
        assert service._resolve_whisperx_alignment_settings(
            whisperx_align_language_override="ZH"
        ) == ("zh", False)
        assert service._resolve_whisperx_alignment_settings(None) == ("en", True)
    finally:
        settings.whisperx_align_language = original_align_language
        settings.whisperx_detect_language = original_detect_language


def test_karaoke_alignment_requires_json_before_replacing_media(db_session, tmp_path, monkeypatch):
    """Old Demucs services that return stems without aligned JSON must not replace media."""
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    media_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)

    original_media = media_root / "original.mp3"
    original_media.write_bytes(b"original")
    lyrics_file = media_root / "align-song.lrc"
    lyrics_file.write_text("[00:01.00]Line", encoding="utf-8")
    no_vocals = cache_root / "demucs_outputs" / "no_vocals.wav"
    vocals = cache_root / "demucs_outputs" / "vocals.wav"
    no_vocals.parent.mkdir(parents=True, exist_ok=True)
    no_vocals.write_bytes(b"no vocals")
    vocals.write_bytes(b"vocals")

    media = MediaItem(
        title="Align Song",
        artist="Singer",
        file_stem="align-song",
        media_path="/media/original.mp3",
        lyrics_path="/media/align-song.lrc",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    db_session.refresh(media)

    task = ProcessingTask(
        task_type="media_karaoke_align",
        source_kind="library_media",
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.PENDING.value,
        stage="queued",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    service = KaraokeService()
    service.demucs_client.separate_vocals = AsyncMock(
        return_value=DemucsResponse(
            no_vocals_path=str(no_vocals),
            vocals_path=str(vocals),
            aligned_lyrics_path=None,
        )
    )

    with pytest.raises(RuntimeError, match="missing aligned lyrics"):
        asyncio.run(
            service._process_karaoke(
                db_session,
                task,
                queue_item=None,
                media_item=media,
                video_path=original_media,
                audio_path=original_media,
                align_lyrics=True,
            )
        )

    db_session.refresh(media)
    assert original_media.exists()
    assert media.media_path == "/media/original.mp3"
    assert media.lyrics_path == "/media/align-song.lrc"
    assert not (media_root / "align-song.wav").exists()
    assert not (media_root / "align-song.vocals.wav").exists()
    assert not (media_root / "align-song.json").exists()


def test_process_karaoke_success_deletes_remote_demucs_job(db_session, tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    media_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)

    source_media = media_root / "source.mp3"
    source_media.write_bytes(b"source")
    no_vocals = cache_root / "demucs_outputs" / "1" / "no_vocals.wav"
    vocals = cache_root / "demucs_outputs" / "1" / "vocals.wav"
    no_vocals.parent.mkdir(parents=True, exist_ok=True)
    no_vocals.write_bytes(b"no vocals")
    vocals.write_bytes(b"vocals")

    media = MediaItem(title="Song", file_stem="song", media_path="/media/source.mp3", missing=False)
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

    service = KaraokeService()
    service._separate_vocals_with_retry = AsyncMock(
        return_value=DemucsResponse(
            job_id="job-success",
            no_vocals_path=str(no_vocals),
            vocals_path=str(vocals),
        )
    )
    service.demucs_client.delete_job_artifacts = Mock()

    with patch.object(processing_task_service, "set_stage", AsyncMock()), patch.object(
        processing_task_service, "emit_progress", AsyncMock()
    ), patch.object(processing_task_service, "set_status", AsyncMock()):
        asyncio.run(
            service._process_karaoke(
                db_session,
                task,
                queue_item=None,
                media_item=media,
                video_path=source_media,
                audio_path=source_media,
            )
        )

    service.demucs_client.delete_job_artifacts.assert_called_once_with("job-success")


def test_process_karaoke_failure_before_done_keeps_remote_demucs_job(db_session, tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    media_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)

    source_media = media_root / "source.mp3"
    source_media.write_bytes(b"source")
    no_vocals = cache_root / "demucs_outputs" / "1" / "no_vocals.wav"
    vocals = cache_root / "demucs_outputs" / "1" / "vocals.wav"
    no_vocals.parent.mkdir(parents=True, exist_ok=True)
    no_vocals.write_bytes(b"no vocals")
    vocals.write_bytes(b"vocals")

    media = MediaItem(title="Song", file_stem="song", media_path="/media/source.mp3", missing=False)
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

    service = KaraokeService()
    service._separate_vocals_with_retry = AsyncMock(
        return_value=DemucsResponse(
            job_id="job-failure",
            no_vocals_path=str(no_vocals),
            vocals_path=str(vocals),
        )
    )
    service.demucs_client.delete_job_artifacts = Mock()

    with patch.object(processing_task_service, "set_stage", AsyncMock()), patch.object(
        processing_task_service, "emit_progress", AsyncMock()
    ), patch.object(service, "_install_karaoke_outputs", side_effect=RuntimeError("copy failed")):
        with pytest.raises(RuntimeError, match="copy failed"):
            asyncio.run(
                service._process_karaoke(
                    db_session,
                    task,
                    queue_item=None,
                    media_item=media,
                    video_path=source_media,
                    audio_path=source_media,
                )
            )

    service.demucs_client.delete_job_artifacts.assert_not_called()


def test_alignment_cancel_cleanup_preserves_durable_media(db_session, tmp_path, monkeypatch):
    """Alignment task cleanup should remove scratch files only, not library media."""
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    media_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)

    media_file = media_root / "align-song.mp3"
    vocals_file = media_root / "align-song.vocals.wav"
    lyrics_file = media_root / "align-song.lrc"
    media_file.write_bytes(b"media")
    vocals_file.write_bytes(b"vocals")
    lyrics_file.write_text("[00:01.00]Line", encoding="utf-8")

    media = MediaItem(
        title="Align Song",
        artist="Singer",
        file_stem="align-song",
        media_path="/media/align-song.mp3",
        vocals_path="/media/align-song.vocals.wav",
        lyrics_path="/media/align-song.lrc",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    db_session.refresh(media)

    task = ProcessingTask(
        task_type="media_karaoke_align",
        source_kind="uploaded_media",
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.PROCESSING.value,
        stage="demucs",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    for root_name in ("ytdlp", "audio", "processed", "demucs_outputs"):
        artifact_root = cache_root / root_name
        artifact_root.mkdir(parents=True, exist_ok=True)
        (artifact_root / "align-song.partial").write_bytes(b"partial")

    temp_output = media_root / f".align-song.{task.id}.primary.tmp.wav"
    temp_output.write_bytes(b"temp")

    KaraokeService().cleanup_canceled_task(db_session, task)
    db_session.refresh(media)

    assert media_file.exists()
    assert vocals_file.exists()
    assert lyrics_file.exists()
    assert media.missing is False
    assert media.vocals_path == "/media/align-song.vocals.wav"
    assert not temp_output.exists()
    for root_name in ("ytdlp", "audio", "processed", "demucs_outputs"):
        assert not (cache_root / root_name / "align-song.partial").exists()
