/**
 * Find the Better Move — Training PWA
 *
 * Loads pre-generated training data (from chess-self-coach train --prepare),
 * displays mistake positions on a chessground board, and uses SM-2 spaced
 * repetition to schedule reviews.
 */

// --- State ---
let Chessground, Chess;
let trainingData = null;
let srsState = {};
let session = [];
let currentIndex = 0;
let attempts = 0;
let sessionResults = [];
let cg = null;

// --- Settings ---
const DEFAULT_SETTINGS = { sessionSize: 10, difficulty: 'all' };

function loadSettings() {
  try {
    return { ...DEFAULT_SETTINGS, ...JSON.parse(localStorage.getItem('train_settings') || '{}') };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

function saveSettings(s) {
  localStorage.setItem('train_settings', JSON.stringify(s));
}

// --- SRS (SM-2 algorithm) ---

function updateSRS(state, correct) {
  const quality = correct ? 4 : 1;
  let { interval = 0, ease = 2.5, repetitions = 0, history = [] } = state;

  if (correct) {
    if (repetitions === 0) interval = 1;
    else if (repetitions === 1) interval = 3;
    else interval = Math.round(interval * ease);
    repetitions++;
  } else {
    interval = 1;
    repetitions = 0;
  }

  ease = ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02));
  ease = Math.max(1.3, ease);

  const nextDate = new Date();
  nextDate.setDate(nextDate.getDate() + interval);

  return {
    interval,
    ease: Math.round(ease * 100) / 100,
    repetitions,
    next_review: nextDate.toISOString().split('T')[0],
    history: [...history, { date: new Date().toISOString().split('T')[0], correct }],
  };
}

function loadSRSState() {
  try {
    return JSON.parse(localStorage.getItem('train_srs') || '{}');
  } catch {
    return {};
  }
}

function saveSRSState() {
  localStorage.setItem('train_srs', JSON.stringify(srsState));
}

// --- Session selection ---

function selectPositions(positions, count) {
  const today = new Date().toISOString().split('T')[0];
  const settings = loadSettings();

  // Filter by difficulty
  let filtered = positions;
  if (settings.difficulty === 'blunders') {
    filtered = positions.filter((p) => p.category === 'blunder');
  } else if (settings.difficulty === 'blunders+mistakes') {
    filtered = positions.filter((p) => p.category !== 'inaccuracy');
  }
  if (filtered.length === 0) filtered = positions;

  const overdue = [];
  const newPos = [];
  const learning = [];

  for (const pos of filtered) {
    const state = srsState[pos.id];
    if (!state) {
      newPos.push(pos);
    } else if (state.next_review <= today) {
      overdue.push(pos);
    } else if (state.interval < 7) {
      learning.push(pos);
    }
    // mastered or not yet due: skip
  }

  // Priority: overdue > new (already sorted by severity) > learning
  const selected = [];
  for (const list of [overdue, newPos, learning]) {
    for (const pos of list) {
      if (selected.length >= count) break;
      selected.push(pos);
    }
  }

  return selected;
}

// --- Board ---

function getLegalDests(fen) {
  const chess = new Chess(fen);
  const dests = new Map();
  for (const move of chess.moves({ verbose: true })) {
    if (!dests.has(move.from)) dests.set(move.from, []);
    dests.get(move.from).push(move.to);
  }
  return dests;
}

function setupBoard(position) {
  const boardEl = document.getElementById('board');
  const color = position.player_color;
  const fen = position.fen;

  if (cg) cg.destroy();

  cg = Chessground(boardEl, {
    fen,
    orientation: color,
    turnColor: color,
    movable: {
      free: false,
      color,
      dests: getLegalDests(fen),
      events: {
        after: (orig, dest) => handleMove(orig, dest),
      },
    },
    draggable: { enabled: true },
    highlight: { lastMove: true, check: true },
  });
}

function handleMove(orig, dest) {
  const position = session[currentIndex];
  const chess = new Chess(position.fen);

  // Try the move (auto-promote to queen)
  const move = chess.move({ from: orig, to: dest, promotion: 'q' });
  if (!move) return;

  const san = move.san;
  attempts++;

  if (position.acceptable_moves.includes(san) || san === position.best_move) {
    // Correct!
    showFeedback(true, position);
    recordResult(true);
  } else if (attempts >= 3) {
    // Out of attempts
    showFeedback(false, position, true);
    recordResult(false);
  } else {
    // Wrong, try again
    showTryAgain();
    setTimeout(() => setupBoard(position), 400);
  }
}

// --- Feedback ---

function showFeedback(correct, position, gaveUp = false) {
  const feedbackEl = document.getElementById('feedback');
  const feedbackText = document.getElementById('feedback-text');
  const explanationEl = document.getElementById('explanation');
  const nextBtn = document.getElementById('next-btn');

  feedbackEl.classList.remove('hidden');
  nextBtn.classList.remove('hidden');

  if (correct) {
    feedbackText.textContent = 'Correct!';
    feedbackText.className = 'correct';
  } else {
    feedbackText.textContent = gaveUp
      ? 'The answer was: ' + position.best_move
      : 'Not quite.';
    feedbackText.className = 'incorrect';

    // Show the best move on the board
    try {
      const chess = new Chess(position.fen);
      const move = chess.move(position.best_move);
      if (move && cg) {
        cg.set({
          fen: chess.fen(),
          lastMove: [move.from, move.to],
          movable: { dests: new Map() },
        });
      }
    } catch {
      // Ignore if move can't be played on board
    }
  }

  explanationEl.textContent = position.explanation;

  // Disable further moves
  if (cg) {
    cg.set({ movable: { dests: new Map() } });
  }
}

