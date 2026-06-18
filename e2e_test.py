"""
End-to-end test for the Live Quiz synchronized flow.
Simulates: admin creates quiz, 2 participants join, admin starts,
both participants answer every question, results are checked.
Run with: python e2e_test.py
"""

import requests, json, time, sys, threading
from datetime import datetime

BASE = "http://127.0.0.1:8000"
PASS = "Test@1234"

RESULTS = {"admin": None, "p1": None, "p2": None}
ERRORS  = []

# ── helpers ─────────────────────────────────────────────────────────────────

def ts():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

def ok(label, resp):
    if resp.status_code not in (200, 201):
        msg = f"FAIL [{label}] {resp.status_code}: {resp.text[:200]}"
        ERRORS.append(msg)
        print(f"  [FAIL] {label} -> {resp.status_code} {resp.text[:120]}")
        return None
    print(f"  [OK]   {label}")
    return resp.json()

def post(path, body, token=None):
    hdrs = {"Authorization": f"Bearer {token}"} if token else {}
    return requests.post(BASE + path, json=body, headers=hdrs, timeout=10)

def get(path, token=None):
    hdrs = {"Authorization": f"Bearer {token}"} if token else {}
    return requests.get(BASE + path, headers=hdrs, timeout=10)

def register_login(email, username, role):
    post(f"/api/v1/auth/register", {"email": email, "username": username,
                                     "password": PASS, "role": role})
    r = post("/api/v1/auth/login", {"email": email, "password": PASS})
    data = ok(f"login {username}", r)
    if not data:
        return None, None
    return data["access_token"], data["user"]

# ── sample quiz payload ──────────────────────────────────────────────────────

QUIZ_PAYLOAD = {
    "title": "E2E Test Quiz",
    "description": "Automated test",
    "total_questions": 3,
    "marks_per_question": 2,
    "pass_marks": 4,
    "question_duration": 6,   # 6 seconds per Q so test finishes fast
    "questions": [
        {"question_text": "1+1 = ?",
         "option_a": "1", "option_b": "2", "option_c": "3", "option_d": "4",
         "correct_options": ["b"], "is_multiselect": False, "question_number": 1},
        {"question_text": "2+2 = ?",
         "option_a": "3", "option_b": "4", "option_c": "5", "option_d": "6",
         "correct_options": ["b"], "is_multiselect": False, "question_number": 2},
        {"question_text": "3+3 = ?",
         "option_a": "5", "option_b": "6", "option_c": "7", "option_d": "8",
         "correct_options": ["b"], "is_multiselect": False, "question_number": 3},
    ]
}

# ── participant worker ───────────────────────────────────────────────────────

def run_participant(label, token, quiz_id):
    """Join, poll for questions, answer all, collect result."""
    try:
        # --- Join ---
        r = post(f"/api/v1/questions/join/{quiz_id}", {}, token)
        d = ok(f"  [{label}] join", r)
        if not d:
            return
        session_id = d["session_id"]
        print(f"    [{label}] session_id={session_id}  quiz_status={d['quiz_status']}")

        answered = set()
        last_q   = None
        deadline = time.time() + 60   # overall timeout

        while time.time() < deadline:
            r2 = get(f"/api/v1/questions/current/{session_id}", token)
            if r2.status_code != 200:
                print(f"    [{label}] current -> {r2.status_code}"); time.sleep(1); continue

            data = r2.json()
            status = data.get("status")

            if status == "waiting":
                time.sleep(0.5); continue

            if status == "ended":
                result = data.get("result")
                if result:
                    RESULTS[label] = result
                    print(f"    [{label}] DONE  score={result['total_score']}/{result['total_marks']}  passed={result['passed']}")
                return

            if status == "active":
                q_num = data["question_number"]
                q_id  = data["question"]["id"]

                if q_num != last_q:
                    last_q = q_num
                    print(f"    [{label}] Q{q_num}: {data['question']['question_text'][:40]}  time_left={data['time_remaining']}s")

                if q_id not in answered and not data.get("already_answered"):
                    ar = post("/api/v1/answers/submit",
                              {"session_id": session_id, "question_id": q_id, "selected_options": ["b"]},
                              token)
                    if ar.status_code == 200:
                        ans = ar.json()
                        answered.add(q_id)
                        print(f"    [{label}] answered Q{q_num}  correct={ans['is_correct']}  marks={ans['marks_obtained']}")
                    else:
                        detail = ar.json().get("detail","")
                        if "already" not in detail.lower():
                            print(f"    [{label}] submit failed: {detail}")
                        answered.add(q_id)

            time.sleep(0.8)

        print(f"  [FAIL] [{label}] timed out")
        ERRORS.append(f"{label} timed out")

    except Exception as e:
        ERRORS.append(f"{label} exception: {e}")
        print(f"  [FAIL] [{label}] exception: {e}")

# ── main test sequence ───────────────────────────────────────────────────────

