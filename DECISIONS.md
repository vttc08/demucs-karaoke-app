# Architectural Decisions

## ADR-001: Use FastAPI for Web Framework

**Status**: Accepted

**Context**: Need a Python web framework for serving HTML pages and REST APIs.

**Decision**: Use FastAPI with Jinja2 templates.

**Rationale**:
- Native async support for external API calls (Demucs)
- Auto-generated API docs
- Type validation with Pydantic
- Lightweight and fast
- Easy integration with SQLAlchemy

**Consequences**:
- Positive: Clean async/await code, type safety, good developer experience
- Negative: Requires Python 3.11+ for best type hints

---

## ADR-002: SQLite for Queue Storage

**Status**: Accepted

**Context**: Need to persist queue state across restarts.

**Decision**: Use SQLite via SQLAlchemy.

**Rationale**:
- Zero configuration for MVP
- File-based, no separate DB server needed
- SQLAlchemy provides migration path to PostgreSQL if needed
- Sufficient for single-server home use

**Consequences**:
- Positive: Simple setup, portable
- Negative: Limited concurrency (fine for home use)

---

## ADR-003: Adapter Pattern for External Tools

**Status**: Accepted

**Context**: Need to call yt-dlp, ffmpeg, and Demucs.

**Decision**: Wrap external tools in adapter classes.

**Rationale**:
- Isolates subprocess calls
- Easy to mock in tests
- Can swap implementations if tools change
- Centralizes error handling

**Consequences**:
- Positive: Testable, maintainable, clear boundaries
- Negative: Extra layer of abstraction

---

## ADR-004: Synchronous Processing for MVP

**Status**: Accepted

**Context**: Queue items need downloading, processing, and vocal removal.

**Decision**: Process items synchronously on-demand (blocking endpoint).

**Rationale**:
- Simpler implementation for MVP
- No need for job queue infrastructure (Celery, RQ)
- Background tasks handled by FastAPI BackgroundTasks if needed
- Can add async job queue later if needed

**Consequences**:
- Positive: Simple, no extra dependencies
- Negative: API call blocks until processing completes
- Future: Add job queue (Redis + RQ) for better UX

---

## ADR-005: Server-Rendered HTML with Light JavaScript

**Status**: Accepted

**Context**: Need mobile queue UI and TV playback UI.

**Decision**: Use Jinja2 templates with vanilla JavaScript (no React/Vue).

**Rationale**:
- Simpler architecture, fewer dependencies
- Fast page loads
- Easy to edit over SSH
- Sufficient for MVP UI needs
- Can add HTMX later if needed

**Consequences**:
- Positive: Simple, maintainable, SSH-friendly
- Negative: Manual DOM manipulation for dynamic updates

---

## ADR-006: Placeholder Lyrics Service

**Status**: Accepted

**Context**: Need lyrics for karaoke mode.

**Decision**: MVP returns placeholder lyrics; integrate real API later.

**Rationale**:
- Lyrics APIs (Genius, MusixMatch) require API keys and approval
- Placeholder allows testing full flow
- Can integrate real API in Sprint 02

**Consequences**:
- Positive: Unblocks MVP development
- Negative: Karaoke videos have placeholder lyrics for now

---

## ADR-007: Simple Time-Based Subtitles

**Status**: Accepted

**Context**: Need to generate SRT subtitles for karaoke.

**Decision**: Split lyrics into lines with fixed 5-second intervals.

**Rationale**:
- MVP approach, no complex timing analysis
- Sufficient for basic karaoke experience
- Can add Whisper alignment in future sprint

**Consequences**:
- Positive: Simple implementation
- Negative: Subtitles not synchronized with actual singing
- Future: Add Whisper for word-level timestamps

---

## ADR-008: Demucs as External Service

**Status**: Accepted

**Context**: Demucs requires GPU and is compute-intensive.

**Decision**: Run Demucs on separate machine, call via HTTP API.

**Rationale**:
- Demucs needs GPU (not available on all machines)
- Separates compute-heavy processing
- Allows scaling Demucs independently
- Development can use mock/stub

**Consequences**:
- Positive: Flexible deployment, scalable
- Negative: Network dependency, requires separate service setup

---

## ADR-009: Bind on 0.0.0.0 for Remote Access

**Status**: Accepted

**Context**: Need to access app from mobile devices and TV on local network.

**Decision**: Bind server to `0.0.0.0` instead of `localhost`.

**Rationale**:
- Allows access from other devices on LAN
- Common pattern for home services
- SSH development workflow requires remote access

**Consequences**:
- Positive: Mobile and TV can connect
- Negative: Exposed on local network (acceptable for home use)
- Note: Do not expose to internet without authentication

---

## ADR-010: Use uv for Dependency Management

**Status**: Accepted

**Context**: Need fast, reliable Python dependency management.

**Decision**: Use `uv` instead of pip/poetry/pipenv.

**Rationale**:
- Extremely fast installs
- pyproject.toml support
- Compatible with standard Python workflows
- Good for SSH/mobile development (fast sync)

**Consequences**:
- Positive: Fast, modern, standards-compliant
- Negative: Requires uv installation (one-time setup)
