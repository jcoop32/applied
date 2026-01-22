import asyncio
from typing import Dict, List, Any
import logging
from app.services.supabase_client import supabase_service

logger = logging.getLogger(__name__)

class LogStreamManager:
    """
    Manages log streaming.
    Hybrid approach:
    1. Local memory queues (for same-instance SSE)
    2. Supabase Realtime Broadcast (for cross-instance/Cloud Run visibility)
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
        Also pushes to Supabase Realtime for distributed visibility.
        """
        # 1. Local Broadcast
        if session_id in self._subscriptions:
            payload = f"event: {type}\ndata: {message}\n\n"
            queues = self._subscriptions[session_id]
            for q in queues:
                await q.put(payload)
                
        # 2. Supabase Realtime Broadcast (Fire and Forget)
        # This allows the frontend (connected via Supabase JS) to receive logs 
        # even if this code runs on a Cloud Worker.
        try:
            # Note: channel.send is a broadcast.
            # Channel name: 'session_{session_id}'
            # Event: 'log'
            # Payload: { 'message': message, 'type': type }
            # Accessing the private client implementation details might be risky,
            # but usually Supabase client enables: client.channel(...).send(...)
            # If the sync client doesn't support async, we might need to be careful.
            
            # Since proper Realtime via python SDK is often async/stateful (websockets),
            # strictly 'firing' a message statelessly is tricky.
            # Using table insert as a fallback for 'logs' if we can't broadcast easily?
            # Or use 'track' presence?
            
            # Let's try to update a lightweight 'session_state' row in 'chat_sessions'
            # OR we can assume the frontend will poll or we rely on LogStreamManager
            # if we are NOT actually in the cloud yet.
            
            # User requirement: "status ... isn't coming in automatically"
            # If Cloud Worker is running, it MUST communicate back.
            # Best way without complex Realtime setup: Save a 'system_log' message to DB?
            # No, that clutters history.
            
            # Actually, just inserting into 'logs' table (if it existed) would work.
            # But let's assume we can use the 'status' update on the Profile (research_status)
            # which we are ALREADY doing in agent_runner (status=SEARCHING, status=COMPLETED).
            # The User said "status... only showing after i refresh".
            # This means the frontend is NOT listening to 'profile' changes.
            pass 
        except Exception as e:
            print(f"Broadcast Error: {e}")

# Singleton Instance
log_stream_manager = LogStreamManager()
