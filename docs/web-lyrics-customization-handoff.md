# Web Lyrics Customization Handoff

This document captures extension points for future lyric-style customization on `/stage`.

## Current baseline
- Overlay is rendered in `templates/stage.html` as `#stage-lyrics-overlay`.
- Timed cues are loaded from `GET /api/queue/{item_id}/lyrics-cues`.
- Active line uses `.stage-lyric-line--current` (red), nearby lines use `.stage-lyric-line` (white).
- Timeline authority is `video.currentTime`.

## Recommended future customization surfaces

1. **Typography + color tokens**
- Move hardcoded lyric colors/font sizes into runtime-configurable tokens.
- Keep defaults identical to current behavior for backwards compatibility.

2. **Line window behavior**
- Current window is fixed (roughly previous 2 + current + next 2).
- Add settings for:
  - number of previous lines
  - number of upcoming lines
  - optional single-line focus mode

3. **Animation behaviors**
- Add optional transitions for active-line changes:
  - fade
  - slide
  - scale pulse on active line
- Ensure reduced-motion mode is supported.

4. **Positioning and safe areas**
- Expose vertical anchor (bottom/center/top) and margin offsets.
- Keep overlays clear of stage controls/QR overlays.

5. **Data enrichment**
- If future lyric providers include per-word timing, extend cue schema with nested timing while preserving current line-level `time/text` compatibility.

## Compatibility guidance
- Keep endpoint output backward-compatible:
  - required: `time`, `text`
  - optional: future style/animation hints
- Avoid breaking existing `.lrc` parser behavior (`[mm:ss]`, `[mm:ss.xx]`, multi-timestamp, `offset`).
