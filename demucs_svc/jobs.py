from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Condition, RLock
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class DemucsJobState:
    job_id: str
    model: str
    device: str
    output_format: str
    mp3_bitrate: int | None
    original_filename: str
    job_kind: str = "separation"
    status: str = "queued"
    progress_percent: int = 0
    progress_message: str = "Queued"
    error_detail: str | None = None
    duration_ms: int | None = None
    no_vocals_path: str | None = None
    vocals_path: str | None = None
    aligned_lyrics_path: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime = field(default_factory=utc_now)
    sequence: int = 0
    output_tail: deque[str] = field(default_factory=deque)
    cancel_requested: bool = False
    process: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "progress_percent": self.progress_percent,
            "progress_message": self.progress_message,
            "error_detail": self.error_detail,
            "duration_ms": self.duration_ms,
            "model": self.model,
            "device": self.device,
            "output_format": self.output_format,
            "mp3_bitrate": self.mp3_bitrate,
            "original_filename": self.original_filename,
            "job_kind": self.job_kind,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "updated_at": self.updated_at,
            "sequence": self.sequence,
            "output_tail": list(self.output_tail),
            "cancel_requested": self.cancel_requested,
            "no_vocals_path": self.no_vocals_path,
            "vocals_path": self.vocals_path,
            "aligned_lyrics_path": self.aligned_lyrics_path,
        }


class DemucsJobStore:
    def __init__(self, *, tail_limit: int):
        self._tail_limit = tail_limit
        self._jobs: dict[str, DemucsJobState] = {}
        self._lock = RLock()
        self._condition = Condition(self._lock)

    def create(self, job: DemucsJobState) -> DemucsJobState:
        with self._lock:
            job.output_tail = deque(maxlen=self._tail_limit)
            job.sequence = max(1, int(job.sequence))
            job.updated_at = utc_now()
            self._jobs[job.job_id] = job
            self._condition.notify_all()
            return job

    def get(self, job_id: str) -> DemucsJobState | None:
        with self._lock:
            return self._jobs.get(job_id)

    def require(self, job_id: str) -> DemucsJobState:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return job

    def update(self, job_id: str, **changes: Any) -> DemucsJobState:
        with self._lock:
            job = self.require(job_id)
            for key, value in changes.items():
                setattr(job, key, value)
            job.sequence += 1
            job.updated_at = utc_now()
            self._condition.notify_all()
            return job

    def append_output(self, job_id: str, line: str) -> DemucsJobState:
        with self._lock:
            job = self.require(job_id)
            job.output_tail.append(line)
            job.sequence += 1
            job.updated_at = utc_now()
            self._condition.notify_all()
            return job

    def all(self) -> list[DemucsJobState]:
        with self._lock:
            return list(self._jobs.values())

    def delete(self, job_id: str) -> DemucsJobState | None:
        with self._lock:
            job = self._jobs.pop(job_id, None)
            if job is not None:
                self._condition.notify_all()
            return job

    def wait_for_update(
        self,
        job_id: str,
        after_sequence: int,
        timeout_seconds: float | None = None,
    ) -> tuple[DemucsJobState | None, bool, bool]:
        with self._condition:
            job = self._jobs.get(job_id)
            if job is None:
                return None, False, True
            if job.sequence > after_sequence:
                return job, True, False

            self._condition.wait(timeout_seconds)

            job = self._jobs.get(job_id)
            if job is None:
                return None, False, True
            if job.sequence > after_sequence:
                return job, True, False
            return job, False, False
