# ARCHITECTURE.md

## Current architecture
This project currently uses two services:

1. Main app
- serves mobile queue page and TV playback page
- manages queue state
- searches YouTube
- downloads video/audio
- fetches lyrics
- calls Demucs service
- generates output karaoke video

2. Demucs service
- receives audio processing request
- runs demucs two-stem vocals separation
- returns path or metadata for generated `no_vocals.wav`

## Design principles
- Keep the MVP CLI-friendly and easy to run locally
- Prefer local filesystem storage for media artifacts
- Prefer SQLite for queue and metadata during MVP
- Keep Demucs integration simple and replaceable
- Keep playback flow deterministic and testable

## Current scope
In scope:
- YouTube search
- queue song
- TV playback
- karaoke vs non-karaoke handling
- basic lyrics lookup
- basic burned subtitles
- Demucs offload API

Out of scope:
- Whisper transcription
- file upload
- user accounts
- streaming optimization
- distributed job queues