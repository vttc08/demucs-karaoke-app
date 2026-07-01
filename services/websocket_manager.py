"""WebSocket connection manager for real-time queue and presence updates."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

from config import settings

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections, queue events, and live queue presence."""

    QUEUE_EVENT_ROLES = frozenset({"queue", "stage"})
    STAGE_STATE_ROLES = frozenset({"queue", "stage", "lyrics_viewer"})
    STAGE_CLOCK_ROLES = frozenset({"lyrics_viewer"})

    def __init__(self):
        self.active_connections: list[Any] = []
        self._lock = asyncio.Lock()
        self._connection_context: dict[Any, dict[str, Any]] = {}
        self._queue_presence: dict[str, dict[str, Any]] = {}
        self._stage_presence: dict[str, dict[str, Any]] = {}
        self._stage_state = {
            "is_paused": False,
            "vocals_enabled": True,
            "vocals_volume": settings.stage_vocals_volume_default,
            "lyrics_enabled": True,
            "current_time": 0.0,
        }
        self._sync_version = 0

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    async def connect(self, websocket: WebSocket):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        now = self._timestamp()
        async with self._lock:
            self.active_connections.append(websocket)
            self._connection_context[websocket] = {
                "connected_at": now,
                "last_seen_at": now,
                "last_ping_at": None,
                "last_pong_at": now,
            }
        logger.info("WebSocket connected total_connections=%s", len(self.active_connections))

    async def disconnect(self, websocket: Any):
        """Remove a WebSocket connection and update live presence state."""
        left_payload = None
        notify_clock_subscribers = False
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

            context = self._connection_context.pop(websocket, None)
            notify_clock_subscribers = context is not None and context.get("role") == "lyrics_viewer"
            if context and context.get("page") == "queue":
                guest_id = context.get("guest_id")
                tab_id = context.get("tab_id")
                if guest_id and tab_id:
                    presence = self._queue_presence.get(guest_id)
                    if presence:
                        presence["tab_ids"].discard(tab_id)
                        if not presence["tab_ids"]:
                            self._queue_presence.pop(guest_id, None)
                            left_payload = {"guest_id": guest_id}
            if context and context.get("page") == "stage":
                stage_id = context.get("stage_id")
                if stage_id:
                    presence = self._stage_presence.get(stage_id)
                    if presence:
                        presence["connections"].discard(websocket)
                        if not presence["connections"]:
                            self._stage_presence.pop(stage_id, None)

        logger.info(
            "WebSocket disconnected total_connections=%s", len(self.active_connections)
        )
        if left_payload:
            await self.broadcast_queue_presence_event("user_left", left_payload)
        if context and context.get("page") == "stage":
            await self.broadcast_stage_presence_snapshot()
        if notify_clock_subscribers:
            await self.broadcast_stage_clock_subscribers_update()

    async def send_personal_message(self, message: dict, websocket: Any):
        """Send a message to a specific connection."""
        try:
            await websocket.send_json(message)
        except Exception:
            logger.exception("Failed personal websocket send")
            await self.disconnect(websocket)

    async def touch_connection(self, websocket: Any):
        """Refresh the activity timestamp for one connection."""
        async with self._lock:
            context = self._connection_context.get(websocket)
            if context is None:
                return
            context["last_seen_at"] = self._timestamp()

    async def mark_connection_ping(self, websocket: Any):
        """Record the last heartbeat ping sent to one connection."""
        async with self._lock:
            context = self._connection_context.get(websocket)
            if context is None:
                return
            context["last_ping_at"] = self._timestamp()

    async def mark_connection_pong(self, websocket: Any):
        """Record the last heartbeat pong received from one connection."""
        async with self._lock:
            context = self._connection_context.get(websocket)
            if context is None:
                return
            now = self._timestamp()
            context["last_pong_at"] = now
            context["last_seen_at"] = now

    async def is_connection_stale(
        self,
        websocket: Any,
        *,
        heartbeat_interval_seconds: float,
        grace_seconds: float = 5.0,
    ) -> bool:
        """Return whether a connection has missed enough heartbeats to be evicted."""
        async with self._lock:
            context = self._connection_context.get(websocket)
            if context is None:
                return False
            last_seen_at = context.get("last_seen_at")
        if last_seen_at is None:
            return False
        try:
            last_seen = datetime.fromisoformat(last_seen_at)
        except ValueError:
            return False
        age_seconds = (datetime.now(timezone.utc) - last_seen).total_seconds()
        stale_after_seconds = max(0.0, float(heartbeat_interval_seconds)) * 2 + max(0.0, float(grace_seconds))
        return age_seconds > stale_after_seconds

    async def broadcast(self, message: dict):
        """Broadcast a message to all active connections."""
        await self._broadcast_to_connections(message, None)

    async def _broadcast_to_connections(
        self, message: dict, connections: list[Any] | None
    ):
        async with self._lock:
            targets = (
                self.active_connections.copy()
                if connections is None
                else [connection for connection in connections if connection in self.active_connections]
            )

        if not targets:
            return

        failed_connections = []
        for connection in targets:
            try:
                await connection.send_json(message)
            except Exception:
                logger.warning(
                    "Failed websocket broadcast message_type=%s",
                    message.get("type"),
                )
                failed_connections.append(connection)

        for connection in failed_connections:
            await self.disconnect(connection)

    async def _get_queue_connections(self, exclude: Any | None = None) -> list[Any]:
        async with self._lock:
            return [
                connection
                for connection in self.active_connections
                if connection is not exclude
                and self._connection_context.get(connection, {}).get("page") == "queue"
            ]

    async def _get_connections_by_roles(
        self,
        roles: set[str] | frozenset[str],
        *,
        exclude: Any | None = None,
    ) -> list[Any]:
        async with self._lock:
            return [
                connection
                for connection in self.active_connections
                if connection is not exclude
                and self._connection_context.get(connection, {}).get("role") in roles
            ]

    async def set_connection_role(self, websocket: Any, role: str):
        """Assign a logical websocket role used for targeted broadcasts."""
        notify_clock_subscribers = False
        async with self._lock:
            context = self._connection_context.get(websocket, {}).copy()
            previous_role = context.get("role")
            context["role"] = role
            self._connection_context[websocket] = context
            notify_clock_subscribers = (
                previous_role != role
                and (previous_role == "lyrics_viewer" or role == "lyrics_viewer")
            )

        if role == "stage":
            await self.send_stage_clock_subscribers_update(websocket)
        if notify_clock_subscribers:
            await self.broadcast_stage_clock_subscribers_update()

    async def get_stage_clock_subscriber_count(self) -> int:
        """Return the number of connected clients that need live playback clock ticks."""
        async with self._lock:
            return sum(
                1
                for connection in self.active_connections
                if self._connection_context.get(connection, {}).get("role") == "lyrics_viewer"
            )

    async def _stage_clock_subscribers_payload(self) -> dict[str, Any]:
        count = await self.get_stage_clock_subscriber_count()
        return {
            "lyrics_viewer_count": count,
            "clock_enabled": count > 0,
        }

    async def send_stage_clock_subscribers_update(self, websocket: Any):
        """Send live clock demand state to one stage client."""
        await self.send_personal_message(
            {
                "type": "stage_clock_subscribers_update",
                "data": await self._stage_clock_subscribers_payload(),
                "timestamp": self._timestamp(),
            },
            websocket,
        )

    async def broadcast_stage_clock_subscribers_update(self):
        """Tell stage clients whether any lyrics viewer currently needs clock ticks."""
        targets = await self._get_connections_by_roles({"stage"})
        await self._broadcast_to_connections(
            {
                "type": "stage_clock_subscribers_update",
                "data": await self._stage_clock_subscribers_payload(),
                "timestamp": self._timestamp(),
            },
            targets,
        )

    def get_stage_presence_snapshot(self) -> list[dict[str, Any]]:
        """Return a stable snapshot of active stage displays."""
        displays = [
            {
                "stage_id": stage_id,
                "stage_name": presence["stage_name"],
                "connected_at": presence["connected_at"],
                "last_seen": presence["last_seen"],
                "connection_count": len(presence["connections"]),
            }
            for stage_id, presence in self._stage_presence.items()
        ]
        displays.sort(key=lambda item: (item["stage_name"].lower(), item["stage_id"]))
        return displays

    async def register_stage_presence(
        self,
        websocket: Any,
        *,
        stage_id: str,
        stage_name: str,
    ):
        """Register or refresh a connected stage display."""
        now = self._timestamp()
        async with self._lock:
            self._connection_context[websocket] = {
                "page": "stage",
                "role": "stage",
                "stage_id": stage_id,
                "connected_at": now,
                "last_seen_at": now,
                "last_ping_at": None,
                "last_pong_at": now,
            }
            existing = self._stage_presence.get(stage_id)
            if existing is None:
                self._stage_presence[stage_id] = {
                    "stage_name": stage_name,
                    "connected_at": now,
                    "last_seen": now,
                    "connections": {websocket},
                }
            else:
                existing["stage_name"] = stage_name or existing["stage_name"]
                existing["last_seen"] = self._timestamp()
                existing["connections"].add(websocket)

        await self.broadcast_stage_presence_snapshot()

    async def send_stage_presence_snapshot(self, websocket: Any):
        """Send the current stage display snapshot to one websocket client."""
        await self.send_personal_message(
            {
                "type": "stage_presence_snapshot",
                "data": {"stages": self.get_stage_presence_snapshot()},
                "timestamp": self._timestamp(),
            },
            websocket,
        )

    async def broadcast_stage_presence_snapshot(self):
        """Broadcast active stage display state to queue-page clients."""
        targets = await self._get_connections_by_roles({"queue"})
        await self._broadcast_to_connections(
            {
                "type": "stage_presence_snapshot",
                "data": {"stages": self.get_stage_presence_snapshot()},
                "timestamp": self._timestamp(),
            },
            targets,
        )

    def has_stage_display(self, stage_id: str) -> bool:
        """Return whether a stage display id is currently connected."""
        return stage_id in self._stage_presence

    def get_queue_presence_snapshot(self) -> list[dict[str, Any]]:
        """Return a stable snapshot of active queue viewers."""
        users = [
            {
                "guest_id": guest_id,
                "display_name": presence["display_name"],
                "joined_at": presence["joined_at"],
                "connection_count": len(presence["tab_ids"]),
            }
            for guest_id, presence in self._queue_presence.items()
        ]
        users.sort(key=lambda item: (item["joined_at"], item["display_name"], item["guest_id"]))
        return users

    def _build_presence_payload(self, guest_id: str) -> dict[str, Any] | None:
        """Build a single-presence payload for websocket events."""
        presence = self._queue_presence.get(guest_id)
        if presence is None:
            return None
        return {
            "guest_id": guest_id,
            "display_name": presence["display_name"],
            "joined_at": presence["joined_at"],
            "connection_count": len(presence["tab_ids"]),
        }

    async def register_queue_presence(
        self,
        websocket: Any,
        *,
        guest_id: str,
        display_name: str,
        tab_id: str,
    ):
        """Register or refresh queue-page presence for a websocket connection."""
        join_payload = None
        update_payload = None
        now = self._timestamp()
        async with self._lock:
            self._connection_context[websocket] = {
                "page": "queue",
                "role": "queue",
                "guest_id": guest_id,
                "tab_id": tab_id,
                "connected_at": now,
                "last_seen_at": now,
                "last_ping_at": None,
                "last_pong_at": now,
            }

            existing = self._queue_presence.get(guest_id)
            if existing is None:
                self._queue_presence[guest_id] = {
                    "display_name": display_name,
                    "joined_at": now,
                    "tab_ids": {tab_id},
                }
                join_payload = self._build_presence_payload(guest_id)
            else:
                name_changed = bool(display_name) and display_name != existing["display_name"]
                existing["display_name"] = display_name or existing["display_name"]
                existing["tab_ids"].add(tab_id)
                if name_changed:
                    update_payload = self._build_presence_payload(guest_id)
            snapshot = self.get_queue_presence_snapshot()

        await self.send_personal_message(
            {
                "type": "presence_snapshot",
                "data": {"users": snapshot},
                "timestamp": self._timestamp(),
            },
            websocket,
        )

        if join_payload:
            await self.broadcast_queue_presence_event(
                "user_joined", join_payload, exclude=websocket
            )
        elif update_payload:
            await self.broadcast_queue_presence_event(
                "user_updated", update_payload, exclude=websocket
            )

    async def update_queue_presence(
        self,
        websocket: Any,
        *,
        guest_id: str,
        display_name: str,
        tab_id: str,
    ):
        """Update queue presence display name after a local rename."""
        update_payload = None
        async with self._lock:
            presence = self._queue_presence.get(guest_id)
            if presence is None:
                self._connection_context[websocket] = {
                    "page": "queue",
                    "role": "queue",
                    "guest_id": guest_id,
                    "tab_id": tab_id,
                    "connected_at": self._timestamp(),
                    "last_seen_at": self._timestamp(),
                    "last_ping_at": None,
                    "last_pong_at": self._timestamp(),
                }
            else:
                self._connection_context[websocket] = {
                    "page": "queue",
                    "role": "queue",
                    "guest_id": guest_id,
                    "tab_id": tab_id,
                    "connected_at": self._timestamp(),
                    "last_seen_at": self._timestamp(),
                    "last_ping_at": None,
                    "last_pong_at": self._timestamp(),
                }
                presence["tab_ids"].add(tab_id)
                presence["display_name"] = display_name or presence["display_name"]
                update_payload = self._build_presence_payload(guest_id)
        if presence is None:
            await self.register_queue_presence(
                websocket,
                guest_id=guest_id,
                display_name=display_name,
                tab_id=tab_id,
            )
            return

        await self.send_personal_message(
            {
                "type": "presence_snapshot",
                "data": {"users": self.get_queue_presence_snapshot()},
                "timestamp": self._timestamp(),
            },
            websocket,
        )
        if update_payload:
            await self.broadcast_queue_presence_event("user_updated", update_payload)

    async def broadcast_queue_presence_event(
        self, event_type: str, payload: dict[str, Any], exclude: Any | None = None
    ):
        """Broadcast presence events to queue-page clients only."""
        targets = await self._get_queue_connections(exclude=exclude)
        await self._broadcast_to_connections(
            {
                "type": event_type,
                "data": payload,
                "timestamp": self._timestamp(),
            },
            targets,
        )

    async def broadcast_queue_item_added(self, item_data: dict):
        """Broadcast when a new item is added to the queue."""
        targets = await self._get_connections_by_roles(self.QUEUE_EVENT_ROLES)
        await self._broadcast_to_connections(
            {
                "type": "queue_item_added",
                "data": item_data,
                "timestamp": self._timestamp(),
            },
            targets,
        )

    async def broadcast_queue_item_updated(self, item_data: dict):
        """Broadcast when a queue item's status or data is updated."""
        targets = await self._get_connections_by_roles(self.QUEUE_EVENT_ROLES)
        await self._broadcast_to_connections(
            {
                "type": "queue_item_updated",
                "data": item_data,
                "timestamp": self._timestamp(),
            },
            targets,
        )

    async def broadcast_queue_item_progress(self, item_data: dict):
        """Broadcast lightweight live progress for queue items."""
        targets = await self._get_connections_by_roles({"queue"})
        await self._broadcast_to_connections(
            {
                "type": "queue_item_progress",
                "data": item_data,
                "timestamp": self._timestamp(),
            },
            targets,
        )

    async def broadcast_queue_item_removed(self, item_id: int):
        """Broadcast when a queue item is removed."""
        targets = await self._get_connections_by_roles(self.QUEUE_EVENT_ROLES)
        await self._broadcast_to_connections(
            {
                "type": "queue_item_removed",
                "data": {"id": item_id},
                "timestamp": self._timestamp(),
            },
            targets,
        )

    async def broadcast_queue_cleared(self):
        """Broadcast when the queue is cleared."""
        targets = await self._get_connections_by_roles(self.QUEUE_EVENT_ROLES)
        await self._broadcast_to_connections(
            {"type": "queue_cleared", "data": {}, "timestamp": self._timestamp()},
            targets,
        )

    async def broadcast_current_item_changed(
        self, current_id: int | None, previous_id: int | None = None
    ):
        """Broadcast when the currently playing item changes."""
        targets = await self._get_connections_by_roles(self.STAGE_STATE_ROLES)
        await self._broadcast_to_connections(
            {
                "type": "current_item_changed",
                "data": {"id": current_id, "previous_id": previous_id},
                "timestamp": self._timestamp(),
            },
            targets,
        )
        await self.reset_stage_state(source="queue")

    async def broadcast_queue_item_failed(self, item_id: int, error: str):
        """Broadcast when a queue item fails."""
        targets = await self._get_connections_by_roles(self.QUEUE_EVENT_ROLES)
        await self._broadcast_to_connections(
            {
                "type": "queue_item_failed",
                "data": {"id": item_id, "error": error},
                "timestamp": self._timestamp(),
            },
            targets,
        )

    async def broadcast_stage_control_command(
        self,
        command: str,
        source: str = "unknown",
        extra_data: dict | None = None,
        target_stage_id: str | None = None,
    ):
        """Broadcast a stage control command to all or one connected stage display."""
        payload = {"command": command, "source": source}
        if extra_data:
            payload.update(extra_data)
        if target_stage_id:
            async with self._lock:
                targets = [
                    connection
                    for connection in self.active_connections
                    if self._connection_context.get(connection, {}).get("role") == "stage"
                    and self._connection_context.get(connection, {}).get("stage_id") == target_stage_id
                ]
        else:
            targets = await self._get_connections_by_roles(self.STAGE_STATE_ROLES)
        await self._broadcast_to_connections(
            {
                "type": "stage_control_command",
                "data": payload,
                "timestamp": self._timestamp(),
            },
            targets,
        )

    async def broadcast_lyrics_settings_ack(self, payload: dict[str, Any]):
        """Forward a stage lyrics settings acknowledgement to queue clients."""
        targets = await self._get_connections_by_roles({"queue"})
        await self._broadcast_to_connections(
            {
                "type": "lyrics_settings_ack",
                "data": payload,
                "timestamp": self._timestamp(),
            },
            targets,
        )

    async def broadcast_stage_state_update(self, source: str = "unknown"):
        """Broadcast stage playback + mix state update to all connected clients."""
        state = self.get_stage_state()
        targets = await self._get_connections_by_roles(self.STAGE_STATE_ROLES)
        await self._broadcast_to_connections(
            {
                "type": "stage_state_update",
                "data": {
                    "is_paused": state["is_paused"],
                    "vocals_enabled": state["vocals_enabled"],
                    "vocals_volume": state["vocals_volume"],
                    "lyrics_enabled": state["lyrics_enabled"],
                    "current_time": state["current_time"],
                    "source": source,
                },
                "timestamp": self._timestamp(),
            },
            targets,
        )

    async def broadcast_stage_time_update(self, source: str = "unknown"):
        """Broadcast the authoritative playback clock to lyrics viewers."""
        state = self.get_stage_state()
        targets = await self._get_connections_by_roles(self.STAGE_CLOCK_ROLES)
        await self._broadcast_to_connections(
            {
                "type": "stage_time_update",
                "data": {
                    "current_time": state["current_time"],
                    "is_paused": state["is_paused"],
                    "source": source,
                },
                "timestamp": self._timestamp(),
            },
            targets,
        )

    def get_stage_state(self) -> dict:
        """Return a copy of current in-memory stage state."""
        state = dict(self._stage_state)
        state["sync_version"] = self._sync_version
        return state

    def next_stage_sync_version(self) -> int:
        """Return the next monotonic resync version for client-side de-duplication."""
        self._sync_version += 1
        return self._sync_version

    async def set_stage_paused(self, is_paused: bool, source: str = "unknown"):
        """Set paused flag and broadcast full stage state."""
        self._stage_state["is_paused"] = bool(is_paused)
        await self.broadcast_stage_state_update(source=source)

    async def set_stage_current_time(
        self,
        current_time: float,
        source: str = "unknown",
        is_paused: bool | None = None,
        broadcast_state: bool = False,
    ):
        """Set the current playback timestamp and broadcast clock or full state."""
        self._stage_state["current_time"] = max(0.0, float(current_time))
        if isinstance(is_paused, bool):
            self._stage_state["is_paused"] = is_paused
        if broadcast_state:
            await self.broadcast_stage_state_update(source=source)
        else:
            await self.broadcast_stage_time_update(source=source)

    async def set_stage_vocals_enabled(
        self, vocals_enabled: bool, source: str = "unknown"
    ):
        """Set vocals enabled flag and broadcast full stage state."""
        self._stage_state["vocals_enabled"] = bool(vocals_enabled)
        await self.broadcast_stage_state_update(source=source)

    async def set_stage_vocals_volume(
        self, vocals_volume: float, source: str = "unknown"
    ):
        """Set vocals volume (0..1) and broadcast full stage state."""
        clamped = max(0.0, min(1.0, float(vocals_volume)))
        self._stage_state["vocals_volume"] = clamped
        await self.broadcast_stage_state_update(source=source)

    async def set_stage_lyrics_enabled(
        self, lyrics_enabled: bool, source: str = "unknown"
    ):
        """Set lyrics overlay visibility and broadcast full stage state."""
        self._stage_state["lyrics_enabled"] = bool(lyrics_enabled)
        await self.broadcast_stage_state_update(source=source)

    async def reset_stage_state(self, source: str = "unknown"):
        """Reset per-item playback state while preserving user mix preferences."""
        self._stage_state["is_paused"] = False
        self._stage_state["current_time"] = 0.0
        await self.broadcast_stage_state_update(source=source)

    def get_connection_count(self) -> int:
        """Get the number of active connections."""
        return len(self.active_connections)


manager = ConnectionManager()
