# ARCHITECTURE.md

## Current architecture
This project currently uses two services:

1. Main app
- serves mobile queue page and TV playback page
- serves stage-focused presentation page
- manages queue state
- searches YouTube
- downloads video/audio
- fetches lyrics
- calls Demucs service
- generates output karaoke video

## Playback surfaces

- `/playback`: legacy TV playback page with fuller playback context.
- `/stage`: presentation-first stage output page for fullscreen display, minimal controls,
  and compact "up next" context.
- `/playback` still uses polling-based queue/current synchronization.
- `/stage` now uses websocket-first synchronization and control commands via `/api/queue/ws`.

2. Demucs service
- receives audio processing request
- runs demucs two-stem vocals separation
- returns path or metadata for generated `no_vocals.wav`

## Real-time queue update architecture

The queue page uses a hybrid update model:

- Primary: WebSocket push at `/api/queue/ws`
- Fallback: periodic polling from `static/queue.js` when WebSocket reconnect attempts are exhausted

The stage page uses a websocket-first model:

- Primary: WebSocket push and control commands at `/api/queue/ws`
- Reconnect behavior: automatic reconnect loop from page script
- No periodic polling loop on `/stage`

### WebSocket server flow

- `routes/queue.py` hosts the WebSocket endpoint and heartbeat loop (server `ping`, client `pong`).
- `services/websocket_manager.py` tracks active connections and broadcasts queue events.
- `routes/queue.py` also accepts client `stage_command` messages (`play`, `pause`, `skip`).
- For `play`/`pause`, the server broadcasts:
  - `stage_control_command`
  - `stage_state_update`
- For `skip`, server-side queue skip logic runs and then broadcasts:
  - `stage_control_command`
  - `current_item_changed`
- Queue REST routes broadcast immediate state changes:
  - `queue_item_added`
  - `queue_item_removed`
  - `queue_cleared`
  - `current_item_changed`
- Background processing status changes are broadcast from `QueueService.update_status_async`:
  - `queue_item_updated`
  - `queue_item_failed`

### WebSocket client flow

- `static/queue.js` maintains a single `QueueWebSocket` connection.
- On disconnect, it retries with exponential backoff (1s, 2s, 4s, 8s up to max attempts).
- If retries fail, it falls back to polling every 15s.
- Queue actions no longer rely on full-page reloads; UI updates are driven by pushed events.
- Queue page now includes stage remote controls that send websocket `stage_command` messages.
- Stage page consumes websocket queue events and stage-control events to stay in sync without polling.

## Software Stack

**Backend**: FastAPI

**Frontend**: HTML Jinja Templates/Tailwind CSS

**Database**: SQLite

**Other Services**: yt-dlp, ffmpeg, [Demucs](https://github.com/facebookresearch/demucs)

## Queue + media data model

- `media_items` is the durable catalog record:
  - `youtube_id` (nullable, unique when present)
  - `title`, `artist`
  - filesystem-relative `media_path`
  - optional sidecars: `lyrics_path`, `vocals_path`
  - `missing` flag for future filesystem reconciliation
- `queue_items` is active queue state only:
  - `media_id` FK (`ON DELETE RESTRICT`)
  - sparse `position` ordering (`1000` step)
  - runtime queue state (`requested_karaoke`, `requested_burn_lyrics`, `status`, `error`)
  - rows are removed when songs are skipped/completed (active queue persists across crashes)

## Runtime yt-dlp proxy flow

- Runtime settings expose `ytdlp_proxy_url` through:
  - `GET /api/settings/runtime`
  - `PATCH /api/settings/runtime`
- `services/runtime_settings_service.py` validates proxy values and allows:
  - Empty value (direct connection)
  - Schemes: `http`, `https`, `socks4`, `socks4a`, `socks5`, `socks5h`
- `adapters/ytdlp.py` injects `--proxy <url>` into yt-dlp commands for:
  - YouTube search
  - Audio download
  - Video-only download
  - Progressive video+audio download

This is applied at command build time, so new operations use updated proxy settings immediately without app restart.

## Runtime settings persistence

- Runtime settings editable from the web UI are stored in the `runtime_settings` table as key/value rows.
- The application loads those persisted values during startup after database initialization.
- Explicit `.env` / environment values remain authoritative and are not overwritten by database values.
- The settings update route writes validated UI changes back to the database and the in-memory `settings` object in the same request.
- The persisted settings currently include:
  - `demucs_api_url`
  - `demucs_model`
  - `demucs_device`
  - `demucs_output_format`
  - `demucs_mp3_bitrate`
  - `ffmpeg_preset`
  - `ffmpeg_crf`
  - `ytdlp_path`
  - `ytdlp_proxy_url`
  - `concurrent_ytdlp_search_enabled`
  - `ffmpeg_path`
  - `media_path`
  - `cache_path`
  - `stage_qr_url`

## Concurrent search mode

- Runtime settings expose `concurrent_ytdlp_search_enabled` through:
  - `GET /api/settings/`
  - `PATCH /api/settings/`
- In `services/youtube_service.py`, search behavior is:
  - Query looks like YouTube URL or 11-char video id: single metadata fetch (`yt-dlp --dump-single-json`) and return one addable result
  - Disabled: single yt-dlp search for original query
  - Enabled + query contains `karaoke` (case-insensitive substring): single search
  - Enabled + query without `karaoke`: two concurrent searches (`query` and `query + " karaoke"`)
- Results are merged as interleaved/staggered entries (normal, karaoke, normal, ...),
  de-duplicated by `video_id`, then capped to requested `max_results`.

## Design principles
- Keep the MVP CLI-friendly and easy to run locally
- Prefer local filesystem storage for media artifacts
- Prefer SQLite for queue and metadata during MVP
- Keep Demucs integration simple and replaceable
- Keep playback flow deterministic and testable