function showTryAgain() {
  const feedbackEl = document.getElementById('feedback');
  const feedbackText = document.getElementById('feedback-text');
  const remaining = 3 - attempts;

  feedbackEl.classList.remove('hidden');
  feedbackText.textContent = `Not quite. Try again. (${remaining} attempt${remaining !== 1 ? 's' : ''} left)`;
  feedbackText.className = 'try-again';
  document.getElementById('explanation').textContent = '';
}

function recordResult(correct) {
  const position = session[currentIndex];
  const state = srsState[position.id] || {
    interval: 0,
    ease: 2.5,
    repetitions: 0,
    history: [],
  };
  srsState[position.id] = updateSRS(state, correct);
  saveSRSState();
  sessionResults.push({ id: position.id, correct, attempts });
}

// --- Session flow ---

function showPosition(index) {
  if (index >= session.length) {
    showSummary();
    return;
  }

  currentIndex = index;
  attempts = 0;
  const position = session[index];

  document.getElementById('progress').textContent = `${index + 1} / ${session.length}`;
  document.getElementById('prompt').textContent =
    `You played ${position.player_move}. Can you find a better move?`;
  document.getElementById('game-info').textContent =
    `vs ${position.game.opponent} (${position.game.source}, ${position.game.date})`;

  document.getElementById('feedback').classList.add('hidden');
  document.getElementById('next-btn').classList.add('hidden');

  setupBoard(position);
}

function showSummary() {
  const modal = document.getElementById('summary-modal');
  const statsEl = document.getElementById('summary-stats');
  const correct = sessionResults.filter((r) => r.correct).length;
  const total = sessionResults.length;
  const pct = total > 0 ? Math.round((correct / total) * 100) : 0;
  const firstTry = sessionResults.filter((r) => r.correct && r.attempts === 1).length;

  // Build summary with safe DOM methods
  statsEl.textContent = '';
  const line1 = document.createElement('p');
  const strong = document.createElement('strong');
  strong.textContent = `${correct} / ${total}`;
  line1.appendChild(strong);
  line1.appendChild(document.createTextNode(` correct (${pct}%)`));
  statsEl.appendChild(line1);

  const line2 = document.createElement('p');
  line2.textContent = `First attempt: ${firstTry}`;
  statsEl.appendChild(line2);

  modal.classList.remove('hidden');
}

function startSession() {
  const settings = loadSettings();
  session = selectPositions(trainingData.positions, settings.sessionSize);
  sessionResults = [];

  if (session.length === 0) {
    document.getElementById('prompt').textContent =
      'No positions to review! All caught up.';
    document.getElementById('progress').textContent = '';
    document.getElementById('game-info').textContent = '';
    return;
  }

  showPosition(0);
}

// --- Init ---

async function init() {
  // Load dependencies from CDN
  try {
    const [cgMod, chessMod] = await Promise.all([
      import('https://cdn.jsdelivr.net/npm/chessground@9/+esm'),
      import('https://cdn.jsdelivr.net/npm/chess.js@1/+esm'),
    ]);
    Chessground = cgMod.Chessground;
    Chess = chessMod.Chess;
  } catch (err) {
    document.getElementById('prompt').textContent =
      'Failed to load chess libraries. Check your internet connection.';
    console.error('CDN import failed:', err);
    return;
  }

  // Load training data
  try {
    const resp = await fetch('training_data.json');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    trainingData = await resp.json();
  } catch (err) {
    document.getElementById('prompt').textContent =
      'Could not load training data. Run: chess-self-coach train --prepare';
    console.error('Training data load failed:', err);
    return;
  }

  // Load SRS state
  srsState = loadSRSState();

  // Wire up controls
  document.getElementById('next-btn').addEventListener('click', () => {
    showPosition(currentIndex + 1);
  });

  document.getElementById('settings-btn').addEventListener('click', () => {
    const modal = document.getElementById('settings-modal');
    const settings = loadSettings();
    document.getElementById('session-size').value = settings.sessionSize;
    document.getElementById('difficulty').value = settings.difficulty;
    modal.classList.remove('hidden');
  });

  document.getElementById('close-settings').addEventListener('click', () => {
    const settings = {
      sessionSize: parseInt(document.getElementById('session-size').value) || 10,
      difficulty: document.getElementById('difficulty').value,
    };
    saveSettings(settings);
    document.getElementById('settings-modal').classList.add('hidden');
  });

  document.getElementById('reset-progress').addEventListener('click', () => {
    if (confirm('Reset all training progress? This cannot be undone.')) {
      localStorage.removeItem('train_srs');
      srsState = {};
      document.getElementById('settings-modal').classList.add('hidden');
      startSession();
    }
  });

  document.getElementById('new-session').addEventListener('click', () => {
    document.getElementById('summary-modal').classList.add('hidden');
    startSession();
  });

  // Register service worker
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch((err) =>
      console.warn('SW registration failed:', err)
    );
  }

  // Start first session
  startSession();
}

init();
