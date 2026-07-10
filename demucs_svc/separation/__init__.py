from __future__ import annotations

from .base import (
    SeparationCanceled,
    SeparationProvider,
    SeparationRequest,
    SeparationResult,
    SeparationRuntime,
)
from .demucs import DemucsProvider
from .sherpa_spleeter import SherpaSpleeterProvider


def create_provider(
    backend: str,
    *,
    sherpa_model_root,
    sherpa_num_threads: int,
    sherpa_ffmpeg_path: str,
) -> SeparationProvider:
    if backend == "demucs":
        return DemucsProvider()
    if backend == "sherpa_spleeter":
        return SherpaSpleeterProvider(
            model_root=sherpa_model_root,
            num_threads=sherpa_num_threads,
            ffmpeg_path=sherpa_ffmpeg_path,
        )
    raise ValueError(f"Unsupported separation backend: {backend}")


__all__ = [
    "SeparationCanceled",
    "SeparationRequest",
    "SeparationResult",
    "SeparationRuntime",
    "create_provider",
]
