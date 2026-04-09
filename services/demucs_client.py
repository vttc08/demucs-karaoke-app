"""Demucs API client for vocal separation."""
from pathlib import Path
from io import BytesIO
import zipfile
import httpx

from config import settings
from models import DemucsHealthResponse, DemucsResponse


class DemucsClient:
    """Client for Demucs vocal separation service."""
    HEALTH_TIMEOUT_SECONDS = 2.0

    def __init__(self, api_url: str = None):
        self.api_url = api_url or settings.demucs_api_url

    @staticmethod
    def _extract_stems_zip(payload: bytes) -> tuple[bytes, bytes, str]:
        """Extract no_vocals and vocals bytes + extension from service ZIP payload."""
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

    async def separate_vocals(self, audio_path: Path) -> DemucsResponse:
        """
        Send audio to Demucs service for vocal separation.

        Args:
            audio_path: Path to audio file

        Returns:
            Response with paths to separated audio files
        """
        if not audio_path.exists():
            raise RuntimeError(f"Audio path does not exist: {audio_path}")

        out_dir = settings.cache_path / "demucs_outputs"
        out_dir.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient(timeout=600.0) as client:
            with audio_path.open("rb") as fh:
                data = {
                    "model": settings.demucs_model,
                    "device": settings.demucs_device,
                    "output_format": settings.demucs_output_format,
                }
                if settings.demucs_output_format == "mp3":
                    data["mp3_bitrate"] = str(settings.demucs_mp3_bitrate)
                response = await client.post(
                    f"{self.api_url}/separate",
                    files={"file": (audio_path.name, fh, "audio/wav")},
                    data=data,
                )
            response.raise_for_status()

            job_id = response.headers.get("X-Job-Id", "unknown")
            response_format = response.headers.get("X-Response-Format", "").lower()
            output_format = response.headers.get("X-Output-Format", "wav").lower()
            extension = "mp3" if output_format == "mp3" else "wav"
            output_path = out_dir / f"{audio_path.stem}_{job_id}_no_vocals.{extension}"
            vocals_output_path = out_dir / f"{audio_path.stem}_{job_id}_vocals.{extension}"

            if response_format == "zip" or response.headers.get("content-type", "").startswith("application/zip"):
                no_vocals_bytes, vocals_bytes, extension = self._extract_stems_zip(response.content)
                output_path = out_dir / f"{audio_path.stem}_{job_id}_no_vocals.{extension}"
                vocals_output_path = out_dir / f"{audio_path.stem}_{job_id}_vocals.{extension}"
                output_path.write_bytes(no_vocals_bytes)
                vocals_output_path.write_bytes(vocals_bytes)
            else:
                output_path.write_bytes(response.content)
                vocals_header_path = response.headers.get("X-Vocals-Path")
                vocals_output_path = Path(vocals_header_path) if vocals_header_path else None

            return DemucsResponse(
                no_vocals_path=str(output_path),
                vocals_path=(str(vocals_output_path) if vocals_output_path else None),
            )

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
