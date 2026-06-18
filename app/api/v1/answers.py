from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, QuizSession, Answer, Question, Quiz
from app.schemas import AnswerSubmit, AnswerResponse
from app.auth.permissions import require_participant
from app.utils.quiz_time import get_current_question_number
import json

router = APIRouter(prefix="/api/v1/answers", tags=["answers"])


@router.post("/submit", response_model=AnswerResponse)
async def submit_answer(
    answer_data: AnswerSubmit,
    current_user: User = Depends(require_participant),
    db: Session = Depends(get_db)
):
    session = db.query(QuizSession).filter(QuizSession.id == answer_data.session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.participant_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized")
    if session.status != "ongoing":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Session is '{session.status}' — cannot submit answers"
        )

    quiz = db.query(Quiz).filter(Quiz.id == session.quiz_id).first()

    # Enforce: quiz must be live
    if quiz.quiz_status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Quiz is not active (status: {quiz.quiz_status})"
        )

    # Determine which question is live on the global clock
    current_q_number = get_current_question_number(
        quiz.total_questions, quiz.question_duration, quiz.started_at
    )
    if current_q_number is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quiz time has elapsed. No more answers accepted."
        )

    # The submitted question must match what the clock says is live right now
    current_question = db.query(Question).filter(
        Question.quiz_id == quiz.id,
        Question.question_number == current_q_number
    ).first()

    if answer_data.question_id != current_question.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Wrong question. The live question right now is "
                f"Q{current_q_number} (id={current_question.id}). "
                f"Call GET /questions/current/{{session_id}} to get it."
            )
        )

    # Duplicate answer check
    existing = db.query(Answer).filter(
        Answer.session_id == answer_data.session_id,
        Answer.question_id == answer_data.question_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Answer already submitted for this question"
        )

    # Evaluate
    correct_options = json.loads(current_question.correct_options)
    is_correct = set(answer_data.selected_options) == set(correct_options)
    marks_obtained = quiz.marks_per_question if is_correct else 0.0

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
    session = db.query(QuizSession).filter(QuizSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.participant_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized")
    return db.query(Answer).filter(Answer.session_id == session_id).all()
