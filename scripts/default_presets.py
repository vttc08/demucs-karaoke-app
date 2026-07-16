"""Install the built-in stage lyric presets and their background assets.

Run from the application checkout after configuring ``DATABASE_URL`` and
``MEDIA_PATH``:

    uv run python scripts/default_presets.py

The command is safe to run again. It never replaces a preset or media asset
that is already present in the user's environment.
"""

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
from database import SessionLocal, init_db
from models import LyricsPreset


cap = {"fontPreset": "custom", "customFontFamily": "Roboto", "customFontWeight": 700, "sizeVw": 4.5, "lineWidthPct": 90, "lineGapVw": 0.8, "neighborLineScalePct": 73, "neighborLineOpacityPct": 75, "textColor": "#939393", "activeColor": "#ffffff", "outlineColor": "#000000", "outlineWidth": 2, "previousLines": 1, "nextLines": 2, "lineBehavior": "rolling", "animation": "slide", "backgroundMediaEnabled": False, "backgroundMediaPath": "", "backgroundMediaOpacityPct": 62}

cyber = {"fontPreset": "custom", "customFontFamily": "Orbitron", "customFontWeight": 700, "sizeVw": 4.1, "lineWidthPct": 90, "lineGapVw": 1.15, "neighborLineScalePct": 62, "neighborLineOpacityPct": 32, "textColor": "#d9faff", "activeColor": "#39ff88", "outlineColor": "#001b22", "outlineWidth": 6, "previousLines": 1, "nextLines": 2, "lineBehavior": "fixed_group", "animation": "crop", "backgroundMediaEnabled": False, "backgroundMediaPath": "", "backgroundMediaOpacityPct": 86}

classic = {"fontPreset": "custom", "customFontFamily": "Playfair Display", "customFontWeight": 700, "sizeVw": 4.2, "lineWidthPct": 76, "lineGapVw": 1.45, "neighborLineScalePct": 74, "neighborLineOpacityPct": 40, "textColor": "#f8efd8", "activeColor": "#e8bd55", "outlineColor": "#1c1409", "outlineWidth": 5, "previousLines": 1, "nextLines": 1, "lineBehavior": "rolling", "animation": "crop", "backgroundMediaEnabled": False, "backgroundMediaPath": "", "backgroundMediaOpacityPct": 78}

fun = {"fontPreset": "custom", "customFontFamily": "Playfair Display", "customFontWeight": 700, "sizeVw": 4.2, "lineWidthPct": 76, "lineGapVw": 1.45, "neighborLineScalePct": 74, "neighborLineOpacityPct": 40, "textColor": "#f8efd8", "activeColor": "#e8bd55", "outlineColor": "#1c1409", "outlineWidth": 5, "previousLines": 1, "nextLines": 1, "lineBehavior": "rolling", "animation": "crop", "backgroundMediaEnabled": False, "backgroundMediaPath": "", "backgroundMediaOpacityPct": 78}

country = {"fontPreset": "custom", "customFontFamily": "Alfa Slab One", "customFontWeight": 400, "sizeVw": 4.6, "lineWidthPct": 85, "lineGapVw": 1.1, "neighborLineScalePct": 65, "neighborLineOpacityPct": 45, "textColor": "#eed6b1", "activeColor": "#ffaa00", "outlineColor": "#2b1a09", "outlineWidth": 5, "previousLines": 1, "nextLines": 2, "lineBehavior": "rolling", "animation": "crop", "backgroundMediaEnabled": False, "backgroundMediaPath": "", "backgroundMediaOpacityPct": 100}

neon = {"fontPreset": "custom", "customFontFamily": "Bungee", "customFontWeight": 400, "sizeVw": 3.8, "lineWidthPct": 90, "lineGapVw": 1.2, "neighborLineScalePct": 68, "neighborLineOpacityPct": 38, "textColor": "#f6e7ff", "activeColor": "#00f5ff", "outlineColor": "#2b0045", "outlineWidth": 6, "previousLines": 1, "nextLines": 2, "lineBehavior": "fixed_group", "animation": "crop", "backgroundMediaEnabled": False, "backgroundMediaPath": "", "backgroundMediaOpacityPct": 82}

branded = {"fontPreset": "custom", "customFontFamily": "Nunito", "customFontWeight": 700, "sizeVw": 4, "lineWidthPct": 85, "lineGapVw": 0.8, "neighborLineScalePct": 100, "neighborLineOpacityPct": 100, "textColor": "#833e1d", "activeColor": "#ff8040", "outlineColor": "#000000", "outlineWidth": 4, "previousLines": 0, "nextLines": 3, "lineBehavior": "fixed_group", "animation": "crop", "backgroundMediaEnabled": True, "backgroundMediaPath": "/media/branding1.jpg", "backgroundMediaOpacityPct": 100}

zh_caligraphy = {"fontPreset": "custom", "customFontFamily": "Zhi Mang Xing", "customFontWeight": 400, "sizeVw": 4.65, "lineWidthPct": 86, "lineGapVw": 1.45, "neighborLineScalePct": 68, "neighborLineOpacityPct": 38, "textColor": "#c0c0c0", "activeColor": "#408080", "outlineColor": "#183c55", "outlineWidth": 6, "previousLines": 1, "nextLines": 2, "lineBehavior": "rolling", "animation": "crop", "backgroundMediaEnabled": False, "backgroundMediaPath": "", "backgroundMediaOpacityPct": 78}

zh_fun = {"fontPreset": "custom", "customFontFamily": "ZCOOL KuaiLe", "customFontWeight": 400, "sizeVw": 4.65, "lineWidthPct": 86, "lineGapVw": 1.45, "neighborLineScalePct": 68, "neighborLineOpacityPct": 38, "textColor": "#fffdf3", "activeColor": "#47e5ff", "outlineColor": "#183c55", "outlineWidth": 6, "previousLines": 1, "nextLines": 2, "lineBehavior": "rolling", "animation": "crop", "backgroundMediaEnabled": False, "backgroundMediaPath": "", "backgroundMediaOpacityPct": 78}

blue = {"fontPreset": "custom", "customFontFamily": "Lora", "customFontWeight": 700, "sizeVw": 4, "lineWidthPct": 78, "lineGapVw": 1.5, "neighborLineScalePct": 65, "neighborLineOpacityPct": 45, "textColor": "#add8f1", "activeColor": "#1b9ee4", "outlineColor": "#102656", "outlineWidth": 5, "previousLines": 0, "nextLines": 3, "lineBehavior": "fixed_group", "animation": "crop", "backgroundMediaEnabled": False, "backgroundMediaPath": "", "backgroundMediaOpacityPct": 100}

dimmed = {"fontPreset": "readable_cjk", "customFontFamily": "", "customFontWeight": 700, "sizeVw": 3.9, "lineWidthPct": 85, "lineGapVw": 0.8, "neighborLineScalePct": 73, "neighborLineOpacityPct": 75, "textColor": "#ffffff", "activeColor": "#ad75e4", "outlineColor": "#000000", "outlineWidth": 8, "previousLines": 1, "nextLines": 2, "lineBehavior": "rolling", "animation": "crop", "backgroundMediaEnabled": True, "backgroundMediaPath": "/media/black.png", "backgroundMediaOpacityPct": 55}

DEFAULT_PRESETS: Mapping[str, dict] = {
    "cap": cap,
    "cyber": cyber,
    "classic": classic,
    "fun": fun,
    "country": country,
    "neon": neon,
    "branded": branded,
    "zh_caligraphy": zh_caligraphy,
    "zh_fun": zh_fun,
    "blue": blue,
    "dimmed": dimmed,
}
STAGE_ASSETS_DIR = ROOT / "static" / "stage"
STAGE_ASSET_NAMES = ("branding1.jpg", "black.png")


def seed_default_presets(db: Session) -> tuple[list[str], list[str]]:
    """Insert missing built-in presets, matching names without case sensitivity."""
    added: list[str] = []
    skipped: list[str] = []

    for name, preset_settings in DEFAULT_PRESETS.items():
        existing = (
            db.query(LyricsPreset.id)
            .filter(func.lower(LyricsPreset.name) == name.lower())
            .first()
        )
        if existing is not None:
            skipped.append(name)
            continue

        db.add(
            LyricsPreset(
                name=name,
                settings_json=json.dumps(preset_settings, separators=(",", ":")),
            )
        )
        added.append(name)

    db.commit()
    return added, skipped


def install_stage_assets(media_path: Path, source_dir: Path = STAGE_ASSETS_DIR) -> tuple[list[Path], list[Path]]:
    """Copy packaged background assets to MEDIA_PATH without replacing user files."""
    media_path.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    skipped: list[Path] = []

    for asset_name in STAGE_ASSET_NAMES:
        source = source_dir / asset_name
        if not source.is_file():
            raise FileNotFoundError(f"Built-in stage asset is missing: {source}")

        destination = media_path / asset_name
        if destination.exists():
            skipped.append(destination)
            continue

        shutil.copy2(source, destination)
        copied.append(destination)

    return copied, skipped


def main() -> int:
    """Install ready-to-use shared presets and their optional background media."""
    try:
        init_db()
        with SessionLocal() as db:
            added, skipped = seed_default_presets(db)
        copied, existing_assets = install_stage_assets(settings.media_path)
    except Exception as error:
        print(f"Unable to install default presets: {error}", file=sys.stderr)
        return 1

    print(f"Presets added: {', '.join(added) if added else 'none'}")
    print(f"Presets already present: {', '.join(skipped) if skipped else 'none'}")
    print(f"Assets copied to {settings.media_path}: {', '.join(path.name for path in copied) if copied else 'none'}")
    print(f"Assets already present: {', '.join(path.name for path in existing_assets) if existing_assets else 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
