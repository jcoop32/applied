
import asyncio
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class TaskManager:
    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}

    def register_task(self, task_id: str, task: asyncio.Task):
        """Register a task to be tracked."""
        self._tasks[str(task_id)] = task
        # Remove from dict when done to prevent memory leak
        task.add_done_callback(lambda t: self._cleanup(str(task_id)))

    def _cleanup(self, task_id: str):
        if task_id in self._tasks:
            del self._tasks[task_id]

    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancels a running task by ID.
        Returns True if cancelled, False if not found.
        """
        task_id = str(task_id)
        if task_id in self._tasks:
            task = self._tasks[task_id]
            if not task.done():
                logger.info(f"Cancelling task {task_id}")
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                return True
        return False

# Global Instance
task_manager = TaskManager()
