# syntax=docker/dockerfile:1.7

# Deno's official bin image supplies only the architecture-matched executable.
ARG DENO_VERSION=2.8.0
ARG UV_VERSION=0.11.2
FROM denoland/deno:bin-${DENO_VERSION} AS deno

# uv is used only while building the virtual environment; it is not present in
# either production target.
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:3.12-slim-bookworm AS dependencies
COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

FROM dependencies AS vocal-sync-dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra vocal-sync

FROM python:3.12-slim-bookworm AS runtime-base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    HOST=0.0.0.0 \
    PORT=8000 \
    DATABASE_URL=sqlite:////data/karaoke.db \
    MEDIA_PATH=/data/media \
    CACHE_PATH=/data/cache \
    LOG_DIR=/data/logs \
    YTDLP_PATH=yt-dlp \
    YTDLP_DENO_PATH=/usr/local/bin/deno \
    FFMPEG_PATH=ffmpeg

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir /app /data \
    && chmod 0777 /data

WORKDIR /app
COPY --from=deno /deno /usr/local/bin/deno
COPY adapters/ ./adapters/
COPY demucs_svc/__init__.py demucs_svc/lyrics_line_processor.py demucs_svc/whisperx_pipeline.py ./demucs_svc/
COPY locales/ ./locales/
COPY routes/ ./routes/
COPY services/ ./services/
COPY static/ ./static/
COPY templates/ ./templates/
COPY config.py database.py logging_config.py main.py models.py ./

# The default numeric identity is intentionally unprivileged. Override it with
# Compose's `user: "${PUID}:${PGID}"` to match ownership on a host bind mount.
USER 10001:10001
EXPOSE 8000
VOLUME ["/data"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# Opt-in scientific stack for automatic guide-vocal offset estimation.
FROM runtime-base AS vocal-sync
COPY --from=vocal-sync-dependencies /opt/venv /opt/venv

# Lightweight default: core application dependencies only.
FROM runtime-base AS app
COPY --from=dependencies /opt/venv /opt/venv
