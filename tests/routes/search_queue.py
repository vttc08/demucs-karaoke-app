from .common import *


TTML_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<tt xmlns="http://www.w3.org/ns/ttml" xmlns:itunes="http://music.apple.com/lyrics">
  <body>
    <div itunes:song-part="Verse">
      <p begin="00:00:15.053" end="00:00:20.562">
        <span begin="00:00:15.053" end="00:00:15.522">I </span>
        <span begin="00:00:15.522" end="00:00:16.021">know </span>
        <span begin="00:00:16.021" end="00:00:16.437">that </span>
        <span begin="00:00:16.437" end="00:00:16.704">the </span>
        <span begin="00:00:16.704" end="00:00:17.104">bar </span>
        <span begin="00:00:17.104" end="00:00:17.789">closes </span>
        <span begin="00:00:17.789" end="00:00:18.256">at </span>
        <span begin="00:00:18.256" end="00:00:20.562">11</span>
      </p>
    </div>
  </body>
</tt>
"""


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_search_youtube_marks_downloaded_results(client):
    """Search API should include downloaded markers when library rows exist."""
    with patch("routes.search.youtube_service.search") as mock_search:
        mock_search.return_value = [
            {
                "video_id": "saved123",
                "title": "Already Saved",
                "channel": "Library",
                "duration": "2:00",
                "thumbnail": "https://i.ytimg.com/vi/saved123/hqdefault.jpg",
                "downloaded": True,
            }
        ]
        response = client.get("/api/search/?q=saved123")

    assert response.status_code == 200
    data = response.json()
    assert data[0]["downloaded"] is True
    mock_search.assert_called_once()
    assert "db" in mock_search.call_args.kwargs

def test_search_with_source_local_filter(client):
    """Search with source=local should only call search with source filter."""
    with patch("routes.search.youtube_service.search") as mock_search:
        mock_search.return_value = [
            {
                "source": "local",
                "media_item_id": 1,
                "video_id": None,
                "title": "Local Song",
                "channel": "Local Artist",
                "duration": None,
                "thumbnail": None,
                "downloaded": True,
            }
        ]
        response = client.get("/api/search/?q=test&source=local")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["source"] == "local"
    assert data[0]["media_item_id"] == 1
    mock_search.assert_called_once()
    # Verify source parameter was passed
    call_kwargs = mock_search.call_args.kwargs
    assert call_kwargs.get("source") == "local"

def test_search_with_source_youtube_filter(client):
    """Search with source=youtube should only call search with source filter."""
    with patch("routes.search.youtube_service.search") as mock_search:
        mock_search.return_value = [
            {
                "source": "youtube",
                "media_item_id": None,
                "video_id": "yt123",
                "title": "YouTube Song",
                "channel": "YouTube Channel",
                "duration": "3:45",
                "thumbnail": "https://example.com/thumb.jpg",
                "downloaded": False,
            }
        ]
        response = client.get("/api/search/?q=test&source=youtube")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["source"] == "youtube"
    assert data[0]["video_id"] == "yt123"
    mock_search.assert_called_once()
    # Verify source parameter was passed
    call_kwargs = mock_search.call_args.kwargs
    assert call_kwargs.get("source") == "youtube"

def test_search_with_invalid_source_returns_error(client):
    """Search with invalid source parameter should return 400 error."""
    response = client.get("/api/search/?q=test&source=invalid")
    assert response.status_code == 400
    data = response.json()
    assert "source must be" in data["detail"].lower()

def test_search_without_source_returns_mixed(client):
    """Search without source parameter should return mixed results (default behavior)."""
    with patch("routes.search.youtube_service.search") as mock_search:
        mock_search.return_value = [
            {
                "source": "local",
                "media_item_id": 1,
                "video_id": None,
                "title": "Local Song",
                "channel": "Local Artist",
                "duration": None,
                "thumbnail": None,
                "downloaded": True,
            },
            {
                "source": "youtube",
                "media_item_id": None,
                "video_id": "yt123",
                "title": "YouTube Song",
                "channel": "YouTube Channel",
                "duration": "4:00",
                "thumbnail": "https://example.com/thumb.jpg",
                "downloaded": False,
            },
        ]
        response = client.get("/api/search/?q=test")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["source"] == "local"
    assert data[1]["source"] == "youtube"
    mock_search.assert_called_once()
    # Verify source parameter was None (default)
    call_kwargs = mock_search.call_args.kwargs
    assert call_kwargs.get("source") is None

def test_add_to_queue(client):
    """Test adding item to queue."""
    response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "test123",
            "title": "Test Song",
            "artist": "Test Artist",
            "is_karaoke": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["youtube_id"] == "test123"
    assert data["title"] == "Test Song"
    assert data["is_karaoke"] is True
    assert data["status"] == "pending"

def test_add_to_queue_persists_whisperx_language_override(client):
    """Queue items should persist a per-song WhisperX language override."""
    response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "test456",
            "title": "Override Song",
            "artist": "Test Artist",
            "is_karaoke": True,
            "whisperx_align_language_override": "JA",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["whisperx_align_language_override"] == "ja"

    with TestingSessionLocal() as db:
        stored = db.query(QueueItem).filter(QueueItem.id == data["id"]).first()

    assert stored is not None
    assert stored.whisperx_align_language_override == "ja"


def test_add_to_queue_persists_line_processing_settings(client):
    response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "lineproc123",
            "title": "Wrapped Song",
            "artist": "Test Artist",
            "is_karaoke": True,
            "align_lyrics": True,
            "process_lyrics_lines": True,
            "max_line_length": 40,
            "max_line_length_cjk": 14,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["process_lyrics_lines"] is True
    assert data["max_line_length"] == 40
    assert data["max_line_length_cjk"] == 14

    with TestingSessionLocal() as db:
        stored = db.query(QueueItem).filter(QueueItem.id == data["id"]).first()

    assert stored is not None
    assert stored.process_lyrics_lines is True
    assert stored.max_line_length == 40
    assert stored.max_line_length_cjk == 14


def test_add_to_queue_ignores_line_processing_lengths_when_disabled(client):
    response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "lineproc-off",
            "title": "Wrapped Song Off",
            "process_lyrics_lines": False,
            "max_line_length": -5,
            "max_line_length_cjk": 0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["process_lyrics_lines"] is False
    assert data["max_line_length"] is None
    assert data["max_line_length_cjk"] is None


def test_add_to_queue_rejects_invalid_line_processing_lengths(client):
    response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "lineproc-bad",
            "title": "Wrapped Song Bad",
            "process_lyrics_lines": True,
            "max_line_length": 0,
            "max_line_length_cjk": 14,
        },
    )
    assert response.status_code == 422

def test_process_queue_item_returns_task_id(client):
    """Queue processing trigger should create or reuse a durable task id."""
    client.cookies.set("karaoke_guest_id", "task-owner")
    queue_response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "task123",
            "title": "Task Song",
            "is_karaoke": False,
        },
    )
    item_id = queue_response.json()["id"]

    with patch("routes.queue.task_execution_coordinator.start") as mock_start:
        response = client.post(f"/api/queue/{item_id}/process")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "processing"
    assert isinstance(payload["task_id"], int)
    mock_start.assert_called_once_with(payload["task_id"])

def test_process_queue_item_restarts_existing_active_task(client):
    """Queue processing trigger should still hand active durable tasks to the coordinator."""
    client.cookies.set("karaoke_guest_id", "active-task-owner")
    queue_response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "active-task123",
            "title": "Active Task Song",
            "is_karaoke": False,
        },
    )
    item_id = queue_response.json()["id"]

    with TestingSessionLocal() as db:
        queue_item = db.query(QueueItem).filter(QueueItem.id == item_id).first()
        assert queue_item is not None
        queue_item.status = QueueStatus.DOWNLOADING.value
        db.add(
            ProcessingTask(
                task_type="queue_prepare",
                source_kind="youtube",
                target_queue_item_id=item_id,
                target_media_item_id=queue_item.media_id,
                status=ProcessingTaskStatus.DOWNLOADING.value,
                stage="download",
            )
        )
        db.commit()

    with patch("routes.queue.task_execution_coordinator.start") as mock_start:
        response = client.post(f"/api/queue/{item_id}/process")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "processing"
    assert isinstance(payload["task_id"], int)
    mock_start.assert_called_once_with(payload["task_id"])


def test_process_queue_item_rejects_a_different_guest(client):
    client.cookies.set("karaoke_guest_id", "queue-owner")
    item_id = client.post(
        "/api/queue/",
        json={"youtube_id": "owned-process", "title": "Owned Process"},
    ).json()["id"]
    client.cookies.set("karaoke_guest_id", "other-guest")

    response = client.post(f"/api/queue/{item_id}/process")

    assert response.status_code == 403

def test_media_karaoke_route_creates_task(client, tmp_path):
    """Admin media karaoke trigger should create a durable media task."""
    authenticate_admin_client(client)
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        (settings.media_path / "local-track.mp4").write_bytes(b"video")
        with TestingSessionLocal() as db:
            media_item = MediaItem(
                title="Local Track",
                artist="Singer",
                file_stem="local-track",
                media_path="/media/local-track.mp4",
                missing=False,
            )
            db.add(media_item)
            db.commit()
            db.refresh(media_item)
            media_id = media_item.id

        healthy = DemucsHealthResponse(api_url="http://demucs", healthy=True, detail="ok")
        with (
            patch(
                "routes.media_library.runtime_settings_service.get_demucs_health",
                return_value=healthy,
            ),
            patch("routes.media_library.task_execution_coordinator.start") as mock_start,
        ):
            response = client.post(f"/api/media/{media_id}/karaoke")

        assert response.status_code == 200
        payload = response.json()
        assert payload["media_id"] == media_id
        assert isinstance(payload["task_id"], int)
        mock_start.assert_called_once_with(payload["task_id"])
    finally:
        settings.media_path = original_media

def test_media_karaoke_route_rejects_existing_multitrack(client, tmp_path):
    """Existing vocals sidecars should prevent duplicate karaoke tasks."""
    authenticate_admin_client(client)
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        (settings.media_path / "ready.mp4").write_bytes(b"video")
        (settings.media_path / "ready.vocals.wav").write_bytes(b"vocals")
        with TestingSessionLocal() as db:
            media = MediaItem(
                title="Ready",
                media_path="/media/ready.mp4",
                vocals_path="/media/ready.vocals.wav",
                missing=False,
            )
            db.add(media)
            db.commit()
            media_id = media.id

        response = client.post(f"/api/media/{media_id}/karaoke")

        assert response.status_code == 409
        assert "already multi-track" in response.json()["detail"]
    finally:
        settings.media_path = original_media

def test_tasks_api_lists_active_tasks(client):
    """Admin tasks API should include durable task rows."""
    authenticate_admin_client(client)
    with TestingSessionLocal() as db:
        media_item = MediaItem(
            title="Task Media",
            artist="Artist",
            file_stem="task-media",
            media_path="/media/task-media.mp4",
            missing=False,
        )
        db.add(media_item)
        db.flush()
        task = ProcessingTask(
            task_type="media_karaoke",
            source_kind="library_media",
            target_media_item_id=media_item.id,
            status=ProcessingTaskStatus.PENDING.value,
            stage="queued",
        )
        db.add(task)
        db.commit()
        task_id = task.id

    asyncio.run(
        processing_task_service.emit_progress(
            task_id,
            progress_percent=57,
            progress_label="Downloading video",
            progress_label_key="task.downloading_video",
            progress_step_index=1,
            progress_step_total=4,
            status=ProcessingTaskStatus.DOWNLOADING.value,
            stage="download",
        )
    )

    response = client.get("/api/tasks/")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["task_type"] == "media_karaoke"
    assert payload[0]["status"] == "pending"
    assert payload[0]["live"]["progress_percent"] == 57
    assert payload[0]["live"]["progress_label_key"] == "task.downloading_video"
    assert payload[0]["live"]["progress_step_index"] == 1
    assert payload[0]["live"]["progress_step_total"] == 4
    asyncio.run(task_stream_manager.clear_task(task_id))

def test_tasks_stream_route_returns_sse_snapshot(client):
    """Task summary stream should resolve to the SSE route, not the task-id route."""
    response = client.get("/api/tasks/stream")

    assert response.status_code in {401, 403}
    assert response.status_code != 422

def test_cancel_task_route_admin_cancels_same_media_tasks(client):
    """Admins should be able to cancel a task and its same-media follow-on tasks."""
    authenticate_admin_client(client)

    with TestingSessionLocal() as db:
        media = MediaItem(
            youtube_id="route-cancel-media",
            file_stem="route-cancel-media",
            title="Route Cancel Song",
            media_path="/media/route-cancel-media.mp4",
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)

        queue_item = QueueItem(
            media_id=media.id,
            position=1,
            requested_karaoke=False,
            status=QueueStatus.DOWNLOADING.value,
        )
        db.add(queue_item)
        db.commit()
        db.refresh(queue_item)

        queue_task = ProcessingTask(
            task_type="queue_prepare",
            source_kind="youtube",
            target_queue_item_id=queue_item.id,
            target_media_item_id=media.id,
            status=ProcessingTaskStatus.DOWNLOADING.value,
            stage="download",
        )
        follow_on_task = ProcessingTask(
            task_type="media_karaoke",
            source_kind="library_media",
            target_media_item_id=media.id,
            status=ProcessingTaskStatus.PROCESSING.value,
            stage="demucs",
        )
        db.add_all([queue_task, follow_on_task])
        db.commit()
        db.refresh(queue_task)
        db.refresh(follow_on_task)
        media_id = media.id
        queue_item_id = queue_item.id
        queue_task_id = queue_task.id
        follow_on_task_id = follow_on_task.id

    response = client.post(f"/api/tasks/{queue_task_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "canceled"

    with TestingSessionLocal() as db:
        refreshed_queue_task = db.query(ProcessingTask).filter(ProcessingTask.id == queue_task_id).first()
        refreshed_follow_on_task = db.query(ProcessingTask).filter(ProcessingTask.id == follow_on_task_id).first()
        refreshed_queue_item = db.query(QueueItem).filter(QueueItem.id == queue_item_id).first()
        refreshed_media = db.query(MediaItem).filter(MediaItem.id == media_id).first()

        assert refreshed_queue_task is not None
        assert refreshed_follow_on_task is not None
        assert refreshed_queue_item is not None
        assert refreshed_media is not None
        assert refreshed_queue_task.status == ProcessingTaskStatus.CANCELED.value
        assert refreshed_follow_on_task.status == ProcessingTaskStatus.CANCELED.value
        assert refreshed_queue_item.status == QueueStatus.PENDING.value
        assert refreshed_queue_item.error is None
        assert refreshed_media.missing is True

    asyncio.run(task_stream_manager.clear_task(queue_task_id))
    asyncio.run(task_stream_manager.clear_task(follow_on_task_id))

def test_cancel_task_route_guest_requires_own_queue_item(client):
    """Guests should only cancel tasks they created."""
    with TestingSessionLocal() as db:
        owned_media = MediaItem(
            youtube_id="route-owned-media",
            file_stem="route-owned-media",
            title="Owned Route Song",
            media_path="/media/route-owned-media.mp4",
            missing=False,
        )
        other_media = MediaItem(
            youtube_id="route-other-media",
            file_stem="route-other-media",
            title="Other Route Song",
            media_path="/media/route-other-media.mp4",
            missing=False,
        )
        db.add_all([owned_media, other_media])
        db.commit()
        db.refresh(owned_media)
        db.refresh(other_media)

        owned_queue = QueueItem(
            media_id=owned_media.id,
            position=1,
            requested_karaoke=False,
            user_id="guest-owner",
            status=QueueStatus.DOWNLOADING.value,
        )
        other_queue = QueueItem(
            media_id=other_media.id,
            position=2,
            requested_karaoke=False,
            user_id="guest-other",
            status=QueueStatus.DOWNLOADING.value,
        )
        db.add_all([owned_queue, other_queue])
        db.commit()
        db.refresh(owned_queue)
        db.refresh(other_queue)

        owned_task = ProcessingTask(
            task_type="queue_prepare",
            source_kind="youtube",
            target_queue_item_id=owned_queue.id,
            target_media_item_id=owned_media.id,
            status=ProcessingTaskStatus.DOWNLOADING.value,
            stage="download",
        )
        other_task = ProcessingTask(
            task_type="queue_prepare",
            source_kind="youtube",
            target_queue_item_id=other_queue.id,
            target_media_item_id=other_media.id,
            status=ProcessingTaskStatus.DOWNLOADING.value,
            stage="download",
        )
        db.add_all([owned_task, other_task])
        db.commit()
        db.refresh(owned_task)
        db.refresh(other_task)
        owned_task_id = owned_task.id
        other_task_id = other_task.id

    client.cookies.set("karaoke_guest_id", "guest-owner")

    own_response = client.post(f"/api/tasks/{owned_task_id}/cancel")
    assert own_response.status_code == 200
    assert own_response.json()["status"] == "canceled"

    forbidden_response = client.post(f"/api/tasks/{other_task_id}/cancel")
    assert forbidden_response.status_code == 403

    asyncio.run(task_stream_manager.clear_task(owned_task_id))
    asyncio.run(task_stream_manager.clear_task(other_task_id))


def test_list_tasks_route_returns_only_guest_owned_tasks(client):
    """Guest task lists should only include the viewer's queue-backed tasks."""
    with TestingSessionLocal() as db:
        owned_media = MediaItem(
            youtube_id="list-owned-media",
            file_stem="list-owned-media",
            title="List Owned Media",
            media_path="/media/list-owned-media.mp4",
            missing=False,
        )
        other_media = MediaItem(
            youtube_id="list-other-media",
            file_stem="list-other-media",
            title="List Other Media",
            media_path="/media/list-other-media.mp4",
            missing=False,
        )
        db.add_all([owned_media, other_media])
        db.commit()
        db.refresh(owned_media)
        db.refresh(other_media)

        owned_queue = QueueItem(
            media_id=owned_media.id,
            position=1,
            requested_karaoke=False,
            user_id="guest-owner",
            status=QueueStatus.FAILED.value,
        )
        other_queue = QueueItem(
            media_id=other_media.id,
            position=2,
            requested_karaoke=False,
            user_id="guest-other",
            status=QueueStatus.FAILED.value,
        )
        db.add_all([owned_queue, other_queue])
        db.commit()
        db.refresh(owned_queue)
        db.refresh(other_queue)

        owned_task = ProcessingTask(
            task_type="queue_prepare",
            source_kind="youtube",
            target_queue_item_id=owned_queue.id,
            target_media_item_id=owned_media.id,
            status=ProcessingTaskStatus.FAILED.value,
            stage="failed",
        )
        other_task = ProcessingTask(
            task_type="queue_prepare",
            source_kind="youtube",
            target_queue_item_id=other_queue.id,
            target_media_item_id=other_media.id,
            status=ProcessingTaskStatus.FAILED.value,
            stage="failed",
        )
        db.add_all([owned_task, other_task])
        db.commit()
        db.refresh(owned_task)
        db.refresh(other_task)

    client.cookies.set("karaoke_guest_id", "guest-owner")
    response = client.get("/api/tasks/")

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == [owned_task.id]


