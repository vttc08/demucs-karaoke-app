"""Prepare and commit guide vocals for existing karaoke media."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from adapters.ffmpeg import FFmpegAdapter
from config import settings
from models import MediaItem
from services.demucs_client import DemucsClient
from services.media_naming import build_media_stem
from services.queue_service import QueueService
from services.runtime_settings_service import RuntimeSettingsService
from services.youtube_service import YouTubeService

logger = logging.getLogger(__name__)

_UPLOAD_EXTENSIONS = {".mp3", ".mp4", ".webm", ".mkv", ".mov", ".avi", ".m4v", ".wav", ".flac", ".aac", ".ogg", ".opus"}
_TARGET_SAMPLE_RATE = 22050


class VocalSyncError(RuntimeError):
    """Base error for vocal-sync workflow failures."""


class VocalSyncNotFoundError(VocalSyncError):
    """Raised when a media item or review session is missing."""


class VocalSyncConflictError(VocalSyncError):
    """Raised when the media state cannot accept added vocals."""


@dataclass(frozen=True)
class VocalSyncSession:
    """Prepared vocal-sync review session."""

    session_id: str
    media_item_id: int
    media_url: str
    vocals_url: str
    estimated_offset_seconds: float
    method: str
    source_kind: str
    title: str
    artist: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "media_item_id": self.media_item_id,
            "media_url": self.media_url,
            "vocals_url": self.vocals_url,
            "estimated_offset_seconds": self.estimated_offset_seconds,
            "method": self.method,
            "source_kind": self.source_kind,
            "title": self.title,
            "artist": self.artist,
        }


class VocalSyncService:
    """Orchestrate source separation, local offset estimation, and sidecar commit."""

    def __init__(self):
        self.demucs_client = DemucsClient()
        self.youtube_service = YouTubeService()
        self.ffmpeg = FFmpegAdapter()
        self.runtime_settings_service = RuntimeSettingsService()

    @staticmethod
    def session_root() -> Path:
        path = settings.cache_path / "vocal_sync"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _session_dir(session_id: str) -> Path:
        if not session_id or any(ch not in "0123456789abcdef-" for ch in session_id.lower()):
            raise VocalSyncNotFoundError("Invalid vocal sync session")
        return VocalSyncService.session_root() / session_id

    @staticmethod
    def _manifest_path(session_id: str) -> Path:
        return VocalSyncService._session_dir(session_id) / "manifest.json"

    @staticmethod
    def _cache_url(path: Path) -> str:
        try:
            relative = path.resolve().relative_to(settings.cache_path.resolve())
        except ValueError as exc:
            raise VocalSyncError(f"Path is not under cache: {path}") from exc
        return f"/cache/{relative.as_posix()}"

    @staticmethod
    def _media_url(path: Path) -> str:
        return QueueService.build_media_url(path)

    @staticmethod
    def _local_media_path(media_item: MediaItem) -> Path:
        media_path = QueueService._media_url_to_file(media_item.media_path)
        if media_item.missing or media_path is None or not media_path.is_file():
            raise VocalSyncConflictError("Media item file is missing")
        return media_path

    @staticmethod
    def _media_stem(media_item: MediaItem) -> str:
        return media_item.file_stem or build_media_stem(
            media_item.title,
            media_item.artist,
            fallback=media_item.youtube_id or f"media-{media_item.id}",
        )

    @staticmethod
    def _validate_media_for_prepare(media_item: MediaItem | None) -> MediaItem:
        if media_item is None:
            raise VocalSyncNotFoundError("Media item not found")
        if media_item.vocals_path and media_item.vocals_path.strip():
            raise VocalSyncConflictError("Media item already has guide vocals")
        VocalSyncService._local_media_path(media_item)
        return media_item

    def _check_demucs_available(self) -> None:
        health = self.runtime_settings_service.get_demucs_health()
        if not health.healthy:
            raise VocalSyncConflictError(f"Demucs unavailable: {health.detail}")

    async def prepare_from_youtube(
        self,
        db: Session,
        media_item_id: int,
        youtube_id: str,
    ) -> VocalSyncSession:
        media_item = self._validate_media_for_prepare(
            db.query(MediaItem).filter(MediaItem.id == media_item_id).first()
        )
        self._check_demucs_available()
        session_id = str(uuid.uuid4())
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=False)
        source_path = await asyncio.to_thread(
            self.youtube_service.download_audio,
            youtube_id,
            session_dir,
        )
        return await self._prepare_from_source(
            media_item=media_item,
            source_path=source_path,
            session_id=session_id,
            source_kind="youtube",
            source_ref=youtube_id,
        )

    async def prepare_from_upload(
        self,
        db: Session,
        media_item_id: int,
        *,
        source_filename: str,
        source_file,
    ) -> VocalSyncSession:
        media_item = self._validate_media_for_prepare(
            db.query(MediaItem).filter(MediaItem.id == media_item_id).first()
        )
        ext = Path(source_filename or "").suffix.lower()
        if ext not in _UPLOAD_EXTENSIONS:
            raise VocalSyncConflictError("Unsupported vocal source upload type")
        self._check_demucs_available()
        session_id = str(uuid.uuid4())
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=False)
        source_path = session_dir / f"source{ext}"
        with source_path.open("wb") as target:
            shutil.copyfileobj(source_file, target)
        return await self._prepare_from_source(
            media_item=media_item,
            source_path=source_path,
            session_id=session_id,
            source_kind="upload",
            source_ref=source_filename,
        )

    async def _prepare_from_source(
        self,
        *,
        media_item: MediaItem,
        source_path: Path,
        session_id: str,
        source_kind: str,
        source_ref: str,
    ) -> VocalSyncSession:
        session_dir = self._session_dir(session_id)
        media_path = self._local_media_path(media_item)
        demucs_response = await self.demucs_client.separate_vocals(source_path)
        no_vocals_path = Path(demucs_response.no_vocals_path)
        vocals_path = Path(demucs_response.vocals_path)
        if not no_vocals_path.is_file() or not vocals_path.is_file():
            raise VocalSyncError("Demucs response missing separated stems")

        review_vocals_path = session_dir / f"review_vocals{vocals_path.suffix.lower() or '.wav'}"
        review_bg_path = session_dir / f"review_background{no_vocals_path.suffix.lower() or '.wav'}"
        shutil.copy2(vocals_path, review_vocals_path)
        shutil.copy2(no_vocals_path, review_bg_path)

        karaoke_wav = session_dir / "karaoke_mono.wav"
        background_wav = session_dir / "background_mono.wav"
        self.prepare_mono_wav(media_path, karaoke_wav)
        self.prepare_mono_wav(review_bg_path, background_wav)
        offset_seconds = self.estimate_offset_seconds(
            reference_path=background_wav,
            target_path=karaoke_wav,
        )
        manifest = {
            "session_id": session_id,
            "media_item_id": media_item.id,
            "media_url": media_item.media_path,
            "media_path": str(media_path),
            "vocals_path": str(review_vocals_path),
            "background_path": str(review_bg_path),
            "karaoke_wav_path": str(karaoke_wav),
            "background_wav_path": str(background_wav),
            "estimated_offset_seconds": offset_seconds,
            "method": "scipy_cross_correlation",
            "source_kind": source_kind,
            "source_ref": source_ref,
            "title": media_item.title,
            "artist": media_item.artist,
        }
        self._write_manifest(session_id, manifest)
        logger.info(
            "Prepared vocal sync session media_id=%s session_id=%s offset=%.6f",
            media_item.id,
            session_id,
            offset_seconds,
        )
        return self._session_from_manifest(manifest)

    def get_session(self, session_id: str) -> VocalSyncSession:
        return self._session_from_manifest(self._read_manifest(session_id))

    def commit_session(
        self,
        db: Session,
        media_item_id: int,
        session_id: str,
        offset_seconds: float,
    ) -> VocalSyncSession:
        manifest = self._read_manifest(session_id)
        if int(manifest.get("media_item_id") or 0) != int(media_item_id):
            raise VocalSyncConflictError("Vocal sync session does not match media item")
        media_item = db.query(MediaItem).filter(MediaItem.id == media_item_id).first()
        media_item = self._validate_media_for_prepare(media_item)
        vocals_source = Path(str(manifest["vocals_path"]))
        if not vocals_source.is_file():
            raise VocalSyncNotFoundError("Prepared vocals file is missing")
        media_path = self._local_media_path(media_item)
        media_stem = self._media_stem(media_item)
        output_path = settings.media_path / f"{media_stem}.vocals.wav"
        temp_path = settings.media_path / f".{media_stem}.{session_id}.vocals.tmp.wav"
        try:
            self.render_aligned_vocals(
                vocals_path=vocals_source,
                karaoke_path=media_path,
                output_path=temp_path,
                offset_seconds=float(offset_seconds),
            )
            os.replace(temp_path, output_path)
        finally:
            if temp_path.exists():
                temp_path.unlink()
        media_item.vocals_path = self._media_url(output_path)
        media_item.missing = False
        db.commit()
        manifest["committed_vocals_path"] = str(output_path)
        manifest["committed_offset_seconds"] = float(offset_seconds)
        self._write_manifest(session_id, manifest)
        session = self._session_from_manifest(manifest)
        self.delete_session(session_id)
        return session

    def delete_session(self, session_id: str) -> None:
        session_dir = self._session_dir(session_id)
        if session_dir.exists():
            shutil.rmtree(session_dir)

    @classmethod
    def _read_manifest(cls, session_id: str) -> dict[str, Any]:
        path = cls._manifest_path(session_id)
        if not path.is_file():
            raise VocalSyncNotFoundError("Vocal sync session not found")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise VocalSyncError("Vocal sync session manifest is invalid") from exc

    @classmethod
    def _write_manifest(cls, session_id: str, payload: dict[str, Any]) -> None:
        path = cls._manifest_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temp_path, path)

    @classmethod
    def _session_from_manifest(cls, manifest: dict[str, Any]) -> VocalSyncSession:
        vocals_path = Path(str(manifest["vocals_path"]))
        return VocalSyncSession(
            session_id=str(manifest["session_id"]),
            media_item_id=int(manifest["media_item_id"]),
            media_url=str(manifest["media_url"]),
            vocals_url=cls._cache_url(vocals_path),
            estimated_offset_seconds=float(manifest["estimated_offset_seconds"]),
            method=str(manifest.get("method") or "scipy_cross_correlation"),
            source_kind=str(manifest.get("source_kind") or "unknown"),
            title=str(manifest.get("title") or ""),
            artist=manifest.get("artist"),
        )

    @staticmethod
    def prepare_mono_wav(source_path: Path, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            settings.ffmpeg_path,
            "-y",
            "-i",
            str(source_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(_TARGET_SAMPLE_RATE),
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return output_path

    @staticmethod
    def load_mono_wav(path: Path):
        import numpy as np

        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            sample_rate = handle.getframerate()
            frames = handle.readframes(handle.getnframes())
        if sample_width != 2:
            raise VocalSyncError(f"Expected 16-bit PCM WAV: {path}")
        audio = np.frombuffer(frames, dtype="<i2").astype(np.float32)
        if channels > 1:
            audio = audio.reshape(-1, channels).mean(axis=1)
        audio -= np.mean(audio)
        peak = np.max(np.abs(audio)) + 1e-9
        audio /= peak
        return audio, sample_rate

    @staticmethod
    def estimate_offset_seconds(reference_path: Path, target_path: Path) -> float:
        import numpy as np
        from scipy.signal import correlate, correlation_lags

        reference, reference_sr = VocalSyncService.load_mono_wav(reference_path)
        target, target_sr = VocalSyncService.load_mono_wav(target_path)
        if reference_sr != target_sr:
            raise VocalSyncError("Prepared WAV sample rates do not match")
        corr = correlate(target, reference, mode="full", method="fft")
        lags = correlation_lags(len(target), len(reference), mode="full")
        best_lag = int(lags[int(np.argmax(corr))])
        return best_lag / float(reference_sr)

    def render_aligned_vocals(
        self,
        *,
        vocals_path: Path,
        karaoke_path: Path,
        output_path: Path,
        offset_seconds: float,
    ) -> Path:
        duration = float(self.ffmpeg.probe_media(karaoke_path)["duration"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if abs(offset_seconds) < 0.001:
            filter_expr = f"[0:a]asetpts=PTS-STARTPTS,apad,atrim=0:{duration:.6f}[a]"
        elif offset_seconds > 0:
            delay_ms = max(0, round(float(offset_seconds) * 1000))
            filter_expr = f"[0:a]adelay={delay_ms}:all=1,apad,atrim=0:{duration:.6f}[a]"
        else:
            shift = abs(float(offset_seconds))
            filter_expr = f"[0:a]atrim=start={shift:.6f},asetpts=PTS-STARTPTS,apad,atrim=0:{duration:.6f}[a]"
        cmd = [
            settings.ffmpeg_path,
            "-y",
            "-i",
            str(vocals_path),
            "-filter_complex",
            filter_expr,
            "-map",
            "[a]",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return output_path
