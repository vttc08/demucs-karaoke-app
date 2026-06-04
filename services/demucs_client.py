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
from models import DemucsHealthResponse, DemucsResponse


ProgressCallback = Callable[[int, str, dict | None], None]
LogCallback = Callable[[str, str], None]


class DemucsClient:
    """Client for Demucs vocal separation service."""

    HEALTH_TIMEOUT_SECONDS = 5.0
    REQUEST_TIMEOUT_SECONDS = 600.0
    POLL_INTERVAL_SECONDS = 0.75

    def __init__(self, api_url: str = None):
        self.api_url = api_url or settings.demucs_api_url

    @staticmethod
    def _extract_stems_zip(payload: bytes) -> tuple[bytes, bytes, str]:
        with zipfile.ZipFile(BytesIO(payload), mode="r") as archive:
            names = set(archive.namelist())
            no_vocals_name = next((name for name in names if name.startswith("no_vocals.")), None)
            vocals_name = next((name for name in names if name.startswith("vocals.")), None)
            if not no_vocals_name or not vocals_name:
                raise RuntimeError("Demucs ZIP payload missing no_vocals or vocals file")

            extension = Path(no_vocals_name).suffix.lstrip(".").lower() or "wav"
            no_vocals_bytes = archive.read(no_vocals_name)
            vocals_bytes = archive.read(vocals_name)
            return no_vocals_bytes, vocals_bytes, extension

    def _build_request_data(self) -> dict[str, str]:
        data = {
            "model": settings.demucs_model,
            "device": settings.demucs_device,
            "output_format": settings.demucs_output_format,
        }
        if settings.demucs_output_format == "mp3":
            data["mp3_bitrate"] = str(settings.demucs_mp3_bitrate)
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

    async def separate_vocals(
        self,
        audio_path: Path,
        *,
        cancel_event: threading.Event | None = None,
        progress_callback: ProgressCallback | None = None,
        log_callback: LogCallback | None = None,
    ) -> DemucsResponse:
        if not audio_path.exists():
            raise RuntimeError(f"Audio path does not exist: {audio_path}")
        if cancel_event is not None and cancel_event.is_set():
            raise asyncio.CancelledError()

        out_dir = settings.cache_path / "demucs_outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        seen_output_lines: set[str] = set()

        async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT_SECONDS) as client:
            with audio_path.open("rb") as fh:
                create_response = await client.post(
                    f"{self.api_url}/jobs",
                    files={"file": (audio_path.name, fh, "audio/wav")},
                    data=self._build_request_data(),
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

            try:
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        await client.delete(f"{self.api_url}/jobs/{job_id}")
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
                        no_vocals_bytes, vocals_bytes, extension = self._extract_stems_zip(result_response.content)
                        output_path = out_dir / f"{audio_path.stem}_{job_id}_no_vocals.{extension}"
                        vocals_output_path = out_dir / f"{audio_path.stem}_{job_id}_vocals.{extension}"
                        output_path.write_bytes(no_vocals_bytes)
                        vocals_output_path.write_bytes(vocals_bytes)
                        self._emit_progress(
                            progress_callback,
                            100,
                            str(status_payload.get("progress_message") or "Completed"),
                            {"job_id": job_id, "status": status},
                        )
                        return DemucsResponse(
                            no_vocals_path=str(output_path),
                            vocals_path=str(vocals_output_path),
                        )

                    if status == "failed":
                        raise RuntimeError(
                            status_payload.get("error_detail") or "Demucs job failed"
                        )
                    if status == "canceled":
                        raise asyncio.CancelledError()

                    await asyncio.sleep(self.POLL_INTERVAL_SECONDS)
            except Exception:
                if cancel_event is not None and cancel_event.is_set():
                    try:
                        await client.delete(f"{self.api_url}/jobs/{job_id}")
                    except Exception:
                        pass
                raise

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
