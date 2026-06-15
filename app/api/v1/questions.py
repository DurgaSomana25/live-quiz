from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Quiz, QuizSession, Question, Answer
from app.schemas import QuizSessionStartResponse, QuestionResponse, QuizSessionResult
from app.auth.jwt_handler import get_current_user
from app.auth.permissions import require_participant
from app.config import settings
from datetime import datetime
import json
import asyncio

router = APIRouter(prefix="/api/v1/questions", tags=["questions"])

@router.post("/start-session/{quiz_id}", response_model=QuizSessionStartResponse)
async def start_quiz_session(
    quiz_id: int,
    current_user: User = Depends(require_participant),
    db: Session = Depends(get_db)
):
    """Start a new quiz session"""
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found"
        )
    
    if not quiz.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quiz is not active"
        )
    
    # Create session
    session = QuizSession(
        quiz_id=quiz_id,
        participant_id=current_user.id,
        status="ongoing"
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    
    # Get first question
    first_question = db.query(Question).filter(
        Question.quiz_id == quiz_id,
        Question.question_number == 1
    ).first()
    
    if not first_question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No questions found for quiz"
        )
    
    return {
        "session_id": session.id,
        "quiz_id": quiz.id,
        "started_at": session.started_at,
        "question": first_question,
        "question_number": 1,
        "total_questions": quiz.total_questions,
        "time_remaining": quiz.question_duration
    }

@router.get("/next/{session_id}")
async def get_next_question(
    session_id: int,
    current_question_number: int,
    current_user: User = Depends(require_participant),
    db: Session = Depends(get_db)
):
    """Get next question for quiz session"""
    session = db.query(QuizSession).filter(QuizSession.id == session_id).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )

    if session.participant_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized"
        )

    if session.status != "ongoing":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session has ended"
        )

    next_question_number = current_question_number + 1
    quiz = db.query(Quiz).filter(Quiz.id == session.quiz_id).first()

    if next_question_number > quiz.total_questions:
        session.status = "completed"
        session.ended_at = datetime.utcnow()

        answers = db.query(Answer).filter(Answer.session_id == session_id).all()
        total_score = sum(ans.marks_obtained for ans in answers)
        session.total_score = total_score
        session.passed = total_score >= quiz.pass_marks

        db.commit()

        return {
            "status": "completed",
            "result": {
                "session_id": session.id,
                "total_score": session.total_score,
                "passed": session.passed,
                "total_marks": quiz.total_questions * quiz.marks_per_question,
                "pass_marks": quiz.pass_marks,
                "correct_answers": len([a for a in answers if a.is_correct]),
                "total_questions": quiz.total_questions
            }
        }

    next_question = db.query(Question).filter(
        Question.quiz_id == session.quiz_id,
        Question.question_number == next_question_number
    ).first()

    if not next_question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question not found"
        )

    return {
        "status": "next_question",
        "question": QuestionResponse.model_validate(next_question).model_dump(),
        "question_number": next_question_number,
        "total_questions": quiz.total_questions,
        "time_remaining": quiz.question_duration
    }