def test_delete_canceled_task_route_removes_orphaned_media_and_task(client, tmp_path):
    """Admins should be able to delete a canceled task and its orphaned media row."""
    authenticate_admin_client(client)
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "delete-canceled.mp4"
        media_file.write_text("video", encoding="utf-8")

        with TestingSessionLocal() as db:
            media = MediaItem(
                youtube_id="delete-canceled",
                file_stem="delete-canceled",
                title="Delete Canceled",
                media_path="/media/delete-canceled.mp4",
                missing=True,
            )
            db.add(media)
            db.commit()
            db.refresh(media)

            queue_item = QueueItem(
                media_id=media.id,
                position=1,
                requested_karaoke=False,
                status=QueueStatus.PENDING.value,
            )
            db.add(queue_item)
            db.commit()
            db.refresh(queue_item)

            task = ProcessingTask(
                task_type="queue_prepare",
                source_kind="youtube",
                target_queue_item_id=queue_item.id,
                target_media_item_id=media.id,
                status=ProcessingTaskStatus.CANCELED.value,
                stage="canceled",
            )
            db.add(task)
            db.commit()
            task_id = task.id
            media_id = media.id
            queue_item_id = queue_item.id

        response = client.delete(f"/api/tasks/{task_id}")

        assert response.status_code == 200
        payload = response.json()
        assert payload["deleted_task_id"] == task_id
        assert payload["deleted_queue_item_id"] == queue_item_id
        assert payload["deleted_media_item_id"] == media_id

        with TestingSessionLocal() as db:
            assert db.query(ProcessingTask).filter(ProcessingTask.id == task_id).first() is None
            assert db.query(QueueItem).filter(QueueItem.id == queue_item_id).first() is None
            assert db.query(MediaItem).filter(MediaItem.id == media_id).first() is None
        assert not media_file.exists()
    finally:
        settings.media_path = original_media


