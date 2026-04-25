# TASKS.md

## Sprint 01 goal
Build a working end-to-end MVP for mobile queueing, TV playback, YouTube download, Demucs offload, and basic remuxed karaoke generation with sidecar lyrics.

## Completed tasks ✓
- [x] Create base FastAPI app structure
- [x] Add mobile queue page
- [x] Add stage page
- [x] Implement YouTube search endpoint
- [x] Implement queue add/list/current endpoints
- [x] Implement yt-dlp download adapter
- [x] Implement lyrics lookup service (placeholder)
- [x] Implement Demucs API client
- [x] Implement ffmpeg karaoke media merge/remux generation
- [x] Add SQLite queue persistence
- [x] Add API tests
- [x] Document setup and sprint behavior

## New Todos
- [x] settings page and checking the health status of demucs backend
- [x] disable karaoke mode if demucs is determined unhealthy
- [x] customize file behavior of karaoke cache and media and configure it to be served from different location
- [x] implement logging
- [x] demucs API microservice as configurable options for cpu, cuda, demucs model and mp3 output
- [x] real time application push instead of polling
- [x] yt-dlp refinement, fix bugs with video downloading and less errors
- [x] check/update yt-dlp version from settings UI
- [x] concurrent ytdlp search for karaoke phrase and settings page and filter for results
- [x] configure proxy settings for YTDLP
- [x] support direct YouTube link/id input in search box
- [x] mark already-downloaded search results and reuse existing media on queue add
- [ ] ~~ffmpeg microservice~~
- [x] custom playback engine 
- [x] background splash, show qrcode
- [x] manage playback on other devices
- [x] database improvement, periodic and manual cleanup of failed songs and already played/skipped
- [x] fulltext and file search existing media
- [x] persist settings in database
- [ ] integrate whisper (lang detect, word by word transcription), align lyrics if lyrics file present
- [x] explore client side lyrics compositing
- [x] explore client side multi-track playback and toggle vocals
- [x] add google search links for lyrics
- [x] add YouTube link on queue lyrics page
- [x] proxy support for lyrics
- [x] cache searched results and lyrics
- [x] modular provider files and user can disable or implement their own
- [x] investigate search slowness, specifically local
- [x] nudge user options whether to enable karaoke or lyrics based on video title
- [ ] store media name more human readable
- [ ] store demucs output not in cache, all should be served from media
- [ ] file manager with real data
- [ ] scan database button to sync states
- [ ] perform crud on karaoke media
- [ ] refine UI screen: add to queue condensed (mobile)
- [ ] user can upload mp3 and mp4 videos screen: media upload (mobile+desktop)
- [ ] queue page with users
- [ ] frontend settings page polish
- [ ] blueprints for subfolder custom path support
- [x] consistent themed restriction page for outside network and splash screen
- [ ] admin login page for settings and splash
- [ ] login page for device identification only, stored in local storage (Login Screen)
- [ ] real time join and enqueue feature
- [ ] admin has ability to remove, skip or reorder queue
- [ ] fix multi track audio sync issues
- [x] customize lyric tracks behavior
- [x] lyrics-assisted add-to-queue flow with manual lyrics override
- [ ] oidc authelia support
- [ ] batching demucs using load balancer and split file into small segments for batch processing

## Next steps (future sprints)
- [x] Integrate real lyrics API (Genius/MusixMatch)
- [ ] Add Whisper for lyrics alignment
- [ ] Add file upload support
- [ ] Implement background job queue (Redis + RQ)
- [ ] Add authentication
- [ ] Add real-time streaming optimization
- [ ] Add user profiles
