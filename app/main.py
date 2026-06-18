from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from pathlib import Path
from app.config import settings
from app.database import engine, Base
from app.api.v1 import auth, quiz, questions, answers, leaderboard
from app.websocket.manager import manager
import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Create tables
Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup")
    yield
    logger.info("Application shutdown")

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = (time.time() - start) * 1000
    logger.info(f"{request.method} {request.url.path} → {response.status_code} ({duration:.1f}ms)")
    return response

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

# Serve the frontend — must be after all API routes
_frontend = Path(__file__).parent.parent / "frontend"
if _frontend.exists():
    app.mount("/app", StaticFiles(directory=str(_frontend), html=True), name="frontend")

@app.websocket("/ws/quiz/{quiz_id}/{user_id}")
async def websocket_endpoint(websocket: WebSocket, quiz_id: int, user_id: int):
    """
    Connect to a quiz room to receive real-time events:
      - quiz_started  : admin fired the clock, includes Q1
      - question      : new question is now live (Q2, Q3, ...)
      - quiz_ended    : quiz clock ran out
      - pong          : keep-alive reply
    """
    await manager.connect(websocket, quiz_id)
    try:
        await manager.send_personal_message(websocket, {
            "type": "connected",
            "quiz_id": quiz_id,
            "participants_online": manager.get_participant_count(quiz_id)
        })
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await manager.send_personal_message(websocket, {"type": "pong"})
            elif data.get("type") == "get_status":
                await manager.send_personal_message(websocket, {
                    "type": "status",
                    "quiz_id": quiz_id,
                    "participants_online": manager.get_participant_count(quiz_id)
                })
    except WebSocketDisconnect:
        manager.disconnect(websocket, quiz_id)
    except Exception as e:
        manager.disconnect(websocket, quiz_id)
        logger.error(f"WebSocket error quiz {quiz_id}: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=settings.DEBUG)