def test_delete_failed_task_route_removes_orphaned_media_and_task(client, tmp_path):
    """Admins should be able to delete a failed task and its orphaned media row."""
    authenticate_admin_client(client)
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "delete-failed.mp4"
        media_file.write_text("video", encoding="utf-8")

        with TestingSessionLocal() as db:
            media = MediaItem(
                youtube_id="delete-failed",
                file_stem="delete-failed",
                title="Delete Failed",
                media_path="/media/delete-failed.mp4",
                missing=True,
            )
            db.add(media)
            db.commit()
            db.refresh(media)

            queue_item = QueueItem(
                media_id=media.id,
                position=1,
                requested_karaoke=False,
                status=QueueStatus.FAILED.value,
            )
            db.add(queue_item)
            db.commit()
            db.refresh(queue_item)

            task = ProcessingTask(
                task_type="queue_prepare",
                source_kind="youtube",
                target_queue_item_id=queue_item.id,
                target_media_item_id=media.id,
                status=ProcessingTaskStatus.FAILED.value,
                stage="failed",
            )
            db.add(task)
            db.commit()
            task_id = task.id
            media_id = media.id
            queue_item_id = queue_item.id

        response = client.delete(f"/api/tasks/{task_id}")

        assert response.status_code == 200
        payload = response.json()
        assert payload["deleted_task_id"] == task_id
        assert payload["deleted_queue_item_id"] == queue_item_id
        assert payload["deleted_media_item_id"] == media_id

        with TestingSessionLocal() as db:
            assert db.query(ProcessingTask).filter(ProcessingTask.id == task_id).first() is None
            assert db.query(QueueItem).filter(QueueItem.id == queue_item_id).first() is None
        assert db.query(MediaItem).filter(MediaItem.id == media_id).first() is None
        assert not media_file.exists()
    finally:
        settings.media_path = original_media


