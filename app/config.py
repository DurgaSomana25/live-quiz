from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Database - Use SQLite by default for development
    DATABASE_URL: str
    
    # JWT
    SECRET_KEY: str = "your-secret-key-change-this"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Server
    DEBUG: bool = True
    APP_NAME: str = "Live Quiz API"
    
    # Quiz Settings
    QUESTION_DURATION_SECONDS: int = 30
    TOTAL_QUESTIONS: int = 10
    MARKS_PER_QUESTION: int = 2
    PASS_MARKS: int = 14
    
    class Config:
        env_file = ".env"

settings = Settings()
