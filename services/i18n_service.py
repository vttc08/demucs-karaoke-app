"""Frontend internationalization helpers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from config import Settings

from fastapi import Request


LOCALE_COOKIE = "karaoke_locale"
DEFAULT_LOCALE = "en"
ENABLED_LOCALES = Settings().enabled_locales.split(",")
ALL_LOCALES = {
    "en": "English",
    "fr": "Français",
    "zh-CN": "简体中文",
    "zh-TW": "繁體中文",
}
SUPPORTED_LOCALES = {code: label for code, label in ALL_LOCALES.items() if code in ENABLED_LOCALES}
_LOCALE_DIR = Path(__file__).resolve().parent.parent / "locales"


def load_catalogs() -> dict[str, dict[str, str]]:
    """Load locale catalogs from disk."""
    catalogs: dict[str, dict[str, str]] = {}
    for locale in SUPPORTED_LOCALES:
        path = _LOCALE_DIR / f"{locale}.json"
        catalogs[locale] = json.loads(path.read_text(encoding="utf-8"))
    return catalogs


def normalize_locale(locale: str | None) -> str | None:
    """Return a supported locale code for common aliases."""
    if not locale:
        return None
    cleaned = locale.strip().replace("_", "-")
    if cleaned in SUPPORTED_LOCALES:
        return cleaned
    lowered = cleaned.lower()
    if lowered == "zh" or lowered.startswith("zh-cn") or lowered.startswith("zh-hans"):
        return "zh-CN"
    if lowered == "zh-tw" or lowered.startswith("zh-hant"):
        return "zh-TW"
    all_supported_languages = [code.lower() for code in SUPPORTED_LOCALES]
    if lowered in all_supported_languages:
        return next(code for code in SUPPORTED_LOCALES if code.lower() == lowered)
    return None


def resolve_locale(request: Request | None) -> str:
    """Resolve the active frontend locale for a request."""
    if request is None:
        return DEFAULT_LOCALE

    cookie_locale = normalize_locale(request.cookies.get(LOCALE_COOKIE))
    if cookie_locale:
        return cookie_locale

    accept_language = request.headers.get("accept-language", "")
    for raw_part in accept_language.split(","):
        locale_part = raw_part.split(";", 1)[0]
        accepted = normalize_locale(locale_part)
        if accepted:
            return accepted

    return DEFAULT_LOCALE


def translate(locale: str, key: str, **params: Any) -> str:
    """Translate a key with English fallback."""
    catalogs = load_catalogs()
    template = catalogs.get(locale, {}).get(key) or catalogs[DEFAULT_LOCALE].get(key) or key
    if params:
        try:
            return template.format(**params)
        except (KeyError, ValueError):
            return template
    return template


def catalog_payload() -> dict[str, dict[str, str]]:
    """Return all frontend catalogs for the browser helper."""
    return load_catalogs()


def supported_locale_options() -> list[dict[str, str]]:
    """Return locale options for templates."""
    return [{"code": code, "label": label} for code, label in SUPPORTED_LOCALES.items()]
