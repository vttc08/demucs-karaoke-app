# ARCHITECTURE.md

## Current architecture
This project currently uses two services:

1. Main app
- serves mobile queue page, stage page, and settings page
- serves media library management page (`/media`) with database-backed listing and CRUD actions
- serves upload page (`/upload`) for saving uploaded MP3/MP4 files into the media library and optionally queueing the new item
- reconciles media library metadata with filesystem on startup and via manual scan API trigger
- serves a static access-restricted gate page (`/access-restricted`) for reverse-proxy network checks
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
- optionally runs WhisperX forced alignment when lyrics are supplied
- returns a ZIP payload containing both `no_vocals` and `vocals` stems, plus `aligned_lyrics.json` when alignment was performed

## Test layout

- Route/API tests live under `tests/routes/` and service tests live under `tests/services/`.
- `tests/test_routes.py` and `tests/test_services.py` remain thin pytest shims that import the focused modules.
- Shared route fixtures and helpers live in `tests/routes/common.py`; shared service fixtures live in `tests/services/common.py`; cross-cutting pytest fixtures stay in `tests/conftest.py`.
- Run tests with `uv run pytest`; the workspace does not rely on bare `python` being on PATH.

## Reverse proxy subpath support

- The main app can be served at `/` or under a preserved proxy prefix such as `/karaoke`.
- `KARAOKE_BASE_PATH` controls the public prefix. Empty or `/` keeps root-mode behavior.
- When set to `/karaoke`, pages, APIs, WebSockets, static assets, and media/cache file routes are
  registered under `/karaoke/...`.
- The reverse proxy must preserve the prefix when forwarding to FastAPI.
- Database values for media/cache references remain canonical (`/media/...`, `/cache/...`). Templates
  and frontend helpers add the public prefix only when rendering browser-facing URLs.

## Frontend internationalization

- UI internationalization is intentionally lightweight and framework-free:
  - locale catalogs live in `locales/en.json` and `locales/zh-CN.json`
  - `services/i18n_service.py` resolves the active locale and provides English fallback
  - Jinja templates use the global `t("key")` helper for server-rendered UI copy
  - `templates/base.html` exposes the same catalogs to JavaScript through `window.KaraokeI18n`
- The active locale is resolved from the `karaoke_locale` cookie, then `Accept-Language`, then English.
- `POST /language` validates the requested language, stores the cookie, and redirects only to app-local
  paths so language switching works under `KARAOKE_BASE_PATH` without open redirects.
- Only frontend UI elements are translated. Backend content such as song titles, artist names, lyrics,
  filenames, provider output, and API payload data stays in its original language.

## Media library permissions

- The media library page is browse-first for guests.
- Guests can view entries and add them to the queue.
- Edit, refresh-sidecar, scan, upload-shortcut, and delete controls are admin-only.
- The media edit and scan API routes enforce admin sessions server-side so the page stays queue-only even if a guest tampers with the DOM.
- The edit modal links to the admin-only `/media-editor/{item_id}` page. It renders an immediate
  shell with the native browser media player, then hydrates duration and ffprobe I-frame timestamps
  asynchronously from `/api/media/{item_id}/trim-info` without introducing a frontend framework.
- `MediaTrimService` owns trim validation, conflict checks, sidecar shifting, and atomic file
  replacement. `FFmpegAdapter` owns ffprobe metadata/keyframe reads and `ffmpeg -c copy` remuxing.
- Video ranges snap outward to surrounding keyframes; audio-only ranges retain exact requested
  timestamps. The resolved range is also applied to vocals and timed lyrics.
- Staged files and temporary rollback files are created beside each source so `os.replace` remains
  same-filesystem and atomic. Rollback files are removed after success and are not permanent backups.

## Real-time queue update architecture

The queue page uses a hybrid update model:

- Primary: WebSocket push at `/api/queue/ws`
- Fallback: periodic polling from `static/queue.js` when WebSocket reconnect attempts are exhausted
- Presence roster fallback: `GET /api/queue/presence` on the same polling interval when WebSocket is unavailable

The stage page uses a websocket-first model:

- Primary: WebSocket push and control commands at `/api/queue/ws`
- Reconnect behavior: automatic reconnect loop from page script
- No periodic polling loop on `/stage`
- Stage now switches media sources in-place (no full-page reload) so fullscreen remains active across
  skip/end/current-item transitions.
