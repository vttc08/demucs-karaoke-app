"""Demucs API client for vocal separation."""
from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
import threading
from typing import Callable
import zipfile

import httpx

from config import settings
from models import (
    DemucsIoCleanupResponse,
    DemucsIoUsageResponse,
    DemucsGarbageCollectionResponse,
    DemucsHealthResponse,
    DemucsResponse,
    WhisperXPreloadResponse,
)


ProgressCallback = Callable[[int, str, dict | None], None]
LogCallback = Callable[[str, str], None]


class DemucsClient:
    """Client for Demucs vocal separation service."""

    HEALTH_TIMEOUT_SECONDS = 5.0
    GC_TIMEOUT_SECONDS = 120.0
    IO_TIMEOUT_SECONDS = 10.0
    IO_CLEANUP_TIMEOUT_SECONDS = 120.0
    PRELOAD_TIMEOUT_SECONDS = 1800.0
    REQUEST_TIMEOUT_SECONDS = 600.0
    DELETE_TIMEOUT_SECONDS = 30.0

    def __init__(self, api_url: str = None, poll_interval_seconds: float | None = None):
        self.api_url = api_url or settings.demucs_api_url
        self.poll_interval_seconds = poll_interval_seconds

    @staticmethod
    def _extract_stems_zip(payload: bytes) -> tuple[bytes, bytes, bytes | None, str]:
        with zipfile.ZipFile(BytesIO(payload), mode="r") as archive:
            names = set(archive.namelist())
            no_vocals_name = next((name for name in names if name.startswith("no_vocals.")), None)
            vocals_name = next((name for name in names if name.startswith("vocals.")), None)
            if not no_vocals_name or not vocals_name:
                raise RuntimeError("Demucs ZIP payload missing no_vocals or vocals file")

            extension = Path(no_vocals_name).suffix.lstrip(".").lower() or "wav"
            no_vocals_bytes = archive.read(no_vocals_name)
            vocals_bytes = archive.read(vocals_name)
            aligned_bytes = None
            aligned_name = next(
                (name for name in names if name == "aligned_lyrics.json" or name.endswith("/aligned_lyrics.json")),
                None,
            )
            if aligned_name:
                aligned_bytes = archive.read(aligned_name)
            return no_vocals_bytes, vocals_bytes, aligned_bytes, extension

    def _build_request_data(
        self,
        *,
        lyrics_text: str | None = None,
        lyrics_format: str | None = None,
        transcription_model: str | None = None,
        align_language: str | None = None,
        detect_language: bool | None = None,
        use_synced_lyrics: bool | None = None,
        whisperx_preload_models: str | None = None,
        process_lyrics_lines: bool | None = None,
        max_line_length: int | None = None,
        max_line_length_cjk: int | None = None,
        compute_type: str | None = None,
    ) -> dict[str, str]:
        data = {
            "model": settings.demucs_model,
            "device": settings.demucs_device,
            "output_format": settings.demucs_output_format,
            "transcription_model": transcription_model or settings.whisperx_transcription_model,
            "align_language": align_language if align_language is not None else settings.whisperx_align_language,
            "detect_language": str(
                settings.whisperx_detect_language if detect_language is None else detect_language
            ).lower(),
            "use_synced_lyrics": str(
                settings.whisperx_use_synced_lyrics if use_synced_lyrics is None else use_synced_lyrics
            ).lower(),
            "whisperx_preload_models": whisperx_preload_models or settings.whisperx_preload_models,
        }
        if settings.demucs_output_format == "mp3":
            data["mp3_bitrate"] = str(settings.demucs_mp3_bitrate)
        if lyrics_text:
            data["lyrics_text"] = lyrics_text
        if lyrics_format:
            data["lyrics_format"] = lyrics_format
        if process_lyrics_lines is not None:
            data["process_lyrics_lines"] = str(process_lyrics_lines).lower()
        if max_line_length is not None:
            data["max_line_length"] = str(max_line_length)
        if max_line_length_cjk is not None:
            data["max_line_length_cjk"] = str(max_line_length_cjk)
        if compute_type:
            data["compute_type"] = compute_type
        return data

    @staticmethod
    def _emit_progress(
        callback: ProgressCallback | None,
        percent: int,
        message: str,
        metadata: dict | None = None,
    ) -> None:
        if callback is not None:
            callback(max(0, min(100, int(percent))), message, metadata)

    @staticmethod
    def _emit_remote_log_lines(
        callback: LogCallback | None,
        output_tail: list[str],
        seen_lines: set[str],
    ) -> None:
        if callback is None:
            return
        for line in output_tail:
            if line in seen_lines:
                continue
            seen_lines.add(line)
            callback("remote", line)

    async def _cancel_remote_job(
        self,
        client: httpx.AsyncClient,
        job_id: str,
        log_callback: LogCallback | None = None,
    ) -> None:
        try:
            await client.delete(f"{self.api_url}/jobs/{job_id}", timeout=self.DELETE_TIMEOUT_SECONDS)
            if log_callback is not None:
                log_callback("remote", f"Requested remote Demucs cancellation for job {job_id}")
        except Exception as error:
            if log_callback is not None:
                log_callback("remote", f"Failed to request remote Demucs cancellation for job {job_id}: {error}")

    async def separate_vocals(
        self,
        audio_path: Path,
        *,
        output_dir: Path | None = None,
        lyrics_text: str | None = None,
        lyrics_format: str | None = None,
        transcription_model: str | None = None,
        align_language: str | None = None,
        detect_language: bool | None = None,
        use_synced_lyrics: bool | None = None,
        whisperx_preload_models: str | None = None,
        process_lyrics_lines: bool | None = None,
        max_line_length: int | None = None,
        max_line_length_cjk: int | None = None,
        compute_type: str | None = None,
        cancel_event: threading.Event | None = None,
        progress_callback: ProgressCallback | None = None,
        log_callback: LogCallback | None = None,
    ) -> DemucsResponse:
        if not audio_path.exists():
            raise RuntimeError(f"Audio path does not exist: {audio_path}")
        if cancel_event is not None and cancel_event.is_set():
            raise asyncio.CancelledError()

        out_dir = output_dir or settings.cache_path / "demucs_outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        seen_output_lines: set[str] = set()

        async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT_SECONDS) as client:
            with audio_path.open("rb") as fh:
                create_response = await client.post(
                    f"{self.api_url}/jobs",
                    files={"file": (audio_path.name, fh, "audio/wav")},
                    data=self._build_request_data(
                        lyrics_text=lyrics_text,
                        lyrics_format=lyrics_format,
                        transcription_model=transcription_model,
                        align_language=align_language,
                        detect_language=detect_language,
                        use_synced_lyrics=use_synced_lyrics,
                        whisperx_preload_models=whisperx_preload_models,
                        process_lyrics_lines=process_lyrics_lines,
                        max_line_length=max_line_length,
                        max_line_length_cjk=max_line_length_cjk,
                        compute_type=compute_type,
                    ),
                )
            create_response.raise_for_status()
            payload = create_response.json()
            job_id = payload["job_id"]
            self._emit_progress(
                progress_callback,
                int(payload.get("progress_percent", 0)),
                str(payload.get("progress_message") or "Queued"),
                {"job_id": job_id, "status": payload.get("status")},
            )
            if log_callback is not None:
                log_callback("remote", f"Started remote Demucs job {job_id}")

            remote_cancel_requested = False
            try:
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        await self._cancel_remote_job(client, job_id, log_callback)
                        remote_cancel_requested = True
                        raise asyncio.CancelledError()

                    status_response = await client.get(f"{self.api_url}/jobs/{job_id}")
                    status_response.raise_for_status()
                    status_payload = status_response.json()
                    self._emit_remote_log_lines(
                        log_callback,
                        status_payload.get("output_tail") or [],
                        seen_output_lines,
                    )
                    self._emit_progress(
                        progress_callback,
                        int(status_payload.get("progress_percent", 0)),
                        str(status_payload.get("progress_message") or "Running Demucs"),
                        {
                            "job_id": job_id,
                            "status": status_payload.get("status"),
                            "error_detail": status_payload.get("error_detail"),
                        },
                    )

                    status = str(status_payload.get("status"))
                    if status == "completed":
                        result_response = await client.get(f"{self.api_url}/jobs/{job_id}/result")
                        result_response.raise_for_status()
                        no_vocals_bytes, vocals_bytes, aligned_bytes, extension = self._extract_stems_zip(
                            result_response.content
                        )
                        output_path = out_dir / f"{audio_path.stem}_{job_id}_no_vocals.{extension}"
                        vocals_output_path = out_dir / f"{audio_path.stem}_{job_id}_vocals.{extension}"
                        output_path.write_bytes(no_vocals_bytes)
                        vocals_output_path.write_bytes(vocals_bytes)
                        aligned_output_path = None
                        if aligned_bytes is not None:
                            aligned_output_path = out_dir / f"{audio_path.stem}_{job_id}_aligned_lyrics.json"
                            aligned_output_path.write_bytes(aligned_bytes)
                        self._emit_progress(
                            progress_callback,
                            100,
                            str(status_payload.get("progress_message") or "Completed"),
                            {"job_id": job_id, "status": status},
                        )
                        return DemucsResponse(
                            job_id=job_id,
                            no_vocals_path=str(output_path),
                            vocals_path=str(vocals_output_path),
                            aligned_lyrics_path=str(aligned_output_path) if aligned_output_path else None,
                        )

                    if status == "failed":
                        raise RuntimeError(
                            status_payload.get("error_detail") or "Demucs job failed"
                        )
                    if status == "canceled":
                        raise asyncio.CancelledError()

                    poll_interval = (
                        self.poll_interval_seconds
                        if self.poll_interval_seconds is not None
                        else settings.demucs_poll_interval_seconds
                    )
                    await asyncio.sleep(poll_interval)
            except asyncio.CancelledError:
                if not remote_cancel_requested:
                    await self._cancel_remote_job(client, job_id, log_callback)
                raise
            except Exception:
                if cancel_event is not None and cancel_event.is_set() and not remote_cancel_requested:
                    await self._cancel_remote_job(client, job_id, log_callback)
                raise

    async def align_lyrics(
        self,
        vocals_path: Path,
        *,
        output_dir: Path | None = None,
        lyrics_text: str,
        lyrics_format: str | None = None,
        transcription_model: str | None = None,
        align_language: str | None = None,
        detect_language: bool | None = None,
        use_synced_lyrics: bool | None = None,
        whisperx_preload_models: str | None = None,
        process_lyrics_lines: bool | None = None,
        max_line_length: int | None = None,
        max_line_length_cjk: int | None = None,
        compute_type: str | None = None,
        cancel_event: threading.Event | None = None,
        progress_callback: ProgressCallback | None = None,
        log_callback: LogCallback | None = None,
    ) -> tuple[Path, str]:
        """Run WhisperX alignment against an existing vocals sidecar."""
        if not vocals_path.exists():
            raise RuntimeError(f"Vocals path does not exist: {vocals_path}")
        if not (lyrics_text or "").strip():
            raise RuntimeError("lyrics_text is required for alignment")
        if cancel_event is not None and cancel_event.is_set():
            raise asyncio.CancelledError()

        out_dir = output_dir or settings.cache_path / "demucs_outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        seen_output_lines: set[str] = set()

        async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT_SECONDS) as client:
            with vocals_path.open("rb") as fh:
                create_response = await client.post(
                    f"{self.api_url}/align-jobs",
                    files={"file": (vocals_path.name, fh, "audio/wav")},
                    data=self._build_request_data(
                        lyrics_text=lyrics_text,
                        lyrics_format=lyrics_format,
                        transcription_model=transcription_model,
                        align_language=align_language,
                        detect_language=detect_language,
                        use_synced_lyrics=use_synced_lyrics,
                        whisperx_preload_models=whisperx_preload_models,
                        process_lyrics_lines=process_lyrics_lines,
                        max_line_length=max_line_length,
                        max_line_length_cjk=max_line_length_cjk,
                        compute_type=compute_type,
                    ),
                )
            create_response.raise_for_status()
            payload = create_response.json()
            job_id = payload["job_id"]
            self._emit_progress(
                progress_callback,
                int(payload.get("progress_percent", 0)),
                str(payload.get("progress_message") or "Queued"),
                {"job_id": job_id, "status": payload.get("status")},
            )
            if log_callback is not None:
                log_callback("remote", f"Started remote WhisperX alignment job {job_id}")

            remote_cancel_requested = False
            try:
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        await self._cancel_remote_job(client, job_id, log_callback)
                        remote_cancel_requested = True
                        raise asyncio.CancelledError()

                    status_response = await client.get(f"{self.api_url}/jobs/{job_id}")
                    status_response.raise_for_status()
                    status_payload = status_response.json()
                    self._emit_remote_log_lines(
                        log_callback,
                        status_payload.get("output_tail") or [],
                        seen_output_lines,
                    )
                    self._emit_progress(
                        progress_callback,
                        int(status_payload.get("progress_percent", 0)),
                        str(status_payload.get("progress_message") or "Aligning lyrics"),
                        {
                            "job_id": job_id,
                            "status": status_payload.get("status"),
                            "error_detail": status_payload.get("error_detail"),
                        },
                    )

                    status = str(status_payload.get("status"))
                    if status == "completed":
                        result_response = await client.get(f"{self.api_url}/align-jobs/{job_id}/result")
                        result_response.raise_for_status()
                        aligned_output_path = out_dir / f"{vocals_path.stem}_{job_id}_aligned_lyrics.json"
                        aligned_output_path.write_bytes(result_response.content)
                        self._emit_progress(
                            progress_callback,
                            100,
                            str(status_payload.get("progress_message") or "Completed"),
                            {"job_id": job_id, "status": status},
                        )
                        return aligned_output_path, job_id

                    if status == "failed":
                        raise RuntimeError(
                            status_payload.get("error_detail") or "Lyrics alignment job failed"
                        )
                    if status == "canceled":
                        raise asyncio.CancelledError()

                    poll_interval = (
                        self.poll_interval_seconds
                        if self.poll_interval_seconds is not None
                        else settings.demucs_poll_interval_seconds
                    )
                    await asyncio.sleep(poll_interval)
            except asyncio.CancelledError:
                if not remote_cancel_requested:
                    await self._cancel_remote_job(client, job_id, log_callback)
                raise
            except Exception:
                if cancel_event is not None and cancel_event.is_set() and not remote_cancel_requested:
                    await self._cancel_remote_job(client, job_id, log_callback)
                raise

    def preload_whisperx_models(
        self,
        *,
        whisperx_preload_models: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
    ) -> WhisperXPreloadResponse:
        preload_value = whisperx_preload_models or settings.whisperx_preload_models
        if not preload_value or not preload_value.strip():
            raise RuntimeError("whisperx_preload_models cannot be empty")

        data = {
            "whisperx_preload_models": preload_value.strip(),
            "device": device or settings.demucs_device,
        }
        if compute_type:
            data["compute_type"] = compute_type

        response = httpx.post(
            f"{self.api_url}/whisperx/preload",
            data=data,
            timeout=self.PRELOAD_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return WhisperXPreloadResponse(**response.json())

    def health_check(self) -> DemucsHealthResponse:
        """Check if Demucs service is available and ready."""
        try:
            response = httpx.get(
                f"{self.api_url}/health", timeout=self.HEALTH_TIMEOUT_SECONDS
            )
            if response.status_code != 200:
                return DemucsHealthResponse(
                    api_url=self.api_url,
                    healthy=False,
                    detail=f"Health endpoint returned HTTP {response.status_code}",
                )

            payload = response.json()
            status = str(payload.get("status", "")).lower()
            if status in {"ok", "healthy"}:
                return DemucsHealthResponse(
                    api_url=self.api_url,
                    healthy=True,
                    detail="Demucs service is healthy",
                )

            detail = payload.get("detail") or payload.get("reason") or "Demucs not ready"
            return DemucsHealthResponse(
                api_url=self.api_url,
                healthy=False,
                detail=str(detail),
            )
        except httpx.TimeoutException:
            return DemucsHealthResponse(
                api_url=self.api_url,
                healthy=False,
                detail="Health check timed out",
            )
        except httpx.RequestError as error:
            return DemucsHealthResponse(
                api_url=self.api_url,
                healthy=False,
                detail=f"Cannot reach Demucs service: {error}",
            )
        except Exception as error:
            return DemucsHealthResponse(
                api_url=self.api_url,
                healthy=False,
                detail=f"Demucs health check failed: {error}",
            )

    def trigger_garbage_collection(
        self, *, mode: str = "adaptive"
    ) -> DemucsGarbageCollectionResponse:
        """Ask the remote Demucs service to reclaim memory."""
        response = httpx.post(
            f"{self.api_url}/gc",
            params={"mode": mode},
            timeout=self.GC_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        return DemucsGarbageCollectionResponse(**payload)

    def get_io_usage(self) -> DemucsIoUsageResponse:
        """Fetch the current remote Demucs IO footprint."""
        response = httpx.get(
            f"{self.api_url}/io",
            timeout=self.IO_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return DemucsIoUsageResponse(**response.json())

    def cleanup_io(self) -> DemucsIoCleanupResponse:
        """Delete all remote Demucs IO scratch files when no jobs are active."""
        response = httpx.delete(
            f"{self.api_url}/io",
            timeout=self.IO_CLEANUP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return DemucsIoCleanupResponse(**response.json())

    def delete_job_artifacts(self, job_id: str) -> None:
        """Delete remote job input/output artifacts after local success is durable."""
        response = httpx.delete(
            f"{self.api_url}/jobs/{job_id}/artifacts",
            timeout=self.DELETE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
