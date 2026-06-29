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


def test_media_subtitles_split_merge_page_renders_admin_shell(client, tmp_path, monkeypatch):
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
                        "text": "Hello world",
                        "words": [
                            {"word": "Hello", "start": 0.0, "end": 0.5},
                            {"word": "world", "start": 0.5, "end": 1.0},
                        ],
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

    response = client.get(f"/media-subtitles/{media_id}/split-merge")

    assert response.status_code == 200
    assert 'id="subtitle-split-merge-page"' in response.text
    assert "/static/media_subtitle_split_merge.js" in response.text
    assert "Split/Merge Editor" in response.text
    assert f'data-json-url="/api/media/{media_id}/subtitles/json"' in response.text
    assert f'href="/media-subtitles/{media_id}"' in response.text


def test_media_subtitles_split_merge_page_returns_404_shell_when_json_missing(client, tmp_path, monkeypatch):
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

    response = client.get(f"/media-subtitles/{media_id}/split-merge")

    assert response.status_code == 404
    assert "Subtitle workflow unavailable" in response.text
    assert "This media item does not have synced JSON lyrics" in response.text
    assert f'href="/media-subtitles/{media_id}"' in response.text


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


def test_subtitle_json_process_and_save_routes_round_trip(client, tmp_path, monkeypatch):
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
                        "end": 4.0,
                        "text": "I can get em both I dont wanna choose",
                        "words": [
                            {"word": "I", "start": 0.0, "end": 0.1},
                            {"word": "can", "start": 0.1, "end": 0.2},
                            {"word": "get", "start": 0.2, "end": 0.3},
                            {"word": "em", "start": 0.3, "end": 0.4},
                            {"word": "both", "start": 0.4, "end": 0.5},
                            {"word": "I", "start": 0.5, "end": 0.6},
                            {"word": "dont", "start": 0.6, "end": 0.7},
                            {"word": "wanna", "start": 0.7, "end": 0.8},
                            {"word": "choose", "start": 0.8, "end": 0.9},
                        ],
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

    json_response = client.get(f"/api/media/{media_id}/subtitles/json")
    process_response = client.post(
        f"/api/media/{media_id}/subtitles/process",
        json={
            "segments": json_response.json()["segments"],
            "max_line_length": 12,
            "max_line_length_cjk": 4,
        },
    )
    save_response = client.post(
        f"/api/media/{media_id}/subtitles/save",
        json={
            "segments": process_response.json()["segments"],
            "max_line_length": 12,
            "max_line_length_cjk": 4,
        },
    )

    assert json_response.status_code == 200
    assert json_response.json()["source_format"] == "json"
    assert process_response.status_code == 200
    assert [segment["text"] for segment in process_response.json()["segments"]] == [
        "I can get em",
        "both I",
        "dont",
        "wanna choose",
    ]
    assert save_response.status_code == 200
    assert [segment["text"] for segment in save_response.json()["segments"]] == [
        "I can get em",
        "both I",
        "dont",
        "wanna choose",
    ]
    saved_payload = json.loads(lyrics_file.read_text(encoding="utf-8"))
    assert [segment["text"] for segment in saved_payload["segments"]] == [
        "I can get em",
        "both I",
        "dont",
        "wanna choose",
    ]


def test_subtitle_process_endpoint_reloads_persisted_json_before_rewrapping(client, tmp_path, monkeypatch):
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
                        "text": "I can get em both I dont wanna choose",
                        "words": [
                            {"word": "I", "start": 0.0, "end": 0.1},
                            {"word": "can", "start": 0.1, "end": 0.2},
                            {"word": "get", "start": 0.2, "end": 0.3},
                            {"word": "em", "start": 0.3, "end": 0.4},
                            {"word": "both", "start": 0.4, "end": 0.5},
                            {"word": "I", "start": 0.5, "end": 0.6},
                            {"word": "dont", "start": 0.6, "end": 0.7},
                            {"word": "wanna", "start": 0.7, "end": 0.8},
                            {"word": "choose", "start": 0.8, "end": 0.9},
                        ],
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

    response = client.post(
        f"/api/media/{media_id}/subtitles/process",
        json={
            "segments": [
                {
                    "start": 99.0,
                    "end": 100.0,
                    "text": "local browser edits should not matter",
                    "words": [{"word": "local", "start": 99.0, "end": 99.5}],
                }
            ],
            "max_line_length": 12,
            "max_line_length_cjk": 4,
        },
    )

    assert response.status_code == 200
    assert [segment["text"] for segment in response.json()["segments"]] == [
        "I can get em",
        "both I",
        "dont",
        "wanna choose",
    ]


def test_subtitle_json_endpoint_rejects_non_json_sidecars(client, tmp_path, monkeypatch):
    authenticate_admin_client(client)
    monkeypatch.setattr(settings, "media_path", tmp_path)
    media_file = tmp_path / "song.mp4"
    lyrics_file = tmp_path / "song.lrc"
    media_file.write_bytes(b"video")
    lyrics_file.write_text("[00:00.00]Hello", encoding="utf-8")
    with TestingSessionLocal() as db:
        media = MediaItem(
            title="Song",
            artist="Artist",
            media_path="/media/song.mp4",
            lyrics_path="/media/song.lrc",
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)
        media_id = media.id

    response = client.get(f"/api/media/{media_id}/subtitles/json")

    assert response.status_code == 409
    assert "synced JSON lyrics" in response.json()["detail"]


def test_subtitle_process_endpoint_validates_max_lengths(client):
    authenticate_admin_client(client)
    response = client.post(
        "/api/media/42/subtitles/process",
        json={
            "segments": [],
            "max_line_length": 0,
            "max_line_length_cjk": 12,
        },
    )

    assert response.status_code == 422
