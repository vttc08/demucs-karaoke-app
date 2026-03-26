# AGENTS.md

## Project summary
This is a lightweight AI-powered karaoke application for home use.

Current sprint goal:
- mobile-friendly queue page
- TV playback webpage
- YouTube search and queue
- basic karaoke/non-karaoke branching
- Demucs offload to external service
- generate a simple burned-subtitle video

## Priorities
1. Keep the MVP simple and working end-to-end.
2. Prefer server-rendered HTML with minimal JavaScript.
3. Use FastAPI for backend APIs and page serving.
4. Keep code modular and easy to continue from a mobile SSH workflow.
5. Bind development servers to `0.0.0.0`.
6. Add tests for routes and core service logic.
7. Update docs in `/docs` when behavior or architecture changes.

## Constraints
- Do not implement future sprints unless explicitly requested.
- Do not add Whisper yet.
- Do not add file upload yet.
- Do not add authentication yet.
- Do not add a complex frontend framework unless explicitly requested.
- Demucs runs on a separate machine and must be accessed through a simple API client.
- Most development happens over SSH/tmux/mobile, so keep workflows CLI-friendly.

## Coding rules
- Prefer simple Python modules over heavy abstractions.
- Use `uv` for virtual environment management and running commands.
- Keep route handlers thin; business logic belongs in `services/`.
- External tools such as `yt-dlp` and `ffmpeg` should be wrapped in adapters.
- Use environment variables for service URLs and media paths.
- Avoid hardcoding personal paths, IPs, or secrets.
- Use clear filenames and small functions.
- Prefer incremental changes and minimal diffs.
- Use module-level loggers (`logging.getLogger(__name__)`) and structured context in log messages (ids, operation, paths where relevant).
- Do not log secrets, credentials, or full sensitive payloads.
- Prefer `logger.exception(...)` when handling unexpected exceptions to preserve stack traces.
- Keep logs actionable and concise; avoid noisy per-line debug logging in normal flows.

## Required behavior for agents
Before making changes, read:
- `README.md`
- `TASKS.md`
- `ARCHITECTURE.md`
- relevant docs in `/docs`

For each non-trivial change:
1. briefly summarize the plan
2. list files to create or modify
3. state assumptions

When finished:
- update docs if needed
- update tasks if scope changed
- include commands to run and test
- commit the changes with git if the change is major
  - check whether there are uncommitted changes or secrets

## Testing requirements
- Add or update API tests for new endpoints
- Add service-level tests where practical
- Prefer mock/stub subprocess calls in tests
- Do not rely on Demucs being available in the dev workspace
- For logging changes, add focused tests that validate configuration behavior (handlers, levels, rotation setup) without brittle string matching.

## Documentation 
- If you need to create summary documents or instruction, please place it in the `/docs` and not in the root folder
