### Media Items
```sql
CREATE TABLE media_items (
    id INTEGER PRIMARY KEY,
    youtube_id TEXT UNIQUE,
    title TEXT,
    artist TEXT,
    media_path TEXT NOT NULL UNIQUE,
    lyrics_path TEXT,
    vocals_path TEXT,
    missing INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    last_scanned_at DATETIME
);
```
Meaning
media_path: always relative app path such as /media/abc123.webm
lyrics_path: optional sidecar like /media/abc123.lrc
vocals_path: optional sidecar like /media/abc123.vocals.m4a
missing: file not currently found on disk

plain video:
lyrics_path IS NULL
vocals_path IS NULL
video + lyrics:
lyrics_path IS NOT NULL
video + karaoke assist:
vocals_path IS NOT NULL
full enriched item:
both present

Note: this is for the future where multi-track playback would be implemented

### Queue Items
```sql
CREATE TABLE queue_items (
    id INTEGER PRIMARY KEY,
    media_id INTEGER NOT NULL REFERENCES media_items(id) ON DELETE RESTRICT,
    position INTEGER NOT NULL,
    requested_karaoke INTEGER NOT NULL DEFAULT 0,
    requested_burn_lyrics INTEGER NOT NULL DEFAULT 0,
    user_id TEXT,
    session_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);
```

user_id / session_id can stay nullable for now, for future multi-room/user 
queue_items only stores active queue
runtime queue-state fields (`requested_*`, `status`, `error`) are allowed here.

### Indexes
```sql
CREATE INDEX idx_media_items_title ON media_items(title);
CREATE INDEX idx_media_items_artist ON media_items(artist);
CREATE INDEX idx_queue_position ON queue_items(position);
CREATE INDEX idx_queue_items_media_id ON queue_items(media_id);
```

### Queue ordering
- Use sparse integer positions: 1000, 2000, 3000...
- Helpers:
  - append to end: max(position) + 1000
  - add to front: min(position) - 1000 (with renumber guard)
  - insert between: midpoint if gap exists
  - renumber when gap is exhausted

### Migration steps from legacy single table
1. Create `media_items`.
2. Backfill `media_items` from legacy `queue_items` (`youtube_id` dedupe, placeholder `/media/{youtube_id}.mp4` when no media path exists).
3. Create `queue_items_new` with `media_id` FK + sparse `position`.
4. Backfill active queue rows from legacy table into `queue_items_new`.
5. Drop old `queue_items`, rename `queue_items_new` to `queue_items`.
6. Ensure indexes.

### Future sync direction (not implemented yet)
- File exists but no DB row: insert minimal `media_items`.
- DB row exists but file missing: set `missing = 1`.
- `youtube_id` row exists and content was deleted: reuse existing row on re-download.