- Stage keeps an always-on lobby loop media source when no queue item is playing and switches back to
  lobby automatically after the queue drains.

### WebSocket server flow

- `routes/queue.py` hosts the WebSocket endpoint and heartbeat loop (server `ping`, client `pong`).
- `services/websocket_manager.py` tracks active connections and broadcasts queue events.
- WebSocket clients now register a page role after connect (`queue`, `stage`, `lyrics_viewer`) so the
  server can target event delivery instead of broadcasting every event to every page.
- `services/websocket_manager.py` also tracks in-memory queue presence keyed by guest id and deduplicates multiple browser tabs for the same guest.
- `services/websocket_manager.py` also tracks connected stage displays by browser-local `stage_id`;
  multiple tabs for the same display id are grouped into one target with a connection count.
- `routes/queue.py` also accepts client `stage_command` messages (`play`, `pause`, `skip`).
- `routes/queue.py` also accepts queue-page presence messages:
  - `presence_hello` for initial roster registration
  - `presence_update` when a guest renames themselves
- `routes/queue.py` also accepts `seek` stage commands for synchronized timeline jumps across stage clients.
- `routes/queue.py` also accepts `resync` stage commands so remote controls can force hard local
  video/vocals recovery on stage clients. Resync broadcasts include a monotonic `sync_version`, and
  stage-originated resync may include `seek_time`/`is_paused` for a concrete recovery timeline.
- `routes/queue.py` also accepts `stage_time_update` messages from the stage page and stores the
  authoritative playback clock in shared websocket state.
- `routes/queue.py` also accepts stage mix commands (`set_vocals_enabled`, `set_vocals_volume`)
  for runtime-only vocal assist control.
- `routes/queue.py` also accepts `set_lyrics_enabled` for runtime-only lyrics overlay visibility.
- `routes/queue.py` also accepts stage display discovery and targeted lyrics settings messages:
  - `stage_presence_hello` from `/stage` registers browser-local `stage_id` and display name.
  - `stage_presence_request` from `/queue` returns connected stage displays for manual targeting.
  - `apply_lyrics_settings` is admin-only and sends one targeted command containing target stage id,
    optional shared preset id, lyrics visibility, text size, and max width.
  - `lyrics_settings_ack` lets the target stage confirm success or failure back to queue clients.
- Stage control commands are authorized server-side. Admin sessions may control any current item.
  Guest websocket/REST skip commands are accepted only when the currently playing item is owned by
  that guest's persistent `karaoke_guest_id`.
- Admin queue-as ownership transfer is presence-bound: selecting a live guest stores that guest's
  `guest_id` in `queue_items.user_id`, while manually typed queue-as names only change the visible
  requester label and do not transfer control.
- `stage_time_update` messages are accepted only from admin sessions because they represent the
  authoritative stage playback clock.
- Periodic playback clock updates are rebroadcast only to `stage` and `lyrics_viewer` clients.
- For `play`/`pause`, the server broadcasts:
  - `stage_control_command`
  - `stage_state_update`
- For `seek`, the server validates `seek_time` and broadcasts:
  - `stage_control_command` with `seek_time` (+ optional `is_paused`)
  - `stage_state_update` when paused state is included, now carrying `current_time`
- For `skip`, server-side queue skip logic runs and then broadcasts:
  - `stage_control_command`
  - `current_item_changed`
- `services/websocket_manager.py` stores in-memory stage state:
  - `is_paused`
  - `current_time`
  - `vocals_enabled`
  - `vocals_volume` (`0.0` to `1.0`)
  - `lyrics_enabled`
  and includes it in low-frequency `stage_state_update` broadcasts.
- Playback clock fan-out uses a dedicated `stage_time_update` event instead of reusing
  `stage_state_update` for every timer tick.
- Queue REST routes broadcast immediate state changes:
  - `queue_item_added`
  - `queue_item_updated` for admin reorders and status refreshes
  - `queue_item_removed`
  - `queue_cleared`
  - `current_item_changed`
- Live processing progress broadcasts:
  - `queue_item_progress` for lightweight live progress ticks on queue clients only
- Queue presence broadcasts are queue-page only:
  - `presence_snapshot`
  - `user_joined`
  - `user_updated`
  - `user_left`
- Background processing status changes are broadcast from `QueueService.update_status_async`:
  - `queue_item_updated`
  - `queue_item_failed`
