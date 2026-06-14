# Testing Layout

Use `uv run` for all Python commands in this workspace. Bare `python` is not guaranteed to be on PATH.

## Shared Fixtures

- `tests/conftest.py` holds cross-cutting pytest fixtures such as the fast WebSocket heartbeat.
- `tests/routes/common.py` holds shared route-test setup: the FastAPI test client, DB override, and admin/WebSocket helpers.
- `tests/services/common.py` holds shared service-test setup: the test database fixture and common service imports.

## Route Tests

Route/API coverage is split into focused modules under `tests/routes/`:

- `search_queue.py`
- `pages.py`
- `upload_media.py`
- `settings_api.py`
- `queue_state.py`
- `lyrics_files.py`
- `websocket.py`

`tests/test_routes.py` remains a thin import shim so pytest still discovers the route suite through the legacy entrypoint.

## Service Tests

Service coverage is split into focused modules under `tests/services/`:

- `queue_service.py`
- `auth_service.py`
- `media_library_sync.py`
- `media_library_maintenance.py`
- `media_library_misc.py`
- `processing_task.py`
- `youtube_service.py`
- `lyrics_service.py`
- `runtime_settings.py`
- `stage_lobby.py`

`tests/test_services.py` remains a thin import shim so pytest still discovers the service suite through the legacy entrypoint.

## Adding New Tests

- Put route/API tests in the matching module under `tests/routes/`.
- Put service tests in the matching module under `tests/services/`.
- Keep shared setup in the corresponding `common.py` file or `tests/conftest.py`.
- Add new focused modules when a feature area grows instead of extending the shims.
- Run the relevant suite with `uv run pytest` or the legacy shim entrypoint when you need the full collected set.
