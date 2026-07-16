"""Tests for the ready-to-use stage preset bootstrap script."""

from .common import *

import json

from models import LyricsPreset
from scripts.default_presets import DEFAULT_PRESETS, install_stage_assets, seed_default_presets


def test_default_preset_bootstrap_inserts_once_and_preserves_existing_names(db_session):
    """The bootstrap must be idempotent and retain a user-owned duplicate name."""
    db_session.add(LyricsPreset(name="CAP", settings_json='{"user":true}'))
    db_session.commit()

    added, skipped = seed_default_presets(db_session)
    added_again, skipped_again = seed_default_presets(db_session)

    assert "cap" not in added
    assert "cap" in skipped
    assert set(added) == set(DEFAULT_PRESETS) - {"cap"}
    assert added_again == []
    assert set(skipped_again) == set(DEFAULT_PRESETS)

    rows = db_session.query(LyricsPreset).all()
    assert len(rows) == len(DEFAULT_PRESETS)
    assert next(row.settings_json for row in rows if row.name == "CAP") == '{"user":true}'
    branded = next(row for row in rows if row.name == "branded")
    assert json.loads(branded.settings_json)["backgroundMediaPath"] == "/media/branding1.jpg"


def test_default_preset_bootstrap_copies_stage_assets_without_overwriting(tmp_path):
    """Packaged backgrounds belong in MEDIA_PATH and existing user files win."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "branding1.jpg").write_bytes(b"branding")
    (source_dir / "black.png").write_bytes(b"black")
    media_path = tmp_path / "media"

    copied, skipped = install_stage_assets(media_path, source_dir)
    (media_path / "branding1.jpg").write_bytes(b"user branding")
    copied_again, skipped_again = install_stage_assets(media_path, source_dir)

    assert {path.name for path in copied} == {"branding1.jpg", "black.png"}
    assert skipped == []
    assert copied_again == []
    assert {path.name for path in skipped_again} == {"branding1.jpg", "black.png"}
    assert (media_path / "branding1.jpg").read_bytes() == b"user branding"