def test_delete_failed_task_route_allows_owner_guest(client, tmp_path):
    """Guests should be able to delete their own failed task and orphaned media row."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "delete-failed-guest.mp4"
        media_file.write_text("video", encoding="utf-8")

        with TestingSessionLocal() as db:
            media = MediaItem(
                youtube_id="delete-failed-guest",
                file_stem="delete-failed-guest",
                title="Delete Failed Guest",
                media_path="/media/delete-failed-guest.mp4",
                missing=True,
            )
            db.add(media)
            db.commit()
            db.refresh(media)

            queue_item = QueueItem(
                media_id=media.id,
                position=1,
                requested_karaoke=False,
                user_id="guest-owner",
                status=QueueStatus.FAILED.value,
            )
            db.add(queue_item)
            db.commit()
            db.refresh(queue_item)

            task = ProcessingTask(
                task_type="queue_prepare",
                source_kind="youtube",
                target_queue_item_id=queue_item.id,
                target_media_item_id=media.id,
                status=ProcessingTaskStatus.FAILED.value,
                stage="failed",
            )
            db.add(task)
            db.commit()
            task_id = task.id
            media_id = media.id
            queue_item_id = queue_item.id

        client.cookies.set("karaoke_guest_id", "guest-owner")
        response = client.delete(f"/api/tasks/{task_id}")

        assert response.status_code == 200
        payload = response.json()
        assert payload["deleted_task_id"] == task_id
        assert payload["deleted_queue_item_id"] == queue_item_id
        assert payload["deleted_media_item_id"] == media_id

        with TestingSessionLocal() as db:
            assert db.query(ProcessingTask).filter(ProcessingTask.id == task_id).first() is None
            assert db.query(QueueItem).filter(QueueItem.id == queue_item_id).first() is None
            assert db.query(MediaItem).filter(MediaItem.id == media_id).first() is None
        assert not media_file.exists()
    finally:
        settings.media_path = original_media


def test_delete_failed_task_route_rejects_non_owner_guest(client):
    """Guests should not delete another guest's failed task."""
    with TestingSessionLocal() as db:
        media = MediaItem(
            youtube_id="delete-failed-other-guest",
            file_stem="delete-failed-other-guest",
            title="Delete Failed Other Guest",
            media_path="/media/delete-failed-other-guest.mp4",
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)

        queue_item = QueueItem(
            media_id=media.id,
            position=1,
            requested_karaoke=False,
            user_id="guest-owner",
            status=QueueStatus.FAILED.value,
        )
        db.add(queue_item)
        db.commit()
        db.refresh(queue_item)

        task = ProcessingTask(
            task_type="queue_prepare",
            source_kind="youtube",
            target_queue_item_id=queue_item.id,
            target_media_item_id=media.id,
            status=ProcessingTaskStatus.FAILED.value,
            stage="failed",
        )
        db.add(task)
        db.commit()
        task_id = task.id

    client.cookies.set("karaoke_guest_id", "guest-other")
    response = client.delete(f"/api/tasks/{task_id}")

    assert response.status_code == 403


