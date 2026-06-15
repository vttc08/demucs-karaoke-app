# Lossless Trim Editor

## Scope

The admin-only editor at `/media-editor/{item_id}` removes an intro and/or outro. It does not
support crop, effects, filters, transitions, or re-encoding.

Open a media row's edit modal on `/media`, then select **Lossless Trim**. The other two media-tool
buttons are placeholders and remain disabled.

## Range handling

- FFprobe reads the duration, stream types, and I-frame timestamps.
- Video start values snap backward to the nearest I-frame.
- Video end values snap forward to the nearest I-frame or the media duration.
- Audio-only files use the exact requested values.
- The backend repeats validation and snapping; frontend values are not trusted.
- The item cannot be trimmed while it is playing or has an active processing task.

## File processing

Primary media and vocals sidecars use FFmpeg stream copy:

```bash
ffmpeg -ss START -i INPUT -t DURATION -map 0 -c copy \
  -avoid_negative_ts make_zero OUTPUT
```

MP4/MOV-family outputs also use `-movflags +faststart`. No video or audio encoder is selected.

Timed lyrics are shifted to the resolved retained interval:

- `.lrc`: parsed and serialized with `pylrc`
- `.srt`: parsed, clipped, shifted, and serialized with `srt`
- `.json`: WhisperX-style segment lists or objects containing `segments`, `cues`, `items`, or `lines`
- `.txt`: copied unchanged because it has no timing data

JSON segments and nested words are clipped to the interval and shifted so the retained start is
time zero.

## Replacement and recovery

The operation is destructive and does not retain a permanent backup.

All outputs are first written to hidden staged files beside their sources. After every staged asset
passes validation, originals are moved to temporary rollback paths and staged outputs are installed
with same-filesystem `os.replace` calls. If installation fails, originals are restored. Temporary
rollback files are removed after success.

The request is synchronous. The editor disables its submit button while FFmpeg and sidecar updates
run, then returns to `/media` after success.

## Dependencies

The app dependencies include:

```text
pylrc>=0.1.2
srt>=3.5.3
```

Install/update the environment with `uv sync`.

## Tests

Run focused coverage:

```bash
uv run pytest tests/test_ffmpeg_adapter.py tests/services/media_trim.py tests/routes/media_trim.py
```

Run the full suite:

```bash
uv run pytest
```
