# Internationalization

The app uses a small catalog-based i18n setup for frontend UI text.

## Current Locales

- `en`: English fallback/source catalog
- `zh-CN`: Simplified Chinese UI catalog
- `fr`: French UI catalog

Only frontend UI copy is translated. Song titles, artists, lyrics, media filenames, provider output,
and API payload content remain unchanged.

Only enabled locales are loaded at runtime. To enable a locale, add it to the `ENABLED_LOCALES` env var in `.env`.

## Runtime Flow

- `services/i18n_service.py` resolves locale from `karaoke_locale`, then `Accept-Language`, then `en`.
- Templates call `t("key")`.
- Browser scripts call `window.KaraokeI18n.t("key", params)`.
- The header language selector posts to `POST /language`, which sets `karaoke_locale` and redirects
  back to the current app-local page.

## Add A Locale

1. Add the locale code and label to `ALL_LOCALES` in `services/i18n_service.py`.
2. Create `locales/<code>.json` with the same keys as `locales/en.json`.
3. Translate UI strings only; keep placeholders like `{title}` and `{count}` unchanged.
4. Run:

```bash
uv run pytest tests/routes/pages.py::test_locale_catalogs_have_matching_keys
```

Also run the catalog reachability audit:

```bash
uv run python scripts/audit_i18n.py --check
```

If production code intentionally constructs a key dynamically, list that exact key in `DYNAMIC_KEYS` in `scripts/audit_i18n.py` rather than retaining unrelated catalog entries.

The route tests include a catalog key parity check so missing translations fail fast.
