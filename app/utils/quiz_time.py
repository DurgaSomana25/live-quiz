from datetime import datetime
from typing import Optional


def get_current_question_number(
    total_questions: int, question_duration: int, started_at: datetime
) -> Optional[int]:
    """
    Returns the question number that is live right now based on elapsed time.
    Returns None if the full quiz duration has passed.
    Pure function — no ORM dependency so it stays easy to test.
    """
    elapsed = (datetime.utcnow() - started_at).total_seconds()
    if elapsed >= total_questions * question_duration:
        return None
    return int(elapsed // question_duration) + 1


def get_time_remaining_in_question(question_duration: int, started_at: datetime) -> int:
    """Returns seconds left in the current question window."""
    elapsed = (datetime.utcnow() - started_at).total_seconds()
    position = elapsed % question_duration
    return max(0, int(question_duration - position))
