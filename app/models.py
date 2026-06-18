from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum, Text, Float
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.database import Base

class RoleEnum(str, enum.Enum):
    ADMIN = "admin"
    PARTICIPANT = "participant"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(Enum(RoleEnum), default=RoleEnum.PARTICIPANT)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    quiz_sessions = relationship("QuizSession", back_populates="participant")
    answers = relationship("Answer", back_populates="user")

class Quiz(Base):
    __tablename__ = "quizzes"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(Text)
    total_questions = Column(Integer, default=10)
    marks_per_question = Column(Integer, default=2)
    pass_marks = Column(Integer, default=14)
    question_duration = Column(Integer, default=30)  # seconds per question
    is_active = Column(Boolean, default=True)
    quiz_status = Column(String, default="pending")  # pending, active, ended
    started_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"))
    
    questions = relationship("Question", back_populates="quiz", cascade="all, delete-orphan")
    sessions = relationship("QuizSession", back_populates="quiz")

class Question(Base):
    __tablename__ = "questions"
    
    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"))
    question_text = Column(Text)
    option_a = Column(String)
    option_b = Column(String)
    option_c = Column(String)
    option_d = Column(String)
    correct_options = Column(String)  # JSON string: ["a", "b"] for multi-select
    is_multiselect = Column(Boolean, default=False)
    question_number = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    quiz = relationship("Quiz", back_populates="questions")
    answers = relationship("Answer", back_populates="question")

class QuizSession(Base):
    __tablename__ = "quiz_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"))
    participant_id = Column(Integer, ForeignKey("users.id"))
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    total_score = Column(Float, default=0.0)
    passed = Column(Boolean, nullable=True)
    status = Column(String, default="ongoing")  # waiting, ongoing, completed, abandoned
    
    quiz = relationship("Quiz", back_populates="sessions")
    participant = relationship("User", back_populates="quiz_sessions")
    answers = relationship("Answer", back_populates="session")

class Answer(Base):
    __tablename__ = "answers"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("quiz_sessions.id"))
    question_id = Column(Integer, ForeignKey("questions.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    selected_options = Column(String)  # JSON string: ["a", "b"]
    is_correct = Column(Boolean, default=False)
    marks_obtained = Column(Float, default=0.0)
    answered_at = Column(DateTime, default=datetime.utcnow)
    
    session = relationship("QuizSession", back_populates="answers")
    question = relationship("Question", back_populates="answers")
    user = relationship("User", back_populates="answers")

