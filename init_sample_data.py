"""
Sample data initialization script
Run this to populate the database with sample quizzes
"""

from app.database import SessionLocal, Base, engine
from app.models import User, Quiz, Question, RoleEnum
from app.auth.jwt_handler import hash_password
import json

def init_sample_data():
    """Initialize sample data"""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    # Clear existing data
    db.query(Question).delete()
    db.query(Quiz).delete()
    db.query(User).delete()
    db.commit()
    
    # Create admin user
    admin = User(
        email="admin@example.com",
        username="admin",
        hashed_password=hash_password("admin123"),
        role=RoleEnum.ADMIN,
        is_active=True
    )
    db.add(admin)
    db.flush()
    
    # Create sample participants
    participants = []
    for i in range(3):
        user = User(
            email=f"user{i}@example.com",
            username=f"user{i}",
            hashed_password=hash_password("password123"),
            role=RoleEnum.PARTICIPANT,
            is_active=True
        )
        db.add(user)
        participants.append(user)
    
    db.commit()
    
    # Create sample quiz
    quiz = Quiz(
        title="Python Fundamentals",
        description="10 questions to test your Python knowledge",
        total_questions=10,
        marks_per_question=2,
        pass_marks=14,
        question_duration=30,
        created_by=admin.id,
        is_active=True
    )
    db.add(quiz)
    db.flush()
    
    # Add sample questions
    questions_data = [
        ("What is Python?", ["a"], False),
        ("What does PEP stand for?", ["b"], False),
        ("Which keyword is used to create a function?", ["a"], False),
        ("What is the correct way to create a list?", ["b"], False),
        ("What is the output of print(2 ** 3)?", ["c"], False),
        ("Which of these is a mutable data type?", ["a", "d"], True),
        ("What is the purpose of __init__?", ["b"], False),
        ("How do you create a dictionary in Python?", ["a"], False),
        ("Which statement is used to skip an iteration?", ["a"], False),
        ("What is the correct syntax for a lambda function?", ["c"], False),
    ]
    
    options = [
        ("A programming language", "A snake", "Not used", "A dance"),
        ("Python Enhancement Proposal", "Programming Enhancement Platform", "Python Error Protocol", "Pre-Execution Path"),
        ("define", "def", "function", "func"),
        ("list = []", "list()", "Both", "list = ()"),
        ("5", "6", "8", "9"),
        ("list", "tuple", "string", "set"),
        ("Constructor method", "Main method", "Special variable", "Error handler"),
        ("{key: value}", "(key: value)", "[key: value]", "dict()"),
        ("break", "continue", "pass", "skip"),
        ("lambda x: x * 2", "lambda: x * 2", "func x: x * 2", "def x: x * 2"),
    ]
    
    for i, (question_text, correct_opts, is_multi) in enumerate(questions_data, 1):
        q = Question(
            quiz_id=quiz.id,
            question_text=question_text,
            option_a=options[i-1][0],
            option_b=options[i-1][1],
            option_c=options[i-1][2],
            option_d=options[i-1][3],
            correct_options=json.dumps(correct_opts),
            is_multiselect=is_multi,
            question_number=i
        )
        db.add(q)
    
    db.commit()
    db.close()
    
    print("✅ Sample data initialized successfully!")
    print("\nTest Credentials:")
    print("  Admin: admin@example.com / admin123")
    print("  User1: user0@example.com / password123")
    print("  User2: user1@example.com / password123")
    print("  User3: user2@example.com / password123")

if __name__ == "__main__":
    init_sample_data()
