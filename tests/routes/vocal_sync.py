from .common import *
from io import BytesIO

from services.vocal_sync_service import VocalSyncService


def test_vocal_sync_routes_require_admin(client):
    assert client.post("/api/media/42/vocals-sync/prepare-youtube", json={"youtube_id": "abcdefghijk"}).status_code == 403
    assert client.post("/api/media/42/vocals-sync/prepare-upload", files={"file": ("source.mp3", b"x", "audio/mpeg")}).status_code == 403
    assert client.get("/api/media/42/vocals-sync/status").status_code == 403
    assert client.get("/api/media/42/vocals-sync/sessions/session-id").status_code == 403
    assert client.post("/api/media/42/vocals-sync/sessions/session-id/commit", json={"offset_seconds": 0}).status_code == 403
    response = client.get("/media-vocals/42", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_media_vocals_page_renders_admin_shell(client, tmp_path, monkeypatch):
    authenticate_admin_client(client)
    monkeypatch.setattr(settings, "media_path", tmp_path)
    media_file = tmp_path / "song.mp4"
    media_file.write_bytes(b"video")
    with TestingSessionLocal() as db:
        media = MediaItem(
            title="Song",
            artist="Artist",
            media_path="/media/song.mp4",
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)
        media_id = media.id

    response = client.get(f"/media-vocals/{media_id}")

    assert response.status_code == 200
    assert 'id="vocal-sync-page"' in response.text
    assert f'data-media-id="{media_id}"' in response.text
    assert "/static/media_vocals.js" in response.text
    assert "Song" in response.text
    assert "Artist" in response.text
    assert 'id="vocal-sync-youtube-progress"' in response.text
    assert 'id="vocal-sync-youtube-selected"' in response.text
    assert 'id="vocal-sync-prepare-youtube"' in response.text
    assert 'type="submit" aria-label="Prepare Upload"' in response.text


def test_prepare_youtube_returns_task_id(client):
    authenticate_admin_client(client)
    task = Mock(id=17)
    with patch(
        "routes.vocal_sync.vocal_sync_service.validate_media_item_for_prepare",
        return_value=Mock(id=42),
    ), patch(
        "routes.vocal_sync.processing_task_service.create_media_vocal_sync_prepare_task",
        return_value=task,
    ) as create_task, patch(
        "routes.vocal_sync.vocal_sync_service.create_youtube_prepare_task_manifest",
    ) as create_manifest, patch(
        "routes.vocal_sync.task_execution_coordinator.start",
    ) as start_task:
        response = client.post(
            "/api/media/42/vocals-sync/prepare-youtube",
            json={"youtube_id": "abcdefghijk"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "processing", "task_id": 17}
    create_task.assert_called_once_with(ANY, 42)
    create_manifest.assert_called_once_with(17, media_item_id=42, youtube_id="abcdefghijk")
    start_task.assert_called_once_with(17)


def test_prepare_upload_returns_task_id(client):
    authenticate_admin_client(client)
    task = Mock(id=23)
    with patch(
        "routes.vocal_sync.vocal_sync_service.validate_media_item_for_prepare",
        return_value=Mock(id=42),
    ), patch(
        "routes.vocal_sync.processing_task_service.create_media_vocal_sync_prepare_task",
        return_value=task,
    ) as create_task, patch(
        "routes.vocal_sync.vocal_sync_service.create_upload_prepare_task_manifest",
    ) as create_manifest, patch(
        "routes.vocal_sync.task_execution_coordinator.start",
    ) as start_task:
        response = client.post(
            "/api/media/42/vocals-sync/prepare-upload",
            files={"file": ("source.mp3", b"audio", "audio/mpeg")},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "processing", "task_id": 23}
    create_task.assert_called_once_with(ANY, 42, source_kind="upload")
    create_manifest.assert_called_once()
    start_task.assert_called_once_with(23)


def test_status_returns_active_prepare_task(client):
    authenticate_admin_client(client)
    with TestingSessionLocal() as db:
        media = MediaItem(title="Song", artist="Artist", media_path="/media/song.mp4", missing=False)
        db.add(media)
        db.commit()
        db.refresh(media)
        task = ProcessingTask(
            task_type="media_vocal_sync_prepare_upload",
            source_kind="upload",
            target_media_item_id=media.id,
            status=ProcessingTaskStatus.PROCESSING.value,
            stage="demucs",
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        media_id = media.id
        task_id = task.id

    response = client.get(f"/api/media/{media_id}/vocals-sync/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "preparing"
    assert payload["task"]["id"] == task_id
    assert payload["task"]["source_kind"] == "upload"
    assert payload["session"] is None


def test_status_returns_idle_without_task_or_review(client):
    authenticate_admin_client(client)
    with TestingSessionLocal() as db:
        media = MediaItem(title="Song", artist="Artist", media_path="/media/song.mp4", missing=False)
        db.add(media)
        db.commit()
        db.refresh(media)
        media_id = media.id

    response = client.get(f"/api/media/{media_id}/vocals-sync/status")

    assert response.status_code == 200
    assert response.json() == {"status": "idle", "task": None, "session": None, "message": None}


def test_status_returns_ready_review_session(client, tmp_path, monkeypatch):
    authenticate_admin_client(client)
    monkeypatch.setattr(settings, "cache_path", tmp_path)
    session_id = "11111111-1111-1111-1111-111111111111"
    session_dir = tmp_path / "vocal_sync" / session_id
    session_dir.mkdir(parents=True)
    vocals_file = session_dir / "review_vocals.wav"
    vocals_file.write_bytes(b"vocals")
    with TestingSessionLocal() as db:
        media = MediaItem(title="Song", artist="Artist", media_path="/media/song.mp4", missing=False)
        db.add(media)
        db.commit()
        db.refresh(media)
        task = ProcessingTask(
            task_type="media_vocal_sync_prepare_youtube",
            source_kind="youtube",
            target_media_item_id=media.id,
            status=ProcessingTaskStatus.DONE.value,
            stage="ready",
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        VocalSyncService.create_youtube_prepare_task_manifest(task.id, media_item_id=media.id, youtube_id="abcdefghijk")
        VocalSyncService.update_task_manifest_session(task.id, session_id)
        VocalSyncService._write_manifest(
            session_id,
            {
                "session_id": session_id,
                "media_item_id": media.id,
                "media_url": "/media/song.mp4",
                "vocals_path": str(vocals_file),
                "estimated_offset_seconds": 0.5,
                "method": "scipy_cross_correlation",
                "source_kind": "youtube",
                "title": "Song",
                "artist": "Artist",
            },
        )
        media_id = media.id

    response = client.get(f"/api/media/{media_id}/vocals-sync/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["task"]["status"] == "done"
    assert payload["session"]["session_id"] == session_id
    assert payload["session"]["vocals_url"] == f"/cache/vocal_sync/{session_id}/review_vocals.wav"


def test_prepare_upload_rejects_active_youtube_task(client):
    authenticate_admin_client(client)
    with TestingSessionLocal() as db:
        task = ProcessingTask(
            task_type="media_vocal_sync_prepare_youtube",
            source_kind="youtube",
            target_media_item_id=42,
            status=ProcessingTaskStatus.DOWNLOADING.value,
            stage="download",
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id

    with patch("routes.vocal_sync.vocal_sync_service.validate_media_item_for_prepare", return_value=Mock(id=42)):
        response = client.post(
            "/api/media/42/vocals-sync/prepare-upload",
            files={"file": ("source.mp3", b"audio", "audio/mpeg")},
        )

    assert response.status_code == 409
    assert response.json()["detail"]["status"] == "preparing"
    assert response.json()["detail"]["existing_task_id"] == task_id


def test_prepare_youtube_rejects_active_upload_task(client):
    authenticate_admin_client(client)
    with TestingSessionLocal() as db:
        task = ProcessingTask(
            task_type="media_vocal_sync_prepare_upload",
            source_kind="upload",
            target_media_item_id=42,
            status=ProcessingTaskStatus.PROCESSING.value,
            stage="demucs",
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id

    with patch("routes.vocal_sync.vocal_sync_service.validate_media_item_for_prepare", return_value=Mock(id=42)):
        response = client.post(
            "/api/media/42/vocals-sync/prepare-youtube",
            json={"youtube_id": "abcdefghijk"},
        )

    assert response.status_code == 409
    assert response.json()["detail"]["status"] == "preparing"
    assert response.json()["detail"]["existing_task_id"] == task_id


def test_prepare_youtube_rejects_ready_review(client, tmp_path, monkeypatch):
    authenticate_admin_client(client)
    monkeypatch.setattr(settings, "cache_path", tmp_path)
    session_id = "22222222-2222-2222-2222-222222222222"
    session_dir = tmp_path / "vocal_sync" / session_id
    session_dir.mkdir(parents=True)
    vocals_file = session_dir / "review_vocals.wav"
    vocals_file.write_bytes(b"vocals")
    with TestingSessionLocal() as db:
        task = ProcessingTask(
            task_type="media_vocal_sync_prepare_upload",
            source_kind="upload",
            target_media_item_id=42,
            status=ProcessingTaskStatus.DONE.value,
            stage="ready",
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        VocalSyncService.create_upload_prepare_task_manifest(
            task.id,
            media_item_id=42,
            source_filename="source.mp3",
            source_file=BytesIO(b"audio"),
        )
        VocalSyncService.update_task_manifest_session(task.id, session_id)
        VocalSyncService._write_manifest(
            session_id,
            {
                "session_id": session_id,
                "media_item_id": 42,
                "media_url": "/media/song.mp4",
                "vocals_path": str(vocals_file),
                "estimated_offset_seconds": 0.5,
                "method": "scipy_cross_correlation",
                "source_kind": "upload",
                "title": "Song",
                "artist": "Artist",
            },
        )

    with patch("routes.vocal_sync.vocal_sync_service.validate_media_item_for_prepare", return_value=Mock(id=42)):
        response = client.post(
            "/api/media/42/vocals-sync/prepare-youtube",
            json={"youtube_id": "abcdefghijk"},
        )

    assert response.status_code == 409
    assert response.json()["detail"]["status"] == "ready"
    assert response.json()["detail"]["existing_session_id"] == session_id


def test_commit_session_rejects_mismatched_session(client):
    authenticate_admin_client(client)
    service_session = Mock(media_item_id=99)
    with patch(
        "routes.vocal_sync.vocal_sync_service.get_session",
        return_value=service_session,
    ):
        response = client.get("/api/media/42/vocals-sync/sessions/abc")

    assert response.status_code == 409


def test_get_task_session_returns_prepared_session(client):
    authenticate_admin_client(client)
    service_session = Mock(media_item_id=42)
    service_session.to_dict.return_value = {
        "session_id": "11111111-1111-1111-1111-111111111111",
        "media_item_id": 42,
        "media_url": "/media/song.mp4",
        "vocals_url": "/cache/vocal_sync/111/review_vocals.wav",
        "estimated_offset_seconds": 0.25,
        "method": "scipy_cross_correlation",
        "source_kind": "youtube",
        "title": "Song",
        "artist": "Artist",
    }
    with patch(
        "routes.vocal_sync.processing_task_service.get_task",
        return_value=Mock(target_media_item_id=42),
    ), patch(
        "routes.vocal_sync.vocal_sync_service.read_task_manifest",
        return_value={"session_id": "11111111-1111-1111-1111-111111111111"},
    ), patch(
        "routes.vocal_sync.vocal_sync_service.get_session",
        return_value=service_session,
    ):
        response = client.get("/api/media/42/vocals-sync/tasks/17/session")

    assert response.status_code == 200
    assert response.json()["session"]["session_id"] == "11111111-1111-1111-1111-111111111111"
