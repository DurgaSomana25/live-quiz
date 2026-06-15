from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Quiz, Question
from app.schemas import QuizCreate, QuizResponse, QuizDetailResponse
from app.auth.jwt_handler import get_current_user
from app.auth.permissions import require_admin
import json

router = APIRouter(prefix="/api/v1/quizzes", tags=["quiz"])

@router.post("/", response_model=QuizResponse)
async def create_quiz(
    quiz_data: QuizCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    quiz = Quiz(
        title=quiz_data.title,
        description=quiz_data.description,
        total_questions=quiz_data.total_questions,
        marks_per_question=quiz_data.marks_per_question,
        pass_marks=quiz_data.pass_marks,
        question_duration=quiz_data.question_duration,
        created_by=current_user.id
    )
    db.add(quiz)
    db.flush()
    
    # Add questions
    for q_data in quiz_data.questions:
        question = Question(
            quiz_id=quiz.id,
            question_text=q_data.question_text,
            option_a=q_data.option_a,
            option_b=q_data.option_b,
            option_c=q_data.option_c,
            option_d=q_data.option_d,
            correct_options=json.dumps(q_data.correct_options),
            is_multiselect=q_data.is_multiselect,
            question_number=q_data.question_number
        )
        db.add(question)
    
    db.commit()
    db.refresh(quiz)
    return quiz

@router.get("/", response_model=list[QuizResponse])
async def get_quizzes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    quizzes = db.query(Quiz).filter(Quiz.is_active == True).all()
    return quizzes

@router.get("/{quiz_id}", response_model=QuizDetailResponse)
async def get_quiz(
    quiz_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found"
        )
    
    return quiz
