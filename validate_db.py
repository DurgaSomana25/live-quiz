"""
DB validation — checks every row for data consistency.
Run: python validate_db.py
"""
import json, sys
from app.database import SessionLocal
from app.models import User, Quiz, Question, QuizSession, Answer

db     = SessionLocal()
errors = []
passed = 0

def chk(cond, msg):
    global passed
    if cond:
        passed += 1
    else:
        errors.append(msg)
    return cond

print("=" * 62)
print("  DB VALIDATION")
print("=" * 62)

# ── 1. Users ────────────────────────────────────────────────────
users = db.query(User).all()
print(f"\n[Users]  {len(users)} rows")
for u in users:
    chk(bool(u.email and "@" in u.email), f"User id={u.id} bad email")
    chk(bool(u.username),                 f"User id={u.id} missing username")
    chk(bool(u.hashed_password),          f"User id={u.id} missing password hash")
    chk(u.role.value in ("admin", "participant"), f"User id={u.id} bad role: {u.role}")
    print(f"  id={u.id:<3} {u.email:<30} role={u.role.value:<13} active={u.is_active}")

# ── 2. Quizzes ──────────────────────────────────────────────────
quizzes = db.query(Quiz).all()
print(f"\n[Quizzes]  {len(quizzes)} rows")
for q in quizzes:
    qs_count = db.query(Question).filter(Question.quiz_id == q.id).count()
    nums = [x.question_number for x in db.query(Question).filter(Question.quiz_id == q.id).all()]
    expected_nums = list(range(1, qs_count + 1))

    chk(qs_count == q.total_questions,
        f"Quiz id={q.id} declares {q.total_questions} questions but DB has {qs_count}")
    chk(q.quiz_status in ("pending", "active", "ended"),
        f"Quiz id={q.id} bad status: {q.quiz_status}")
    chk(q.question_duration > 0,
        f"Quiz id={q.id} bad question_duration: {q.question_duration}")
    chk(sorted(nums) == expected_nums,
        f"Quiz id={q.id} question_numbers not sequential: {sorted(nums)}")

    max_marks = q.total_questions * q.marks_per_question
    print(f"  id={q.id}  {q.title:<28} status={q.quiz_status:<8} "
          f"Qs={qs_count}/{q.total_questions}  max_marks={max_marks}  duration={q.question_duration}s")

# ── 3. Questions ────────────────────────────────────────────────
questions = db.query(Question).all()
print(f"\n[Questions]  {len(questions)} rows")
q_errors = 0
for q in questions:
    bad = []
    for field in ("question_text", "option_a", "option_b", "option_c", "option_d", "correct_options"):
        if not getattr(q, field):
            bad.append(f"missing {field}")
    try:
        opts = json.loads(q.correct_options)
        chk(isinstance(opts, list) and len(opts) >= 1,
            f"Q id={q.id} correct_options not a non-empty list: {q.correct_options}")
        valid_vals = all(o in ("a", "b", "c", "d") for o in opts)
        chk(valid_vals,
            f"Q id={q.id} invalid correct_option values: {opts}")
    except Exception as e:
        errors.append(f"Q id={q.id} correct_options JSON parse error: {e}")
        q_errors += 1
    if bad:
        q_errors += 1
        errors.append(f"Q id={q.id} (quiz={q.quiz_id} #Q{q.question_number}): {bad}")

print(f"  {len(questions) - q_errors} / {len(questions)} questions valid")

# ── 4. Sessions ─────────────────────────────────────────────────
sessions = db.query(QuizSession).all()
print(f"\n[Sessions]  {len(sessions)} rows")
for s in sessions:
    user    = db.query(User).filter(User.id == s.participant_id).first()
    quiz    = db.query(Quiz).filter(Quiz.id == s.quiz_id).first()
    ans_all = db.query(Answer).filter(Answer.session_id == s.id).all()

    chk(user is not None, f"Session id={s.id} references missing user {s.participant_id}")
    chk(quiz is not None, f"Session id={s.id} references missing quiz {s.quiz_id}")
    chk(s.status in ("waiting", "ongoing", "completed", "abandoned"),
        f"Session id={s.id} bad status: {s.status}")

    computed = round(sum(a.marks_obtained for a in ans_all), 4)
    stored   = round(float(s.total_score or 0), 4)

    if s.status in ("completed", "abandoned"):
        chk(computed == stored,
            f"Session id={s.id} score mismatch: stored={stored} computed_from_answers={computed}")
        if quiz:
            expected_pass = stored >= quiz.pass_marks
            chk(s.passed == expected_pass,
                f"Session id={s.id} passed={s.passed} wrong: score={stored} pass_mark={quiz.pass_marks}")

    # No duplicate answers for the same question in one session
    qids = [a.question_id for a in ans_all]
    dupes = [x for x in set(qids) if qids.count(x) > 1]
    chk(len(dupes) == 0,
        f"Session id={s.id} duplicate answers for question id(s): {dupes}")

    uname  = user.username if user else "?"
    qtitle = (quiz.title[:18] if quiz else "?")
    max_m  = (quiz.total_questions * quiz.marks_per_question) if quiz else "?"
    print(f"  id={s.id:<3} {uname:<14} quiz={qtitle:<20} "
          f"status={s.status:<10} score={stored}/{max_m}  "
          f"passed={str(s.passed):<5} answers={len(ans_all)}")

# ── 5. Answers ──────────────────────────────────────────────────
answers_all = db.query(Answer).all()
print(f"\n[Answers]  {len(answers_all)} rows")
a_errors = 0
for a in answers_all:
    bad = []
    sess  = db.query(QuizSession).filter(QuizSession.id == a.session_id).first()
    quest = db.query(Question).filter(Question.id == a.question_id).first()

    if not sess:
        bad.append(f"dangling session_id={a.session_id}")
    if not quest:
        bad.append(f"dangling question_id={a.question_id}")

    if sess and quest:
        try:
            selected = set(json.loads(a.selected_options))
            correct  = set(json.loads(quest.correct_options))
            expected_correct = (selected == correct)
            chk(a.is_correct == expected_correct,
                f"Answer id={a.id} is_correct={a.is_correct} but selected={selected} correct={correct}")

            quiz2 = db.query(Quiz).filter(Quiz.id == sess.quiz_id).first()
            if quiz2:
                exp_marks = float(quiz2.marks_per_question) if a.is_correct else 0.0
                chk(round(a.marks_obtained, 4) == round(exp_marks, 4),
                    f"Answer id={a.id} marks={a.marks_obtained} expected={exp_marks}")
        except Exception as e:
            bad.append(f"JSON error: {e}")

    if bad:
        a_errors += 1
        errors.append(f"Answer id={a.id}: {bad}")

print(f"  {len(answers_all) - a_errors} / {len(answers_all)} answers valid")

# ── Summary ─────────────────────────────────────────────────────
print(f"\n{'=' * 62}")
print("  SUMMARY")
print(f"{'=' * 62}")
print(f"  Checks passed : {passed}")
print(f"  Errors found  : {len(errors)}")
if errors:
    print()
    for e in errors:
        print(f"  [FAIL] {e}")
    sys.exit(1)
else:
    print("  All rows consistent — DB is clean")

db.close()
