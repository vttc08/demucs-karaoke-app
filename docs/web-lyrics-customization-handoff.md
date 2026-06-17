# Web Lyrics Customization Handoff

This document captures extension points for future lyric-style customization on `/stage`.

## Current baseline
- Overlay is rendered in `templates/stage.html` as `#stage-lyrics-overlay`.
- Stage lyric cue rendering and browser-local appearance settings live in `static/stage-lyrics.js`.
- Timed cues are loaded from `GET /api/queue/{item_id}/lyrics-cues`.
- Active line uses `.stage-lyric-line--current`, nearby lines use `.stage-lyric-line`.
- Aligned JSON cues may include `words: [{word, start, end}]`; the stage progressively highlights
  completed/current words while leaving upcoming words in the configured base color.
- Timeline authority is `video.currentTime`.
- Appearance settings are stored per browser in `localStorage` under
  `karaoke_stage_lyrics_settings_v1` and can be downloaded/uploaded as JSON.
- The default font stack is CJK-safe: self-hosted ZCOOL KuaiLe with Noto Sans SC and local system
  CJK fallbacks.

## Recommended future customization surfaces

1. **Typography + color tokens**
- Typography, color, size, and outline are now browser-configurable CSS tokens.
- Keep backend lyrics payloads independent of presentation settings.

2. **Line window behavior**
- Previous and upcoming line counts are browser-configurable.
- Single-line focus is available by setting both values to `0`.

3. **Animation behaviors**
- Supported settings:
  - `slide` for word-aligned JSON tracks
  - `fade`
  - `none`
- Reduced-motion mode disables motion while preserving lyric state.

4. **Positioning and safe areas**
- Default position is centered/slightly below midpoint to read like karaoke instead of captions.
- If adding position controls later, keep overlays clear of stage controls/QR overlays.

5. **Data enrichment**
- Preserve the optional nested word timing schema while keeping line-level `time/text` compatibility.

## Compatibility guidance
- Keep endpoint output backward-compatible:
  - required: `time`, `text`
  - optional: future style/animation hints
- Avoid breaking existing `.lrc` parser behavior (`[mm:ss]`, `[mm:ss.xx]`, multi-timestamp, `offset`).
