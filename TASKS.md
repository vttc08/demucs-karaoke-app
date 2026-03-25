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

## New Todos
- [x] settings page and checking the health status of demucs backend
- [x] disable karaoke mode if demucs is determined unhealthy
- [ ] customize file behavior of karaoke cache and media and configure it to be served from different location
- [ ] demucs API microservice as configurable options for cpu, cuda, demucs model and mp3 output
- [ ] real time application push instead of polling
- [ ] yt-dlp refinement, fix bugs with video downloading and less errors
- [ ] concurrent ytdlp search for karaoke phrase and settings page
- [ ] configure proxy settings for YTDLP
- [ ] custom playback engine, since some browser don't autoplay
- [ ] background splash, show qrcode
- [ ] database improvement, periodic and manual cleanup of failed songs and already played/skipped
- [ ] fulltext and file search existing media
- [ ] integrate whisper (lang detect, word by word transcription), align lyrics if lyrics file present
- [ ] explore client side lyrics compositing
- [ ] explore client side multi-track playback and toggle vocals

## Next steps (future sprints)
- [x] Integrate real lyrics API (Genius/MusixMatch)
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