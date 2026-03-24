# TASKS.md

## Sprint 01 goal
Build a working end-to-end MVP for mobile queueing, TV playback, YouTube download, Demucs offload, and basic subtitle-burned karaoke generation.

## Completed tasks ✓
- [x] Create base FastAPI app structure
- [x] Add mobile queue page
- [x] Add TV playback page
- [x] Implement YouTube search endpoint
- [x] Implement queue add/list/current endpoints
- [x] Implement yt-dlp download adapter
- [x] Implement lyrics lookup service (placeholder)
- [x] Implement Demucs API client
- [x] Implement ffmpeg subtitle-burn video generation
- [x] Add SQLite queue persistence
- [x] Add API tests
- [x] Document setup and sprint behavior

## Next steps (future sprints)
- [ ] Integrate real lyrics API (Genius/MusixMatch)
- [ ] Add Whisper for lyrics alignment
- [ ] Add file upload support
- [ ] Implement background job queue (Redis + RQ)
- [ ] Add authentication
- [ ] Add real-time streaming optimization
- [ ] Add user profiles

## Out of scope for this sprint
- [ ] file upload
- [ ] Whisper transcription
- [ ] advanced lyric alignment
- [ ] real-time streaming optimization
- [ ] auth and user profiles