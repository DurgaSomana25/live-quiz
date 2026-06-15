# Live Quiz — Backend API

A real-time quiz platform built with **FastAPI + PostgreSQL**. Supports role-based access (Admin / Participant), JWT authentication, timed questions, live scoring, and a leaderboard.

---

## Tech Stack

| Layer        | Technology                         |
|--------------|------------------------------------|
| Framework    | FastAPI 0.104                      |
| Database     | PostgreSQL (SQLAlchemy ORM)        |
| Auth         | JWT (python-jose) + Argon2 hashing |
| Migrations   | Alembic                            |
| Server       | Uvicorn                            |
| Python       | 3.14                               |

---

## Project Structure

```
live-quiz/
├── app/
│   ├── main.py              # App entry point, middleware, WebSocket
│   ├── config.py            # Settings loaded from .env
│   ├── database.py          # SQLAlchemy engine & session
│   ├── models.py            # DB table definitions
│   ├── schemas.py           # Pydantic request/response models
│   ├── auth/
│   │   ├── jwt_handler.py   # Token creation, validation, password hashing
│   │   └── permissions.py   # Role guards (admin / participant)
│   ├── api/v1/
│   │   ├── auth.py          # Register, Login, /me
│   │   ├── quiz.py          # Create & list quizzes
│   │   ├── questions.py     # Start session, get next question
│   │   ├── answers.py       # Submit answer, view session answers
│   │   └── leaderboard.py   # Quiz leaderboard, user results
│   └── websocket/
│       └── manager.py       # WebSocket connection manager
├── alembic/                 # DB migration scripts
├── scripts/
│   └── create_tables.py     # One-time table creation helper
├── init_sample_data.py      # Seeds DB with sample quiz + users
├── requirements.txt
└── .env                     # DB URL, JWT secret (not committed)
```

---

## Database Schema

```
users          → id, email, username, hashed_password, role, is_active
quizzes        → id, title, description, total_questions, marks_per_question,
                 pass_marks, question_duration, is_active, created_by
questions      → id, quiz_id, question_text, option_a/b/c/d,
                 correct_options (JSON array), is_multiselect, question_number
quiz_sessions  → id, quiz_id, participant_id, status (ongoing/completed),
                 total_score, passed, started_at, ended_at
answers        → id, session_id, question_id, user_id,
                 selected_options (JSON array), is_correct, marks_obtained
leaderboards   → id, quiz_id, user_id, score, rank, passed
```

---

## Roles

| Role        | Can Do                                           |
|-------------|--------------------------------------------------|
| admin       | Create quizzes, view all data                    |
| participant | Start sessions, submit answers, view leaderboard |

---

## API Endpoints

### Auth — `/api/v1/auth`

| Method | Endpoint    | Auth | Description               |
|--------|-------------|------|---------------------------|
| POST   | `/register` | No   | Create new account        |
| POST   | `/login`    | No   | Returns JWT access token  |
| GET    | `/me`       | Yes  | Current user profile      |

### Quizzes — `/api/v1/quizzes`

| Method | Endpoint | Role       | Description                |
|--------|----------|------------|----------------------------|
| GET    | `/`      | Any        | List all active quizzes    |
| GET    | `/{id}`  | Any        | Quiz detail with questions |
| POST   | `/`      | Admin only | Create quiz with questions |

### Quiz Flow — `/api/v1/questions`

| Method | Endpoint                                                        | Role        | Description                          |
|--------|-----------------------------------------------------------------|-------------|--------------------------------------|
| POST   | `/start-session/{quiz_id}`                                      | Participant | Start session, returns first question |
| GET    | `/next/{session_id}?current_question_number=N`                  | Participant | Next question or final result        |

### Answers — `/api/v1/answers`

| Method | Endpoint           | Role        | Description                  |
|--------|--------------------|-------------|------------------------------|
| POST   | `/submit`          | Participant | Submit answer for a question |
| GET    | `/session/{id}`    | Participant | All answers for a session    |

### Leaderboard — `/api/v1/leaderboard`

| Method | Endpoint          | Auth | Description                     |
|--------|-------------------|------|---------------------------------|
| GET    | `/{quiz_id}`      | Yes  | Ranked results for a quiz       |
| GET    | `/user/{user_id}` | Yes  | All quiz results for a user     |

---

## How the Quiz Flow Works

```
1. POST /api/v1/auth/login
        → returns access_token

2. POST /api/v1/questions/start-session/{quiz_id}
        → returns session_id + first question

3. POST /api/v1/answers/submit
        body: { "session_id": 1, "question_id": 1, "selected_options": ["a"] }
        → returns { is_correct, marks_obtained }

4. GET /api/v1/questions/next/{session_id}?current_question_number=1
        → returns next question
          (repeat steps 3 and 4 for each question)

5. After the last question, /next returns:
        { "status": "completed", "result": { total_score, passed, correct_answers, ... } }

6. GET /api/v1/leaderboard/{quiz_id}
        → shows ranked entries for all completed sessions
```

---

## Authentication

All protected endpoints require:
```
Authorization: Bearer <token>
```

Tokens are HS256-signed JWTs, expire in 30 minutes.  
The Swagger UI at `/docs` has an **Authorize** button to paste the token globally for testing.

---

## Setup & Run

```bash
# 1. Activate virtual environment
.venv\Scripts\activate            # Windows
source .venv/bin/activate         # Linux / Mac

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
copy .env.example .env
# Edit .env — set DATABASE_URL and SECRET_KEY

# 4. Create tables
python scripts/create_tables.py

# 5. (Optional) Seed sample data
python init_sample_data.py
# Creates: admin@example.com / admin123
#          user0@example.com / password123

# 6. Start server
uvicorn app.main:app --reload
# API:  http://localhost:8000
# Docs: http://localhost:8000/docs
```

---

## Environment Variables (`.env`)

| Variable                       | Example                                           |
|--------------------------------|---------------------------------------------------|
| `DATABASE_URL`                 | `postgresql://user:pass@localhost:5432/live_quiz` |
| `SECRET_KEY`                   | `change-this-to-a-long-random-string`             |
| `ACCESS_TOKEN_EXPIRE_MINUTES`  | `30`                                              |
| `DEBUG`                        | `True`                                            |

---

## WebSocket

Real-time events at:
```
ws://localhost:8000/ws/quiz/{session_id}/{user_id}
```
Supports live answer broadcasts, active participant count, and ping/pong keep-alive.
