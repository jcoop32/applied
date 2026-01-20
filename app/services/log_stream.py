import asyncio
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)

class LogStreamManager:
    """
    Manages in-memory subscriptions for real-time agent logs (SSE).
    Assumes single-instance deployment (Cloud Run with session affinity or sticky sessions).
    For multi-instance scaling, this would need a Redis backend.
    """
    def __init__(self):
        # Maps session_id -> List of active queues
        self._subscriptions: Dict[str, List[asyncio.Queue]] = {}

    async def subscribe(self, session_id: str):
        """
        Creates a new subscription queue for a given session.
        Returns an async generator that yields messages.
        """
        queue = asyncio.Queue()
        if session_id not in self._subscriptions:
            self._subscriptions[session_id] = []
        
        self._subscriptions[session_id].append(queue)
        
        try:
            while True:
                # Wait for message
                message = await queue.get()
                yield message
                queue.task_done()
        except asyncio.CancelledError:
            # Cleanup on disconnect
            print(f"🔌 Client disconnected from stream {session_id}")
        finally:
            if session_id in self._subscriptions:
                self._subscriptions[session_id].remove(queue)
                if not self._subscriptions[session_id]:
                    del self._subscriptions[session_id]

    async def broadcast(self, session_id: str, message: str, type: str = "log"):
        """
        Broadcasts a message to all connected clients for a session.
        """
        if session_id not in self._subscriptions:
            return

        payload = f"event: {type}\ndata: {message}\n\n"
        
        queues = self._subscriptions[session_id]
        for q in queues:
            await q.put(payload)

# Singleton Instance
log_stream_manager = LogStreamManager()
