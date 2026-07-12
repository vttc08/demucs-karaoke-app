from .common import *
from services.lyrics_preset_service import (
    LyricsPresetConflictError,
    LyricsPresetService,
    LyricsPresetNotFoundError,
    LyricsPresetValidationError,
)


def test_lyrics_preset_service_normalizes_settings_payload():
    """Preset settings should normalize to the same canonical shape as the stage controller."""
    service = LyricsPresetService()

    normalized = service.normalize_settings(
        {
            "fontPreset": "unknown",
            "customFontFamily": "  Noto Sans SC  ",
            "customFontWeight": 900,
            "sizeVw": 50,
            "lineWidthPct": 12,
            "lineGapVw": 50,
            "neighborLineScalePct": 27,
            "neighborLineOpacityPct": 3,
            "textColor": "not-a-color",
            "activeColor": "#123456",
            "outlineColor": "#abcdef",
            "outlineWidth": 99,
                "previousLines": -1,
                "nextLines": 6,
                "animation": "spin",
                "backgroundMediaEnabled": False,
                "backgroundMediaPath": "/media/brand-loop.mp4",
                "backgroundMediaOpacityPct": 2,
            }
        )

    assert normalized == {
        "fontPreset": "readable_cjk",
        "customFontFamily": "Noto Sans SC",
        "customFontWeight": 700,
        "sizeVw": 8.8,
        "lineWidthPct": 60,
        "lineGapVw": 2,
        "neighborLineScalePct": 30,
        "neighborLineOpacityPct": 10,
        "textColor": "#fff8df",
        "activeColor": "#123456",
        "outlineColor": "#abcdef",
        "outlineWidth": 14,
        "previousLines": 0,
        "nextLines": 3,
        "animation": "fade",
        "backgroundMediaEnabled": False,
        "backgroundMediaPath": "/media/brand-loop.mp4",
        "backgroundMediaOpacityPct": 10,
    }


def test_lyrics_preset_service_crud_round_trip(db_session):
    """Preset CRUD should persist and return canonical JSON settings."""
    service = LyricsPresetService()

    created = service.create_preset(
        db_session,
        LyricsPresetCreateRequest(
            name=" TV Pink ",
            settings={
                "fontPreset": "custom",
                "customFontFamily": '"Noto Sans SC", sans-serif',
                "customFontWeight": 500,
                "sizeVw": 4.1,
                "lineGapVw": 1.4,
                "animation": "slide",
                "activeColor": "#ff00aa",
                "backgroundMediaEnabled": False,
                "backgroundMediaPath": "/media/brand-loop.webm",
                "backgroundMediaOpacityPct": 72,
            },
        ),
    )

    assert created.name == "TV Pink"
    assert created.settings["fontPreset"] == "custom"
    assert created.settings["customFontFamily"] == '"Noto Sans SC", sans-serif'
    assert created.settings["customFontWeight"] == 500
    assert created.settings["lineGapVw"] == 1.4
    assert created.settings["activeColor"] == "#ff00aa"
    assert created.settings["backgroundMediaEnabled"] is False
    assert created.settings["backgroundMediaPath"] == "/media/brand-loop.webm"
    assert created.settings["backgroundMediaOpacityPct"] == 72

    listed = service.list_presets(db_session)
    assert [item.id for item in listed] == [created.id]

    fetched = service.get_preset(db_session, created.id)
    assert fetched.id == created.id
    assert fetched.settings == created.settings

    updated = service.update_preset(
        db_session,
        created.id,
        LyricsPresetUpdateRequest(
            name="Bedroom TV",
            settings={
                "fontPreset": "readable_cjk",
                "sizeVw": 5.2,
                "textColor": "#eeeeee",
            },
        ),
    )

    assert updated.name == "Bedroom TV"
    assert updated.settings["fontPreset"] == "readable_cjk"
    assert updated.settings["sizeVw"] == 5.2
    assert updated.settings["textColor"] == "#eeeeee"

    service.delete_preset(db_session, created.id)
    with pytest.raises(LyricsPresetNotFoundError):
        service.get_preset(db_session, created.id)


def test_lyrics_preset_service_rejects_duplicate_names(db_session):
    """Preset names should be unique regardless of case."""
    service = LyricsPresetService()
    service.create_preset(
        db_session,
        LyricsPresetCreateRequest(
            name="TV",
            settings={"fontPreset": "readable_cjk"},
        ),
    )

    with pytest.raises(LyricsPresetConflictError):
        service.create_preset(
            db_session,
            LyricsPresetCreateRequest(
                name=" tv ",
                settings={"fontPreset": "custom", "customFontFamily": "Sans"},
            ),
        )


def test_lyrics_preset_service_requires_settings_object():
    """Preset settings payloads need at least one recognized lyric key."""
    service = LyricsPresetService()

    with pytest.raises(LyricsPresetValidationError):
        service.normalize_settings({})
