"""In-memory live task stream state for SSE reconnect support."""
from __future__ import annotations

import asyncio
from collections import deque
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any


def utc_now() -> datetime:
    """Return timezone-aware UTC timestamp for stream payloads."""
    return datetime.now(timezone.utc)


class TaskStreamManager:
    """Retain live task snapshots and recent events in memory."""

    TERMINAL_STATUSES = {"done", "failed"}

    def __init__(
        self,
        *,
        per_task_buffer: int = 200,
        done_ttl_seconds: int = 60,
        failed_ttl_seconds: int = 900,
    ):
        self._per_task_buffer = per_task_buffer
        self._done_ttl = timedelta(seconds=done_ttl_seconds)
        self._failed_ttl = timedelta(seconds=failed_ttl_seconds)
        self._state: dict[int, dict[str, Any]] = {}
        self._events: dict[int, deque[dict[str, Any]]] = {}
        self._summary_subscribers: set[asyncio.Queue] = set()
        self._task_subscribers: dict[int, set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def ensure_task(self, task_id: int, *, status: str | None = None, stage: str | None = None):
        """Ensure a task exists in in-memory state."""
        async with self._lock:
            self._prune_expired_locked()
            state = self._state.setdefault(
                task_id,
                {
                    "task_id": task_id,
                    "status": status,
                    "stage": stage,
                    "progress_percent": None,
                    "progress_label": None,
                    "progress_label_key": None,
                    "progress_label_args": None,
                    "progress_step_index": None,
                    "progress_step_total": None,
                    "event_sequence": 0,
                    "event_count": 0,
                    "updated_at": utc_now(),
                    "expires_at": None,
                },
            )
            if status is not None:
                state["status"] = status
            if stage is not None:
                state["stage"] = stage
            if status not in self.TERMINAL_STATUSES:
                state["expires_at"] = None
            self._events.setdefault(task_id, deque(maxlen=self._per_task_buffer))
            return self._public_state_copy(state)

    async def clear_task(self, task_id: int):
        """Drop completed task live state from memory."""
        async with self._lock:
            self._state.pop(task_id, None)
            self._events.pop(task_id, None)
            self._task_subscribers.pop(task_id, None)

    async def snapshot(self, task_id: int) -> dict[str, Any] | None:
        """Return the latest live snapshot for one task."""
        async with self._lock:
            self._prune_expired_locked()
            state = self._state.get(task_id)
            return self._public_state_copy(state) if state else None

    def snapshot_now(self, task_id: int) -> dict[str, Any] | None:
        """Return the latest snapshot without awaiting, for sync response mappers."""
        state = self._state.get(task_id)
        if state is None or self._is_expired_state(state):
            return None
        return self._public_state_copy(state) if state else None

    async def recent_events(self, task_id: int) -> list[dict[str, Any]]:
        """Return buffered events for one task."""
        async with self._lock:
            self._prune_expired_locked()
            events = self._events.get(task_id, deque())
            return [deepcopy(event) for event in events]

    async def active_summaries(self) -> list[dict[str, Any]]:
        """Return all active task snapshots."""
        async with self._lock:
            self._prune_expired_locked()
            return [self._public_state_copy(state) for state in self._state.values()]

    def active_summaries_now(self) -> list[dict[str, Any]]:
        """Return active summaries without awaiting, for sync callers."""
        return [
            self._public_state_copy(state)
            for state in self._state.values()
            if not self._is_expired_state(state)
        ]

    async def register_summary_subscriber(self) -> asyncio.Queue:
        """Register a queue for summary events."""
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._prune_expired_locked()
            self._summary_subscribers.add(queue)
        return queue

    async def unregister_summary_subscriber(self, queue: asyncio.Queue):
        """Remove a summary subscriber."""
        async with self._lock:
            self._summary_subscribers.discard(queue)

    async def register_task_subscriber(self, task_id: int) -> asyncio.Queue:
        """Register a queue for per-task events."""
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._prune_expired_locked()
            subscribers = self._task_subscribers.setdefault(task_id, set())
            subscribers.add(queue)
        return queue

    async def unregister_task_subscriber(self, task_id: int, queue: asyncio.Queue):
        """Remove a task subscriber."""
        async with self._lock:
            subscribers = self._task_subscribers.get(task_id)
            if not subscribers:
                return
            subscribers.discard(queue)
            if not subscribers:
                self._task_subscribers.pop(task_id, None)

    async def publish(
        self,
        task_id: int,
        *,
        event_type: str,
        status: str | None = None,
        stage: str | None = None,
        progress_percent: int | None = None,
        progress_label: str | None = None,
        progress_label_key: str | None = None,
        progress_label_args: dict[str, Any] | None = None,
        progress_step_index: int | None = None,
        progress_step_total: int | None = None,
        message: str | None = None,
        stream: str | None = None,
    ) -> dict[str, Any]:
        """Publish a live task event and update current snapshot."""
        async with self._lock:
            state = self._state.setdefault(
                task_id,
                {
                    "task_id": task_id,
                    "status": status,
                    "stage": stage,
                    "progress_percent": None,
                    "progress_label": None,
                    "progress_label_key": None,
                    "progress_label_args": None,
                    "progress_step_index": None,
                    "progress_step_total": None,
                    "event_sequence": 0,
                    "event_count": 0,
                    "updated_at": utc_now(),
                    "expires_at": None,
                },
            )
            if status is not None:
                state["status"] = status
            if stage is not None:
                state["stage"] = stage
            if progress_percent is not None:
                state["progress_percent"] = progress_percent
            if progress_label is not None:
                state["progress_label"] = progress_label
            if progress_label_key is not None:
                state["progress_label_key"] = progress_label_key
            if progress_label_args is not None:
                state["progress_label_args"] = deepcopy(progress_label_args)
            if progress_step_index is not None:
                state["progress_step_index"] = progress_step_index
            if progress_step_total is not None:
                state["progress_step_total"] = progress_step_total
            if status not in self.TERMINAL_STATUSES:
                state["expires_at"] = None

            state["event_sequence"] += 1
            state["event_count"] += 1
            state["updated_at"] = utc_now()

            payload = {
                "task_id": task_id,
                "event_type": event_type,
                "status": state.get("status"),
                "stage": state.get("stage"),
                "progress_percent": state.get("progress_percent"),
                "progress_label": state.get("progress_label"),
                "progress_label_key": state.get("progress_label_key"),
                "progress_label_args": deepcopy(state.get("progress_label_args")),
                "progress_step_index": state.get("progress_step_index"),
                "progress_step_total": state.get("progress_step_total"),
                "message": message,
                "stream": stream,
                "sequence": state["event_sequence"],
                "timestamp": state["updated_at"],
            }
            events = self._events.setdefault(task_id, deque(maxlen=self._per_task_buffer))
            events.append(deepcopy(payload))

            summary_subscribers = list(self._summary_subscribers)
            task_subscribers = list(self._task_subscribers.get(task_id, set()))

        for queue in summary_subscribers:
            await queue.put(deepcopy(payload))
        for queue in task_subscribers:
            await queue.put(deepcopy(payload))
        return payload

    async def mark_task_terminal(self, task_id: int, *, status: str):
        """Set an expiry time for terminal task live state."""
        async with self._lock:
            self._prune_expired_locked()
            state = self._state.get(task_id)
            if state is None:
                return
            state["expires_at"] = self._expiry_for_status(status, state.get("updated_at") or utc_now())

    def _expiry_for_status(self, status: str, base_time: datetime) -> datetime | None:
        if status == "done":
            return base_time + self._done_ttl
        if status == "failed":
            return base_time + self._failed_ttl
        return None

    @staticmethod
    def _public_state_copy(state: dict[str, Any]) -> dict[str, Any]:
        return deepcopy({key: value for key, value in state.items() if key != "expires_at"})

    def _is_expired_state(self, state: dict[str, Any], now: datetime | None = None) -> bool:
        expires_at = state.get("expires_at")
        if expires_at is None:
            return False
        current = now or utc_now()
        return expires_at <= current

    def _prune_expired_locked(self):
        now = utc_now()
        expired_task_ids = [
            task_id
            for task_id, state in self._state.items()
            if self._is_expired_state(state, now)
        ]
        for task_id in expired_task_ids:
            self._state.pop(task_id, None)
            self._events.pop(task_id, None)
            self._task_subscribers.pop(task_id, None)


task_stream_manager = TaskStreamManager()
