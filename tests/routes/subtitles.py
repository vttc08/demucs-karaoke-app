from .common import *

from io import BytesIO


def test_subtitle_routes_require_admin(client):
    assert client.get("/api/media/42/subtitles/ass").status_code == 403
    assert client.get("/api/media/42/subtitles/srt").status_code == 403
    assert client.post(
        "/api/media/42/subtitles/preview",
        files={"file": ("edited.ass", b"", "text/plain")},
    ).status_code == 403
    assert client.post(
        "/api/media/42/subtitles/upload",
        files={"file": ("edited.srt", b"", "text/plain")},
    ).status_code == 403
    response = client.get("/media-subtitles/42", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_media_subtitles_page_renders_admin_shell(client, tmp_path, monkeypatch):
    authenticate_admin_client(client)
    monkeypatch.setattr(settings, "media_path", tmp_path)
    media_file = tmp_path / "song.mp4"
    lyrics_file = tmp_path / "song.json"
    media_file.write_bytes(b"video")
    lyrics_file.write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "start": 0.0,
                        "end": 1.0,
                        "text": "Hello",
                        "words": [{"word": "Hello", "start": 0.0, "end": 1.0}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with TestingSessionLocal() as db:
        media = MediaItem(
            title="Song",
            artist="Artist",
            media_path="/media/song.mp4",
            lyrics_path="/media/song.json",
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)
        media_id = media.id

    response = client.get(f"/media-subtitles/{media_id}")

    assert response.status_code == 200
    assert 'id="subtitle-workflow-page"' in response.text
    assert f'data-media-id="{media_id}"' in response.text
    assert "/static/media_subtitles.js" in response.text
    assert "Lyrics Editor" in response.text
    assert 'data-subtitle-upload-form="ass"' in response.text
    assert 'data-subtitle-upload-form="srt"' in response.text


def test_media_subtitles_page_shows_404_when_synced_lyrics_are_missing(client, tmp_path, monkeypatch):
    authenticate_admin_client(client)
    monkeypatch.setattr(settings, "media_path", tmp_path)
    media_file = tmp_path / "song.mp4"
    media_file.write_bytes(b"video")
    with TestingSessionLocal() as db:
        media = MediaItem(
            title="Song",
            artist="Artist",
            media_path="/media/song.mp4",
            lyrics_path=None,
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)
        media_id = media.id

    response = client.get(f"/media-subtitles/{media_id}")

    assert response.status_code == 404
    assert "Subtitle workflow unavailable" in response.text
    assert "This media item does not have synced JSON lyrics" in response.text
    assert "history.back()" in response.text
    assert "/media" in response.text


def test_media_subtitles_page_shows_404_when_lyrics_sidecar_is_missing(client, tmp_path, monkeypatch):
    authenticate_admin_client(client)
    monkeypatch.setattr(settings, "media_path", tmp_path)
    media_file = tmp_path / "song.mp4"
    lyrics_file = tmp_path / "song.json"
    media_file.write_bytes(b"video")
    lyrics_file.unlink(missing_ok=True)
    with TestingSessionLocal() as db:
        media = MediaItem(
            title="Song",
            artist="Artist",
            media_path="/media/song.mp4",
            lyrics_path="/media/song.json",
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)
        media_id = media.id

    response = client.get(f"/media-subtitles/{media_id}")

    assert response.status_code == 404
    assert "Subtitle workflow unavailable" in response.text
    assert "could not be found" in response.text


def test_subtitle_export_routes_return_downloads(client):
    authenticate_admin_client(client)
    with patch(
        "routes.media_subtitles.subtitle_workflow_service.build_export_text",
        return_value=("ASS CONTENT", "song.ass", {"warning_count": 0}),
    ) as build_export:
        ass_response = client.get("/api/media/42/subtitles/ass")
        srt_response = client.get("/api/media/42/subtitles/srt")

    assert ass_response.status_code == 200
    assert srt_response.status_code == 200
    assert "attachment; filename=\"song.ass\"" in ass_response.headers["content-disposition"]
    assert ass_response.text == "ASS CONTENT"
    assert srt_response.text == "ASS CONTENT"
    assert build_export.call_count == 2


def test_subtitle_preview_and_upload_routes_forward_uploads(client):
    authenticate_admin_client(client)
    with patch(
        "routes.media_subtitles.subtitle_workflow_service.preview_upload",
        return_value={
            "status": "ok",
            "media_id": 42,
            "source_format": "ass",
            "preview": {"warning_count": 1, "warnings": [{"type": "overlap"}]},
        },
    ) as preview_upload, patch(
        "routes.media_subtitles.subtitle_workflow_service.replace_from_upload",
        return_value={"status": "ok", "media_id": 42, "lyrics_path": "/media/song.json"},
    ) as replace_upload:
        preview_response = client.post(
            "/api/media/42/subtitles/preview",
            files={"file": ("edited.ass", b"content", "text/plain")},
        )
        upload_response = client.post(
            "/api/media/42/subtitles/upload",
            files={"file": ("edited.srt", b"content", "text/plain")},
        )

    assert preview_response.status_code == 200
    assert upload_response.status_code == 200
    assert preview_response.json()["preview"]["warning_count"] == 1
    assert upload_response.json()["lyrics_path"] == "/media/song.json"
    preview_upload.assert_called_once()
    replace_upload.assert_called_once()

