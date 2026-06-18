// ============================================================================
//  Live Quiz — Frontend
// ============================================================================

// ---- State -----------------------------------------------------------------

const S = {
  token:   localStorage.getItem('lq_token')                    || null,
  user:    JSON.parse(localStorage.getItem('lq_user') || 'null'),
  screen:  'auth',
  quizzes: [],
  quiz:    null,     // current Quiz object
  session: null,     // {session_id, quiz_id, quiz_status, session_status}
  question:null,     // question object from /questions/current
  qNumber: 0,
  selected:null,     // 'a' | 'b' | 'c' | 'd'
  answered:false,
  timerVal:0,
  totalTime:30,
  _timerIv:  null,
  _syncIv:   null,
  _pollIv:   null,
  _adminRefIv: null,
  ws: null,
};

// ---- HTTP helpers ----------------------------------------------------------

async function api(method, path, body) {
  try {
    const r = await fetch(path, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...(S.token ? { Authorization: `Bearer ${S.token}` } : {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
    const data = await r.json();
    if (!r.ok) {
      if (r.status === 401) { logout(); return null; }
      throw new Error(data.detail || `HTTP ${r.status}`);
    }
    return data;
  } catch (e) {
    toast(e.message, 'error');
    return null;
  }
}

const GET  = (p)    => api('GET',  p);
const POST = (p, b) => api('POST', p, b);

// ---- Toast -----------------------------------------------------------------

function toast(msg, type = '') {
  const el = document.createElement('div');
  el.className = 'toast' + (type ? ` toast-${type}` : '');
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3800);
}

// ---- Navigation ------------------------------------------------------------

function showScreen(name) {
  document.querySelectorAll('.screen').forEach(s => s.classList.add('hidden'));
  const el = document.getElementById(`screen-${name}`);
  if (el) el.classList.remove('hidden');
  S.screen = name;
  const nav = document.getElementById('nav');
  if (name === 'auth') nav.classList.add('hidden');
  else               nav.classList.remove('hidden');
}

function updateNav() {
  if (!S.user) return;
  document.getElementById('nav-username').textContent = S.user.username;
  const rb = document.getElementById('nav-role');
  rb.className = `badge badge-${S.user.role}`;
  rb.textContent = S.user.role;
}

// ---- Auth ------------------------------------------------------------------

async function login(email, password) {
  const data = await POST('/api/v1/auth/login', { email, password });
  if (!data) return;
  S.token = data.access_token;
  S.user  = data.user;
  localStorage.setItem('lq_token', S.token);
  localStorage.setItem('lq_user',  JSON.stringify(S.user));
  updateNav();
  afterLogin();
}

async function register(email, username, password, role) {
  const data = await POST('/api/v1/auth/register', { email, username, password, role });
  if (!data) return;
  toast('Registered! Logging in...', 'success');
  await login(email, password);
}

function logout() {
  S.token = null; S.user = null;
  localStorage.removeItem('lq_token');
  localStorage.removeItem('lq_user');
  stopAll();
  wsDisconnect();
  S.quiz = null; S.session = null;
  showScreen('auth');
}

function afterLogin() {
  updateNav();
  if (S.user.role === 'admin') { showScreen('admin'); loadAdmin('quizzes'); }
  else                         { showScreen('pdash'); loadDash(); }
}

// ---- Stop all intervals ----------------------------------------------------

function stopAll() {
  [S._timerIv, S._syncIv, S._pollIv, S._adminRefIv].forEach(iv => { if (iv) clearInterval(iv); });
  S._timerIv = S._syncIv = S._pollIv = S._adminRefIv = null;
}

// ---- Participant dashboard -------------------------------------------------

async function loadDash() {
  stopAll();
  showScreen('pdash');
  const quizzes = await GET('/api/v1/quizzes/');
  if (!quizzes) return;
  S.quizzes = quizzes;

  const list = document.getElementById('pdash-list');
  if (!quizzes.length) {
    list.innerHTML = '<p style="text-align:center;padding:2rem;color:var(--muted)">No quizzes available yet.</p>';
    return;
  }

  list.innerHTML = quizzes.map(q => `
    <div class="quiz-card">
      <div class="quiz-card-info">
        <div class="quiz-card-title">${esc(q.title)}</div>
        <div class="quiz-card-meta">${q.total_questions} questions &nbsp;•&nbsp; ${q.question_duration}s each &nbsp;•&nbsp; Pass: ${q.pass_marks}/${q.total_questions * q.marks_per_question} pts</div>
      </div>
      <div class="quiz-card-actions">
        <span class="badge badge-${q.quiz_status}">${q.quiz_status}</span>
        ${q.quiz_status !== 'ended'
          ? `<button class="btn btn-primary btn-sm" onclick="joinQuiz(${q.id})">Join Quiz</button>`
          : `<span style="font-size:.8rem;color:var(--muted)">Ended</span>`}
      </div>
    </div>
  `).join('');
}

async function joinQuiz(quizId) {
  S.quiz = S.quizzes.find(q => q.id === quizId) || { id: quizId };
  const data = await POST(`/api/v1/questions/join/${quizId}`);
  if (!data) return;
  S.session = data;
  wsConnect(quizId);

  if (data.quiz_status === 'active') {
    await goQuiz();
  } else if (data.quiz_status === 'pending') {
    goWaiting();
  } else {
    toast('Quiz has already ended', 'error');
  }
}

// ---- Waiting room ----------------------------------------------------------

function goWaiting() {
  stopAll();
  showScreen('waiting');
  $('waiting-title').textContent = S.quiz?.title || 'Quiz';

  // Poll quiz list every 3s as fallback if WS misses the start
  S._pollIv = setInterval(async () => {
    const qs = await GET('/api/v1/quizzes/');
    if (!qs) return;
    const q = qs.find(x => x.id === S.quiz.id);
    if (!q) return;
    S.quiz = q;
    if (q.quiz_status === 'active')  { clearInterval(S._pollIv); await goQuiz(); }
    if (q.quiz_status === 'ended')   { clearInterval(S._pollIv); fetchResultsAndShow(); }
  }, 3000);
}

// ---- Live quiz screen ------------------------------------------------------

async function goQuiz() {
  stopAll();
  showScreen('quiz');
  $('quiz-title-label').textContent = S.quiz?.title || 'Quiz';
  await syncQuestion();
  S._syncIv = setInterval(syncQuestion, 4000);
}

async function syncQuestion() {
  if (!S.session) return;
  const data = await GET(`/api/v1/questions/current/${S.session.session_id}`);
  if (!data) return;

  if (data.status === 'waiting') { goWaiting(); return; }

  if (data.status === 'ended') {
    stopAll();
    data.result ? showResults(data.result) : fetchResultsAndShow();
    return;
  }

  // Active — re-render only when question changes
  const newNum = data.question_number;
  if (newNum !== S.qNumber) {
    S.qNumber  = newNum;
    S.question = data.question;
    S.selected = null;
    S.answered = data.already_answered;
    renderQuestion(data);
    setTimer(data.time_remaining);
  } else if (data.already_answered && !S.answered) {
    S.answered = true;
    showAnswered();
  }
}

function renderQuestion(data) {
  const q = data.question;
  $('quiz-progress').textContent = `Q ${data.question_number} / ${data.total_questions}`;
  $('q-text').textContent = q.question_text;

  $('opts').innerHTML = ['a','b','c','d'].map(k => `
    <button class="opt-btn${S.selected === k ? ' sel' : ''}${S.answered ? ' done' : ''}"
            id="opt-${k}"
            onclick="${S.answered ? '' : `pickOpt('${k}')`}">
      <span class="opt-key">${k.toUpperCase()}</span>
      <span>${esc(q['option_'+k])}</span>
    </button>
  `).join('');

  $('submit-btn').classList.toggle('hidden', S.answered);
  $('submit-btn').disabled = !S.selected;
  $('answered-msg').classList.toggle('hidden', !S.answered);
}

function pickOpt(k) {
  if (S.answered) return;
  S.selected = k;
  document.querySelectorAll('.opt-btn').forEach(b => b.classList.remove('sel'));
  const btn = $(`opt-${k}`);
  if (btn) { btn.classList.add('sel'); btn.querySelector('.opt-key').style.background='var(--primary)'; btn.querySelector('.opt-key').style.color='#fff'; }
  $('submit-btn').disabled = false;
}

async function doSubmit() {
  if (!S.selected || S.answered || !S.question) return;
  const btn = $('submit-btn');
  btn.disabled = true;
  btn.textContent = 'Submitting...';

  const data = await POST('/api/v1/answers/submit', {
    session_id:       S.session.session_id,
    question_id:      S.question.id,
    selected_options: [S.selected],
  });

  if (!data) { btn.disabled = false; btn.textContent = 'Submit Answer'; return; }

  S.answered = true;
  showAnswered();
  toast(data.is_correct ? `✓ Correct! +${data.marks_obtained} marks` : '✗ Wrong. Next question soon.', data.is_correct ? 'success' : '');
}

function showAnswered() {
  $('submit-btn').classList.add('hidden');
  $('answered-msg').classList.remove('hidden');
  document.querySelectorAll('.opt-btn').forEach(b => b.classList.add('done'));
}

// ---- Timer -----------------------------------------------------------------

function setTimer(secs) {
  S.timerVal  = secs;
  S.totalTime = S.quiz?.question_duration || 30;
  if (S._timerIv) clearInterval(S._timerIv);
  drawTimer();
  S._timerIv = setInterval(() => {
    S.timerVal = Math.max(0, S.timerVal - 1);
    drawTimer();
    if (S.timerVal === 0) { clearInterval(S._timerIv); S._timerIv = null; }
  }, 1000);
}

function drawTimer() {
  const v   = S.timerVal;
  const pct = (v / S.totalTime) * 100;
  const el  = $('timer-num');
  const bar = $('timer-fill');
  if (!el || !bar) return;
  el.textContent  = `${pad(Math.floor(v/60))}:${pad(v%60)}`;
  bar.style.width = `${pct}%`;
  const cls = v > 15 ? 't-ok' : v > 7 ? 't-mid' : 't-low';
  el.className = `timer-num ${cls}`;
  bar.style.background = v > 15 ? 'var(--primary)' : v > 7 ? 'var(--warning)' : 'var(--danger)';
}

// ---- Results ---------------------------------------------------------------

async function fetchResultsAndShow() {
  if (!S.session) return;
  const data = await GET(`/api/v1/questions/current/${S.session.session_id}`);
  if (!data) return;
  if (data.result) showResults(data.result);
  else {
    stopAll(); wsDisconnect(); showScreen('results');
    $('results-body').innerHTML = `
      <p style="color:var(--muted);margin-bottom:1rem">Calculating results...</p>
      <button class="btn btn-primary" onclick="loadDash()">Back to Dashboard</button>`;
  }
}

function showResults(r) {
  stopAll(); wsDisconnect(); showScreen('results');
  const pct = r.total_marks ? Math.round((r.total_score / r.total_marks) * 100) : 0;
  $('results-body').innerHTML = `
    <div class="results-card">
      <div style="font-size:.875rem;color:var(--muted);margin-bottom:.25rem">${esc(S.quiz?.title || 'Quiz')}</div>
      <h2 style="margin-bottom:.5rem">Quiz Complete!</h2>
      <div class="results-score ${r.passed ? 'score-pass' : 'score-fail'}">${r.total_score} / ${r.total_marks}</div>
      <div class="${r.passed ? 'result-badge-pass' : 'result-badge-fail'}">${r.passed ? '🎉 PASSED' : '✗ FAILED'}</div>
      <div class="stats-grid">
        <div class="stat-box"><div class="stat-val">${r.correct_answers}</div><div class="stat-lbl">Correct</div></div>
        <div class="stat-box"><div class="stat-val">${r.total_questions}</div><div class="stat-lbl">Questions</div></div>
        <div class="stat-box"><div class="stat-val">${pct}%</div><div class="stat-lbl">Score %</div></div>
        <div class="stat-box"><div class="stat-val">${r.pass_marks}</div><div class="stat-lbl">Pass mark</div></div>
      </div>
      <button class="btn btn-primary btn-full" onclick="loadDash()">Back to Dashboard</button>
    </div>`;
}

// ---- WebSocket -------------------------------------------------------------

function wsConnect(quizId) {
  wsDisconnect();
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  S.ws = new WebSocket(`${proto}://${location.host}/ws/quiz/${quizId}/${S.user.id}`);
  S.ws.onmessage = e => onWS(JSON.parse(e.data));
  S.ws.onopen    = () => setWsDot(true, '...');
  S.ws.onclose   = () => {
    setWsDot(false);
    setTimeout(() => {
      if (S.quiz && (S.screen==='waiting'||S.screen==='quiz')) wsConnect(S.quiz.id);
    }, 3000);
  };
  S.ws.onerror = () => setWsDot(false);
}

function wsDisconnect() {
  if (!S.ws) return;
  S.ws.onclose = null;
  S.ws.close();
  S.ws = null;
}

function onWS(msg) {
  switch (msg.type) {
    case 'connected':
      setWsDot(true, msg.participants_online);
      break;

    case 'quiz_started':
      toast('Quiz is live!', 'success');
      if (S.screen === 'waiting') { clearInterval(S._pollIv); goQuiz(); }
      break;

    case 'question':
      if (S.screen === 'quiz') {
        S.qNumber  = msg.question_number;
        S.question = msg.question;
        S.selected = null;
        S.answered = false;
        renderQuestion({ ...msg, already_answered: false });
        setTimer(msg.time_remaining || S.quiz?.question_duration || 30);
      }
      break;

    case 'quiz_ended':
      toast('Quiz ended!');
      if (S.screen === 'quiz' || S.screen === 'waiting') fetchResultsAndShow();
      break;

    case 'status':
      setWsDot(true, msg.participants_online);
      break;
  }
}

function setWsDot(live, count) {
  const dot = $('ws-dot'); const txt = $('ws-txt');
  if (!dot || !txt) return;
  dot.className = 'ws-dot' + (live ? ' live' : '');
  txt.textContent = live ? `Live · ${count ?? '?'} online` : 'Reconnecting...';
}

// ---- Admin -----------------------------------------------------------------

let _aTab = 'quizzes';

async function loadAdmin(tab) {
  if (tab) _aTab = tab;
  showScreen('admin');
  document.querySelectorAll('.a-tab').forEach(t => t.classList.remove('active'));
  document.querySelector(`.a-tab[data-tab="${_aTab}"]`)?.classList.add('active');
  if (_aTab === 'quizzes')  await adminQuizzes();
  if (_aTab === 'sessions') await adminSessions();
}

async function adminQuizzes() {
  const qs = await GET('/api/v1/quizzes/');
  if (!qs) return;
  S.quizzes = qs;
  const c = $('admin-content');
  if (!qs.length) { c.innerHTML = '<p style="text-align:center;padding:2rem;color:var(--muted)">No quizzes yet. Create one!</p>'; return; }
  c.innerHTML = `<div class="quiz-grid">${qs.map(q => `
    <div class="quiz-card">
      <div class="quiz-card-info">
        <div class="quiz-card-title">${esc(q.title)}</div>
        <div class="quiz-card-meta">${q.total_questions} Q · ${q.question_duration}s each · Total ${q.total_questions * q.question_duration}s${q.started_at ? ` · Started ${timeStr(q.started_at)}` : ''}</div>
      </div>
      <div class="quiz-card-actions">
        <span class="badge badge-${q.quiz_status}">${q.quiz_status}</span>
        ${q.quiz_status === 'pending' ? `<button class="btn btn-success btn-sm" onclick="adminStart(${q.id})">▶ Start</button>` : ''}
        ${q.quiz_status === 'active'  ? `<button class="btn btn-ghost btn-sm" onclick="loadAdmin('sessions')">Live View</button>` : ''}
      </div>
    </div>`).join('')}</div>`;
}

async function adminStart(quizId) {
  const q = S.quizzes.find(x => x.id === quizId);
  if (!confirm(`Start "${q?.title}"?\n\nAll joined participants will receive the quiz simultaneously.`)) return;
  const data = await POST(`/api/v1/quizzes/${quizId}/start`);
  if (!data) return;
  toast(`Quiz started! ${data.waiting_participants_activated} participant(s) activated.`, 'success');
  await adminQuizzes();
}

async function adminSessions() {
  const rows = await GET('/api/v1/quizzes/sessions/all');
  if (!rows) return;
  const c = $('admin-content');
  if (!rows.length) { c.innerHTML = '<p style="text-align:center;padding:2rem;color:var(--muted)">No sessions yet.</p>'; return; }
  c.innerHTML = `
    <div style="display:flex;justify-content:flex-end;margin-bottom:.75rem">
      <button class="btn btn-ghost btn-sm" onclick="adminSessions()">↻ Refresh</button>
    </div>
    <div style="overflow-x:auto">
      <table class="tbl">
        <thead><tr>
          <th>#</th><th>Participant</th><th>Quiz</th><th>Status</th><th>Score</th><th>Pass</th><th>Time</th>
        </tr></thead>
        <tbody>${rows.map(s => `
          <tr>
            <td style="color:var(--muted)">${s.session_id}</td>
            <td><strong>${esc(s.username)}</strong></td>
            <td>${esc(s.quiz_title)} <span class="badge badge-${s.quiz_status}" style="font-size:.65rem">${s.quiz_status}</span></td>
            <td><span class="badge badge-${s.status}">${s.status}</span></td>
            <td>${s.total_score ?? '—'}</td>
            <td>${s.passed === null ? '—' : s.passed ? '<span style="color:var(--success)">✓</span>' : '<span style="color:var(--danger)">✗</span>'}</td>
            <td style="font-size:.8125rem;color:var(--muted)">${s.started_at ? timeStr(s.started_at) : '—'}</td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}

// ---- Create Quiz modal -----------------------------------------------------

let _questions = [];

function initQuestions() {
  _questions = [1,2,3].map(() => ({ text:'', a:'', b:'', c:'', d:'', correct:'a' }));
  renderQBuilders();
}

function renderQBuilders() {
  $('q-builder').innerHTML = _questions.map((q, i) => `
    <div class="qb">
      <div class="qb-top">
        <span>Question ${i+1}</span>
        <button class="btn btn-danger btn-sm" onclick="removeQ(${i})">Remove</button>
      </div>
      <div class="form-group" style="margin-bottom:.5rem">
        <input type="text" placeholder="Question text..." value="${esc(q.text)}"
               oninput="_questions[${i}].text=this.value" />
      </div>
      <div class="opts-2col">${['a','b','c','d'].map(k => `
        <div class="opt-row">
          <span class="opt-letter">${k.toUpperCase()}</span>
          <input type="text" placeholder="Option ${k.toUpperCase()}" value="${esc(q[k])}"
                 oninput="_questions[${i}]['${k}']=this.value" />
        </div>`).join('')}
      </div>
      <div class="form-group" style="margin-top:.625rem;margin-bottom:0">
        <label>Correct answer</label>
        <select onchange="_questions[${i}].correct=this.value">
          ${['a','b','c','d'].map(k=>`<option value="${k}"${q.correct===k?' selected':''}>${k.toUpperCase()}</option>`).join('')}
        </select>
      </div>
    </div>`).join('');
}

function addQ() {
  _questions.push({ text:'', a:'', b:'', c:'', d:'', correct:'a' });
  renderQBuilders();
}

function removeQ(i) {
  if (_questions.length <= 1) { toast('Need at least 1 question'); return; }
  _questions.splice(i, 1);
  renderQBuilders();
}

function openModal() {
  initQuestions();
  $('create-modal').classList.remove('hidden');
}

function closeModal() { $('create-modal').classList.add('hidden'); }

async function submitQuiz() {
  const title    = $('cq-title').value.trim();
  const desc     = $('cq-desc').value.trim();
  const duration = parseInt($('cq-duration').value) || 30;
  const passM    = parseInt($('cq-pass').value)     || 14;

  if (!title) { toast('Enter a quiz title', 'error'); return; }
  const bad = _questions.findIndex(q => !q.text || !q.a || !q.b || !q.c || !q.d);
  if (bad !== -1) { toast(`Q${bad+1}: fill in all fields`, 'error'); return; }

  const payload = {
    title, description: desc,
    total_questions:    _questions.length,
    marks_per_question: 2,
    pass_marks:         passM,
    question_duration:  duration,
    questions: _questions.map((q, i) => ({
      question_text:   q.text,
      option_a: q.a,  option_b: q.b,  option_c: q.c,  option_d: q.d,
      correct_options: [q.correct],
      is_multiselect:  false,
      question_number: i+1,
    })),
  };

  const data = await POST('/api/v1/quizzes/', payload);
  if (!data) return;
  toast(`Quiz "${data.title}" created!`, 'success');
  closeModal();
  await adminQuizzes();
}

// ---- Auth form toggling ----------------------------------------------------

let _authTab = 'login';

function switchTab(t) {
  _authTab = t;
  ['login','register'].forEach(x => {
    $(`tab-${x}`).classList.toggle('active', x===t);
    $(`form-${x}`).classList.toggle('hidden', x!==t);
  });
}

async function handleLogin(e) {
  e.preventDefault();
  const btn = e.target.querySelector('[type=submit]');
  btn.disabled = true; btn.textContent = 'Logging in...';
  try { await login($('login-email').value, $('login-password').value); }
  finally { btn.disabled = false; btn.textContent = 'Login'; }
}

async function handleRegister(e) {
  e.preventDefault();
  const btn = e.target.querySelector('[type=submit]');
  btn.disabled = true; btn.textContent = 'Registering...';
  try { await register($('reg-email').value, $('reg-username').value, $('reg-password').value, $('reg-role').value); }
  finally { btn.disabled = false; btn.textContent = 'Register'; }
}

// ---- Helpers ---------------------------------------------------------------

const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const pad = n => String(n).padStart(2,'0');
const timeStr = iso => new Date(iso).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'});

// ---- Boot ------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  initQuestions();

  $('tab-login').onclick    = () => switchTab('login');
  $('tab-register').onclick = () => switchTab('register');

  if (S.token && S.user) { updateNav(); afterLogin(); }
  else showScreen('auth');
});
