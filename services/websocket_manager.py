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
    
    async def broadcast_current_item_changed(self, current_id: int, previous_id: int = None):
        """Broadcast when the currently playing item changes."""
        await self.broadcast({
            "type": "current_item_changed",
            "data": {
                "id": current_id,
                "previous_id": previous_id
            },
            "timestamp": datetime.utcnow().isoformat()
        })
    
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
    
    def get_connection_count(self) -> int:
        """Get the number of active connections."""
        return len(self.active_connections)


# Global instance
manager = ConnectionManager()
