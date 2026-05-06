# Stage sync analysis (video + vocals sidecar)

## Scope
This document reviews the current multi-track stage playback behavior where the base track and
vocals sidecar can become audibly out of sync.

The original investigation focused on a pause + websocket disconnect/reconnect flow. New testing
shows a more useful browser split:

1. Firefox desktop/mobile can keep the two tracks aligned reliably.
2. Chromium-family browsers such as Chrome and Brave can drift inconsistently.
3. The exact trigger is not reproducible enough to treat reconnect as the root cause.
4. A full `/stage` refresh reliably recovers because it rebuilds both media elements.

The practical requirement is that the manual Resync button must recover playback regardless of
which browser event caused the drift.

## Current implementation summary
- Stage uses two media elements:
  - `#stage-video-player` for base playback.
  - `#stage-vocals-player` for guide vocals routed through Web Audio `GainNode`.
- Sync is maintained by:
  - event-based nudges (`play`, `seeking`, command handlers), and
  - interval correction every `250ms` (`syncVocalsToVideo`).
- Remote control uses websocket `stage_command` via `/api/queue/ws`.
  - Server (`routes/queue.py`) validates and broadcasts commands via `services/websocket_manager.py`.
  - Stage consumes `stage_control_command` and `stage_state_update`.
- Resync now performs a hard local recovery:
  - pause both media clocks,
  - reload both media sources with cache-busting to reset decoder/media-pipeline state,
  - seek both to the same precise timestamp,
  - wait for seek/readiness,
  - resume the video and vocals from the same timeline,
  - retry once if the explicit recovery operation fails,
  - fall back to a full stage reload only if the manual recovery attempt cannot complete.
- For multi-track items, stage also runs one automatic hard resync at the beginning of playback so
  each item starts from the same reset path as the manual button.

## Why sync can still fail

## 1. Dual media elements = dual clocks
`<video>` and `<audio>` are decoded and scheduled independently. Even when sourced from matching
media, they can drift under buffering, decoder, or scheduling pressure. Firefox appears to handle
this project workload well; Chromium does not always keep the two clocks aligned.

## 2. Chromium behavior is the primary observed risk
The issue is browser-family-specific in current testing. That makes reconnect a possible stressor,
not the proven cause. Reconnect can still expose stale pause/play state, but the recovery logic must
handle arbitrary Chromium media-clock drift.

## 3. Soft correction is not enough for severe drift
Setting `vocalsAudio.currentTime = video.currentTime` while playback is running can be too weak once
Chromium has entered a bad decode/scheduling state. A severe drift needs a paused hard relock, not a
running nudge.

## 4. Seek completion is asynchronous
`currentTime` assignment only starts a seek. Recovery should wait for seek/readiness events and use
long enough fallbacks for busy devices. A short timeout can resume before both elements have settled.

## 5. Refresh works because it rebuilds the media graph
A full `/stage` reload reinitializes both elements and the Web Audio graph. Manual Resync should
approximate that reset in-place by reloading the media sources before seeking, with page reload kept
as a last-resort fallback.

## Implemented recovery approach

## Priority A: hard manual recovery
1. Resync commands carry a monotonic `sync_version` for client de-duplication.
2. Stage-originated resync can include `seek_time` and `is_paused`.
3. Queue-originated resync remains compatible and tells the stage client to recover its local
   current timestamp.
4. Stage hard recovery serializes each sync operation so overlapping media events do not fight.
5. Multi-track item startup runs one local hard resync before normal steady-state sync takes over.

## Priority B: conservative drift handling
1. Mild drift is corrected with a follower seek.
2. Automatic hard relock on buffer/decoder events is intentionally disabled. A previous attempt to
   trigger hard relock from `waiting`, `stalled`, `playing`, `canplay`, `seeked`, `ratechange`, and
   severe drift made playback stutter and could override the Pause button.
3. Hard relock is now only user-initiated through Resync or through an explicit remote Resync command.

## Priority C: fallback behavior
1. If the explicit hard relock operation throws or cannot complete, both media sources reload with
   cache busting and retry once at the same timestamp.
2. If that retry fails, `/stage` reloads as the known-good recovery path.

## Validation checklist
1. Start track and confirm initial sync.
2. Trigger Resync from the stage page while playing.
3. Trigger Resync from the queue page while playing.
4. Pause, resume, and trigger Resync again.
5. Repeat in Chrome/Brave desktop and mobile.
6. Confirm Firefox remains stable.
7. Confirm no audible drift for at least 60 seconds after recovery.
