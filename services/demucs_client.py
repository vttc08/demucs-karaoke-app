"""Demucs API client for vocal separation."""
from pathlib import Path
import httpx

from config import settings
from models import DemucsHealthResponse, DemucsResponse


class DemucsClient:
    """Client for Demucs vocal separation service."""
    HEALTH_TIMEOUT_SECONDS = 2.0

    def __init__(self, api_url: str = None):
        self.api_url = api_url or settings.demucs_api_url

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
                response = await client.post(
                    f"{self.api_url}/separate",
                    files={"file": (audio_path.name, fh, "audio/wav")},
                )
            response.raise_for_status()

            job_id = response.headers.get("X-Job-Id", "unknown")
            output_path = out_dir / f"{audio_path.stem}_{job_id}_no_vocals.wav"
            output_path.write_bytes(response.content)

            vocals_path = response.headers.get("X-Vocals-Path")
            return DemucsResponse(
                no_vocals_path=str(output_path),
                vocals_path=vocals_path,
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