def test_retry_canceled_media_task_route_resets_and_starts_task(client):
    """Admins should be able to retry a canceled media Demucs/WhisperX task."""
    authenticate_admin_client(client)
    with TestingSessionLocal() as db:
        media = MediaItem(
            title="Retry Canceled Media",
            file_stem="retry-canceled-media",
            media_path="/media/retry-canceled-media.mp4",
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)

        task = ProcessingTask(
            task_type="media_lyrics_align",
            source_kind="library_media",
            target_media_item_id=media.id,
            status=ProcessingTaskStatus.CANCELED.value,
            stage="demucs",
            last_error_summary="old cancel",
            last_error_detail="old detail",
        )
        db.add(task)
        db.commit()
        task_id = task.id

    with patch("routes.tasks.task_execution_coordinator.start") as mock_start:
        response = client.post(f"/api/tasks/{task_id}/retry")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == task_id
    assert payload["status"] == ProcessingTaskStatus.PENDING.value
    assert payload["stage"] == "queued"
    assert payload["last_error_summary"] is None
    mock_start.assert_called_once_with(task_id)

    with TestingSessionLocal() as db:
        refreshed = db.query(ProcessingTask).filter(ProcessingTask.id == task_id).first()
        assert refreshed is not None
        assert refreshed.status == ProcessingTaskStatus.PENDING.value
        assert refreshed.stage == "queued"
        assert refreshed.finished_at is None

    asyncio.run(task_stream_manager.clear_task(task_id))


