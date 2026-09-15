from pathlib import Path

from services import i18n_service


def test_catalogs_are_loaded_once_for_repeated_translation_and_payload(monkeypatch):
    original_read_text = Path.read_text
    catalog_reads: list[Path] = []

    def tracked_read_text(path: Path, *args, **kwargs):
        if path.parent == i18n_service._LOCALE_DIR:
            catalog_reads.append(path)
        return original_read_text(path, *args, **kwargs)

    i18n_service.load_catalogs.cache_clear()
    monkeypatch.setattr(Path, "read_text", tracked_read_text)
    try:
        assert i18n_service.translate("en", "media.library") == "Media"
        assert i18n_service.translate("en", "media.library") == "Media"
        assert "en" in i18n_service.catalog_payload()
        assert len(catalog_reads) == len(i18n_service.SUPPORTED_LOCALES)
    finally:
        i18n_service.load_catalogs.cache_clear()


def test_cached_catalogs_preserve_fallback_and_interpolation():
    i18n_service.load_catalogs.cache_clear()
    try:
        assert (
            i18n_service.translate("en", "media.queued", title="Test Song")
            == 'Queued "Test Song"'
        )
        assert i18n_service.translate("unsupported", "media.library") == "Media"
        assert i18n_service.translate("en", "missing.translation.key") == "missing.translation.key"
        assert i18n_service.translate("en", "media.queued") == 'Queued "{title}"'
    finally:
        i18n_service.load_catalogs.cache_clear()
