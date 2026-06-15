from fastapi import WebSocket
from typing import Dict, List, Set
import asyncio
import json
from datetime import datetime

class ConnectionManager:
    """Manages WebSocket connections for real-time quiz sessions"""
    
    def __init__(self):
        # {session_id: set(WebSocket)}
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        # {session_id: question_number}
        self.current_question: Dict[int, int] = {}
        # {session_id: asyncio.Task}
        self.question_timers: Dict[int, asyncio.Task] = {}
    
    async def connect(self, websocket: WebSocket, session_id: int):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = set()
        self.active_connections[session_id].add(websocket)
    
    def disconnect(self, websocket: WebSocket, session_id: int):
        if session_id in self.active_connections:
            self.active_connections[session_id].discard(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
    
    async def broadcast(self, session_id: int, message: dict):
        """Broadcast message to all participants in a session"""
        if session_id not in self.active_connections:
            return
        
        disconnected = set()
        for connection in self.active_connections[session_id]:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.add(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn, session_id)
    
    async def send_personal_message(self, websocket: WebSocket, message: dict):
        """Send message to specific user"""
        try:
            await websocket.send_json(message)
        except Exception:
            pass
    
    def get_active_participants(self, session_id: int) -> int:
        """Get count of active participants"""
        return len(self.active_connections.get(session_id, set()))

manager = ConnectionManager()
