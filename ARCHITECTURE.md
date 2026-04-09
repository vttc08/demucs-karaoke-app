# ARCHITECTURE.md

## Current architecture
This project currently uses two services:

1. Main app
- serves mobile queue page, stage page, and settings page
- serves media library management page (`/media`) with placeholder-first UI interactions
- serves stage-focused presentation page
- manages queue state
- searches YouTube
- downloads video/audio
- fetches lyrics
- calls Demucs service
- generates output karaoke video

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
- `routes/queue.py` also accepts `seek` stage commands for synchronized timeline jumps across stage clients.
- `routes/queue.py` also accepts `resync` stage commands so remote controls can force local
  video/vocals realignment on stage clients.
- `routes/queue.py` also accepts stage mix commands (`set_vocals_enabled`, `set_vocals_volume`)
  for runtime-only vocal assist control.
- `routes/queue.py` also accepts `set_lyrics_enabled` for runtime-only lyrics overlay visibility.
- For `play`/`pause`, the server broadcasts:
  - `stage_control_command`
  - `stage_state_update`
- For `seek`, the server validates `seek_time` and broadcasts:
  - `stage_control_command` with `seek_time` (+ optional `is_paused`)
  - `stage_state_update` when paused state is included
- For `skip`, server-side queue skip logic runs and then broadcasts:
  - `stage_control_command`
  - `current_item_changed`
- `services/websocket_manager.py` stores in-memory stage state:
  - `is_paused`
  - `vocals_enabled`
  - `vocals_volume` (`0.0` to `1.0`)
  - `lyrics_enabled`
  and includes it in `stage_state_update` broadcasts.
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
- Queue page includes stage vocal-assist controls (toggle + volume slider) that send websocket
  mix commands and mirror live `stage_state_update` broadcasts.
- Queue page includes a lyrics overlay toggle that mirrors the stage lyrics visibility state.
- Stage page consumes websocket queue events and stage-control events to stay in sync without polling.

## Sidecar multi-track playback

- The durable media row (`media_items`) carries:
  - `media_path` (primary stage video/audio)
  - `vocals_path` (optional sidecar vocals file)
- Queue/API mapping normalizes persisted filesystem paths into app-served URLs (`/media/...` or `/cache/...`)
  and attempts sidecar recovery when vocals metadata is misassigned (e.g. lyrics accidentally saved into
  `vocals_path`).
- Stage playback is sidecar-first (not browser multi-audio-track MP4 selection):
  - `<video>` plays `media_path`
  - optional hidden `<audio>` plays `vocals_path`
  - vocals are routed through Web Audio `GainNode` for real-time mix control.
- Vocal mix state is runtime-only and resets when the current queue item changes.

## Stage lyrics overlay flow

- Stage uses a custom HTML/CSS/JS overlay (not native WebVTT rendering) on top of the
  `#stage-video-player`.
- Lyrics cues are fetched from `GET /api/queue/{item_id}/lyrics-cues`.
- Backend cue source is media sidecar `lyrics_path` and supports:
  - `.lrc` sidecars parsed into timestamped cues
  - `.json` sidecars validated and normalized into cue objects
- Overlay highlight logic is driven by the video timeline:
  - current line highlighted in red
  - nearby lines shown in white
- This custom pipeline keeps room for future per-user appearance/animation customization.

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
  - indexed `youtube_id` lookup for fast reuse checks
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
- In `services/youtube_service.py`, each `GET /api/search` request now runs:
  - local SQLite FTS search (`media_items.title`, `media_items.artist`)
  - YouTube search flow
  concurrently, then merges outputs.
- Merge behavior is:
  - local matches first (preferred),
  - YouTube matches next,
  - duplicate YouTube entries hidden when they match local items.
- Local queueing uses `media_item_id` for direct enqueue of existing library entries.
- YouTube search behavior remains:
  - Query looks like YouTube URL or 11-char video id: single metadata fetch (`yt-dlp --dump-single-json`) and return one addable result
  - Disabled: single yt-dlp search for original query
  - Enabled + query contains `karaoke` (case-insensitive substring): single search
  - Enabled + query without `karaoke`: two concurrent searches (`query` and `query + " karaoke"`)
- Results are merged as interleaved/staggered entries (normal, karaoke, normal, ...),
  de-duplicated by `video_id`, then capped to requested `max_results`.
- Search results are annotated with a `downloaded` flag when the `video_id` already exists in
  `media_items` with a usable local media file.

## Existing media reuse

- Queue processing checks whether the queue item already points at a usable local media file.
- If usable media already exists, non-karaoke items skip yt-dlp downloads entirely.
- Karaoke items reuse existing media as the video source and only fall back to yt-dlp when no local
  media file is available.

## Design principles
- Keep the MVP CLI-friendly and easy to run locally
- Prefer local filesystem storage for media artifacts
- Prefer SQLite for queue and metadata during MVP
- Keep Demucs integration simple and replaceable
- Keep playback flow deterministic and testable
