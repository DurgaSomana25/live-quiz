from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.database import get_db, SessionLocal
from app.models import User, Quiz, Question, QuizSession, Answer
from app.schemas import QuizCreate, QuizResponse, QuizDetailResponse
from app.auth.jwt_handler import get_current_user
from app.auth.permissions import require_admin
from app.websocket.manager import manager
import asyncio
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/quizzes", tags=["quiz"])


# ---------------------------------------------------------------------------
# Background tasks (run after quiz start)
# ---------------------------------------------------------------------------

async def _auto_end_quiz(quiz_id: int, delay: float):
    """
    Sleep until the quiz total duration elapses, then mark quiz as ended
    and auto-complete all remaining sessions.
    """
    await asyncio.sleep(delay)
    db = SessionLocal()
    try:
        quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
        if not quiz or quiz.quiz_status != "active":
            return

        quiz.quiz_status = "ended"

        sessions = db.query(QuizSession).filter(
            QuizSession.quiz_id == quiz_id,
            QuizSession.status.in_(["ongoing", "waiting"])
        ).all()
        for session in sessions:
            answers = db.query(Answer).filter(Answer.session_id == session.id).all()
            session.total_score = sum(a.marks_obtained for a in answers)
            session.passed = session.total_score >= quiz.pass_marks
            session.status = "completed"
            session.ended_at = datetime.utcnow()

        db.commit()
        logger.info(f"Quiz {quiz_id} auto-ended. {len(sessions)} sessions completed.")

        await manager.broadcast_to_quiz(quiz_id, {
            "type": "quiz_ended",
            "quiz_id": quiz_id,
            "message": "Quiz has ended. Results are now available."
        })
    except Exception as e:
        logger.error(f"_auto_end_quiz error for quiz {quiz_id}: {e}")
    finally:
        db.close()


async def _broadcast_question_transitions(
    quiz_id: int,
    started_at: datetime,
    total_questions: int,
    question_duration: int,
):
    """
    Pushes each question to all WebSocket clients at the exact moment
    its time window opens. Q1 is broadcast immediately on start; this
    task handles Q2 onwards.
    """
    for q_number in range(2, total_questions + 1):
        target_offset = (q_number - 1) * question_duration
        elapsed = (datetime.utcnow() - started_at).total_seconds()
        delay = target_offset - elapsed
        if delay > 0:
            await asyncio.sleep(delay)

        db = SessionLocal()
        try:
            quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
            if not quiz or quiz.quiz_status != "active":
                break

            question = db.query(Question).filter(
                Question.quiz_id == quiz_id,
                Question.question_number == q_number
            ).first()

            if question:
                await manager.broadcast_to_quiz(quiz_id, {
                    "type": "question",
                    "question_number": q_number,
                    "total_questions": total_questions,
                    "time_remaining": question_duration,
                    "question": {
                        "id": question.id,
                        "question_text": question.question_text,
                        "option_a": question.option_a,
                        "option_b": question.option_b,
                        "option_c": question.option_c,
                        "option_d": question.option_d,
                        "is_multiselect": question.is_multiselect,
                        "question_number": q_number
                    }
                })
        except Exception as e:
            logger.error(f"_broadcast_question_transitions error at Q{q_number}: {e}")
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Quiz CRUD
# ---------------------------------------------------------------------------

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
    return db.query(Quiz).filter(Quiz.is_active == True).all()


@router.get("/sessions/active", dependencies=[Depends(require_admin)])
async def get_active_sessions(db: Session = Depends(get_db)):
    """Admin — all currently ongoing sessions across all quizzes."""
    rows = (
        db.query(QuizSession, Quiz, User)
        .join(Quiz, QuizSession.quiz_id == Quiz.id)
        .join(User, QuizSession.participant_id == User.id)
        .filter(QuizSession.status == "ongoing")
        .all()
    )
    return [
        {
            "session_id": s.id,
            "quiz_id": s.quiz_id,
            "quiz_title": q.title,
            "quiz_status": q.quiz_status,
            "participant_id": s.participant_id,
            "username": u.username,
            "started_at": s.started_at,
            "status": s.status
        }
        for s, q, u in rows
    ]


@router.get("/sessions/all", dependencies=[Depends(require_admin)])
async def get_all_sessions(db: Session = Depends(get_db)):
    """Admin — all sessions (any status) with scores, newest first."""
    rows = (
        db.query(QuizSession, Quiz, User)
        .join(Quiz, QuizSession.quiz_id == Quiz.id)
        .join(User, QuizSession.participant_id == User.id)
        .order_by(QuizSession.started_at.desc())
        .all()
    )
    return [
        {
            "session_id": s.id,
            "quiz_id": s.quiz_id,
            "quiz_title": q.title,
            "quiz_status": q.quiz_status,
            "participant_id": s.participant_id,
            "username": u.username,
            "status": s.status,
            "total_score": s.total_score,
            "passed": s.passed,
            "started_at": s.started_at,
            "ended_at": s.ended_at
        }
        for s, q, u in rows
    ]


# ---------------------------------------------------------------------------
# Admin: start quiz (fires the global clock)
# ---------------------------------------------------------------------------

@router.post("/{quiz_id}/start", dependencies=[Depends(require_admin)])
async def start_quiz(quiz_id: int, db: Session = Depends(get_db)):
    """
    Admin fires this to start the synchronized clock for everyone.
    All participants in 'waiting' status are immediately moved to 'ongoing'.
    Background tasks auto-broadcast each question and auto-end the quiz.
    """
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    if quiz.quiz_status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Quiz is already '{quiz.quiz_status}'. Can only start a pending quiz."
        )

    quiz.started_at = datetime.utcnow()
    quiz.quiz_status = "active"

    # Everyone who pre-joined while status was 'waiting' → 'ongoing'
    waiting_count = db.query(QuizSession).filter(
        QuizSession.quiz_id == quiz_id,
        QuizSession.status == "waiting"
    ).update({"status": "ongoing"})

    db.commit()

    # Get first question for the broadcast payload
    first_question = db.query(Question).filter(
        Question.quiz_id == quiz_id,
        Question.question_number == 1
    ).first()

    await manager.broadcast_to_quiz(quiz_id, {
        "type": "quiz_started",
        "quiz_id": quiz_id,
        "started_at": quiz.started_at.isoformat(),
        "total_questions": quiz.total_questions,
        "question_duration": quiz.question_duration,
        "question": {
            "id": first_question.id,
            "question_text": first_question.question_text,
            "option_a": first_question.option_a,
            "option_b": first_question.option_b,
            "option_c": first_question.option_c,
            "option_d": first_question.option_d,
            "is_multiselect": first_question.is_multiselect,
            "question_number": 1
        } if first_question else None
    })

    total_duration = quiz.total_questions * quiz.question_duration
    asyncio.create_task(_auto_end_quiz(quiz_id, total_duration))
    asyncio.create_task(
        _broadcast_question_transitions(
            quiz_id, quiz.started_at, quiz.total_questions, quiz.question_duration
        )
    )

    return {
        "message": "Quiz started",
        "quiz_id": quiz_id,
        "started_at": quiz.started_at,
        "total_duration_seconds": total_duration,
        "ends_at": quiz.started_at + timedelta(seconds=total_duration),
        "waiting_participants_activated": waiting_count,
        "live_participants": manager.get_participant_count(quiz_id)
    }


@router.get("/{quiz_id}", response_model=QuizDetailResponse)
async def get_quiz(
    quiz_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    return quiz