def main():
    print(f"\n{'='*58}")
    print(f"  LIVE QUIZ  end-to-end test   {ts()}")
    print(f"{'='*58}\n")

    # ── 1. Register / login ──────────────────────────────────────
    print("[1] Auth — register & login")
    suffix = int(time.time()) % 100000
    admin_tok,  admin_user  = register_login(f"admin_{suffix}@test.com",  f"admin_{suffix}",  "admin")
    p1_tok,     p1_user     = register_login(f"p1_{suffix}@test.com",     f"p1_{suffix}",     "participant")
    p2_tok,     p2_user     = register_login(f"p2_{suffix}@test.com",     f"p2_{suffix}",     "participant")

    if not all([admin_tok, p1_tok, p2_tok]):
        print("\n[ABORT] Auth failed"); return 1

    # ── 2. Admin creates quiz ────────────────────────────────────
    print("\n[2] Admin — create quiz")
    r = post("/api/v1/quizzes/", QUIZ_PAYLOAD, admin_tok)
    quiz = ok("create quiz", r)
    if not quiz:
        print("[ABORT] quiz creation failed"); return 1
    quiz_id = quiz["id"]
    print(f"  quiz_id={quiz_id}  status={quiz['quiz_status']}  duration={quiz['question_duration']}s/Q")

    # ── 3. Participants join ─────────────────────────────────────
    print("\n[3] Participants join (before start)")
    for tok, lbl in [(p1_tok,"p1"),(p2_tok,"p2")]:
        r = post(f"/api/v1/questions/join/{quiz_id}", {}, tok)
        d = ok(f"  [{lbl}] join", r)
        if d:
            print(f"    session_id={d['session_id']}  quiz_status={d['quiz_status']}  session_status={d['session_status']}")

    # ── 4. Verify GET /quizzes lists the quiz ────────────────────
    print("\n[4] GET /quizzes/ (admin)")
    r = get("/api/v1/quizzes/", admin_tok)
    qs = ok("list quizzes", r)
    found = next((q for q in (qs or []) if q["id"]==quiz_id), None)
    if found:
        print(f"  quiz '{found['title']}'  status={found['quiz_status']}")
    else:
        ERRORS.append("quiz not in list")
        print("  [FAIL] quiz not found in list")

    # ── 5. Admin views sessions ──────────────────────────────────
    print("\n[5] GET /sessions/active (admin)")
    r = get("/api/v1/quizzes/sessions/active", admin_tok)
    sess = ok("sessions/active", r)
    if sess is not None:
        print(f"  waiting sessions: {len(sess)}")

    # ── 6. Start participant threads BEFORE admin starts ─────────
    print("\n[6] Launch participant threads (they will wait for quiz to go active)")
    t1 = threading.Thread(target=run_participant, args=("p1", p1_tok, quiz_id), daemon=True)
    t2 = threading.Thread(target=run_participant, args=("p2", p2_tok, quiz_id), daemon=True)
    t1.start(); t2.start()
    time.sleep(0.5)   # let threads reach the waiting-poll stage

    # ── 7. Admin starts the quiz ─────────────────────────────────
    print(f"\n[7] Admin starts quiz {quiz_id}")
    r = post(f"/api/v1/quizzes/{quiz_id}/start", {}, admin_tok)
    d = ok("start quiz", r)
    if d:
        print(f"  started_at={d['started_at']}  ends_at={d['ends_at']}")
        print(f"  waiting_participants_activated={d['waiting_participants_activated']}")

    # ── 8. Wait for both participants to finish ──────────────────
    total_duration = QUIZ_PAYLOAD["total_questions"] * QUIZ_PAYLOAD["question_duration"]
    wait_secs = total_duration + 8
    print(f"\n[8] Waiting up to {wait_secs}s for quiz to complete...")
    t1.join(timeout=wait_secs)
    t2.join(timeout=wait_secs)

    # ── 9. Admin checks sessions ─────────────────────────────────
    print("\n[9] GET /sessions/all (admin)")
    r = get("/api/v1/quizzes/sessions/all", admin_tok)
    all_sess = ok("sessions/all", r)
    this_quiz_sessions = [s for s in (all_sess or []) if s["quiz_id"] == quiz_id]
    print(f"  sessions for this quiz: {len(this_quiz_sessions)}")
    for s in this_quiz_sessions:
        print(f"    {s['username']:15}  {s['status']:10}  score={s['total_score']}  passed={s['passed']}")

    # ── 10. Leaderboard ──────────────────────────────────────────
    print(f"\n[10] GET /leaderboard/{quiz_id}")
    r = get(f"/api/v1/leaderboard/{quiz_id}", p1_tok)
    lb = ok("leaderboard", r)
    if lb and lb.get("entries"):
        for e in lb["entries"]:
            print(f"    #{e['rank']}  {e['username']:15}  {e['score']}  passed={e['passed']}")
    else:
        print("  (no completed sessions yet or empty leaderboard)")

    # ── 11. Summary ──────────────────────────────────────────────
    print(f"\n{'='*58}")
    print("  RESULTS")
    print(f"{'='*58}")
    for who, res in RESULTS.items():
        if res:
            print(f"  {who:4}  score={res['total_score']}/{res['total_marks']}  "
                  f"correct={res['correct_answers']}/{res['total_questions']}  passed={res['passed']}")

    print()
    if ERRORS:
        print(f"  FAILURES ({len(ERRORS)}):")
        for e in ERRORS:
            print(f"    - {e}")
        print()
        return 1
    else:
        print("  ALL CHECKS PASSED")
        print()
        return 0

if __name__ == "__main__":
    sys.exit(main())
