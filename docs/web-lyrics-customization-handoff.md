# Web Lyrics Customization Handoff

This document captures extension points for future lyric-style customization on `/stage`.

## Current baseline
- Overlay is rendered in `templates/stage.html` as `#stage-lyrics-overlay`.
- Stage lyric cue rendering and browser-local appearance settings live in `static/stage-lyrics.js`.
- Timed cues are loaded from `GET /api/queue/{item_id}/lyrics-cues`.
- Active line uses `.stage-lyric-line--current`, nearby lines use `.stage-lyric-line`.
- Aligned JSON cues may include `words: [{word, start, end}]`; the stage progressively highlights
  completed/current words while leaving upcoming words in the configured base color. The crop mode
  uses a left-to-right clipped fill on the active word to mimic traditional karaoke.
- Visible cues before the active cue are treated as played: plain lines keep the active color via
  `.stage-lyric-line--played`, and word-aligned lines keep all rendered words highlighted.
- When a cue gap exceeds four seconds, `/stage` inserts a short dot countdown before the next lyric
  line so long intros and interludes feel closer to karaoke-style timing prompts.
- Timeline authority is `video.currentTime`.
- Appearance settings are stored per browser in `localStorage` under
  `karaoke_stage_lyrics_settings_v1` and can be downloaded, applied from the textarea, or uploaded as JSON.
- Optional fullscreen lyric background media is stored in the same settings object as
  `backgroundMediaEnabled`, `backgroundMediaPath`, and `backgroundMediaOpacityPct`. The path is
  canonical `/media/...`; images render as cover-fit `<img>` and videos render as muted autoplay loop
  `<video>` with no controls.
  The layer appears only in fullscreen, above the original stage media and below `#stage-lyrics-overlay`.
  The stage only marks the background eligible once lyric cues have loaded successfully for the
  current queue item, so songs without external lyrics stay on the base stage media.
  If the configured file is missing or unsupported, the layer hides and playback continues normally.
- Stage display identity is also browser-local: `karaoke.stage.displayId` stays stable per browser and
  `karaoke.stage.displayName` is only stored when the operator sets a custom name. Otherwise `/stage`
  derives a label from platform, screen size, and id suffix for `/queue` targeting.
- Shared lyric presets are now stored server-side and managed from `/stage` through `/api/lyrics-presets`;
  the stored preset payload should stay aligned with the same normalized stage settings object.
- The desktop-only Style panel groups controls into display identity, typography, line layout,
  color and contrast, lyrics window, motion, background media, and advanced transfer. Keep the
  existing `stage-lyrics-settings-*` element IDs stable when refining that presentation; the
  controller binds directly to them. Custom font inputs stay hidden until the Custom typeface is
  selected so the default tuning flow remains concise.
- The default stage baseline is the sans-serif CJK stack with 4.5vw text, 85% max width, 0.8vw cue-row
  spacing, 5px outline, one previous line, two next lines, 60% surrounding line size/opacity, and fade animation.
- The karaoke preset uses the local `ZCOOL QingKe HuangYou` face instead of the decorative script fallback.
- Custom font stacks are applied as CSS `font-family` values and only take effect when the user clicks
  the explicit Apply or Save actions. At that point the page requests the first non-generic,
  non-local font family from Google Fonts once in light (300), regular (400), medium (500), and bold
  (700) weights when available; typing in the textbox does not trigger network requests.
- The custom-font panel offers those four weights only for Custom typefaces. Built-in CJK presets
  retain their intentional karaoke weight; operators can open the panel-header help link for the
  broader documentation without adding explanatory text to the control row.
- Cue-row spacing is separately configurable from wrapped-text line-height, so operators can make
  the visible lyric window denser or airier without changing the internal leading of a wrapped cue.
- Outline rendering is stroke-first on supporting browsers, with a shadow fallback for older engines.

## Recommended future customization surfaces

1. **Typography + color tokens**
- Typography, color, size, and outline are now browser-configurable CSS tokens.
- Keep backend lyrics payloads independent of presentation settings.
- The default preset is `readable_cjk` rather than the more decorative karaoke face, which keeps the
  stage usable on mobile without further tuning.

2. **Line window behavior**
- Previous and upcoming line counts are browser-configurable.
- Single-line focus is available by setting both values to `0`.
- `lineBehavior` controls how the visible line window advances:
  - `rolling` keeps the active line in the current rolling window using `previousLines` and `nextLines`.
  - `rolling_scroll` keeps the same rolling window bounds as `rolling`, but animates the window upward
    smoothly when the active cue advances into the next row.
  - `fixed_group` ignores `previousLines`, displays fixed chunks of `1 + nextLines` cues, and advances
    only when the active cue leaves the current chunk.
- The lyric row width now scales with the available stage viewport width instead of capping at a fixed pixel value, and the controller stores that width as a percentage setting for later UI exposure.
- The surrounding line size and opacity are browser-configurable percentages relative to the active line, so the window can be tuned without changing cue payloads.

3. **Animation behaviors**
- Supported settings:
  - `slide` for word-aligned JSON tracks
  - `crop` for clipped word fill on aligned JSON tracks
  - `fade`
  - `none`
- These are word-level/current-line animation settings; they do not control fixed-group or rolling line
  window behavior such as `rolling_scroll`.
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
