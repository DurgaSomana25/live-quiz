from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
from app.config import settings
from app.database import engine, Base, get_db
from app.api.v1 import auth, quiz, questions, answers, leaderboard
from app.auth.jwt_handler import get_current_user
from app.websocket.manager import manager
import asyncio

# Create tables
Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Application startup")
    yield
    print("Application shutdown")

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(quiz.router)
app.include_router(questions.router)
app.include_router(answers.router)
app.include_router(leaderboard.router)

@app.get("/")
async def root():
    return {
        "message": "Welcome to Live Quiz API",
        "version": "1.0.0",
        "endpoints": {
            "auth": "/api/v1/auth",
            "quizzes": "/api/v1/quizzes",
            "questions": "/api/v1/questions",
            "answers": "/api/v1/answers",
            "leaderboard": "/api/v1/leaderboard"
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.websocket("/ws/quiz/{session_id}/{user_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: int, user_id: int, db: Session = Depends(get_db)):
    """WebSocket endpoint for real-time quiz participation"""
    await manager.connect(websocket, session_id)
    
    try:
        while True:
            data = await websocket.receive_json()
            
            if data.get("type") == "answer":
                # Broadcast answer submission
                await manager.broadcast(session_id, {
                    "type": "answer_received",
                    "user_id": user_id,
                    "question_id": data.get("question_id")
                })
            
            elif data.get("type") == "get_status":
                # Send current session status
                active_participants = manager.get_active_participants(session_id)
                await manager.send_personal_message(websocket, {
                    "type": "status",
                    "active_participants": active_participants,
                    "session_id": session_id
                })
            
            elif data.get("type") == "ping":
                # Keep-alive
                await manager.send_personal_message(websocket, {
                    "type": "pong"
                })
    
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
    
    except Exception as e:
        manager.disconnect(websocket, session_id)
        print(f"WebSocket error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=settings.DEBUG)
