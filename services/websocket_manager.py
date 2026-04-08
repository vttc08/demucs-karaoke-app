"""WebSocket connection manager for real-time queue updates."""
import asyncio
import logging
from typing import List
from fastapi import WebSocket
from datetime import datetime

logger = logging.getLogger(__name__)

class ConnectionManager:
    """Manages WebSocket connections and broadcasts queue updates."""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()
        self._stage_state = {
            "is_paused": False,
            "vocals_enabled": True,
            "vocals_volume": 1.0,
            "lyrics_enabled": True,
        }
    
    async def connect(self, websocket: WebSocket):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    async def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection from active connections."""
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send a message to a specific connection."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
            await self.disconnect(websocket)
    
    async def broadcast(self, message: dict):
        """Broadcast a message to all active connections."""
        if not self.active_connections:
            logger.debug("No active connections to broadcast to")
            return
        
        logger.debug(f"Broadcasting to {len(self.active_connections)} connections: {message.get('type')}")
        
        # Create a copy of connections to avoid modification during iteration
        async with self._lock:
            connections = self.active_connections.copy()
        
        # Track failed connections to remove
        failed_connections = []
        
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send message to connection: {e}")
                failed_connections.append(connection)
        
        # Remove failed connections
        if failed_connections:
            async with self._lock:
                for connection in failed_connections:
                    if connection in self.active_connections:
                        self.active_connections.remove(connection)
            logger.info(f"Removed {len(failed_connections)} failed connections")
    
    async def broadcast_queue_item_added(self, item_data: dict):
        """Broadcast when a new item is added to the queue."""
        await self.broadcast({
            "type": "queue_item_added",
            "data": item_data,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    async def broadcast_queue_item_updated(self, item_data: dict):
        """Broadcast when a queue item's status or data is updated."""
        await self.broadcast({
            "type": "queue_item_updated",
            "data": item_data,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    async def broadcast_queue_item_removed(self, item_id: int):
        """Broadcast when a queue item is removed."""
        await self.broadcast({
            "type": "queue_item_removed",
            "data": {"id": item_id},
            "timestamp": datetime.utcnow().isoformat()
        })
    
    async def broadcast_queue_cleared(self):
        """Broadcast when the queue is cleared."""
        await self.broadcast({
            "type": "queue_cleared",
            "data": {},
            "timestamp": datetime.utcnow().isoformat()
        })
    
    async def broadcast_current_item_changed(self, current_id: int | None, previous_id: int | None = None):
        """Broadcast when the currently playing item changes."""
        await self.broadcast({
            "type": "current_item_changed",
            "data": {
                "id": current_id,
                "previous_id": previous_id
            },
            "timestamp": datetime.utcnow().isoformat()
        })
        await self.reset_stage_state(source="queue")
    
    async def broadcast_queue_item_failed(self, item_id: int, error: str):
        """Broadcast when a queue item fails."""
        await self.broadcast({
            "type": "queue_item_failed",
            "data": {
                "id": item_id,
                "error": error
            },
            "timestamp": datetime.utcnow().isoformat()
        })

    async def broadcast_stage_control_command(
        self,
        command: str,
        source: str = "unknown",
        extra_data: dict | None = None,
    ):
        """Broadcast a stage control command to all connected clients."""
        payload = {
            "command": command,
            "source": source,
        }
        if extra_data:
            payload.update(extra_data)
        await self.broadcast({
            "type": "stage_control_command",
            "data": payload,
            "timestamp": datetime.utcnow().isoformat()
        })

    async def broadcast_stage_state_update(self, source: str = "unknown"):
        """Broadcast stage playback + mix state update to all connected clients."""
        state = self.get_stage_state()
        await self.broadcast({
            "type": "stage_state_update",
            "data": {
                "is_paused": state["is_paused"],
                "vocals_enabled": state["vocals_enabled"],
                "vocals_volume": state["vocals_volume"],
                "lyrics_enabled": state["lyrics_enabled"],
                "source": source,
            },
            "timestamp": datetime.utcnow().isoformat()
        })

    def get_stage_state(self) -> dict:
        """Return a copy of current in-memory stage state."""
        return dict(self._stage_state)

    async def set_stage_paused(self, is_paused: bool, source: str = "unknown"):
        """Set paused flag and broadcast full stage state."""
        self._stage_state["is_paused"] = bool(is_paused)
        await self.broadcast_stage_state_update(source=source)

    async def set_stage_vocals_enabled(self, vocals_enabled: bool, source: str = "unknown"):
        """Set vocals enabled flag and broadcast full stage state."""
        self._stage_state["vocals_enabled"] = bool(vocals_enabled)
        await self.broadcast_stage_state_update(source=source)

    async def set_stage_vocals_volume(self, vocals_volume: float, source: str = "unknown"):
        """Set vocals volume (0..1) and broadcast full stage state."""
        clamped = max(0.0, min(1.0, float(vocals_volume)))
        self._stage_state["vocals_volume"] = clamped
        await self.broadcast_stage_state_update(source=source)

    async def set_stage_lyrics_enabled(self, lyrics_enabled: bool, source: str = "unknown"):
        """Set lyrics overlay visibility and broadcast full stage state."""
        self._stage_state["lyrics_enabled"] = bool(lyrics_enabled)
        await self.broadcast_stage_state_update(source=source)

    async def reset_stage_state(self, source: str = "unknown"):
        """Reset stage state defaults for a newly playing item."""
        self._stage_state["is_paused"] = False
        self._stage_state["vocals_enabled"] = True
        self._stage_state["vocals_volume"] = 1.0
        self._stage_state["lyrics_enabled"] = True
        await self.broadcast_stage_state_update(source=source)
    
    def get_connection_count(self) -> int:
        """Get the number of active connections."""
        return len(self.active_connections)


# Global instance
manager = ConnectionManager()
