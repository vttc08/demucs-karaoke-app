"""In-memory live task stream state for SSE reconnect support."""
from __future__ import annotations

import asyncio
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    """Return timezone-aware UTC timestamp for stream payloads."""
    return datetime.now(timezone.utc)


class TaskStreamManager:
    """Retain live task snapshots and recent events in memory."""

    def __init__(self, *, per_task_buffer: int = 200):
        self._per_task_buffer = per_task_buffer
        self._state: dict[int, dict[str, Any]] = {}
        self._events: dict[int, deque[dict[str, Any]]] = {}
        self._summary_subscribers: set[asyncio.Queue] = set()
        self._task_subscribers: dict[int, set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def ensure_task(self, task_id: int, *, status: str | None = None, stage: str | None = None):
        """Ensure a task exists in in-memory state."""
        async with self._lock:
            state = self._state.setdefault(
                task_id,
                {
                    "task_id": task_id,
                    "status": status,
                    "stage": stage,
                    "progress_percent": None,
                    "progress_label": None,
                    "event_sequence": 0,
                    "event_count": 0,
                    "updated_at": utc_now(),
                },
            )
            if status is not None:
                state["status"] = status
            if stage is not None:
                state["stage"] = stage
            self._events.setdefault(task_id, deque(maxlen=self._per_task_buffer))
            return deepcopy(state)

    async def clear_task(self, task_id: int):
        """Drop completed task live state from memory."""
        async with self._lock:
            self._state.pop(task_id, None)
            self._events.pop(task_id, None)
            self._task_subscribers.pop(task_id, None)

    async def snapshot(self, task_id: int) -> dict[str, Any] | None:
        """Return the latest live snapshot for one task."""
        async with self._lock:
            state = self._state.get(task_id)
            return deepcopy(state) if state else None

    def snapshot_now(self, task_id: int) -> dict[str, Any] | None:
        """Return the latest snapshot without awaiting, for sync response mappers."""
        state = self._state.get(task_id)
        return deepcopy(state) if state else None

    async def recent_events(self, task_id: int) -> list[dict[str, Any]]:
        """Return buffered events for one task."""
        async with self._lock:
            events = self._events.get(task_id, deque())
            return [deepcopy(event) for event in events]

    async def active_summaries(self) -> list[dict[str, Any]]:
        """Return all active task snapshots."""
        async with self._lock:
            return [deepcopy(state) for state in self._state.values()]

    def active_summaries_now(self) -> list[dict[str, Any]]:
        """Return active summaries without awaiting, for sync callers."""
        return [deepcopy(state) for state in self._state.values()]

    async def register_summary_subscriber(self) -> asyncio.Queue:
        """Register a queue for summary events."""
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
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
                    "event_sequence": 0,
                    "event_count": 0,
                    "updated_at": utc_now(),
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


task_stream_manager = TaskStreamManager()