- When a background status update marks an item `READY` and no queue item is currently `PLAYING`,
  `QueueService` auto-promotes the next ready item to `PLAYING` and broadcasts `current_item_changed`
  immediately.

### WebSocket client flow

- `static/queue.js` maintains a single `QueueWebSocket` connection.
- Queue clients subscribe as `queue`, so they receive queue/presence events and low-frequency stage
  control state, but not the periodic playback clock.
- On disconnect, it retries with exponential backoff (1s, 2s, 4s, 8s up to max attempts).
- If retries fail, it falls back to polling every 15s.
- Queue clients send guest presence metadata (`guest_id`, display name, tab id) after connect and when the local singer name changes.
- Presence join toasts are only shown for incremental `user_joined` events, not for the initial roster snapshot.
- Queue actions no longer rely on full-page reloads; UI updates are driven by pushed events.
- Queue page now includes stage remote controls that send websocket `stage_command` messages.
- Queue clients disable remote stage controls for guests unless the active queue item exposes
  `can_control_stage` for that viewer.
- Queue page includes stage vocal-assist controls (toggle + volume slider) that send websocket
  mix commands and mirror live `stage_state_update` broadcasts.
- Queue page includes a lyrics settings control. Admins can target one connected stage display,
  select a shared lyric preset, adjust text size/max width, and apply that display-local style over
  websocket; guests with stage-control permission still get the basic lyrics visibility toggle.
- Queue page also renders a live "Here Now" roster from presence events and shows requester labels on queue items.
- Queue page updates live download/processing progress from `queue_item_progress` without waiting for a full queue refresh.
- The queue lyrics viewer subscribes as `lyrics_viewer` and follows the authoritative playback clock
  from websocket `stage_time_update` events.
- Stage page subscribes as `stage`, consumes websocket queue events and stage-control events, and
  publishes authoritative playback clock updates at a throttled cadence for lyrics sync.
- Stage page stores its display id/name and lyric appearance in `localStorage`. When it receives a
  targeted lyrics settings command, it fetches the named shared preset itself, merges the quick
  overrides, persists the result locally, and acknowledges the queue client.
- Stage page also exposes desktop keyboard shortcuts for seek/resync/vocals/lyrics/QR and a desktop-only help popover. The help panel stays open until explicitly dismissed, and keyboard or remote-control actions do not auto-reveal the stage chrome.
- Stage page refreshes queue/current state over API and applies source changes to existing media
  elements instead of reloading the page.

## Stage lobby media fallback

- Runtime settings include `stage_lobby_media_path` for optional empty-queue loop media.
- Runtime settings include `stage_qr_url` for the stage QR overlay link.
- Stage QR size and placement are stored in browser local storage on `/stage`, so each device can keep its own layout.
- The stage route resolves lobby playback in this order:
  1. Configured media URL exists (`/media/...` or `/cache/...`) -> use it.
  2. Otherwise generate one deterministic fallback loop media file in `media_path`
     (`stage-lobby-fallback.mp4`) via ffmpeg and use it.
- This keeps stage output continuously playable while queue items are unavailable.

## Sidecar multi-track playback

- The durable media row (`media_items`) carries:
  - `media_path` (primary stage video/audio)
  - `vocals_path` (optional sidecar vocals-only guide track, canonical `*.vocals.<ext>`)
- Queue/API mapping normalizes persisted filesystem paths into app-served URLs (`/media/...` or `/cache/...`)
  and attempts sidecar recovery when vocals metadata is misassigned (e.g. lyrics accidentally saved into
  `vocals_path`).
- yt-dlp downloads and Demucs scratch outputs are staged under `cache/` first; they are not durable
  library assets and should never be imported as standalone media rows.
- Stage playback is sidecar-first (not browser multi-audio-track MP4 selection):
  - `<video>` plays `media_path`
  - optional hidden `<audio>` plays `vocals_path`
  - vocals are routed through Web Audio `GainNode` for real-time mix control.
- Because the base media and vocals sidecar use separate browser media clocks, browser behavior can
  differ. Firefox has tested stable; Chromium-family browsers can drift inconsistently. Manual
  Resync therefore performs a hard relock with retry and page-reload fallback instead of only nudging
  the vocals element while playback continues.
