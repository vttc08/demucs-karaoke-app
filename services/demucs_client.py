"""Demucs API client for vocal separation."""
from __future__ import annotations

import asyncio
import json
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
    STREAM_CONNECT_TIMEOUT_SECONDS = 15.0
    DELETE_TIMEOUT_SECONDS = 30.0

    def __init__(
        self,
        api_url: str = None,
        api_key: str | None = None,
        poll_interval_seconds: float | None = None,
    ):
        self.api_url = api_url or settings.demucs_api_url
        self.api_key = (settings.demucs_api_key if api_key is None else api_key).strip()
        self.poll_interval_seconds = poll_interval_seconds

    def _auth_headers(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        return {"X-API-Key": self.api_key}

    def _request_headers_kwargs(self) -> dict[str, dict[str, str]]:
        headers = self._auth_headers()
        return {"headers": headers} if headers else {}

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
            "separation_backend": settings.separation_backend,
            "sherpa_spleeter_model": settings.sherpa_spleeter_model,
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
    def _progress_metadata(job_id: str, payload: dict, *, status: str | None = None) -> dict:
        return {
            "job_id": job_id,
            "status": status if status is not None else payload.get("status"),
            "error_detail": payload.get("error_detail"),
            "progress_stage": payload.get("progress_stage"),
            "progress_mode": payload.get("progress_mode"),
            "separation_backend": payload.get("separation_backend"),
            "effective_device": payload.get("effective_device"),
        }

    async def _ensure_backend_capability(self, client: httpx.AsyncClient) -> None:
        if settings.separation_backend == "demucs":
            return
        response = await client.get(
            f"{self.api_url}/health",
            params={
                "separation_backend": settings.separation_backend,
                "sherpa_spleeter_model": settings.sherpa_spleeter_model,
            },
            **self._request_headers_kwargs(),
        )
        response.raise_for_status()
        payload = response.json()
        supported = payload.get("supported_backends") or []
        if settings.separation_backend not in supported:
            raise RuntimeError(
                "Remote separation service does not advertise Sherpa+Spleeter support"
            )
        if str(payload.get("status", "")).lower() not in {"ok", "healthy"}:
            raise RuntimeError(
                str(payload.get("detail") or "Selected separation backend is not ready")
            )

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
            await client.delete(
                f"{self.api_url}/jobs/{job_id}",
                timeout=self.DELETE_TIMEOUT_SECONDS,
                **self._request_headers_kwargs(),
            )
            if log_callback is not None:
                log_callback(
                    "remote",
                    f"Requested remote Demucs cancellation for job {job_id}",
                )
        except Exception as error:
            if log_callback is not None:
                log_callback(
                    "remote",
                    f"Failed to request remote Demucs cancellation for job {job_id}: {error}",
                )

    def _stream_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.STREAM_CONNECT_TIMEOUT_SECONDS,
            read=None,
            write=self.REQUEST_TIMEOUT_SECONDS,
            pool=self.REQUEST_TIMEOUT_SECONDS,
        )

    def _job_events_url(self, job_id: str) -> str:
        return f"{self.api_url}/jobs/{job_id}/events"

    def _job_status_url(self, job_id: str) -> str:
        return f"{self.api_url}/jobs/{job_id}"

    def _job_result_url(self, job_id: str) -> str:
        return f"{self.api_url}/jobs/{job_id}/result"

    def _align_job_result_url(self, job_id: str) -> str:
        return f"{self.api_url}/align-jobs/{job_id}/result"

    async def _poll_remote_job(
        self,
        client: httpx.AsyncClient,
        *,
        job_id: str,
        output_tail_seen: set[str],
        progress_callback: ProgressCallback | None,
        log_callback: LogCallback | None,
        cancel_event: threading.Event | None,
        running_message: str,
        result_fetch_url: str,
        out_dir: Path,
        audio_path: Path,
        final_completed_message: str,
        terminal_statuses: set[str],
    ) -> DemucsResponse | tuple[Path, str]:
        poll_interval = (
            self.poll_interval_seconds
            if self.poll_interval_seconds is not None
            else settings.demucs_poll_interval_seconds
        )

        while True:
            if cancel_event is not None and cancel_event.is_set():
                await self._cancel_remote_job(client, job_id, log_callback)
                raise asyncio.CancelledError()

            status_response = await client.get(
                self._job_status_url(job_id),
                **self._request_headers_kwargs(),
            )
            status_response.raise_for_status()
            status_payload = status_response.json()
            self._emit_remote_log_lines(
                log_callback,
                status_payload.get("output_tail") or [],
                output_tail_seen,
            )
            status = str(status_payload.get("status"))
            self._emit_progress(
                progress_callback,
                int(status_payload.get("progress_percent", 0)),
                str(status_payload.get("progress_message") or running_message),
                self._progress_metadata(job_id, status_payload, status=status),
            )

            if status == "completed":
                result_response = await client.get(
                    result_fetch_url,
                    **self._request_headers_kwargs(),
                )
                result_response.raise_for_status()
                if result_fetch_url.endswith("/result") and "/align-jobs/" not in result_fetch_url:
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
                        final_completed_message,
                        {
                            "job_id": job_id,
                            "status": status,
                            "progress_stage": "completed",
                            "progress_mode": "determinate",
                        },
                    )
                    return DemucsResponse(
                        job_id=job_id,
                        no_vocals_path=str(output_path),
                        vocals_path=str(vocals_output_path),
                        aligned_lyrics_path=str(aligned_output_path) if aligned_output_path else None,
                    )

                aligned_output_path = out_dir / f"{audio_path.stem}_{job_id}_aligned_lyrics.json"
                aligned_output_path.write_bytes(result_response.content)
                self._emit_progress(
                    progress_callback,
                    100,
                    final_completed_message,
                    {
                        "job_id": job_id,
                        "status": status,
                        "progress_stage": "completed",
                        "progress_mode": "determinate",
                    },
                )
                return aligned_output_path, job_id

            if status == "failed":
                raise RuntimeError(status_payload.get("error_detail") or "Remote Demucs job failed")
            if status == "canceled":
                raise asyncio.CancelledError()

            await asyncio.sleep(poll_interval)

    async def _stream_remote_job(
        self,
        client: httpx.AsyncClient,
        *,
        job_id: str,
        output_tail_seen: set[str],
        progress_callback: ProgressCallback | None,
        log_callback: LogCallback | None,
        cancel_event: threading.Event | None,
        running_message: str,
        result_fetch_url: str,
        out_dir: Path,
        audio_path: Path,
        final_completed_message: str,
        terminal_statuses: set[str],
    ) -> DemucsResponse | tuple[Path, str] | None:
        last_event_id = 0
        reconnect_attempts = 0
        max_reconnect_attempts = 3

        while True:
            if cancel_event is not None and cancel_event.is_set():
                await self._cancel_remote_job(client, job_id, log_callback)
                raise asyncio.CancelledError()

            headers = self._request_headers_kwargs().get("headers", {}).copy()
            if last_event_id:
                headers["Last-Event-ID"] = str(last_event_id)

            try:
                async with client.stream(
                    "GET",
                    self._job_events_url(job_id),
                    headers=headers,
                    timeout=self._stream_timeout(),
                ) as response:
                    if response.status_code == 404:
                        return None
                    if response.status_code in {405, 406}:
                        return None
                    if response.status_code >= 400:
                        response.raise_for_status()

                    event_type: str | None = None
                    event_id: int | None = None
                    data_lines: list[str] = []

                    async for line in response.aiter_lines():
                        if cancel_event is not None and cancel_event.is_set():
                            await self._cancel_remote_job(client, job_id, log_callback)
                            raise asyncio.CancelledError()
                        if not line:
                            if event_type == "job" and data_lines:
                                payload = json.loads("\n".join(data_lines))
                                event_id = int(payload.get("sequence") or event_id or 0)
                                if event_id:
                                    last_event_id = event_id
                                self._emit_remote_log_lines(
                                    log_callback,
                                    payload.get("output_tail") or [],
                                    output_tail_seen,
                                )
                                status = str(payload.get("status"))
                                self._emit_progress(
                                    progress_callback,
                                    int(payload.get("progress_percent", 0)),
                                    str(payload.get("progress_message") or running_message),
                                    self._progress_metadata(job_id, payload, status=status),
                                )
                                if status == "completed":
                                    result_response = await client.get(
                                        result_fetch_url,
                                        **self._request_headers_kwargs(),
                                    )
                                    result_response.raise_for_status()
                                    if result_fetch_url.endswith("/result") and "/align-jobs/" not in result_fetch_url:
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
                                            final_completed_message,
                                            {
                                                "job_id": job_id,
                                                "status": status,
                                                "progress_stage": "completed",
                                                "progress_mode": "determinate",
                                            },
                                        )
                                        return DemucsResponse(
                                            job_id=job_id,
                                            no_vocals_path=str(output_path),
                                            vocals_path=str(vocals_output_path),
                                            aligned_lyrics_path=str(aligned_output_path) if aligned_output_path else None,
                                        )

                                    aligned_output_path = out_dir / f"{audio_path.stem}_{job_id}_aligned_lyrics.json"
                                    aligned_output_path.write_bytes(result_response.content)
                                    self._emit_progress(
                                        progress_callback,
                                        100,
                                        final_completed_message,
                                        {
                                            "job_id": job_id,
                                            "status": status,
                                            "progress_stage": "completed",
                                            "progress_mode": "determinate",
                                        },
                                    )
                                    return aligned_output_path, job_id
                                if status == "failed":
                                    raise RuntimeError(
                                        payload.get("error_detail") or "Remote Demucs job failed"
                                    )
                                if status == "canceled":
                                    raise asyncio.CancelledError()

                            event_type = None
                            event_id = None
                            data_lines = []
                            continue

                        if line.startswith(":"):
                            continue
                        if line.startswith("event:"):
                            event_type = line.split(":", 1)[1].strip()
                            continue
                        if line.startswith("id:"):
                            raw_event_id = line.split(":", 1)[1].strip()
                            try:
                                event_id = int(raw_event_id)
                            except ValueError:
                                event_id = None
                            continue
                        if line.startswith("data:"):
                            data_lines.append(line.split(":", 1)[1].lstrip())

                    reconnect_attempts = 0
                    if last_event_id:
                        continue
                    return None
            except httpx.HTTPError:
                reconnect_attempts += 1
                if reconnect_attempts >= max_reconnect_attempts:
                    return None
                await asyncio.sleep(min(5.0, float(2 ** (reconnect_attempts - 1))))

    async def _run_remote_job(
        self,
        *,
        audio_path: Path,
        endpoint: str,
        result_url_builder: Callable[[str], str],
        out_dir: Path,
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
        running_message: str,
        final_completed_message: str,
        terminal_statuses: set[str],
    ) -> DemucsResponse | tuple[Path, str]:
        if not audio_path.exists():
            raise RuntimeError(f"Audio path does not exist: {audio_path}")
        if cancel_event is not None and cancel_event.is_set():
            raise asyncio.CancelledError()

        seen_output_lines: set[str] = set()

        async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT_SECONDS) as client:
            if endpoint == f"{self.api_url}/jobs":
                await self._ensure_backend_capability(client)
            with audio_path.open("rb") as fh:
                create_response = await client.post(
                    endpoint,
                    files={"file": (audio_path.name, fh, "audio/wav")},
                    **self._request_headers_kwargs(),
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
                self._progress_metadata(job_id, payload),
            )
            if log_callback is not None:
                log_callback("remote", f"Started remote separation job {job_id}")

            try:
                result_fetch_url = result_url_builder(job_id)
                streamed_result = await self._stream_remote_job(
                    client,
                    job_id=job_id,
                    output_tail_seen=seen_output_lines,
                    progress_callback=progress_callback,
                    log_callback=log_callback,
                    cancel_event=cancel_event,
                    running_message=running_message,
                    result_fetch_url=result_fetch_url,
                    out_dir=out_dir,
                    audio_path=audio_path,
                    final_completed_message=final_completed_message,
                    terminal_statuses=terminal_statuses,
                )
                if streamed_result is not None:
                    return streamed_result
            except asyncio.CancelledError:
                raise
            except Exception:
                if cancel_event is not None and cancel_event.is_set():
                    await self._cancel_remote_job(client, job_id, log_callback)
                raise

            return await self._poll_remote_job(
                client,
                job_id=job_id,
                output_tail_seen=seen_output_lines,
                progress_callback=progress_callback,
                log_callback=log_callback,
                cancel_event=cancel_event,
                running_message=running_message,
                result_fetch_url=result_fetch_url,
                out_dir=out_dir,
                audio_path=audio_path,
                final_completed_message=final_completed_message,
                terminal_statuses=terminal_statuses,
            )

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
        out_dir = output_dir or settings.cache_path / "demucs_outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        return await self._run_remote_job(
            audio_path=audio_path,
            endpoint=f"{self.api_url}/jobs",
            result_url_builder=self._job_result_url,
            out_dir=out_dir,
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
            cancel_event=cancel_event,
            progress_callback=progress_callback,
            log_callback=log_callback,
            running_message="Separating vocals",
            final_completed_message="Completed",
            terminal_statuses={"completed", "failed", "canceled"},
        )

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
        return await self._run_remote_job(
            audio_path=vocals_path,
            endpoint=f"{self.api_url}/align-jobs",
            result_url_builder=self._align_job_result_url,
            out_dir=out_dir,
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
            cancel_event=cancel_event,
            progress_callback=progress_callback,
            log_callback=log_callback,
            running_message="Aligning lyrics",
            final_completed_message="Completed",
            terminal_statuses={"completed", "failed", "canceled"},
        )

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
            **self._request_headers_kwargs(),
            timeout=self.PRELOAD_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return WhisperXPreloadResponse(**response.json())

    def health_check(
        self,
        *,
        separation_backend: str | None = None,
        sherpa_spleeter_model: str | None = None,
    ) -> DemucsHealthResponse:
        """Check if the selected separation backend is available and ready."""
        try:
            selected_backend = separation_backend or settings.separation_backend
            selected_model = sherpa_spleeter_model or settings.sherpa_spleeter_model
            request_kwargs = self._request_headers_kwargs()
            if selected_backend != "demucs":
                request_kwargs["params"] = {
                    "separation_backend": selected_backend,
                    "sherpa_spleeter_model": selected_model,
                }
            response = httpx.get(
                f"{self.api_url}/health",
                **request_kwargs,
                timeout=self.HEALTH_TIMEOUT_SECONDS,
            )
            if response.status_code != 200:
                return DemucsHealthResponse(
                    api_url=self.api_url,
                    healthy=False,
                    detail=f"Health endpoint returned HTTP {response.status_code}",
                )

            payload = response.json()
            status = str(payload.get("status", "")).lower()
            supported_backends = payload.get("supported_backends") or ["demucs"]
            selected_backend_payload = payload.get("selected_backend") or selected_backend
            if selected_backend not in supported_backends:
                return DemucsHealthResponse(
                    api_url=self.api_url,
                    healthy=False,
                    detail=f"Remote service does not support {selected_backend}",
                    supported_backends=supported_backends,
                    selected_backend=selected_backend_payload,
                )
            if status in {"ok", "healthy"}:
                return DemucsHealthResponse(
                    api_url=self.api_url,
                    healthy=True,
                    detail=f"{selected_backend} backend is healthy",
                    supported_backends=supported_backends,
                    selected_backend=selected_backend_payload,
                )

            detail = payload.get("detail") or payload.get("reason") or "Demucs not ready"
            return DemucsHealthResponse(
                api_url=self.api_url,
                healthy=False,
                detail=str(detail),
                supported_backends=supported_backends,
                selected_backend=selected_backend_payload,
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
            **self._request_headers_kwargs(),
            timeout=self.GC_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        return DemucsGarbageCollectionResponse(**payload)

    def get_io_usage(self) -> DemucsIoUsageResponse:
        """Fetch the current remote Demucs IO footprint."""
        response = httpx.get(
            f"{self.api_url}/io",
            **self._request_headers_kwargs(),
            timeout=self.IO_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return DemucsIoUsageResponse(**response.json())

    def cleanup_io(self) -> DemucsIoCleanupResponse:
        """Delete all remote Demucs IO scratch files when no jobs are active."""
        response = httpx.delete(
            f"{self.api_url}/io",
            **self._request_headers_kwargs(),
            timeout=self.IO_CLEANUP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return DemucsIoCleanupResponse(**response.json())

    def delete_job_artifacts(self, job_id: str) -> None:
        """Delete remote job input/output artifacts after local success is durable."""
        response = httpx.delete(
            f"{self.api_url}/jobs/{job_id}/artifacts",
            **self._request_headers_kwargs(),
            timeout=self.DELETE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