def test_retry_failed_queue_task_route_allows_owner_guest(client):
    """Guests should be able to retry their own failed queue task."""
    with TestingSessionLocal() as db:
        media = MediaItem(
            youtube_id="retry-failed-guest",
            file_stem="retry-failed-guest",
            title="Retry Failed Guest",
            media_path="/media/retry-failed-guest.mp4",
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)

        queue_item = QueueItem(
            media_id=media.id,
            position=1,
            requested_karaoke=False,
            user_id="guest-owner",
            status=QueueStatus.FAILED.value,
        )
        db.add(queue_item)
        db.commit()
        db.refresh(queue_item)

        task = ProcessingTask(
            task_type="queue_prepare",
            source_kind="youtube",
            target_queue_item_id=queue_item.id,
            target_media_item_id=media.id,
            status=ProcessingTaskStatus.FAILED.value,
            stage="failed",
            last_error_summary="old error",
            last_error_detail="old detail",
        )
        db.add(task)
        db.commit()
        task_id = task.id

    client.cookies.set("karaoke_guest_id", "guest-owner")

    with patch("routes.tasks.task_execution_coordinator.start") as mock_start:
        response = client.post(f"/api/tasks/{task_id}/retry")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == task_id
    assert payload["status"] == ProcessingTaskStatus.PENDING.value
    mock_start.assert_called_once_with(task_id)

    with TestingSessionLocal() as db:
        refreshed = db.query(ProcessingTask).filter(ProcessingTask.id == task_id).first()
        assert refreshed is not None
        assert refreshed.status == ProcessingTaskStatus.PENDING.value
        assert refreshed.stage == "queued"
        assert refreshed.last_error_summary is None

    asyncio.run(task_stream_manager.clear_task(task_id))


def test_retry_failed_queue_task_route_rejects_non_owner_guest(client):
    """Guests should not retry another guest's failed queue task."""
    with TestingSessionLocal() as db:
        media = MediaItem(
            youtube_id="retry-failed-other",
            file_stem="retry-failed-other",
            title="Retry Failed Other",
            media_path="/media/retry-failed-other.mp4",
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)

        queue_item = QueueItem(
            media_id=media.id,
            position=1,
            requested_karaoke=False,
            user_id="guest-owner",
            status=QueueStatus.FAILED.value,
        )
        db.add(queue_item)
        db.commit()
        db.refresh(queue_item)

        task = ProcessingTask(
            task_type="queue_prepare",
            source_kind="youtube",
            target_queue_item_id=queue_item.id,
            target_media_item_id=media.id,
            status=ProcessingTaskStatus.FAILED.value,
            stage="failed",
        )
        db.add(task)
        db.commit()
        task_id = task.id

    client.cookies.set("karaoke_guest_id", "guest-other")
    response = client.post(f"/api/tasks/{task_id}/retry")

    assert response.status_code == 403
    asyncio.run(task_stream_manager.clear_task(task_id))


def test_retry_active_task_route_rejects_without_starting(client):
    """Retry should not start active tasks, even for admins."""
    authenticate_admin_client(client)
    with TestingSessionLocal() as db:
        media = MediaItem(
            title="Active Retry Media",
            file_stem="active-retry-media",
            media_path="/media/active-retry-media.mp4",
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)

        task = ProcessingTask(
            task_type="media_karaoke",
            source_kind="library_media",
            target_media_item_id=media.id,
            status=ProcessingTaskStatus.PROCESSING.value,
            stage="demucs",
        )
        db.add(task)
        db.commit()
        task_id = task.id

    with patch("routes.tasks.task_execution_coordinator.start") as mock_start:
        response = client.post(f"/api/tasks/{task_id}/retry")

    assert response.status_code == 403
    mock_start.assert_not_called()


def test_add_to_queue_uses_guest_cookies_for_requester(client):
    """Queue add should expose requester label from guest cookies."""
    client.cookies.set("karaoke_guest_id", "guest-123")
    client.cookies.set("karaoke_queue_tab_id", "tab-123")
    client.cookies.set("karaoke_singer", "Alex")

    response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "test123-requester",
            "title": "Requester Song",
            "is_karaoke": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["requested_by_name"] == "Alex"

    with TestingSessionLocal() as db:
        row = db.query(QueueItem).filter(QueueItem.id == data["id"]).first()
        assert row is not None
        assert row.user_id == "guest-123"
        assert row.session_id == "tab-123"
        assert row.requester_name == "Alex"

def test_add_to_queue_rejects_queue_as_name_for_non_admin(client):
    """Non-admin queue adds cannot override requester label via queue_as_name."""
    response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "queue-as-guest-denied",
            "title": "Queue As Denied",
            "is_karaoke": False,
            "queue_as_name": "Taylor",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "queue_as_name requires an admin session"

