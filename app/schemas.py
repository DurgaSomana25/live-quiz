from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from enum import Enum

class RoleEnum(str, Enum):
    ADMIN = "admin"
    PARTICIPANT = "participant"

# User Schemas
class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    role: RoleEnum = RoleEnum.PARTICIPANT

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    role: RoleEnum
    created_at: datetime
    
    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

# Question Schemas
class QuestionCreate(BaseModel):
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_options: List[str]  # ["a", "b"]
    is_multiselect: bool = False
    question_number: int

class QuestionResponse(BaseModel):
    id: int
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    is_multiselect: bool
    question_number: int
    
    class Config:
        from_attributes = True

class QuestionWithAnswersResponse(QuestionResponse):
    correct_options: List[str]

# Quiz Schemas
class QuizCreate(BaseModel):
    title: str
    description: Optional[str] = None
    total_questions: int = 10
    marks_per_question: int = 2
    pass_marks: int = 14
    question_duration: int = 30
    questions: List[QuestionCreate]

class QuizResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    total_questions: int
    marks_per_question: int
    pass_marks: int
    question_duration: int
    is_active: bool
    quiz_status: str
    started_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True

class QuizDetailResponse(QuizResponse):
    questions: List[QuestionResponse]

# Quiz Session Schemas
class QuizSessionStartResponse(BaseModel):
    session_id: int
    quiz_id: int
    started_at: datetime
    question: QuestionResponse
    question_number: int
    total_questions: int
    time_remaining: int

class AnswerSubmit(BaseModel):
    session_id: int
    question_id: int
    selected_options: List[str]  # ["a", "b"]

class AnswerResponse(BaseModel):
    id: int
    is_correct: bool
    marks_obtained: float
    answered_at: datetime
    
    class Config:
        from_attributes = True

class QuizSessionResult(BaseModel):
    session_id: int
    total_score: float
    passed: bool
    total_marks: int
    pass_marks: int
    correct_answers: int
    total_questions: int

# Join / Current Question Schemas
class JoinQuizResponse(BaseModel):
    session_id: int
    quiz_id: int
    quiz_status: str
    session_status: str
    message: str
    websocket_url: str

class CurrentQuestionResponse(BaseModel):
    status: str  # waiting | active | ended
    question: Optional[QuestionResponse] = None
    question_number: Optional[int] = None
    total_questions: Optional[int] = None
    time_remaining: Optional[int] = None
    already_answered: Optional[bool] = None
    result: Optional[QuizSessionResult] = None
    message: Optional[str] = None

# Leaderboard Schemas
class LeaderboardEntry(BaseModel):
    rank: int
    username: str
    score: float
    passed: bool

class LeaderboardResponse(BaseModel):
    quiz_id: int
    entries: List[LeaderboardEntry]
