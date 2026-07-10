from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


class SeparationCanceled(Exception):
    """Raised when a separation provider observes a canceled job."""


@dataclass(frozen=True)
class SeparationRequest:
    job_id: str
    input_path: Path
    output_dir: Path
    model: str
    requested_device: str
    output_format: str
    mp3_bitrate: int | None


@dataclass(frozen=True)
class SeparationResult:
    no_vocals_path: Path
    vocals_path: Path
    separation_backend: str
    separation_model: str
    effective_device: str


@dataclass(frozen=True)
class SeparationRuntime:
    set_process: Callable[[object | None], None]
    append_output: Callable[[str], None]
    emit_progress: Callable[[int | None, str | None, str, str], None]
    is_canceled: Callable[[], bool]
    terminate_process: Callable[[object], None]


class SeparationProvider(Protocol):
    name: str

    def readiness(self, model: str) -> dict[str, object]: ...

    def separate(
        self,
        request: SeparationRequest,
        runtime: SeparationRuntime,
    ) -> SeparationResult: ...