- Karaoke processing persists stems with explicit mapping:
  - yt-dlp source video/audio downloads stay in `cache/`
  - `no_vocals` is muxed into the final canonical `media_path` video as `/media/<stem>.mp4`
  - `vocals` is persisted separately to canonical `vocals_path` as `/media/<stem>.vocals.<ext>`
- Karaoke input prep chooses the Demucs source after a local file exists:
  - audio-only inputs always go directly to Demucs
  - small video/media files can go directly to Demucs based on the persisted direct-media cutoff
  - large YouTube or local video files fall back to the existing audio-only prep path
- Local media karaoke finalization stages both outputs before updating the media row:
  - video inputs remux the `no_vocals` stem with the original video stream
  - audio-only inputs persist `no_vocals` directly as the new primary audio
  - `media_path` and `vocals_path` are committed together only after both durable outputs exist
  - cancellation removes scratch/temporary outputs but preserves the original uploaded or library file
- Media-library scan treats transient files such as `*.audio.*` as scratch artifacts, skips duplicate
  legacy `*.karaoke.*` files when a canonical `/media/<stem>.<ext>` sibling exists, and reattaches
  canonical `*.vocals.*` sidecars when possible.
- Vocal mix state and lyrics visibility persist across queue-item transitions until the user changes them again; only playback position and paused state reset on item changes.

## Local thumbnails and audio cover art

- Local media thumbnails are cached under `cache/media-thumbnails/` and reused by queue, media-library, and stage views.
- Video thumbnails come from a captured frame.
- Audio files (`.mp3`, `.wav`, `.m4a`, `.flac`, `.aac`, `.ogg`, `.opus`) attempt to extract embedded cover art via ffmpeg.
- Uploads generate thumbnails immediately after save, while library scans refresh thumbnails for existing files under the media root.
- Stage keeps the existing `<video>` path for video items and lobby playback, but switches to an `<audio>` primary player for audio-only queue items.
- In audio-only stage mode, the queue item's `thumbnail` URL drives the fullscreen background/artwork treatment; if no cover is available, stage falls back to a branded placeholder background instead of a plain black screen.

## Stage lyrics overlay flow

- Stage uses a custom HTML/CSS/JS overlay (not native WebVTT rendering) on top of the
  `#stage-video-player`.
- The lyrics overlay only becomes visible when the stage player is in fullscreen mode so mobile
  controls stay unobstructed in the default windowed view.
- Lyrics cues are fetched from `GET /api/queue/{item_id}/lyrics-cues`.
- Backend cue source is media sidecar `lyrics_path` and supports:
  - `.lrc` sidecars parsed into timestamped cues
  - `.json` sidecars validated and normalized into line-level cue objects; aligned
    Demucs/WhisperX JSON retains optional nested word start/end timing
  - `.txt` sidecars parsed into unsynced text lines for queue-side viewing
- Karaoke finalization now promotes the returned aligned `.json` sidecar to the active
  `lyrics_path` when Demucs/WhisperX provides one, so stage and queue lyrics views consume the
  rebuilt line-level alignment instead of the original downloaded `.lrc`.
- Overlay highlight logic is driven by the video timeline:
  - ordinary cues highlight the current line without per-word animation
  - aligned JSON progressively highlights completed/current words and can apply the stage word-slide or crop effect
  - nearby lines are shown above/below the active line according to browser-local stage lyrics settings
- Stage lyric appearance is browser-local and stored in `localStorage` by `static/stage-lyrics.js`.
  The settings panel exposes CJK-safe font presets, size, colors, outline, line-window, animation,
  reset, and JSON import/export without changing backend API payloads.
- Stage lyric fonts are self-hosted under `static/fonts/` so fullscreen playback can render Chinese
  lyrics without depending on Google Fonts at runtime.

## Queue lyrics viewer flow

- Queue page links to dedicated lyrics viewer page: `GET /queue/lyrics`.
- Viewer resolves current playing item through `GET /api/queue/current`, then fetches
  `GET /api/queue/{item_id}/lyrics-cues`.
- Lyrics payload now includes:
  - `is_synced` (`true` for `.lrc`/`.json`, `false` for `.txt`)
  - `cues` (timed lines; empty for unsynced lyrics)
  - `lines` (display lines for synced or unsynced rendering)
- Synced mode auto-follows playback time and highlights active lines; manual scroll pauses
  follow mode until the user re-enables it from the viewer UI.
