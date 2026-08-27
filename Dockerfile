# syntax=docker/dockerfile:1.7

# Deno's official bin image supplies only the architecture-matched executable.
ARG DENO_VERSION=2.8.0
ARG UV_VERSION=0.11.2
ARG FFMPEG_VERSION=7.0.2
FROM denoland/deno:bin-${DENO_VERSION} AS deno

# uv is used only while building the virtual environment; it is not present in
# any production target.
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# John Van Sickle publishes architecture-specific, self-contained FFmpeg
# archives. Keep only ffmpeg and ffprobe; the archive also contains manpages,
# source metadata, and optional VMAF models that the app does not use.
FROM alpine:3.22 AS ffmpeg-static
ARG FFMPEG_VERSION
ARG TARGETARCH
RUN apk add --no-cache curl tar xz \
    && case "${TARGETARCH}" in \
         amd64) archive_arch=amd64; checksum=7fa72b652e19bf84c9461e332ea1cdf3 ;; \
         arm64) archive_arch=arm64; checksum=807afe21601db0a73e426121c7d636ea ;; \
         *) echo "Unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
       esac \
    && curl --fail --location --silent --show-error \
         --output /tmp/ffmpeg.tar.xz \
         "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-${archive_arch}-static.tar.xz" \
    && echo "${checksum}  /tmp/ffmpeg.tar.xz" | md5sum -c - \
    && mkdir /tmp/ffmpeg \
    && tar -xJf /tmp/ffmpeg.tar.xz --strip-components=1 -C /tmp/ffmpeg \
    && install -D -m 0755 /tmp/ffmpeg/ffmpeg /out/ffmpeg \
    && install -D -m 0755 /tmp/ffmpeg/ffprobe /out/ffprobe \
    && rm -rf /tmp/ffmpeg /tmp/ffmpeg.tar.xz

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
    YTDLP_DENO_PATH="" \
    FFMPEG_PATH=ffmpeg

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir /app /data \
    && chmod 0777 /data

WORKDIR /app
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

# Debian's FFmpeg package is the default for broad distro integration. The
# static target below is an alternative for comparing image size and runtime
# behavior without pulling FFmpeg's shared-library dependency tree.
FROM runtime-base AS runtime-with-debian-ffmpeg
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
USER 10001:10001

FROM runtime-base AS runtime-with-static-ffmpeg
COPY --from=ffmpeg-static /out/ffmpeg /usr/local/bin/ffmpeg
COPY --from=ffmpeg-static /out/ffprobe /usr/local/bin/ffprobe

FROM runtime-with-debian-ffmpeg AS runtime-with-deno
ENV YTDLP_DENO_PATH=/usr/local/bin/deno
COPY --from=deno /deno /usr/local/bin/deno

# Opt-in scientific stack for automatic guide-vocal offset estimation.
FROM runtime-with-deno AS vocal-sync
COPY --from=vocal-sync-dependencies /opt/venv /opt/venv

# Lightweight default: core application dependencies only.
FROM runtime-with-deno AS app
COPY --from=dependencies /opt/venv /opt/venv

# Experimental smallest core image. yt-dlp external JavaScript execution is unavailable.
FROM runtime-base AS app-no-deno
COPY --from=dependencies /opt/venv /opt/venv

# Experimental image using the pinned static FFmpeg binaries instead of the
# Debian package. This target is intentionally separate from `app` while it is
# being evaluated for compatibility and size reduction.
FROM runtime-with-static-ffmpeg AS app-static-ffmpeg
COPY --from=dependencies /opt/venv /opt/venv

FROM runtime-with-static-ffmpeg AS vocal-sync-static-ffmpeg
COPY --from=vocal-sync-dependencies /opt/venv /opt/venv
