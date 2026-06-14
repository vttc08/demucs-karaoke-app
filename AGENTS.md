# AGENTS.md

## Project summary
This is a lightweight AI-powered karaoke app for home use.

## Priorities
1. Keep the MVP simple and working end-to-end.
2. Use the `Karaoke` project board as the source of truth for active tasks.
3. Prefer server-rendered HTML with minimal JavaScript.
4. Use FastAPI for backend APIs and page serving.
5. Keep code modular and easy to continue from a mobile SSH workflow.
6. Bind development servers to `0.0.0.0`.
7. Add tests for routes and core service logic.
8. Update docs in `/docs` when behavior or architecture changes.

## Constraints
- Do not implement future sprints unless explicitly requested.
- Do not add a complex frontend framework unless explicitly requested.
- Demucs runs on a separate machine and must be accessed through a simple API client.
- Most development happens over SSH/tmux/mobile, so keep workflows CLI-friendly.

## Coding rules
- Prefer simple Python modules over heavy abstractions.
- Use `uv` for virtual environment management and running commands.
- Run Python entrypoints through `uv run`; bare `python` is not guaranteed to be on PATH in this workspace.
- Keep route handlers thin; business logic belongs in `services/`.
- External tools such as `yt-dlp` and `ffmpeg` should be wrapped in adapters.
- Use environment variables for service URLs and media paths.
- Avoid hardcoding personal paths, IPs, or secrets.
- Use clear filenames and small functions.
- Prefer incremental changes and minimal diffs.
- Use module-level loggers (`logging.getLogger(__name__)`) and structured context in log messages (ids, operation, paths where relevant).
- Do not log secrets, credentials, or full sensitive payloads.
- Prefer `logger.exception(...)` when handling unexpected exceptions to preserve stack traces.
- Keep logs actionable and concise; avoid noisy per-line debug logging in normal flows.
- Runtime-configurable settings must be persisted in the database as well as applied in-memory. When adding a new configurable setting, update the runtime settings table/model, startup load path, and save path together so reloads keep the latest UI changes.

## Required behavior for agents
Before making changes, read:
- `README.md`
- `ARCHITECTURE.md`
- relevant docs in `/docs`

For each non-trivial change:
1. briefly summarize the plan
2. list files to create or modify
3. state assumptions

When finished:
- update docs if needed
- include commands to run and test
- commit the changes with git if the change is major
  - check whether there are uncommitted changes or secrets

## Frontend internationalization (i18n)
When making UI changes or adding new frontend features:
- All user-facing text must use the translation system via `t("key")` helper
- Template strings: use `{{ t("key") }}` in Jinja templates
- JavaScript strings: use `window.KaraokeI18n.t("key", {param: value})` in static JS files
- Never hardcode UI text; add it to `locales/en.json` first, then translate to `locales/zh-CN.json`
- Preserve placeholder syntax: `{key}`, `{count}`, etc. in translations; don't replace them
- Run `uv run pytest` before committing - tests verify catalog key parity across all locales
- See [docs/internationalization.md](docs/internationalization.md) for details on adding a new language
- The i18n helper is auto-exposed in `templates/base.html` via `window.KaraokeI18n` and via Jinja template context

## Testing requirements
- Use `uv run pytest` for the full local suite. The shared pytest setup shortens the WebSocket heartbeat during tests, so do not add `WS_HEARTBEAT_INTERVAL=30` or other production heartbeat overrides when running tests.
- When investigating slow tests, use `uv run pytest --durations=20 --durations-min=0.05` and check for heartbeat/timeouts before assuming the whole suite is slow.
- Route tests are split under `tests/routes/` and service tests are split under `tests/services/`.
- `tests/test_routes.py` and `tests/test_services.py` are thin pytest shims only; add new focused tests in the matching submodule instead of extending the shims.
- Shared route fixtures and helpers live in `tests/routes/common.py`; shared service fixtures live in `tests/services/common.py`; cross-cutting pytest fixtures stay in `tests/conftest.py`.
- Add or update API tests for new endpoints
- Add service-level tests where practical
- Prefer mock/stub subprocess calls in tests
- Do not rely on Demucs being available in the dev workspace
- For logging changes, add focused tests that validate configuration behavior (handlers, levels, rotation setup) without brittle string matching.

## Documentation
- If you need to create summary documents or instruction, please place it in the `/docs` and not in the root folder
- Use the project  for task tracking instead of `TASKS.md`.
