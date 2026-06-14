from .common import *



def test_upload_page_loads(client):
    """Test upload page renders with queue toggle and infer button."""
    response = client.get("/upload")
    assert response.status_code == 200
    assert "Upload" in response.text
    assert 'id="add-to-queue" type="checkbox"' in response.text
    assert "Add to queue" in response.text
    assert 'id="artist-name"' in response.text
    assert "(optional)" in response.text
    assert not re.search(r'<input[^>]*id="artist-name"[^>]*required', response.text)
    assert 'id="infer-metadata-btn"' in response.text
    assert "Infer from filename" in response.text

def test_upload_media_saves_file_and_queues_item(client, tmp_path):
    """Uploaded media should be saved, catalogued, and queued when requested."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        healthy = DemucsHealthResponse(api_url="http://demucs", healthy=True, detail="ok")
        with (
            patch("routes.media_library.manager.broadcast_queue_item_added", new=AsyncMock()),
            patch(
                "routes.media_library.runtime_settings_service.get_demucs_health",
                return_value=healthy,
            ),
        ):
            response = client.post(
                "/api/media/upload",
                data={
                    "title": "Upload Song",
                    "artist": "Upload Artist",
                    "add_to_queue": "true",
                },
                files={"file": ("upload-song.mp4", b"video-bytes", "video/mp4")},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["queued"] is True
        assert payload["queue_item_id"] is not None

        saved_file = settings.media_path / payload["filename"]
        assert saved_file.exists()

        with TestingSessionLocal() as db:
            media_item = db.query(MediaItem).filter(MediaItem.id == payload["media_id"]).first()
            assert media_item is not None
            assert media_item.title == "Upload Song"
            assert media_item.artist == "Upload Artist"
            assert media_item.media_path == f"/media/{payload['filename']}"

            queue_item = db.query(QueueItem).filter(QueueItem.id == payload["queue_item_id"]).first()
            assert queue_item is not None
            assert queue_item.media_id == media_item.id
            assert queue_item.requested_karaoke is False
    finally:
        settings.media_path = original_media

def test_upload_media_persists_lyrics_and_queue_karaoke_flag(client, tmp_path):
    """Uploaded lyrics should persist as a sidecar and queued uploads can request karaoke."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        healthy = DemucsHealthResponse(api_url="http://demucs", healthy=True, detail="ok")
        with (
            patch("routes.media_library.manager.broadcast_queue_item_added", new=AsyncMock()),
            patch(
                "routes.media_library.runtime_settings_service.get_demucs_health",
                return_value=healthy,
            ),
        ):
            response = client.post(
                "/api/media/upload",
                data={
                    "title": "Upload Lyrics",
                    "artist": "Upload Artist",
                    "add_to_queue": "true",
                    "is_karaoke": "true",
                    "lyrics_text": "[00:01.00]Uploaded line",
                    "lyrics_format": "lrc",
                },
                files={"file": ("upload-lyrics.mp4", b"video-bytes", "video/mp4")},
            )

        assert response.status_code == 200
        payload = response.json()
        expected_stem = build_media_stem("Upload Lyrics", "Upload Artist")
        assert payload["lyrics_path"] == f"/media/{expected_stem}.lrc"
        assert payload["karaoke_started"] is True
        assert isinstance(payload["karaoke_task_id"], int)
        assert (settings.media_path / f"{expected_stem}.lrc").read_text(
            encoding="utf-8"
        ) == "[00:01.00]Uploaded line"

        with TestingSessionLocal() as db:
            queue_item = db.query(QueueItem).filter(QueueItem.id == payload["queue_item_id"]).first()
            assert queue_item is not None
            assert queue_item.requested_karaoke is True
            assert queue_item.media.lyrics_path == f"/media/{expected_stem}.lrc"
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache

def test_upload_media_starts_media_karaoke_task_without_queue(client, tmp_path):
    """AI uploads should create a media task when Add to queue is disabled."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        healthy = DemucsHealthResponse(api_url="http://demucs", healthy=True, detail="ok")

        with (
            patch(
                "routes.media_library.runtime_settings_service.get_demucs_health",
                return_value=healthy,
            ),
            patch("routes.media_library.task_execution_coordinator.start") as mock_start,
        ):
            response = client.post(
                "/api/media/upload",
                data={
                    "title": "Standalone Karaoke",
                    "add_to_queue": "false",
                    "is_karaoke": "true",
                },
                files={"file": ("standalone.mp3", b"audio-bytes", "audio/mpeg")},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["queued"] is False
        assert payload["karaoke_started"] is True
        assert isinstance(payload["karaoke_task_id"], int)
        mock_start.assert_called_once_with(payload["karaoke_task_id"])
        with TestingSessionLocal() as db:
            task = db.query(ProcessingTask).filter(
                ProcessingTask.id == payload["karaoke_task_id"]
            ).one()
            assert task.task_type == "media_karaoke"
            assert task.target_media_item_id == payload["media_id"]
    finally:
        settings.media_path = original_media

def test_upload_media_offline_saves_and_queues_without_karaoke(client, tmp_path):
    """A late Demucs outage should preserve the upload and queue the original media."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        offline = DemucsHealthResponse(
            api_url="http://demucs",
            healthy=False,
            detail="connection refused",
        )

        with (
            patch("routes.media_library.manager.broadcast_queue_item_added", new=AsyncMock()),
            patch(
                "routes.media_library.runtime_settings_service.get_demucs_health",
                return_value=offline,
            ),
            patch("routes.media_library.task_execution_coordinator.start") as mock_start,
        ):
            response = client.post(
                "/api/media/upload",
                data={
                    "title": "Offline Upload",
                    "add_to_queue": "true",
                    "is_karaoke": "true",
                },
                files={"file": ("offline.mp4", b"video-bytes", "video/mp4")},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["karaoke_requested"] is True
        assert payload["karaoke_started"] is False
        assert payload["karaoke_task_id"] is None
        assert payload["karaoke_warning"] == "demucs_offline"
        assert (settings.media_path / payload["filename"]).exists()
        mock_start.assert_called_once()

        with TestingSessionLocal() as db:
            queue_item = db.query(QueueItem).filter(
                QueueItem.id == payload["queue_item_id"]
            ).one()
            assert queue_item.requested_karaoke is False
    finally:
        settings.media_path = original_media

def test_upload_media_generates_thumbnail_for_mp3(client, tmp_path):
    """Uploaded MP3 files should trigger thumbnail generation immediately."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        with patch("routes.media_library.manager.broadcast_queue_item_added", new=AsyncMock()):
            with patch("routes.media_library.media_thumbnail_service.ensure_thumbnail_for_media_file") as mock_thumb:
                response = client.post(
                    "/api/media/upload",
                    data={
                        "title": "Audio Upload",
                        "artist": "Album Artist",
                        "add_to_queue": "false",
                    },
                    files={"file": ("audio-upload.mp3", b"audio-bytes", "audio/mpeg")},
                )

        assert response.status_code == 200
        payload = response.json()
        mock_thumb.assert_called_once_with(settings.media_path / payload["filename"])
    finally:
        settings.media_path = original_media

@pytest.mark.parametrize(
    "filename",
    ["upload-song.webm", "upload-song.mkv", "upload-song.mov", "upload-song.avi", "upload-song.m4v"],
)
def test_upload_media_supports_common_video_formats(client, tmp_path, filename):
    """Common video uploads should be accepted and catalogued."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        with patch("routes.media_library.manager.broadcast_queue_item_added", new=AsyncMock()):
            response = client.post(
                "/api/media/upload",
                data={
                    "title": "Video Upload",
                    "artist": "",
                    "add_to_queue": "false",
                },
                files={"file": (filename, b"video-bytes", "video/mp4")},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["queued"] is False
        saved_file = settings.media_path / payload["filename"]
        assert saved_file.exists()
        assert saved_file.name.endswith(Path(filename).suffix)
    finally:
        settings.media_path = original_media

def test_media_management_page_loads(client):
    """Test media management page renders."""
    response = client.get("/media")
    assert response.status_code == 200
    assert b"Media" in response.content
    assert b"Manage Existing Media" in response.content

def test_media_management_page_uses_database_rows(client):
    """Media management page should render DB-backed library rows and stats."""
    with TestingSessionLocal() as db:
        db.add_all(
            [
                MediaItem(
                    youtube_id="realabc12345",
                    title="Real Song One",
                    artist="Artist One",
                    media_path="/media/real-song-one.mp4",
                    vocals_path="/media/real-song-one.vocals.wav",
                    lyrics_path="/media/real-song-one.lrc",
                    missing=False,
                ),
                MediaItem(
                    youtube_id="realdef67890",
                    title="Real Song Two",
                    artist="Artist Two",
                    media_path="/media/real-song-two.mp4",
                    missing=False,
                ),
                MediaItem(
                    title="Real Song Missing",
                    artist="Artist Missing",
                    media_path="/media/real-song-missing.mp4",
                    lyrics_path="/media/real-song-missing.lrc",
                    missing=True,
                ),
            ]
        )
        db.commit()

    response = client.get("/media")
    assert response.status_code == 200
    content = response.content

    assert b"Real Song One" in content
    assert b"Artist One" in content
    assert b"Real Song Missing" in content
    assert b"https://i.ytimg.com/vi/realabc12345/hqdefault.jpg" in content
    assert b'data-media-path="/media/real-song-one.mp4"' in content

    assert b'data-action="add-to-queue"' in content
    assert b'data-action="edit"' not in content
    assert b'data-action="delete"' not in content
    assert b'data-action="rename"' not in content
    assert b'id="media-edit-modal"' not in content
    assert b"Missing" in content
    assert b'data-has-multi-track="true"' in content
    assert b'data-has-lyrics="true"' in content
    assert b'data-has-multi-track="false"' in content
    assert b'data-has-lyrics="false"' in content

    assert content.count(b">3</p>") >= 1
    assert content.count(b">1</p>") >= 2
    assert content.count(b">2</p>") >= 1

def test_media_management_page_hides_edit_controls_for_guest(client):
    """Guest media library should be queue-only."""
    with TestingSessionLocal() as db:
        db.add(
            MediaItem(
                title="Admin Delete Song",
                artist="Artist",
                media_path="/media/admin-delete-song.mp4",
                missing=False,
            )
        )
        db.commit()

    response = client.get("/media")

    assert response.status_code == 200
    assert b'data-action="add-to-queue"' in response.content
    assert b'data-action="edit"' not in response.content
    assert b'data-action="delete"' not in response.content
    assert b'data-action="scan-library"' not in response.content
    assert b'data-action="upload-media"' not in response.content

def test_media_management_page_shows_edit_controls_for_admin(client):
    """Admin media library should include edit and delete actions."""
    authenticate_admin_client(client)
    with TestingSessionLocal() as db:
        db.add(
            MediaItem(
                title="Admin Delete Song",
                artist="Artist",
                media_path="/media/admin-delete-song.mp4",
                missing=False,
            )
        )
        db.commit()

    response = client.get("/media")

    assert response.status_code == 200
    assert b'data-action="edit"' in response.content
    assert b'data-action="delete"' in response.content
    assert b'data-action="scan-library"' in response.content
    assert b'data-action="upload-media"' in response.content

def test_media_scan_route_reconciles_filesystem_and_database(client, tmp_path):
    """Manual media scan route should create and mark rows from filesystem diff."""
    authenticate_admin_client(client)
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        (settings.media_path / "scan-song.mp4").write_text("video", encoding="utf-8")

        with TestingSessionLocal() as db:
            db.add(
                MediaItem(
                    title="To Missing",
                    media_path="/media/should-be-missing.mp4",
                    missing=False,
                )
            )
            db.commit()

        response = client.post("/api/media/scan")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["summary"]["created"] == 1
        assert payload["summary"]["marked_missing"] == 1

        with TestingSessionLocal() as db:
            created = db.query(MediaItem).filter(MediaItem.media_path == "/media/scan-song.mp4").first()
            assert created is not None
            assert created.title == "scan-song"

            missing_row = db.query(MediaItem).filter(MediaItem.media_path == "/media/should-be-missing.mp4").first()
        assert missing_row is not None
        assert missing_row.missing is True
    finally:
        settings.media_path = original_media

def test_media_scan_route_requires_admin(client):
    """Guest users should not be able to trigger library scans."""
    response = client.post("/api/media/scan")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin session required"

def test_media_scan_single_item_route_refreshes_sidecars(client, tmp_path, monkeypatch):
    """Single-item media scan route should refresh vocals and lyrics sidecars."""
    authenticate_admin_client(client)
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "route-single-item.mp4"
        vocals_file = settings.media_path / "route-single-item.vocals.mp3"
        lyrics_file = settings.media_path / "route-single-item.lrc"
        media_file.write_text("video", encoding="utf-8")
        vocals_file.write_text("vocals", encoding="utf-8")
        lyrics_file.write_text("[00:01.00]lyrics", encoding="utf-8")

        with TestingSessionLocal() as db:
            media = MediaItem(
                title="Route Single Item",
                media_path="/media/route-single-item.mp4",
                missing=True,
            )
            db.add(media)
            db.commit()
            media_id = media.id

        monkeypatch.setattr(
            "routes.media_library.media_library_sync_service.thumbnail_service.ensure_thumbnail_for_media_file",
            lambda path: False,
        )

        response = client.post(f"/api/media/{media_id}/scan")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["summary"]["scanned_files"] == 1
        assert payload["summary"]["restored"] == 1
        assert payload["summary"]["sidecars_updated"] == 1

        with TestingSessionLocal() as db:
            stored = db.query(MediaItem).filter(MediaItem.id == media_id).first()
            assert stored is not None
            assert stored.missing is False
            assert stored.vocals_path == "/media/route-single-item.vocals.mp3"
            assert stored.lyrics_path == "/media/route-single-item.lrc"
            assert stored.last_scanned_at is not None
    finally:
        settings.media_path = original_media

def test_media_delete_route_removes_row_files_and_queue_items(client, tmp_path):
    """Delete route should remove media rows, queue rows, and local files."""
    authenticate_admin_client(client)
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        (settings.cache_path / "lyrics").mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "delete-route.mp4"
        vocals_file = settings.media_path / "delete-route.vocals.mp3"
        lyrics_file = settings.cache_path / "lyrics" / "delete-route.lrc"
        media_file.write_text("video", encoding="utf-8")
        vocals_file.write_text("vocals", encoding="utf-8")
        lyrics_file.write_text("[00:01.00]lyrics", encoding="utf-8")

        with TestingSessionLocal() as db:
            media = MediaItem(
                title="Delete Route",
                artist="Artist",
                media_path="/media/delete-route.mp4",
                vocals_path="/media/delete-route.vocals.mp3",
                lyrics_path="/cache/lyrics/delete-route.lrc",
                missing=False,
            )
            db.add(media)
            db.flush()
            db.add(
                QueueItem(
                    media_id=media.id,
                    position=1000,
                    status=QueueStatus.PENDING,
                )
            )
            db.commit()
            media_id = media.id

        response = client.delete(f"/api/media/{media_id}")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["summary"]["deleted_files"] == 3
        assert payload["summary"]["removed_queue_items"] == 1

        assert not media_file.exists()
        assert not vocals_file.exists()
        assert not lyrics_file.exists()

        with TestingSessionLocal() as db:
            assert db.query(MediaItem).filter(MediaItem.id == media_id).first() is None
            assert db.query(QueueItem).filter(QueueItem.media_id == media_id).count() == 0
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache

def test_media_delete_route_rejects_playing_item(client):
    """Delete route should reject items that are currently playing."""
    authenticate_admin_client(client)
    with TestingSessionLocal() as db:
        media = MediaItem(
            title="Playing Route",
            artist="Artist",
            media_path="/media/playing-route.mp4",
            missing=False,
        )
        db.add(media)
        db.flush()
        db.add(
            QueueItem(
                media_id=media.id,
                position=1000,
                status=QueueStatus.PLAYING,
            )
        )
        db.commit()
        media_id = media.id

    response = client.delete(f"/api/media/{media_id}")
    assert response.status_code == 409
    assert "currently playing" in response.json()["detail"].lower()

def test_media_delete_route_requires_admin(client):
    """Guest users should not be able to delete media through the API."""
    with TestingSessionLocal() as db:
        media = MediaItem(
            title="Guest Delete Blocked",
            media_path="/media/guest-delete-blocked.mp4",
            missing=False,
        )
        db.add(media)
        db.commit()
        media_id = media.id

    response = client.delete(f"/api/media/{media_id}")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin session required"

def test_media_rename_route_updates_database_and_files(client, tmp_path):
    """Rename route should update metadata and on-disk assets."""
    authenticate_admin_client(client)
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        (settings.cache_path / "lyrics").mkdir(parents=True, exist_ok=True)

        old_media = settings.media_path / "old-route.mp4"
        old_vocals = settings.media_path / "old-route.vocals.wav"
        old_lyrics = settings.cache_path / "lyrics" / "old-route.lrc"
        old_media.write_text("video", encoding="utf-8")
        old_vocals.write_text("vocals", encoding="utf-8")
        old_lyrics.write_text("[00:01.00]lyrics", encoding="utf-8")

        with TestingSessionLocal() as db:
            media = MediaItem(
                title="Old Route",
                artist="Old Artist",
                media_path="/media/old-route.mp4",
                vocals_path="/media/old-route.vocals.wav",
                lyrics_path="/cache/lyrics/old-route.lrc",
                missing=False,
            )
            db.add(media)
            db.commit()
            media_id = media.id

        response = client.patch(
            f"/api/media/{media_id}",
            json={
                "title": "New Route",
                "artist": "New Artist",
                "rename_on_disk": True,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["summary"]["renamed_files"] == 3

        expected_stem = build_media_stem("New Route", "New Artist", fallback="old-route")
        assert not old_media.exists()
        assert not old_vocals.exists()
        assert not old_lyrics.exists()
        assert (settings.media_path / f"{expected_stem}.mp4").exists()
        assert (settings.media_path / f"{expected_stem}.vocals.wav").exists()
        assert (settings.cache_path / "lyrics" / f"{expected_stem}.lrc").exists()

        with TestingSessionLocal() as db:
            stored = db.query(MediaItem).filter(MediaItem.id == media_id).first()
            assert stored is not None
            assert stored.title == "New Route"
            assert stored.artist == "New Artist"
            assert stored.media_path == f"/media/{expected_stem}.mp4"
            assert stored.vocals_path == f"/media/{expected_stem}.vocals.wav"
            assert stored.lyrics_path == f"/cache/lyrics/{expected_stem}.lrc"
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache

def test_media_rename_route_can_start_karaoke_task(client, tmp_path):
    """Saving media edits with AI karaoke should start a media task."""
    authenticate_admin_client(client)
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        media_file = settings.media_path / "edit-karaoke.mp4"
        media_file.write_bytes(b"video")
        with TestingSessionLocal() as db:
            media = MediaItem(
                title="Edit Karaoke",
                artist="Artist",
                file_stem="edit-karaoke",
                media_path="/media/edit-karaoke.mp4",
                missing=False,
            )
            db.add(media)
            db.commit()
            media_id = media.id

        healthy = DemucsHealthResponse(api_url="http://demucs", healthy=True, detail="ok")
        with (
            patch(
                "routes.media_library.runtime_settings_service.get_demucs_health",
                return_value=healthy,
            ),
            patch("routes.media_library.task_execution_coordinator.start") as mock_start,
        ):
            response = client.patch(
                f"/api/media/{media_id}",
                json={
                    "title": "Edit Karaoke",
                    "artist": "Artist",
                    "rename_on_disk": False,
                    "is_karaoke": True,
                },
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["karaoke_requested"] is True
        assert payload["karaoke_started"] is True
        assert isinstance(payload["karaoke_task_id"], int)
        mock_start.assert_called_once_with(payload["karaoke_task_id"])
    finally:
        settings.media_path = original_media

def test_media_rename_route_requires_admin(client):
    """Guest users should not be able to edit media metadata."""
    with TestingSessionLocal() as db:
        media = MediaItem(
            title="Guest Edit Blocked",
            media_path="/media/guest-edit-blocked.mp4",
            missing=False,
        )
        db.add(media)
        db.commit()
        media_id = media.id

    response = client.patch(
        f"/api/media/{media_id}",
        json={
            "title": "Blocked",
            "artist": None,
            "rename_on_disk": False,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin session required"

def test_media_rename_route_persists_lyrics_text(client, tmp_path):
    """Media edit should be able to save lyrics text as a sidecar."""
    authenticate_admin_client(client)
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)
        media_file = settings.media_path / "editable.mp4"
        media_file.write_text("video", encoding="utf-8")

        with TestingSessionLocal() as db:
            media = MediaItem(
                title="Editable",
                artist="Singer",
                file_stem="editable",
                media_path="/media/editable.mp4",
                missing=False,
            )
            db.add(media)
            db.commit()
            media_id = media.id

        response = client.patch(
            f"/api/media/{media_id}",
            json={
                "title": "Editable",
                "artist": "Singer",
                "rename_on_disk": False,
                "lyrics_text": "Plain edited lyrics",
                "lyrics_format": "txt",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"]["lyrics_path"] == "/media/editable.txt"
        assert (settings.media_path / "editable.txt").read_text(
            encoding="utf-8"
        ) == "Plain edited lyrics"

        with TestingSessionLocal() as db:
            stored = db.query(MediaItem).filter(MediaItem.id == media_id).first()
            assert stored is not None
            assert stored.lyrics_path == "/media/editable.txt"
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache

def test_media_scan_preserves_edited_media_adjacent_lyrics(client, tmp_path):
    """Library scan should keep lyrics saved from the edit modal."""
    authenticate_admin_client(client)
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)
        media_file = settings.media_path / "scan-edit.mp4"
        media_file.write_text("video", encoding="utf-8")

        with TestingSessionLocal() as db:
            media = MediaItem(
                title="Scan Edit",
                artist="Singer",
                file_stem="scan-edit",
                media_path="/media/scan-edit.mp4",
                missing=False,
            )
            db.add(media)
            db.commit()
            media_id = media.id

        response = client.patch(
            f"/api/media/{media_id}",
            json={
                "title": "Scan Edit",
                "artist": "Singer",
                "rename_on_disk": False,
                "lyrics_text": "[00:01.00]Still here",
                "lyrics_format": "lrc",
            },
        )
        assert response.status_code == 200
        assert response.json()["summary"]["lyrics_path"] == "/media/scan-edit.lrc"

        scan_response = client.post("/api/media/scan")
        assert scan_response.status_code == 200

        with TestingSessionLocal() as db:
            stored = db.query(MediaItem).filter(MediaItem.id == media_id).first()
            assert stored is not None
            assert stored.lyrics_path == "/media/scan-edit.lrc"
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache
