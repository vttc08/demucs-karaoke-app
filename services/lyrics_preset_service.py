"""Stage lyric preset persistence and validation."""

from __future__ import annotations

import json
from typing import Any

from models import LyricsPreset, LyricsPresetCreateRequest, LyricsPresetResponse, LyricsPresetUpdateRequest
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


class LyricsPresetNotFoundError(Exception):
    """Raised when a preset id cannot be resolved."""


class LyricsPresetConflictError(Exception):
    """Raised when a preset name is already in use."""


class LyricsPresetValidationError(ValueError):
    """Raised when preset payloads are incomplete or invalid."""


class LyricsPresetService:
    """CRUD service for shared stage lyric presets."""

    DEFAULT_SETTINGS = {
        "fontPreset": "readable_cjk",
        "customFontFamily": "",
        "customFontWeight": 700,
        "sizeVw": 4.5,
        "lineWidthPct": 85,
        "lineGapVw": 0.8,
        "neighborLineScalePct": 60,
        "neighborLineOpacityPct": 60,
        "textColor": "#fff8df",
        "activeColor": "#ffd84f",
        "outlineColor": "#050505",
        "outlineWidth": 5,
        "previousLines": 1,
        "nextLines": 2,
        "animation": "fade",
        "backgroundMediaEnabled": True,
        "backgroundMediaPath": "",
        "backgroundMediaOpacityPct": 100,
    }
    FONT_PRESETS = {"karaoke_cjk", "readable_cjk", "system_cjk", "serif_cjk", "custom"}
    CUSTOM_FONT_WEIGHTS = {300, 400, 500, 700}
    ANIMATIONS = {"slide", "crop", "fade", "none"}
    BACKGROUND_MEDIA_EXTENSIONS = {
        ".avi",
        ".avif",
        ".gif",
        ".jpeg",
        ".jpg",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp4",
        ".png",
        ".svg",
        ".webm",
        ".webp",
    }
    SETTINGS_KEYS = set(DEFAULT_SETTINGS)

    def list_presets(self, db: Session) -> list[LyricsPresetResponse]:
        """Return all presets sorted by name."""
        rows = (
            db.query(LyricsPreset)
            .order_by(func.lower(LyricsPreset.name).asc(), LyricsPreset.id.asc())
            .all()
        )
        return [self._to_response(row) for row in rows]

    def get_preset(self, db: Session, preset_id: int) -> LyricsPresetResponse:
        """Return a single preset by id."""
        row = db.query(LyricsPreset).filter(LyricsPreset.id == preset_id).first()
        if row is None:
            raise LyricsPresetNotFoundError(f"Preset {preset_id} not found")
        return self._to_response(row)

    def create_preset(
        self, db: Session, payload: LyricsPresetCreateRequest
    ) -> LyricsPresetResponse:
        """Create a new preset from a validated settings payload."""
        name = self._normalize_name(payload.name)
        settings = self.normalize_settings(payload.settings)

        if self._preset_name_exists(db, name):
            raise LyricsPresetConflictError(f"Preset name '{name}' already exists")

        row = LyricsPreset(
            name=name,
            settings_json=self._dump_settings(settings),
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise LyricsPresetConflictError(f"Preset name '{name}' already exists") from exc
        db.refresh(row)
        return self._to_response(row)

    def update_preset(
        self,
        db: Session,
        preset_id: int,
        payload: LyricsPresetUpdateRequest,
    ) -> LyricsPresetResponse:
        """Update an existing preset name and/or settings payload."""
        row = db.query(LyricsPreset).filter(LyricsPreset.id == preset_id).first()
        if row is None:
            raise LyricsPresetNotFoundError(f"Preset {preset_id} not found")

        if payload.name is None and payload.settings is None:
            raise LyricsPresetValidationError("At least one field must be supplied")

        if payload.name is not None:
            new_name = self._normalize_name(payload.name)
            if new_name.lower() != row.name.lower() and self._preset_name_exists(db, new_name, exclude_id=row.id):
                raise LyricsPresetConflictError(f"Preset name '{new_name}' already exists")
            row.name = new_name

        if payload.settings is not None:
            row.settings_json = self._dump_settings(self.normalize_settings(payload.settings))

        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise LyricsPresetConflictError("Preset update conflicted with an existing name") from exc
        db.refresh(row)
        return self._to_response(row)

    def delete_preset(self, db: Session, preset_id: int) -> None:
        """Remove a preset."""
        row = db.query(LyricsPreset).filter(LyricsPreset.id == preset_id).first()
        if row is None:
            raise LyricsPresetNotFoundError(f"Preset {preset_id} not found")
        db.delete(row)
        db.commit()

    def normalize_settings(self, raw_settings: Any) -> dict[str, Any]:
        """Normalize a preset settings object to the stage controller's canonical shape."""
        if not self._is_plain_object(raw_settings):
            raise LyricsPresetValidationError("settings must be a JSON object")
        if not self._has_recognized_key(raw_settings):
            raise LyricsPresetValidationError("settings must include at least one lyric setting")

        return {
            "fontPreset": self._normalize_font_preset(raw_settings.get("fontPreset")),
            "customFontFamily": self._trim_text(raw_settings.get("customFontFamily"), 220),
            "customFontWeight": self._normalize_custom_font_weight(raw_settings.get("customFontWeight")),
            "sizeVw": self._clamp_number(raw_settings.get("sizeVw"), 3.2, 8.8, self.DEFAULT_SETTINGS["sizeVw"]),
            "lineWidthPct": self._round_number(raw_settings.get("lineWidthPct"), 60, 100, self.DEFAULT_SETTINGS["lineWidthPct"]),
            "lineGapVw": self._clamp_number(raw_settings.get("lineGapVw"), 0.2, 2, self.DEFAULT_SETTINGS["lineGapVw"]),
            "neighborLineScalePct": self._round_number(raw_settings.get("neighborLineScalePct"), 30, 100, self.DEFAULT_SETTINGS["neighborLineScalePct"]),
            "neighborLineOpacityPct": self._round_number(raw_settings.get("neighborLineOpacityPct"), 10, 100, self.DEFAULT_SETTINGS["neighborLineOpacityPct"]),
            "textColor": self._normalize_color(raw_settings.get("textColor"), self.DEFAULT_SETTINGS["textColor"]),
            "activeColor": self._normalize_color(raw_settings.get("activeColor"), self.DEFAULT_SETTINGS["activeColor"]),
            "outlineColor": self._normalize_color(raw_settings.get("outlineColor"), self.DEFAULT_SETTINGS["outlineColor"]),
            "outlineWidth": self._round_number(raw_settings.get("outlineWidth"), 2, 14, self.DEFAULT_SETTINGS["outlineWidth"]),
            "previousLines": self._round_number(raw_settings.get("previousLines"), 0, 3, self.DEFAULT_SETTINGS["previousLines"]),
            "nextLines": self._round_number(raw_settings.get("nextLines"), 0, 3, self.DEFAULT_SETTINGS["nextLines"]),
            "animation": self._normalize_animation(raw_settings.get("animation")),
            "backgroundMediaEnabled": raw_settings.get("backgroundMediaEnabled") is not False,
            "backgroundMediaPath": self._normalize_background_media_path(raw_settings.get("backgroundMediaPath")),
            "backgroundMediaOpacityPct": self._round_number(raw_settings.get("backgroundMediaOpacityPct"), 10, 100, self.DEFAULT_SETTINGS["backgroundMediaOpacityPct"]),
        }

    def _to_response(self, row: LyricsPreset) -> LyricsPresetResponse:
        settings = json.loads(row.settings_json)
        return LyricsPresetResponse(
            id=row.id,
            name=row.name,
            settings=settings,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _preset_name_exists(self, db: Session, name: str, exclude_id: int | None = None) -> bool:
        query = db.query(LyricsPreset.id).filter(func.lower(LyricsPreset.name) == name.lower())
        if exclude_id is not None:
            query = query.filter(LyricsPreset.id != exclude_id)
        return query.first() is not None

    def _normalize_name(self, value: Any) -> str:
        if not isinstance(value, str):
            raise LyricsPresetValidationError("name is required")
        name = " ".join(value.split()).strip()
        if not name:
            raise LyricsPresetValidationError("name is required")
        return name[:80]

    def _normalize_font_preset(self, value: Any) -> str:
        value = value if isinstance(value, str) else ""
        return value if value in self.FONT_PRESETS else self.DEFAULT_SETTINGS["fontPreset"]

    def _normalize_custom_font_weight(self, value: Any) -> int:
        try:
            weight = int(value)
        except (TypeError, ValueError):
            return self.DEFAULT_SETTINGS["customFontWeight"]
        return weight if weight in self.CUSTOM_FONT_WEIGHTS else self.DEFAULT_SETTINGS["customFontWeight"]

    def _normalize_animation(self, value: Any) -> str:
        value = value if isinstance(value, str) else ""
        return value if value in self.ANIMATIONS else self.DEFAULT_SETTINGS["animation"]

    def _normalize_color(self, value: Any, fallback: str) -> str:
        color = value if isinstance(value, str) else ""
        color = color.strip()
        return color if len(color) == 7 and color.startswith("#") and all(ch in "0123456789abcdefABCDEF" for ch in color[1:]) else fallback

    def _trim_text(self, value: Any, max_length: int) -> str:
        if not isinstance(value, str):
            return ""
        return value.strip()[:max_length]

    def _normalize_background_media_path(self, value: Any) -> str:
        if not isinstance(value, str):
            return ""
        path = value.strip()
        if not path or len(path) > 500:
            return ""
        if path.startswith(("http://", "https://", "ws://", "wss://", "//")):
            return ""
        if not path.startswith("/media/"):
            return ""
        if "\\" in path or ".." in path:
            return ""

        media_path = path.split("?", 1)[0].lower()
        suffix = f".{media_path.rsplit('.', 1)[-1]}" if "." in media_path else ""
        if suffix not in self.BACKGROUND_MEDIA_EXTENSIONS:
            return ""
        return path

    def _clamp_number(self, value: Any, minimum: float, maximum: float, fallback: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return fallback
        if number < minimum:
            return minimum
        if number > maximum:
            return maximum
        return number

    def _round_number(self, value: Any, minimum: int, maximum: int, fallback: int) -> int:
        number = self._clamp_number(value, minimum, maximum, fallback)
        return int(round(number))

    def _dump_settings(self, settings: dict[str, Any]) -> str:
        return json.dumps(settings, ensure_ascii=False, sort_keys=True)

    def _is_plain_object(self, value: Any) -> bool:
        return isinstance(value, dict)

    def _has_recognized_key(self, value: dict[str, Any]) -> bool:
        return any(key in self.SETTINGS_KEYS for key in value)


lyrics_preset_service = LyricsPresetService()
