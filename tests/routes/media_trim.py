from .common import *


def test_media_trim_routes_require_admin(client):
    assert client.get("/api/media/42/trim-info").status_code == 403
    assert client.post(
        "/api/media/42/trim",
        json={"start_time": 1.0, "end_time": 2.0},
    ).status_code == 403
    response = client.get("/media-editor/42", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_media_trim_info_and_apply_routes(client):
    authenticate_admin_client(client)
    trim_info = {
        "media_id": 42,
        "title": "Test",
        "artist": "Artist",
        "media_url": "/media/test.mp4",
        "duration": 30.0,
        "has_video": True,
        "has_audio": True,
        "keyframes": [0.0, 10.0, 20.0],
        "vocals_path": None,
        "lyrics_path": None,
        "lyrics_format": None,
    }
    summary = {
        "media_id": 42,
        "requested_start": 4.0,
        "requested_end": 18.0,
        "resolved_start": 0.0,
        "resolved_end": 20.0,
        "duration": 20.0,
        "trimmed_sidecars": [],
    }
    with patch(
        "routes.media_library.media_trim_service.get_trim_info",
        return_value=trim_info,
    ), patch(
        "routes.media_library.media_trim_service.trim_media_item",
        return_value=summary,
    ) as trim:
        info_response = client.get("/api/media/42/trim-info")
        trim_response = client.post(
            "/api/media/42/trim",
            json={"start_time": 4.0, "end_time": 18.0},
        )

    assert info_response.status_code == 200
    assert info_response.json()["keyframes"] == [0.0, 10.0, 20.0]
    assert trim_response.status_code == 200
    assert trim_response.json()["summary"]["resolved_end"] == 20.0
    trim.assert_called_once()


def test_media_editor_page_renders_loading_shell_without_keyframes_probe(
    client, monkeypatch, tmp_path
):
    authenticate_admin_client(client)
    monkeypatch.setattr(settings, "media_path", tmp_path)
    media_file = tmp_path / "test.mp4"
    media_file.write_bytes(b"video")
    with TestingSessionLocal() as db:
        media = MediaItem(title="Test", artist="Artist", media_path="/media/test.mp4")
        db.add(media)
        db.commit()
        db.refresh(media)
        media_id = media.id
    with patch(
        "routes.pages.media_trim_service.get_trim_info",
        side_effect=AssertionError("keyframe probe should not run for the shell"),
    ):
        response = client.get(f"/media-editor/{media_id}")

    assert response.status_code == 200
    assert 'data-editor-state="loading"' in response.text
    assert 'id="trim-loading-state"' in response.text
    assert 'id="trim-keyframe-canvas"' in response.text
    assert 'id="trim-media-player"' in response.text
    assert 'id="trim-playhead"' in response.text
    assert 'id="trim-prev-iframe"' in response.text
    assert 'id="trim-next-iframe"' in response.text
    assert 'data-keyframes=' not in response.text
    assert "Loading keyframes" in response.text
    assert "Test" in response.text
    assert "Artist" in response.text
    assert "/static/media_editor.js" in response.text


def test_media_editor_page_renders_cdg_transcode_shell(
    client, monkeypatch, tmp_path
):
    authenticate_admin_client(client)
    monkeypatch.setattr(settings, "media_path", tmp_path)
    media_file = tmp_path / "cdg-track.mp3"
    lyrics_file = tmp_path / "cdg-track.cdg"
    media_file.write_bytes(b"audio")
    lyrics_file.write_bytes(b"cdg")
    with TestingSessionLocal() as db:
        media = MediaItem(
            title="CDG Track",
            artist="Artist",
            media_path="/media/cdg-track.mp3",
            lyrics_path="/media/cdg-track.cdg",
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)
        media_id = media.id

    response = client.get(f"/media-editor/{media_id}")

    assert response.status_code == 200
    assert 'data-lyrics-kind="cdg"' in response.text
    assert 'id="trim-cdg-panel"' in response.text
    assert 'id="trim-transcode"' in response.text
    assert "Transcode to MP4" in response.text


def test_media_editor_page_honors_explicit_cdg_mode(
    client, monkeypatch, tmp_path
):
    authenticate_admin_client(client)
    monkeypatch.setattr(settings, "media_path", tmp_path)
    media_file = tmp_path / "cdg-track.mp3"
    media_file.write_bytes(b"audio")
    with TestingSessionLocal() as db:
        media = MediaItem(
            title="CDG Track",
            artist="Artist",
            media_path="/media/cdg-track.mp3",
            lyrics_path=None,
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)
        media_id = media.id

    response = client.get(f"/media-editor/{media_id}?mode=cdg")

    assert response.status_code == 200
    assert 'data-lyrics-kind="cdg"' in response.text
    assert 'id="trim-cdg-panel"' in response.text


def test_media_editor_page_infers_cdg_mode_from_sidecar_file(
    client, monkeypatch, tmp_path
):
    authenticate_admin_client(client)
    monkeypatch.setattr(settings, "media_path", tmp_path)
    media_file = tmp_path / "cdg-track.mp3"
    lyrics_file = tmp_path / "cdg-track.cdg"
    media_file.write_bytes(b"audio")
    lyrics_file.write_bytes(b"cdg")
    with TestingSessionLocal() as db:
        media = MediaItem(
            title="CDG Track",
            artist="Artist",
            media_path="/media/cdg-track.mp3",
            lyrics_path=None,
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)
        media_id = media.id

    response = client.get(f"/media-editor/{media_id}")

    assert response.status_code == 200
    assert 'data-lyrics-kind="cdg"' in response.text
    assert 'id="trim-cdg-panel"' in response.text


def test_media_cdg_transcode_route_creates_task(client, monkeypatch, tmp_path):
    authenticate_admin_client(client)
    media_root = tmp_path / "media"
    media_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)

    media_file = media_root / "cdg-track.mp3"
    lyrics_file = media_root / "cdg-track.cdg"
    media_file.write_bytes(b"audio")
    lyrics_file.write_bytes(b"cdg")
    with TestingSessionLocal() as db:
        media = MediaItem(
            title="CDG Track",
            artist="Artist",
            media_path="/media/cdg-track.mp3",
            lyrics_path="/media/cdg-track.cdg",
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)
        media_id = media.id

    response = client.post(
        f"/api/media/{media_id}/transcode-cdg",
        json={"overwrite_original": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_type"] == "media_cdg_transcode"
    assert payload["source_kind"] == "library_media_overwrite"
    assert payload["target_media_item_id"] == media_id