def test_add_to_queue_admin_can_override_requester_name(client):
    """Admin queue adds may set queue_as_name without changing ownership metadata."""
    authenticate_admin_client(client)
    client.cookies.set("karaoke_guest_id", "guest-admin-device")
    client.cookies.set("karaoke_queue_tab_id", "tab-admin-device")
    client.cookies.set("karaoke_singer", "Admin Device")

    response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "queue-as-admin-ok",
            "title": "Queue As Admin",
            "is_karaoke": False,
            "queue_as_name": "Taylor",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["requested_by_name"] == "Taylor"

    with TestingSessionLocal() as db:
        row = db.query(QueueItem).filter(QueueItem.id == data["id"]).first()
        assert row is not None
        assert row.user_id == "guest-admin-device"
        assert row.session_id == "tab-admin-device"
        assert row.requester_name == "Taylor"

def test_add_to_queue_admin_can_delegate_guest_ownership(client):
    """Admin queue adds may transfer ownership to a selected guest id."""
    authenticate_admin_client(client)
    client.cookies.set("karaoke_guest_id", "guest-admin-device")
    client.cookies.set("karaoke_queue_tab_id", "tab-admin-device")
    client.cookies.set("karaoke_singer", "Admin Device")

    response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "queue-as-admin-delegated",
            "title": "Queue As Delegated",
            "is_karaoke": False,
            "queue_as_name": "Taylor",
            "queue_as_guest_id": "guest-target",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["requested_by_name"] == "Taylor"

    with TestingSessionLocal() as db:
        row = db.query(QueueItem).filter(QueueItem.id == data["id"]).first()
        assert row is not None
        assert row.user_id == "guest-target"
        assert row.session_id == "tab-admin-device"
        assert row.requester_name == "Taylor"

def test_add_to_queue_rejects_queue_as_guest_id_for_non_admin(client):
    """Non-admin queue adds cannot set a delegated guest id."""
    response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "queue-as-guest-id-denied",
            "title": "Queue As Guest Id Denied",
            "is_karaoke": False,
            "queue_as_guest_id": "guest-target",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "queue_as_guest_id requires an admin session"

def test_add_to_queue_non_karaoke(client):
    """Non-karaoke queue items should be accepted without burn settings."""
    response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "test124",
            "title": "Test Song 2",
            "is_karaoke": False,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_karaoke"] is False

def test_add_to_queue_persists_inline_lyrics_sidecar(client):
    """Queue add should persist inline lyrics so karaoke processing can reuse them."""
    response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "queue-lyrics-1",
            "title": "Queue Lyrics",
            "artist": "Singer",
            "is_karaoke": True,
            "lyrics_text": "[00:01.00]Lyrics line",
        },
    )
    assert response.status_code == 200
    data = response.json()
    expected_stem = build_media_stem("Queue Lyrics", "Singer", fallback="queue-lyrics-1")
    assert data["lyrics_path"] == f"/cache/lyrics/{expected_stem}.lrc"

def test_add_to_queue_persists_ttml_lyrics_as_json_sidecar(client):
    """Queue TTML input should be normalized to the canonical JSON sidecar."""
    response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "queue-ttml-1",
            "title": "Queue TTML",
            "artist": "Singer",
            "is_karaoke": True,
            "lyrics_text": TTML_SAMPLE,
            "lyrics_format": "ttml",
        },
    )
    assert response.status_code == 200
    data = response.json()
    expected_stem = build_media_stem("Queue TTML", "Singer", fallback="queue-ttml-1")
    assert data["lyrics_path"] == f"/media/{expected_stem}.json"
    with TestingSessionLocal() as db:
        media_item = db.query(MediaItem).filter(MediaItem.id == data["media_id"]).first()
        assert media_item is not None
        assert media_item.lyrics_path == f"/media/{expected_stem}.json"
    saved_payload = json.loads(
        (settings.media_path / f"{expected_stem}.json").read_text(encoding="utf-8")
    )
    assert saved_payload["segments"][0]["text"] == "I know that the bar closes at 11"

