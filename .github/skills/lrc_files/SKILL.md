---
name: lrc_files
description: Skills for reading and parsing lyrics files (.lrc) containing synced lyrics for songs.
---


# LRC Reader Skill

## Overview
This skill reads and parses `.lrc` (Lyric) files.  
It extracts metadata tags and timestamped lyric lines, supporting multiple timestamps per line and offset adjustments.

---

## Supported Features
- Timestamp formats:
  - `[mm:ss.xx]`
  - `[mm:ss]`
- Multiple timestamps per line
- Offset adjustment (shifts all timestamps)
- Sorted output by time

