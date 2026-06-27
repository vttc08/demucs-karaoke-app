from .common import *


def test_lyrics_presets_api_requires_admin(client):
    """Preset CRUD should be admin-only."""
    response = client.get("/api/lyrics-presets/")
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin session required"


def test_lyrics_presets_api_crud(client):
    """Preset API should support create, read, update, and delete."""
    authenticate_admin_client(client)

    create_response = client.post(
        "/api/lyrics-presets/",
        json={
            "name": "Pink TV",
            "settings": {
                "fontPreset": "custom",
                "customFontFamily": '"Noto Sans SC", sans-serif',
                "sizeVw": 4.2,
                "activeColor": "#ff00aa",
                "backgroundMediaEnabled": False,
                "backgroundMediaPath": "/media/brand-loop.mp4",
                "backgroundMediaOpacityPct": 72,
            },
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["name"] == "Pink TV"
    assert created["settings"]["fontPreset"] == "custom"
    assert created["settings"]["activeColor"] == "#ff00aa"
    assert created["settings"]["backgroundMediaEnabled"] is False
    assert created["settings"]["backgroundMediaPath"] == "/media/brand-loop.mp4"
    assert created["settings"]["backgroundMediaOpacityPct"] == 72

    list_response = client.get("/api/lyrics-presets/")
    assert list_response.status_code == 200
    assert [preset["id"] for preset in list_response.json()] == [created["id"]]

    get_response = client.get(f"/api/lyrics-presets/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["settings"] == created["settings"]

    update_response = client.patch(
        f"/api/lyrics-presets/{created['id']}",
        json={
            "name": "Bedroom TV",
            "settings": {
                "fontPreset": "readable_cjk",
                "sizeVw": 5.1,
                "textColor": "#eeeeee",
                "backgroundMediaEnabled": False,
                "backgroundMediaPath": "https://example.com/brand.mp4",
                "backgroundMediaOpacityPct": 200,
            },
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == "Bedroom TV"
    assert updated["settings"]["fontPreset"] == "readable_cjk"
    assert updated["settings"]["sizeVw"] == 5.1
    assert updated["settings"]["textColor"] == "#eeeeee"
    assert updated["settings"]["backgroundMediaEnabled"] is False
    assert updated["settings"]["backgroundMediaPath"] == ""
    assert updated["settings"]["backgroundMediaOpacityPct"] == 100

    delete_response = client.delete(f"/api/lyrics-presets/{created['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "ok"

    missing_response = client.get(f"/api/lyrics-presets/{created['id']}")
    assert missing_response.status_code == 404


def test_lyrics_presets_api_rejects_invalid_payload(client):
    """Preset API should reject invalid settings payloads."""
    authenticate_admin_client(client)

    response = client.post(
        "/api/lyrics-presets/",
        json={"name": "Broken", "settings": {"not": "recognized"}},
    )
    assert response.status_code == 400
    assert "lyric setting" in response.json()["detail"]
