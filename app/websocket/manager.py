from fastapi import WebSocket
from typing import Dict, Set
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections grouped by quiz_id (not session_id).
    All participants in the same quiz are in the same room and receive
    the same broadcasts — question transitions, quiz start/end events.
    """

    def __init__(self):
        # {quiz_id: set(WebSocket)}
        self.quiz_rooms: Dict[int, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, quiz_id: int):
        await websocket.accept()
        if quiz_id not in self.quiz_rooms:
            self.quiz_rooms[quiz_id] = set()
        self.quiz_rooms[quiz_id].add(websocket)
        logger.info(f"WS connected to quiz {quiz_id} — room size: {self.get_participant_count(quiz_id)}")

    def disconnect(self, websocket: WebSocket, quiz_id: int):
        if quiz_id in self.quiz_rooms:
            self.quiz_rooms[quiz_id].discard(websocket)
            if not self.quiz_rooms[quiz_id]:
                del self.quiz_rooms[quiz_id]
        logger.info(f"WS disconnected from quiz {quiz_id}")

    async def broadcast_to_quiz(self, quiz_id: int, message: dict):
        """Push a message to every connected participant in a quiz room."""
        if quiz_id not in self.quiz_rooms:
            return
        dead: Set[WebSocket] = set()
        for ws in self.quiz_rooms[quiz_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.disconnect(ws, quiz_id)

    async def send_personal_message(self, websocket: WebSocket, message: dict):
        try:
            await websocket.send_json(message)
        except Exception:
            pass

    def get_participant_count(self, quiz_id: int) -> int:
        return len(self.quiz_rooms.get(quiz_id, set()))


manager = ConnectionManager()