- Unsynced mode renders large freely scrollable text.
- The viewer can optionally request display-only Chinese normalization from
  `POST /api/lyrics/chinese-transform` so simplified Chinese and pinyin can be shown together
  without changing the stored lyrics payload.
- When no lyrics sidecar exists, viewer falls back to a lightweight empty state using
  current title/artist + external lyrics search link.

## Add-to-queue lyrics flow

- The queue modal now gates the Add to Queue action behind a lyrics resolution step when lyrics are enabled.
- Frontend flow:
  - prefill title/artist from the selected search result
  - resolve synced lyrics through `POST /api/lyrics/resolve`
  - let users replace provider lyrics with manual synced text or an uploaded LRC file
  - submit the resolved title/artist alongside the queue payload so media rows can store normalized metadata
  - local library search results bypass the modal and enqueue immediately as existing media rows
- Backend flow:
  - `routes/lyrics.py` orchestrates the lookup response for the UI
  - `QueueService.add_to_queue` stores inline lyrics as a cache sidecar when karaoke is enabled and lyrics text is provided
  - YouTube-backed media rows are refreshed with the submitted title/artist so resolved lyrics metadata persists in `media_items`
  - `KaraokeService` keeps karaoke output assembly independent from subtitle burn behavior
- Queue, upload, and media edit lyrics interactions share the same lightweight frontend manager/adapter modules:
  - `static/lyrics-manager.js` owns lyrics state, metadata, provider lookup, uploads, and submission payloads
  - `static/lyrics-ui.js` binds that state to page-specific DOM selectors without introducing a frontend framework
- Queue lyrics lookup can carry a per-item WhisperX language override. When present, the queue item stores it and karaoke processing uses that code instead of the global `/settings` detect/alignment defaults for that song only.

## Media upload flow

- The upload page posts multipart form data to `POST /api/media/upload`.
- Backend flow:
  - saves the uploaded file under the configured media root using the normalized title/artist stem
  - creates a durable `media_items` row with `media_path` pointing at the saved file
  - persists submitted `lyrics_text` as a reusable media-adjacent lyrics sidecar on the media row
  - optionally creates a queue row for the new media item when "Add to queue" is enabled
  - checks Demucs health before accepting AI karaoke processing
  - starts one queue preparation task for queued uploads, or one `media_karaoke` task for non-queued AI uploads
  - preserves the saved upload and returns a warning when Demucs becomes unavailable before task creation
  - broadcasts the new queue item so real-time clients stay in sync
- Successful uploads redirect the browser to the media management page.

## Admin authentication

- Admin accounts are stored in `admin_users` and are created or updated from the server with
  `uv run python scripts/admin_user.py create --username admin`.
- Passwords are stored as PBKDF2-SHA256 hashes with random per-password salts. Plaintext passwords
  are only accepted by the CLI prompt or login form and are never persisted.
- Successful admin login creates an `admin_sessions` row. The browser receives an HttpOnly,
  SameSite=Lax cookie containing only the random session token; the database stores a SHA-256 hash
  of that token.
- Logout deletes the persisted admin session and clears the cookie.
- Guest login remains a lightweight device/stage-name identifier for the current sprint. It is not
  an authorization boundary. First-time guests are prompted inline on the queue page, can dismiss the
  prompt to receive a generated guest name, and can edit that name from the queue greeting.
- Queue presence uses a separate browser guest id cookie plus a per-tab id so active queue viewers can
  be tracked in real time without treating multiple tabs as separate people. Queue ownership persists
  `user_id`, `session_id`, and a display-name snapshot on each queue row.
- Guest queue removal authorization uses the persistent `karaoke_guest_id` cookie matched against
  `queue_items.user_id`, so guests can remove their own non-playing items across reloads and tabs on
  the same browser/device.
- The current branch establishes admin credential/session storage. The settings page and settings
  management APIs require an active admin session. The stage page and stage navbar entry are also
  admin-only. Queue clear actions and media delete actions are restricted to admins in both the UI and
  API, while queue item removal is available to admins for any non-playing item and to guests only for
  their own non-playing items. Stage controls are available to admins for any current song and to
  guests only for the current song they queued. Other media/queue authorization gates can still be refined in a later pass.
- Queue add supports an optional admin-only `queue_as_name` field so shared admin tablets can submit
  songs on behalf of someone else without changing device ownership cookies. The frontend "queue as"
  toggle is stored locally per device (not persisted in backend runtime settings).

## Lyrics inference and provider flow

