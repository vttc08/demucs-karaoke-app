"""Checks that app locale catalogs have a reachable MkDocs language tree."""
from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _mkdocs_i18n_config() -> dict:
    config = yaml.load(
        (ROOT / "docs-site" / "mkdocs.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    return next(plugin["i18n"] for plugin in config["plugins"] if isinstance(plugin, dict) and "i18n" in plugin)


def test_every_locale_catalog_has_a_mkdocs_language_with_default_fallback():
    """New UI catalogs must not create unformatted or missing docs links."""
    i18n = _mkdocs_i18n_config()
    configured_locales = {language["locale"] for language in i18n["languages"]}
    catalog_locales = {path.stem for path in (ROOT / "locales").glob("*.json")}
    primary_language_slugs = {locale.split("-", 1)[0].lower() for locale in catalog_locales}

    assert i18n["fallback_to_default"].lower() == "true"
    assert primary_language_slugs <= configured_locales
    assert sum(str(language.get("default", "false")).lower() == "true" for language in i18n["languages"]) == 1
    assert json.loads((ROOT / "locales" / "en.json").read_text(encoding="utf-8"))
