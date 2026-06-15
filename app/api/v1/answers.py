from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, QuizSession, Answer, Question, Quiz
from app.schemas import AnswerSubmit, AnswerResponse
from app.auth.jwt_handler import get_current_user
from app.auth.permissions import require_participant
from datetime import datetime
import json

router = APIRouter(prefix="/api/v1/answers", tags=["answers"])

@router.post("/submit", response_model=AnswerResponse)
async def submit_answer(
    answer_data: AnswerSubmit,
    current_user: User = Depends(require_participant),
    db: Session = Depends(get_db)
):
    """Submit an answer for a question"""
    session = db.query(QuizSession).filter(QuizSession.id == answer_data.session_id).first()
    
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
    
    question = db.query(Question).filter(Question.id == answer_data.question_id).first()
    
    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found"
        )
    
    # Check if answer already exists for this question
    existing_answer = db.query(Answer).filter(
        Answer.session_id == answer_data.session_id,
        Answer.question_id == answer_data.question_id
    ).first()
    
    if existing_answer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Answer already submitted for this question"
        )
    
    # Evaluate answer
    correct_options = json.loads(question.correct_options)
    is_correct = set(answer_data.selected_options) == set(correct_options)
    
    quiz = db.query(Quiz).filter(Quiz.id == session.quiz_id).first()
    marks_obtained = quiz.marks_per_question if is_correct else 0.0
    
    # Save answer
    answer = Answer(
        session_id=answer_data.session_id,
        question_id=answer_data.question_id,
        user_id=current_user.id,
        selected_options=json.dumps(answer_data.selected_options),
        is_correct=is_correct,
        marks_obtained=marks_obtained
    )
    db.add(answer)
    db.commit()
    db.refresh(answer)
    
    return answer

@router.get("/session/{session_id}", response_model=list[AnswerResponse])
async def get_session_answers(
    session_id: int,
    current_user: User = Depends(require_participant),
    db: Session = Depends(get_db)
):
    """Get all answers for a session"""
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
    
    answers = db.query(Answer).filter(Answer.session_id == session_id).all()
    return answers