- Lyrics logic is modularized into:
  - `services/lyrics_service.py`: shared contracts (`InferredSong`, `LyricsPayload`, provider/inferrer protocols), orchestration (`LyricsService.resolve_lyrics`), and cue parsing utilities
  - `services/lyrics_inference.py`: metadata inference (`YouTubeTitleInferrer`) to normalize noisy YouTube titles into title/artist pairs
- `services/lyrics_providers.py`: provider implementations (`MusixmatchLyricsProvider`, `NeteaseLyricsProvider`, `LRCLibLyricsProvider`)
- Provider order is Musixmatch first (when `MUSIXMATCH_TOKEN` is configured), then NetEase, then LRCLib fallback.
- Resolution behavior is Musixmatch-first, then concurrent fallback search across the remaining providers with score-based selection of the best payload.
- Synced lyrics are persisted as `.lrc` sidecars for stage overlay cue parsing.
- Unsynced lyrics can still be persisted as sidecars for future/manual overlay handling.

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
  - runtime queue state (`requested_karaoke`, `status`, `error`)
  - rows are removed when songs are skipped/completed (active queue persists across crashes)

## Durable processing tasks

- `processing_tasks` is the durable processing/restart model:
  - `task_type` (`queue_prepare`, `media_karaoke`)
  - `source_kind` (`youtube`, `library_media`, `uploaded_media`)
  - target linkage to queue and/or media rows
  - coarse durable `status` (`pending`, `downloading`, `processing`, `done`, `failed`)
  - coarse `stage` (`download`, `extract_audio`, `demucs`, `finalize`, etc.)
  - retry metadata (`attempt_count`)
  - terminal failure summaries (`last_error_summary`, `last_error_detail`)
- `queue_items.status` remains the playback-facing queue state for compatibility with stage/queue logic and is mirrored from queue-backed processing tasks.
- Existing media karaoke processing also uses `processing_tasks`, but it does not create queue rows unless the item is separately added to queue.

## Live task progress architecture

- Live task percentages and verbose logs are intentionally in-memory only:
  - `services/task_stream_service.py` retains the latest progress snapshot per active task
  - each task also keeps a rolling log/event buffer for SSE reconnect replay
- This allows:
  - compact progress on `/queue`
  - admin monitoring/log inspection on `/media`
  - reconnectable SSE streams during the current app process lifetime
- This state is not persisted across app restarts by design.

## Processing restart flow

- On app startup, interrupted tasks with durable status `pending`, `downloading`, or `processing` are reset to restartable `pending`.
- The startup flow then re-enqueues them through the task execution coordinator.
- Restart behavior is coarse:
  - yt-dlp downloads restart from the beginning
  - local ffmpeg extraction/remux restart from the beginning
  - Demucs work restarts from the beginning of that stage
- The app does not currently attempt byte-range or partial-percentage resume.

## Runtime outbound proxy flow

- Runtime settings expose `ytdlp_proxy_url` through:
  - `GET /api/settings/`
  - `PATCH /api/settings/`
- `services/runtime_settings_service.py` validates proxy values and allows:
  - Empty value (direct connection)
  - Schemes: `http`, `https`, `socks4`, `socks4a`, `socks5`, `socks5h`
- `adapters/ytdlp.py` injects `--proxy <url>` into yt-dlp commands for:
  - YouTube search
  - Audio download, which now stays on explicit audio-only selectors and never falls back to a video-only stream
  - Video-only download
  - Progressive video+audio download
- `services/lyrics_service.py` exposes shared HTTP client kwargs that add the same proxy for:
  - Musixmatch provider calls
  - NetEase provider calls
  - LRCLib provider calls
  - Last.fm metadata lookup

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
  - `whisperx_transcription_model`
  - `whisperx_align_language`
  - `whisperx_detect_language`
  - `whisperx_use_synced_lyrics`
  - `whisperx_preload_models`
  - WhisperX preload button calls the remote Demucs preload endpoint so missing models are downloaded on the remote host before alignment jobs run
  - `ytdlp_path`
  - `ytdlp_proxy_url`
  - `concurrent_ytdlp_search_enabled`
  - `lyrics_provider_netease_enabled`
  - `lyrics_provider_lrclib_enabled`
  - `ffmpeg_path`
  - `media_path`
  - `cache_path`
  - `stage_qr_url`
  - `stage_lobby_media_path`

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