def test_add_to_queue_with_media_item_id(client):
    """Queue endpoint should enqueue existing local media by media_item_id."""
    with TestingSessionLocal() as db:
        media = MediaItem(
            youtube_id="local-abc",
            title="Local Track",
            artist="Local Artist",
            media_path="/media/local-abc.mp4",
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)
        media_id = media.id

    response = client.post(
        "/api/queue/",
        json={
            "media_item_id": media_id,
            "title": "Local Track",
            "artist": "Local Artist",
            "is_karaoke": False,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["media_id"] == media_id
    assert data["youtube_id"] == "local-abc"
    assert data["thumbnail"] == "https://i.ytimg.com/vi/local-abc/hqdefault.jpg"

def test_queue_page_renders_thumbnail_for_local_media(client, tmp_path, monkeypatch):
    """Queue page should render cached thumbnails for local media items."""
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    media_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)

    media_file = media_root / "queue-thumb.mp4"
    media_file.write_bytes(b"media")
    thumbnail_path = MediaThumbnailService.thumbnail_path_for_media_file(media_file)
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    thumbnail_path.write_bytes(b"thumbnail")

    with TestingSessionLocal() as db:
        media = MediaItem(
            youtube_id=None,
            title="Queue Thumbnail",
            artist="Artist",
            media_path="/media/queue-thumb.mp4",
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)

        queue_item = QueueItem(
            media_id=media.id,
            position=1000,
            requested_karaoke=False,
            status=QueueStatus.PENDING,
        )
        db.add(queue_item)
        db.commit()

    response = client.get("/queue")

    assert response.status_code == 200
    assert MediaThumbnailService.thumbnail_url_for_media_file(media_file) in response.text

def test_queue_page_renders_clickable_processing_items_with_task_ids(client):
    """Processing queue items should expose task metadata for media drill-down."""
    with TestingSessionLocal() as db:
        media = MediaItem(
            youtube_id="queue-task-link",
            title="Queue Task Link",
            artist="Artist",
            media_path="/media/queue-task-link.mp4",
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)

        queue_item = QueueItem(
            media_id=media.id,
            position=1000,
            requested_karaoke=False,
            status=QueueStatus.PENDING,
        )
        db.add(queue_item)
        db.commit()
        db.refresh(queue_item)

        task = processing_task_service.get_or_create_queue_task(db, queue_item.id)
        asyncio.run(
            processing_task_service.set_stage(
                db,
                task.id,
                status=ProcessingTaskStatus.PROCESSING,
                stage="extract_audio",
                progress_label="Extracting audio",
                progress_percent=0,
            )
        )

    response = client.get("/queue")

    assert response.status_code == 200
    assert f'data-task-id="{task.id}"' in response.text
    assert 'data-status="processing"' in response.text
    assert 'data-task-progress-stage="extract_audio"' in response.text
    assert 'cursor-pointer hover:border-primary/30' in response.text


def test_queue_page_renders_indeterminate_progress_mode(client):
    with TestingSessionLocal() as db:
        media = MediaItem(
            youtube_id="queue-progress-mode",
            title="Queue Progress Mode",
            artist="Artist",
            media_path="/media/queue-progress-mode.mp4",
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)

        queue_item = QueueItem(
            media_id=media.id,
            position=1000,
            requested_karaoke=True,
            status=QueueStatus.PROCESSING,
        )
        db.add(queue_item)
        db.commit()
        db.refresh(queue_item)

        task = processing_task_service.get_or_create_queue_task(db, queue_item.id)
        asyncio.run(
            processing_task_service.set_stage(
                db,
                task.id,
                status=ProcessingTaskStatus.PROCESSING,
                stage="whisperx",
                progress_label="Loading audio",
                progress_label_key="task.whisperx_loading_audio",
                progress_mode="indeterminate",
                progress_percent=5,
            )
        )

    response = client.get("/queue")

    assert response.status_code == 200
    assert 'data-task-progress-stage="whisperx"' in response.text
    assert 'data-task-progress-mode="indeterminate"' in response.text

def test_queue_page_renders_ready_items_linking_to_media(client):
    """Completed queue items should be clickable and carry their media id."""
    with TestingSessionLocal() as db:
        media = MediaItem(
            youtube_id="queue-media-link",
            title="Queue Media Link",
            artist="Artist",
            media_path="/media/queue-media-link.mp4",
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)

        queue_item = QueueItem(
            media_id=media.id,
            position=1000,
            requested_karaoke=False,
            status=QueueStatus.READY,
        )
        db.add(queue_item)
        db.commit()
        db.refresh(queue_item)
        media_id = media.id

    response = client.get("/queue")

    assert response.status_code == 200
    assert f'data-media-id="{media_id}"' in response.text
    assert 'data-status="ready"' in response.text
    assert 'cursor-pointer hover:border-primary/30' in response.text

def test_media_management_page_renders_progress_stage_for_finalize_tasks(client):
    """Media task cards should expose their stage for optimistic progress rendering."""
    authenticate_admin_client(client)
    with TestingSessionLocal() as db:
        media = MediaItem(
            youtube_id="media-task-stage",
            title="Media Task Stage",
            artist="Artist",
            media_path="/media/media-task-stage.mp4",
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)

        task = processing_task_service.get_or_create_media_task(db, media.id)
        asyncio.run(
            processing_task_service.set_stage(
                db,
                task.id,
                status=ProcessingTaskStatus.PROCESSING,
                stage="finalize",
                progress_label="Remuxing karaoke media",
                progress_percent=0,
            )
        )

    response = client.get("/media")

    assert response.status_code == 200
    assert f'data-task-id="{task.id}"' in response.text
    assert 'data-task-progress-stage="finalize"' in response.text
    assert '/static/media_management.js?v=' in response.text


def test_media_management_page_renders_indeterminate_progress_mode(client):
    authenticate_admin_client(client)
    with TestingSessionLocal() as db:
        media = MediaItem(
            youtube_id="media-task-progress-mode",
            title="Media Task Progress Mode",
            artist="Artist",
            media_path="/media/media-task-progress-mode.mp4",
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)

        task = processing_task_service.get_or_create_media_task(db, media.id)
        asyncio.run(
            processing_task_service.set_stage(
                db,
                task.id,
                status=ProcessingTaskStatus.PROCESSING,
                stage="whisperx",
                progress_label="Loading audio",
                progress_label_key="task.whisperx_loading_audio",
                progress_mode="indeterminate",
                progress_percent=5,
            )
        )

    response = client.get("/media")

    assert response.status_code == 200
    assert f'data-task-id="{task.id}"' in response.text
    assert 'data-task-progress-stage="whisperx"' in response.text
    assert 'data-task-progress-mode="indeterminate"' in response.text
