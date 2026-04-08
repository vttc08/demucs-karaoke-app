# Stage sync analysis (video + vocals sidecar)

## Scope
This document reviews the current multi-track stage playback implementation and explains why desync can still happen, especially in the reported flow:

1. Fresh `/stage` load is in sync.
2. Pause playback.
3. Connection drops/reconnects.
4. Resume playback.
5. Vocals become desynced.
6. Resync button does not reliably recover.
7. Full `/stage` refresh reliably recovers.

## Current implementation summary
- Stage uses two media elements:
  - `#stage-video-player` for base playback.
  - `#stage-vocals-player` for guide vocals via Web Audio `GainNode`.
- Sync is maintained by:
  - event-based nudges (`play`, `seeking`, command handlers), and
  - interval correction every `250ms` (`syncVocalsToVideo`).
- Remote control uses websocket `stage_command` via `/api/queue/ws`.
  - Server (`routes/queue.py`) validates and broadcasts commands via `services/websocket_manager.py`.
  - Stage consumes `stage_control_command` and `stage_state_update`.
- Resync currently performs pause + seek + optional resume and floors time to the previous second.

## Why sync still fails

## 1. Dual media elements = dual clocks
`<video>` and `<audio>` are decoded and scheduled independently. Even when sourced from matching media, they can drift under buffering/jitter/scheduling pressure. Periodic correction reduces drift but does not remove its root.

## 2. Reconnect path restores pause state, not timeline authority
Current shared stage state is mainly `{ is_paused, vocals_enabled, vocals_volume }`. There is no authoritative timeline payload (e.g., `current_time`, `sync_version`, `issued_at`) in reconnect bootstrap. After disconnect/reconnect, clients can be "correctly paused/resumed" while still misaligned in timeline details.

## 3. Resync command does not carry a server-authoritative target timestamp
`resync` is broadcast as a command, and each stage computes its own local target from local `video.currentTime`. If local timing is already in a bad state, each client can resync to a slightly different or stale point. This weakens determinism after reconnect scenarios.

## 4. Seek completion is approximated with timeout fallback
The seek helper resolves on `seeked`/`error`, but also has a fixed timeout fallback (`350ms`). Under network/decoder pressure this can resolve before both elements are truly ready, so resume can happen from partially settled states.

## 5. Missing event-driven recovery on buffer/decoder transitions
There is no dedicated synchronization policy for `waiting`, `stalled`, and `playing` transitions across both elements. In real-world jitter, one element can stall/continue differently, and interval-based correction can lag behind these transitions.

## 6. Refresh works because it rebuilds a clean aligned graph
A full `/stage` reload reinitializes both elements from fresh load state and immediately applies startup sync logic. That hard reset clears accumulated async/order artifacts that in-session resync currently may not fully reset.

## Relevant Web API behavior
- `HTMLMediaElement.currentTime` seek is asynchronous and media state-dependent.
- `seeked` indicates seek operation completion but does not by itself guarantee stable decode/ready state for both media elements at the same instant.
- `waiting`/`stalled` indicate buffer starvation and should be treated as sync risk points.
- Web Audio contexts may be suspended/resumed by browser policy and lifecycle transitions; resume timing affects play order.

## Proposed fixes (prioritized)

## Priority A (recommended first): make sync deterministic on reconnect/resync
1. Introduce authoritative sync state on server:
   - `sync_version` (monotonic integer)
   - `sync_time` (seconds)
   - `is_paused`
   - `issued_at` (server timestamp)
2. Include that state in websocket `connected` bootstrap and dedicated `stage_sync_update` broadcasts.
3. Change `resync` protocol to carry explicit target timeline (`target_time`) from sender/server, not per-client local derivation.
4. On receiving sync update, stage should always run a single hard-lock routine:
   - pause both
   - seek both to `target_time`
   - wait for both `seeked` + minimum readiness condition (`readyState` threshold)
   - resume according to authoritative `is_paused`

## Priority B: improve runtime drift correction behavior
1. Keep interval correction, but add event-driven checkpoints:
   - `playing`, `waiting`, `stalled`, `seeking`, `seeked`, `ratechange`
2. On `waiting/stalled` of either element:
   - pause follower element
   - perform follower re-lock after `playing/canplay`.
3. Tighten "hard relock" threshold for severe drift (e.g., `>250ms`) using pause+seek, not just follower seek while running.

## Priority C: observability for intermittent failures
1. Add lightweight sync telemetry (debug mode):
   - drift samples, command id/version, seek start/end, readyState snapshots.
2. Correlate reconnect events with first post-reconnect drift sample.
3. Record whether resync completed with both elements in expected state.

## Priority D (fallback architecture)
If browser-side dual-element sync remains unstable on target devices/networks:
- use deterministic pre-muxed playback paths where possible (single media timeline for stage),
- keep sidecar vocals control only when environment quality is adequate.

## Suggested implementation sequence
1. Add server sync model (`sync_version`, `sync_time`, `is_paused`) and broadcast contract.
2. Update stage client to consume authoritative sync payload and use one hard-lock routine.
3. Add buffer event handling (`waiting/stalled/playing`) and re-lock behavior.
4. Add debug telemetry toggles.
5. Validate against the reported pause/disconnect/resume scenario before further tuning.

## Validation checklist for the reported issue
1. Start track and confirm initial sync.
2. Pause on stage.
3. Force websocket drop/reconnect window.
4. Resume from queue and from stage separately.
5. Trigger Resync from queue and stage.
6. Confirm no audible drift for at least 60 seconds after resume.
7. Repeat across Chrome + mobile browser target.
