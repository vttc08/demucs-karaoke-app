# ARCHITECTURE.md

## Current architecture
This project currently uses two services:

1. Main app
- serves mobile queue page and TV playback page
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

### WebSocket server flow

- `routes/queue.py` hosts the WebSocket endpoint and heartbeat loop (server `ping`, client `pong`).
- `services/websocket_manager.py` tracks active connections and broadcasts queue events.
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

## Software Stack

**Backend**: FastAPI

**Frontend**: HTML Jinja Templates/Tailwind CSS

**Database**: SQLite

**Other Services**: yt-dlp, ffmpeg, [Demucs](https://github.com/facebookresearch/demucs)

## Design principles
- Keep the MVP CLI-friendly and easy to run locally
- Prefer local filesystem storage for media artifacts
- Prefer SQLite for queue and metadata during MVP
- Keep Demucs integration simple and replaceable
- Keep playback flow deterministic and testable
