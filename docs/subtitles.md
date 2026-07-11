# Subtitle Workflow

The subtitle editor is an admin-only workflow for round-tripping synced JSON lyrics through desktop subtitle editors.

## Recommended path: ASS + Aegisub

- Export each lyric line as an ASS event.
- Use `{\k123}` karaoke tags for word timing, where the number is centiseconds.
- Aegisub is the preferred editor when the goal is karaoke-style timing edits.
- The edited ASS file is authoritative after upload and is converted back into the app's JSON lyrics sidecar.

## Alternate path: SRT + SubtitleEdit

- Export each word as its own subtitle line.
- Prefix the first line of each segment with a `//wx:{index}//` marker.
- The notebook uses `i * 10` for the marker index so users can insert lines between existing segments later.
- SubtitleEdit is the preferred editor when the goal is word-level reshaping instead of karaoke timing.

## Import path: TTML to JSON

- TTML uploads on `/media-subtitles/{item_id}` are parsed directly into the app's canonical WhisperX JSON sidecar.
- The parser uses Python's built-in XML support and follows the notebook-proven TTML notebook in `docs/ttml.ipynb`.
- Musixmatch TTML can wrap timed word spans in untimed grouping spans (including background-vocal
  containers); those wrappers are ignored so automatic upgrade validation sees the actual timed words
  and JSON conversion does not duplicate the wrapper text.
- XML validation is kept separate so future upload flows can detect TTML or other XML inputs before deciding whether WhisperX alignment is needed.

## Split/Merge editor

- `/media-subtitles/{item_id}/split-merge` opens the synced JSON split/merge editor for a single media item.
- The editor can split a line after a selected word, merge a line with the next line, auto-rewrap the current JSON with the notebook-proven line processor, and save the result back to the JSON sidecar.
- The editor is intentionally scoped to synced JSON lyrics. Plain text and LRC continue to use the queue or WhisperX alignment flows.

## Edge cases

- Overlapping segments are warned about, but they do not block upload.
- For ASS export, earlier lines are truncated to the next line start when overlaps are detected.
- If a karaoke line extends beyond its final word, the final `{\k}` duration is expanded to fill the line.
- If a user shortens a karaoke line in Aegisub, the import path clamps any word timing that now runs past the line end.
- If a word is missing from the edited SRT, the import path keeps the remaining words and rebuilds the segment from what is still present.
- When a media item does not have synced JSON lyrics, `/media-subtitles/{item_id}` returns a 404 page with a back button instead of silently redirecting to `/media`.

## Authoritative source

The current notebook notes in `docs/subtitles.ipynb` are the source of truth for the ASS and SRT conversion behavior. The TTML import notebook in `docs/ttml.ipynb` is the source of truth for TTML parsing behavior.
