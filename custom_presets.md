# Custom Stage Lyrics Presets

A lyrics preset saves the appearance and layout of the karaoke lyrics shown on
the fullscreen [Stage page](/stage). Presets are shared with all stage displays;
an administrator can create, edit, and apply them from the Stage lyrics panel.

This guide is also a contract for generating a preset JSON file with an AI
assistant.

## Start with the built-in presets

The application includes ready-to-use themes, including `cap`, `cyber`,
`classic`, `country`, `neon`, `branded`, Chinese-focused themes, and a dimmed
background theme. After configuring `DATABASE_URL` and `MEDIA_PATH`, install
them from the application checkout:

```bash
uv run python scripts/default_presets.py
```

The command creates only missing preset names (case-insensitive) and never
replaces an existing preset. It also copies `branding1.jpg` and `black.png`
into `MEDIA_PATH` if they are not already there. Those two files are used by
the `branded` and `dimmed` presets through stable `/media/...` URLs.

Run the command again safely after an upgrade or after changing `MEDIA_PATH`.
It preserves any preset or image you have already customized.

## Create or import a preset

1. Open `/stage` as an administrator and open the lyrics settings panel.
2. Tune the preview, then use the preset controls to save it under a new name.
3. To share a preset JSON file, use the panel's export and import controls.

The imported file must be one JSON object. Unknown keys are ignored and missing
keys receive the app defaults, so include every field below when sharing a
finished design.

```json
{
  "fontPreset": "custom",
  "customFontFamily": "Roboto",
  "customFontWeight": 700,
  "sizeVw": 4.5,
  "lineWidthPct": 90,
  "lineGapVw": 0.8,
  "neighborLineScalePct": 73,
  "neighborLineOpacityPct": 75,
  "textColor": "#939393",
  "activeColor": "#ffffff",
  "outlineColor": "#000000",
  "outlineWidth": 2,
  "previousLines": 1,
  "nextLines": 2,
  "lineBehavior": "rolling",
  "animation": "crop",
  "backgroundMediaEnabled": false,
  "backgroundMediaPath": "",
  "backgroundMediaOpacityPct": 62
}
```

## Settings reference

| Setting | Accepted values | What it changes |
| --- | --- | --- |
| `fontPreset` | `karaoke_cjk`, `readable_cjk`, `system_cjk`, `serif_cjk`, `custom` | Selects one of the built-in CJK-safe font stacks, or enables a custom Google Font. |
| `customFontFamily` | A Google Fonts family name, up to 220 characters | Used only with `fontPreset: "custom"`; for example `"Roboto"` or `"Playfair Display"`. The Stage page loads the font when it is available online. |
| `customFontWeight` | `300`, `400`, `500`, `700` | Weight requested for a custom font. Choose a weight the selected Google Font provides. |
| `sizeVw` | `3.2`–`8.8` | Main lyric text size in viewport-width units. |
| `lineWidthPct` | `60`–`100` | Maximum lyric line width as a percentage of the stage width. |
| `lineGapVw` | `0.2`–`2` | Space between visible lyric lines, in viewport-width units. |
| `neighborLineScalePct` | `30`–`100` | Size of preceding and following lines relative to the active line. |
| `neighborLineOpacityPct` | `10`–`100` | Opacity of preceding and following lines. |
| `textColor` | `#RRGGBB` | Color of lyrics that are not currently highlighted. |
| `activeColor` | `#RRGGBB` | Color of the active lyric text or active word. |
| `outlineColor` | `#RRGGBB` | Color of the text outline that protects legibility. |
| `outlineWidth` | `2`–`14` | Width of the lyric text outline. |
| `previousLines` | `0`–`3` | Number of lyric lines before the active line. Ignored by `fixed_group`. |
| `nextLines` | `0`–`3` | Number of lyric lines after the active line. With `fixed_group`, the visible group contains `1 + nextLines` cues. |
| `lineBehavior` | `rolling`, `rolling_scroll`, `fixed_group` | How the visible lyric window advances. See below. |
| `animation` | `slide`, `crop`, `fade`, `none` | Text transition effect. `crop` is closest to a classic karaoke scrolling effect. |
| `backgroundMediaEnabled` | `true` or `false` | Whether to show a media background behind the lyrics. |
| `backgroundMediaPath` | An app-local `/media/...` image or video path | Background asset to display. It cannot be an external URL. |
| `backgroundMediaOpacityPct` | `10`–`100` | Opacity of the background image or video. |

### Line behavior

- `rolling` keeps the active cue in a window defined by `previousLines` and
  `nextLines`.
- `rolling_scroll` uses the same window but animates it upward as lyrics
  advance.
- `fixed_group` ignores `previousLines`, shows a fixed chunk of `1 + nextLines`
  cues, and advances only after the active cue leaves that chunk.

## Generate a design with an AI assistant

Copy the prompt below into an AI chat, then replace the bracketed design brief.
Ask for a different result each time if you want a few visual directions to
compare. You can also copy and paste existing JSON presets and ask the AI to change color scheme, font.

```text
You are a creative designer for a karaoke stage display. Generate one complete,
valid JSON object for a custom lyrics preset. The design brief is:

[Describe the venue, mood, audience, colors to use or avoid, and whether the
lyrics will often be Chinese, Latin-script, or mixed.]

Prioritize visual aesthetics and projected-screen legibility: choose a cohesive
font, color scheme, typography weight, spacing, line hierarchy, and outline
that still read clearly over a moving music video. Make the active lyric color
visually distinct without using low-contrast combinations. Use restrained
neighbor-line opacity and scale so the current line is obvious from a distance.

Include the JSON with the following keys and values:
fontPreset, customFontFamily, customFontWeight, sizeVw, lineWidthPct,
lineGapVw, neighborLineScalePct, neighborLineOpacityPct, textColor,
activeColor, outlineColor, outlineWidth, previousLines, nextLines,
lineBehavior, animation, backgroundMediaEnabled, backgroundMediaPath,
backgroundMediaOpacityPct.

Rules:
- Use one of fontPreset: custom, karaoke_cjk, readable_cjk, system_cjk, serif_cjk.
- For custom fonts, choose a real Google Fonts family and one supported
  weight from 300, 400, 500, or 700. Otherwise set customFontFamily to an empty
  string and customFontWeight to 700.
- Use #RRGGBB colors only.
- Keep values within: sizeVw 3.2-8.8; lineWidthPct 60-100; lineGapVw 0.2-2;
  neighborLineScalePct and neighborLineOpacityPct 30-100; outlineWidth 2-14;
  previousLines and nextLines 0-3; backgroundMediaOpacityPct 10-100.
- Use rolling, rolling_scroll, or fixed_group for lineBehavior; use slide,
  crop, fade, or none for animation.
- The crop animation is preferred for classic karaoke scrolling
- Do not use a background image or video in this generated design: set
  backgroundMediaEnabled to false and backgroundMediaPath to an empty string.
- If the user has specified the JSON which has backgroundMediaEnabled, you can
  keep that value and change other values to match the design brief

```

After importing an AI-generated preset, preview it with actual songs on the
Stage page. Projectors, TVs, and busy video backgrounds can make a technically
valid color palette hard to read; increase `outlineWidth`, contrast, or
`sizeVw` if needed.
