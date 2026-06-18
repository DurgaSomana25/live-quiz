from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import User, Quiz, QuizSession, Answer, RoleEnum
from app.schemas import LeaderboardResponse, LeaderboardEntry
from app.auth.jwt_handler import get_current_user

router = APIRouter(prefix="/api/v1/leaderboard", tags=["leaderboard"])

@router.get("/{quiz_id}", response_model=LeaderboardResponse)
async def get_leaderboard(
    quiz_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get leaderboard for a quiz"""
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found"
        )
    
    # Get all completed sessions for this quiz
    sessions = db.query(QuizSession).filter(
        QuizSession.quiz_id == quiz_id,
        QuizSession.status == "completed"
    ).order_by(QuizSession.total_score.desc()).all()
    
    entries = []
    for rank, session in enumerate(sessions, 1):
        user = db.query(User).filter(User.id == session.participant_id).first()
        entries.append(LeaderboardEntry(
            rank=rank,
            username=user.username,
            score=session.total_score,
            passed=session.passed
        ))
    
    return LeaderboardResponse(
        quiz_id=quiz_id,
        entries=entries
    )

@router.get("/user/{user_id}", response_model=list[dict])
async def get_user_quiz_results(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all quiz results for a user"""
    if current_user.id != user_id and current_user.role != RoleEnum.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized"
        )
    
    sessions = db.query(QuizSession).filter(
        QuizSession.participant_id == user_id,
        QuizSession.status == "completed"
    ).all()
    
    results = []
    for session in sessions:
        quiz = db.query(Quiz).filter(Quiz.id == session.quiz_id).first()
        results.append({
            "session_id": session.id,
            "quiz_id": session.quiz_id,
            "quiz_title": quiz.title,
            "score": session.total_score,
            "passed": session.passed,
            "completed_at": session.ended_at
        })
    
    return results
