from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app.models import User, Quiz, QuizSession, Question, Answer
from app.schemas import JoinQuizResponse, CurrentQuestionResponse, QuestionResponse, QuizSessionResult
from app.auth.permissions import require_participant
from app.utils.quiz_time import get_current_question_number, get_time_remaining_in_question

router = APIRouter(prefix="/api/v1/questions", tags=["questions"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sync_quiz_status(quiz: Quiz, db: Session) -> Quiz:
    """
    Lazily mark quiz as 'ended' when the clock has run out.
    Handles server-restart edge cases where the background task was lost.
    """
    if quiz.quiz_status == "active" and quiz.started_at:
        elapsed = (datetime.utcnow() - quiz.started_at).total_seconds()
        if elapsed >= quiz.total_questions * quiz.question_duration:
            quiz.quiz_status = "ended"
            db.commit()
    return quiz


def _complete_session(session: QuizSession, quiz: Quiz, db: Session):
    """Finalize a session: calculate score, mark as completed."""
    answers = db.query(Answer).filter(Answer.session_id == session.id).all()
    session.total_score = sum(a.marks_obtained for a in answers)
    session.passed = session.total_score >= quiz.pass_marks
    session.status = "completed"
    session.ended_at = datetime.utcnow()
    db.commit()


# ---------------------------------------------------------------------------
# Participant: join a quiz (creates or retrieves their session)
# ---------------------------------------------------------------------------

@router.post("/join/{quiz_id}", response_model=JoinQuizResponse)
async def join_quiz(
    quiz_id: int,
    current_user: User = Depends(require_participant),
    db: Session = Depends(get_db)
):
    """
    Participant calls this once to register for a quiz.
    Idempotent — calling again returns the same session.
    If the quiz is still 'pending', session waits for admin to fire /start.
    If already 'active', session is immediately 'ongoing'.
    """
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    if not quiz.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quiz is not available")
    if quiz.quiz_status == "ended":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quiz has already ended")

    # Idempotent: return existing active session
    existing = db.query(QuizSession).filter(
        QuizSession.quiz_id == quiz_id,
        QuizSession.participant_id == current_user.id,
        QuizSession.status.in_(["waiting", "ongoing"])
    ).first()

    if existing:
        return JoinQuizResponse(
            session_id=existing.id,
            quiz_id=quiz_id,
            quiz_status=quiz.quiz_status,
            session_status=existing.status,
            message="Already joined. Connect to WebSocket to receive live events.",
            websocket_url=f"/ws/quiz/{quiz_id}/{current_user.id}"
        )

    session_status = "ongoing" if quiz.quiz_status == "active" else "waiting"
    session = QuizSession(
        quiz_id=quiz_id,
        participant_id=current_user.id,
        status=session_status
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    msg = (
        "Quiz is live! Call GET /questions/current/{session_id} to get your question."
        if session_status == "ongoing"
        else "Joined. Waiting for admin to start the quiz. Connect to WebSocket for the live signal."
    )

    return JoinQuizResponse(
        session_id=session.id,
        quiz_id=quiz_id,
        quiz_status=quiz.quiz_status,
        session_status=session_status,
        message=msg,
        websocket_url=f"/ws/quiz/{quiz_id}/{current_user.id}"
    )


# ---------------------------------------------------------------------------
# Participant: get the question that is live right now
# ---------------------------------------------------------------------------

@router.get("/current/{session_id}", response_model=CurrentQuestionResponse)
async def get_current_question(
    session_id: int,
    current_user: User = Depends(require_participant),
    db: Session = Depends(get_db)
):
    """
    Returns the question that the global quiz clock says is active right now.
    The participant cannot skip ahead or go back — the clock decides.
    Poll this endpoint (or listen on WebSocket) to stay in sync.
    """
    session = db.query(QuizSession).filter(QuizSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.participant_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized")

    quiz = db.query(Quiz).filter(Quiz.id == session.quiz_id).first()
    quiz = _sync_quiz_status(quiz, db)

    # --- Quiz not started yet ---
    if quiz.quiz_status == "pending":
        return CurrentQuestionResponse(
            status="waiting",
            message="Quiz hasn't started yet. Wait for admin to fire /quizzes/{id}/start."
        )

    # --- Quiz ended ---
    if quiz.quiz_status == "ended":
        if session.status == "ongoing":
            _complete_session(session, quiz, db)
            db.refresh(session)

        if session.status in ("completed", "abandoned"):
            answers = db.query(Answer).filter(Answer.session_id == session.id).all()
            return CurrentQuestionResponse(
                status="ended",
                message="Quiz has ended.",
                result=QuizSessionResult(
                    session_id=session.id,
                    total_score=session.total_score or 0.0,
                    passed=session.passed or False,
                    total_marks=quiz.total_questions * quiz.marks_per_question,
                    pass_marks=quiz.pass_marks,
                    correct_answers=sum(1 for a in answers if a.is_correct),
                    total_questions=quiz.total_questions
                )
            )

    # --- Quiz is active ---
    q_number = get_current_question_number(
        quiz.total_questions, quiz.question_duration, quiz.started_at
    )
    if q_number is None:
        # Clock ran out between our status check and now (race) — treat as ended
        if session.status == "ongoing":
            _complete_session(session, quiz, db)
        return CurrentQuestionResponse(status="ended", message="Quiz has ended.")

    question = db.query(Question).filter(
        Question.quiz_id == quiz.id,
        Question.question_number == q_number
    ).first()
    if not question:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Question not found in DB")

    already_answered = db.query(Answer).filter(
        Answer.session_id == session.id,
        Answer.question_id == question.id
    ).first() is not None

    return CurrentQuestionResponse(
        status="active",
        question=QuestionResponse.model_validate(question),
        question_number=q_number,
        total_questions=quiz.total_questions,
        time_remaining=get_time_remaining_in_question(quiz.question_duration, quiz.started_at),
        already_answered=already_answered
    )


# ---------------------------------------------------------------------------
# Participant: abandon session mid-quiz
# ---------------------------------------------------------------------------

@router.post("/abandon/{session_id}")
async def abandon_session(
    session_id: int,
    current_user: User = Depends(require_participant),
    db: Session = Depends(get_db)
):
    session = db.query(QuizSession).filter(QuizSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.participant_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized")
    if session.status != "ongoing":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Session is already '{session.status}'"
        )

    quiz = db.query(Quiz).filter(Quiz.id == session.quiz_id).first()
    answers = db.query(Answer).filter(Answer.session_id == session_id).all()

    session.status = "abandoned"
    session.ended_at = datetime.utcnow()
    session.total_score = sum(a.marks_obtained for a in answers)
    session.passed = False
    db.commit()

    return {
        "message": "Session abandoned",
        "session_id": session_id,
        "questions_answered": len(answers),
        "total_questions": quiz.total_questions,
        "score_so_far": session.total_score
    }
