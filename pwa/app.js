/**
 * @module ChessSelfCoach
 * @description Chess Self-Coach — Training PWA.
 *
 * Loads pre-generated training data (from chess-self-coach train --prepare),
 * displays mistake positions on a chessground board, and uses SM-2 spaced
 * repetition to schedule reviews.
 *
 * Dependencies (loaded from CDN at runtime):
 * - [chessground](https://github.com/lichess-org/chessground) — interactive chess board
 * - [chess.js](https://github.com/jhlywa/chess.js) — move validation
 */

// --- State ---
/** @type {string} App mode: 'demo' (GitHub Pages) or 'app' (FastAPI backend) */
let appMode = 'demo';
/** @type {string} App version (populated from /api/status in app mode) */
let appVersion = '';

/** @type {Function} Chessground constructor (loaded from CDN) */
let Chessground;
/** @type {Function} Chess constructor (loaded from CDN) */
let Chess;

// --- Stockfish WASM engine (lazy-loaded for punishment moves) ---
/** @type {?Worker} Stockfish Web Worker */
let sfWorker = null;
/** @type {?Function} Resolve callback for current bestmove promise */
let sfResolve = null;

/**
 * Initialize Stockfish WASM engine (lazy, first call only).
 * Uses the lite single-threaded variant for GitHub Pages compatibility.
 */
async function initStockfish() {
  if (sfWorker) return;
  console.log('[initStockfish] Loading Stockfish WASM...');
  sfWorker = new Worker('stockfish/stockfish-18-lite-single.js');
  sfWorker.onmessage = (e) => {
    const line = e.data;
    if (line.startsWith('bestmove') && sfResolve) {
      const match = line.match(/^bestmove\s(\S+)/);
      console.log('[Stockfish] bestmove:', match ? match[1] : 'none');
      sfResolve(match ? match[1] : null);
      sfResolve = null;
    }
  };
  sfWorker.postMessage('uci');
  sfWorker.postMessage('isready');
  console.log('[initStockfish] Engine ready');
}

/**
 * Get Stockfish's best move for a given position.
 * @param {string} fen - Position in FEN notation.
 * @param {number} [depth=12] - Search depth.
 * @returns {Promise<string|null>} Best move in UCI notation (e.g. "e2e4") or null.
 */
async function getBestMove(fen, depth = 12) {
  await initStockfish();
  return new Promise(resolve => {
    sfResolve = resolve;
    sfWorker.postMessage('position fen ' + fen);
    sfWorker.postMessage('go depth ' + depth);
  });
}
/** @type {?Object} Parsed training_data.json */
let trainingData = null;
/** @type {Object.<string, SRSState>} SRS state keyed by position ID */
let srsState = {};
/** @type {Array.<Object>} Positions queue for the current session */
let session = [];
/** @type {number} Index of the current position in the session */
let currentIndex = 0;
/** @type {number} Number of attempts on the current position */
let attempts = 0;
/** @type {Array.<{id: string, correct: boolean, attempts: number}>} Results for the current session */
let sessionResults = [];
/** @type {?Object} Current chessground instance */
let cg = null;
/** @type {Map.<string, number>} Number of times each position appeared in this session */
let sessionAppearances = new Map();
/** @type {number} Count of unique positions completed (for progress display) */
let completedCount = 0;
/** @type {number} Total unique positions in original session */
let sessionOriginalSize = 0;
/** @type {?number} Timer ID for the wrong-move animation sequence */
let animationTimer = null;

// --- Animation constants ---
const CATEGORY_LABELS = { blunder: '??', mistake: '?', inaccuracy: '?!' };
const CATEGORY_COLORS = { blunder: '#e94560', mistake: '#f0a500', inaccuracy: '#999' };

/**
 * @typedef {Object} SRSState
 * @property {number} interval - Days until next review
 * @property {number} ease - Ease factor (minimum 1.3)
 * @property {number} repetitions - Consecutive correct answers
 * @property {string} next_review - ISO date string (YYYY-MM-DD)
 * @property {Array.<{date: string, correct: boolean}>} history - Review history
 */

// --- Settings ---

/** @type {{sessionSize: number, difficulty: string}} */
const DEFAULT_SETTINGS = { sessionSize: 10, difficulty: 'all' };

/**
 * Load user settings from localStorage.
 * @returns {{sessionSize: number, difficulty: string}} Merged settings with defaults.
 */
function loadSettings() {
  try {
    return { ...DEFAULT_SETTINGS, ...JSON.parse(localStorage.getItem('train_settings') || '{}') };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

/**
 * Save user settings to localStorage.
 * @param {{sessionSize: number, difficulty: string}} s - Settings to save.
 */
function saveSettings(s) {
  localStorage.setItem('train_settings', JSON.stringify(s));
}

// --- SRS (SM-2 algorithm) ---

/**
 * Update SRS state using the SM-2 algorithm (Piotr Wozniak, 1987).
 *
 * - Correct: interval progresses (1d → 3d → interval*ease), ease increases
 * - Wrong: interval resets to 1d, repetitions reset, ease decreases
 * - Ease factor never drops below 1.3
 *
 * @param {SRSState} state - Current SRS state for a position.
 * @param {boolean} correct - Whether the answer was correct.
 * @returns {SRSState} Updated SRS state.
 */
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

/**
 * Select positions for a training session using SRS priority.
 *
 * Priority order: overdue (past review date) → new (never seen, blunders first)
 * → learning (interval < 7 days). Mastered or not-yet-due positions are skipped.
 *
 * @param {Array.<Object>} positions - All available training positions.
 * @param {number} count - Maximum positions to select.
 * @returns {Array.<Object>} Selected positions for the session.
 */
function selectPositions(positions, count) {
  const today = new Date().toISOString().split('T')[0];
  const settings = loadSettings();
  console.log(`[selectPositions] ${positions.length} available, selecting up to ${count}, difficulty=${settings.difficulty}`);

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

/**
 * Build a deep link to the specific move position in the original game.
 * @param {string} gameId - Full game URL (lichess.org or chess.com).
 * @param {string} fen - FEN of the position (contains fullmove number and side to move).
 * @returns {string} URL with move anchor/parameter, or original URL if format unknown.
 */
function getMoveLink(gameId, fen, playerColor) {
  const parts = fen.split(' ');
  const turn = parts[1];
  const fullmove = parseInt(parts[5]);
  if (isNaN(fullmove)) return gameId;
  const ply = (fullmove - 1) * 2 + (turn === 'b' ? 1 : 0);

  if (gameId.includes('lichess.org')) {
    const orientation = playerColor === 'black' ? '/black' : '';
    return gameId + orientation + '#' + ply;
  }
  if (gameId.includes('chess.com')) {
    return gameId + '?move=' + ply;
  }
  return gameId;
}

/**
 * Compute legal move destinations for chessground from a FEN.
 * @param {string} fen - FEN string of the position.
 * @returns {Map.<string, Array.<string>>} Map of source square → destination squares.
 */
function getLegalDests(fen) {
  const chess = new Chess(fen);
  const dests = new Map();
  for (const move of chess.moves({ verbose: true })) {
    if (!dests.has(move.from)) dests.set(move.from, []);
    dests.get(move.from).push(move.to);
  }
  return dests;
}

/**
 * Compute material balance from a FEN string and display captured pieces.
 * Shows advantage like chess.com/Lichess: captured pieces + point difference.
 * @param {string} fen - FEN position string.
 * @param {string} orientation - Board orientation ("white" or "black").
 */
function updateMaterialBalance(fen, orientation) {
  const pieces = fen.split(' ')[0];
  const count = { K: 0, Q: 0, R: 0, B: 0, N: 0, P: 0, k: 0, q: 0, r: 0, b: 0, n: 0, p: 0 };
  for (const ch of pieces) {
    if (ch in count) count[ch]++;
  }

  // Starting material
  const start = { K: 1, Q: 1, R: 2, B: 2, N: 2, P: 8 };
  const values = { q: 9, r: 5, b: 3, n: 3, p: 1 };
  const symbols = { q: '\u2655', r: '\u2656', b: '\u2657', n: '\u2658', p: '\u2659' };
  const symbolsBlack = { q: '\u265B', r: '\u265C', b: '\u265D', n: '\u265E', p: '\u265F' };

  // Captured pieces: what's missing from starting position
  let whiteAdv = 0;  // positive = white has more material
  let whiteCaptured = '';  // pieces white captured (black pieces missing)
  let blackCaptured = '';  // pieces black captured (white pieces missing)

  for (const type of ['q', 'r', 'b', 'n', 'p']) {
    const upper = type.toUpperCase();
    const whiteMissing = start[upper] - count[upper];
    const blackMissing = start[upper] - count[type];

    // White pieces missing = captured by black
    for (let i = 0; i < whiteMissing; i++) {
      blackCaptured += symbols[type];
    }
    // Black pieces missing = captured by white
    for (let i = 0; i < blackMissing; i++) {
      whiteCaptured += symbolsBlack[type];
    }

    whiteAdv += (count[upper] - count[type]) * values[type];
  }

  const topEl = document.getElementById('material-top');
  const bottomEl = document.getElementById('material-bottom');

  // Top = opponent, bottom = player (depends on orientation)
  const diffStr = Math.abs(whiteAdv) > 0 ? ` +${Math.abs(whiteAdv)}` : '';
  if (orientation === 'white') {
    topEl.textContent = whiteCaptured + (whiteAdv > 0 ? '' : diffStr);
    bottomEl.textContent = blackCaptured + (whiteAdv > 0 ? diffStr : '');
  } else {
    topEl.textContent = blackCaptured + (whiteAdv > 0 ? diffStr : '');
    bottomEl.textContent = whiteCaptured + (whiteAdv > 0 ? '' : diffStr);
  }
}

/**
 * Format seconds into MM:SS display.
 * @param {number} seconds - Time in seconds.
 * @returns {string} Formatted time string (e.g. "09:00").
 */
function formatClock(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

/**
 * Update clock displays for a position.
 * Top clock = opponent, bottom clock = player (matches board orientation).
 * Hides clocks if position.clock is absent.
 * @param {Object} position - Training position with optional clock field.
 */
function updateClocks(position) {
  const clockTop = document.getElementById('clock-top');
  const clockBottom = document.getElementById('clock-bottom');
  if (!position.clock) {
    clockTop.classList.add('hidden');
    clockBottom.classList.add('hidden');
    return;
  }
  console.log(`[updateClocks] player=${position.clock.player}s, opponent=${position.clock.opponent}s`);
  clockTop.textContent = formatClock(position.clock.opponent);
  clockBottom.textContent = formatClock(position.clock.player);
  clockTop.classList.remove('hidden');
  clockBottom.classList.remove('hidden');
}

/**
 * Animate the player's wrong move on the board, show annotation, then reset.
 * Sequence: 500ms wait → animate move + show badge → 1500ms wait → reset + enable.
 * If chess.move() fails (bad SAN), skips animation and falls back to text prompt.
 * @param {Object} position - Training position.
 */
function animateWrongMove(position) {
  const chess = new Chess(position.fen);
  let move;
  try {
    move = chess.move(position.player_move);
  } catch (err) {
    console.log(`[animateWrongMove] Cannot parse player_move "${position.player_move}", skipping animation`);
    document.getElementById('prompt').textContent =
      `${position.context || ''} You played ${position.player_move}. Can you find a better move?`;
    cg.set({ movable: { color: position.player_color, dests: getLegalDests(position.fen) } });
    return;
  }
  if (!move) {
    console.log(`[animateWrongMove] Invalid move "${position.player_move}", skipping animation`);
    document.getElementById('prompt').textContent =
      `${position.context || ''} You played ${position.player_move}. Can you find a better move?`;
    cg.set({ movable: { color: position.player_color, dests: getLegalDests(position.fen) } });
    return;
  }

  const from = move.from;
  const to = move.to;
  const category = position.category || 'mistake';
  console.log(`[animateWrongMove] ${from}→${to}, category=${category}`);

  // Disable moves during animation
  cg.set({ movable: { dests: new Map() } });

  // Step 1: 500ms delay, then animate the wrong move
  animationTimer = setTimeout(() => {
    cg.move(from, to);
    // Show annotation badge via autoShapes
    cg.set({ drawable: { autoShapes: [
      { orig: to, label: { text: CATEGORY_LABELS[category], fill: CATEGORY_COLORS[category] } }
    ]}});

    // Step 2: 1500ms delay, then reset to original position
    animationTimer = setTimeout(() => {
      cg.set({
        fen: position.fen,
        lastMove: undefined,
        drawable: { autoShapes: [] },
        movable: { color: position.player_color, dests: getLegalDests(position.fen) },
      });
      const ctx = position.context || '';
      document.getElementById('prompt').textContent =
        `${ctx} You played ${position.player_move}. Can you find a better move?`;
      animationTimer = null;
    }, 1500);
  }, 500);
}

/**
 * Initialize the chessground board for a training position.
 * Destroys any existing board, sets orientation to the player's color,
 * and configures legal move destinations.
 * @param {Object} position - Training position from training_data.json.
 */
function setupBoard(position) {
  console.log(`[setupBoard] id=${position.id}, color=${position.player_color}, fen=${position.fen.substring(0, 30)}...`);
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

  updateMaterialBalance(fen, color);
}

/**
 * Handle a move made on the board. Validates with chess.js, compares to
 * acceptable moves, and shows feedback. Allows up to 3 attempts.
 * @param {string} orig - Source square (e.g. "e2").
 * @param {string} dest - Destination square (e.g. "e4").
 */
async function handleMove(orig, dest) {
  const position = session[currentIndex];
  const chess = new Chess(position.fen);

  // Try the move (auto-promote to queen)
  const move = chess.move({ from: orig, to: dest, promotion: 'q' });
  if (!move) {
    console.log('[handleMove] Invalid move:', orig, dest);
    return;
  }

  const san = move.san;
  attempts++;
  console.log(`[handleMove] Played: ${san}, attempt: ${attempts}, best: ${position.best_move}, acceptable: ${position.acceptable_moves}`);

  if (position.acceptable_moves.includes(san) || san === position.best_move) {
    // Correct!
    console.log('[handleMove] → CORRECT, calling showFeedback(true)');
    showFeedback(true, position);
    recordResult(true);
  } else if (attempts >= 3) {
    // Out of attempts
    console.log('[handleMove] → GAVE UP, calling showFeedback(false, gaveUp=true)');
    showFeedback(false, position, true);
    recordResult(false);
  } else {
    // Wrong — show punishment move, then let the player retry
    console.log('[handleMove] → WRONG, try again');
    showTryAgain();
    try {
      const chessAfter = new Chess(position.fen);
      chessAfter.move(san);
      const bestUci = await getBestMove(chessAfter.fen(), 12);
      if (bestUci) {
        const from = bestUci.slice(0, 2);
        const to = bestUci.slice(2, 4);
        console.log(`[handleMove] Punishment: ${from}→${to}`);
        // Show the player's wrong move, then animate the punishment response
        cg.set({ fen: chessAfter.fen(), lastMove: [orig, dest], movable: { dests: new Map() } });
        setTimeout(() => {
          cg.move(from, to);
          setTimeout(() => showRetryButton(position), 1000);
        }, 800);
      } else {
        setTimeout(() => setupBoard(position), 400);
      }
    } catch (err) {
      console.log('[handleMove] Stockfish WASM unavailable, fallback:', err.message);
      setTimeout(() => setupBoard(position), 400);
    }
  }
}

// --- Feedback ---

/**
 * Show the "See moves" deep link for a position.
 * @param {Object} position - Training position with game.id and fen.
 */
function _showSeeMovesLink(position) {
  const gameId = position.game.id || '';
  const playerColor = position.player_color || 'white';
  const seeLinkEl = document.getElementById('see-moves');
  console.log(`[_showSeeMovesLink] gameId="${gameId}", color=${playerColor}, seeLinkEl=${seeLinkEl ? 'found' : 'NULL'}`);
  if (seeLinkEl) {
    if (gameId.startsWith('http')) {
      const moveLink = getMoveLink(gameId, position.fen, playerColor);
      console.log(`[_showSeeMovesLink] href=${moveLink}, removing hidden`);
      seeLinkEl.href = moveLink;
      seeLinkEl.classList.remove('hidden');
      // Chess.com doesn't support board flip in URL — add tooltip for Black
      if (gameId.includes('chess.com') && playerColor === 'black') {
        seeLinkEl.title = 'Click the flip button on chess.com to see the board from your perspective';
      } else {
        seeLinkEl.title = '';
      }
    } else {
      seeLinkEl.classList.add('hidden');
    }
  } else {
    console.error('[_showSeeMovesLink] ERROR: #see-moves element not found in DOM!');
  }
}

/**
 * Display feedback after an answer (correct, wrong, or gave up).
 * Shows the explanation and, on failure, plays the best move on the board.
 * @param {boolean} correct - Whether the answer was correct.
 * @param {Object} position - Current training position.
 * @param {boolean} [gaveUp=false] - True if the player exhausted all attempts.
 */
function showFeedback(correct, position, gaveUp = false) {
  console.log(`[showFeedback] correct=${correct}, gaveUp=${gaveUp}, position.id=${position.id}`);

  const feedbackEl = document.getElementById('feedback');
  const feedbackText = document.getElementById('feedback-text');
  const explanationEl = document.getElementById('explanation');
  const nextBtn = document.getElementById('next-btn');
  const showPosBtn = document.getElementById('show-position-btn');

  const dismissBtn = document.getElementById('dismiss-btn');

  feedbackEl.classList.remove('hidden');
  nextBtn.classList.remove('hidden');
  showPosBtn.classList.remove('hidden');
  dismissBtn.classList.remove('hidden');

  // Compute the FEN after best move for toggle
  let bestMoveFen = null;
  let bestMoveSquares = null;
  try {
    const chess = new Chess(position.fen);
    const move = chess.move(position.best_move);
    if (move) {
      bestMoveFen = chess.fen();
      bestMoveSquares = [move.from, move.to];
    }
  } catch (err) {
    console.error('[showFeedback] Error computing best move FEN:', err);
  }

  if (correct) {
    feedbackText.textContent = 'Correct!';
    feedbackText.className = 'correct';
  } else {
    feedbackText.textContent = gaveUp
      ? 'The answer was: ' + position.best_move
      : 'Not quite.';
    feedbackText.className = 'incorrect';

    // Show the best move on the board
    if (bestMoveFen && cg) {
      cg.set({
        fen: bestMoveFen,
        lastMove: bestMoveSquares,
        movable: { dests: new Map() },
      });
    }
  }

  explanationEl.textContent = position.explanation;

  // Show eval summary
  const evalSummaryEl = document.getElementById('eval-summary');
  if (evalSummaryEl && position.score_after != null) {
    const isWhite = position.player_color === 'white';
    const formatEval = (s) => {
      if (s === 'TB:win') return 'You win (tablebase)';
      if (s === 'TB:loss') return 'Opponent wins (tablebase)';
      if (s === 'TB:draw') return 'Draw (tablebase)';
      const val = parseFloat(s);
      if (isNaN(val)) return s;
      const isPositive = val > 0;
      const playerWins = isWhite ? isPositive : !isPositive;
      if (Math.abs(val) >= 100) return playerWins ? 'You win' : 'Opponent wins';
      if (Math.abs(val) >= 10) return playerWins ? 'You win' : 'Opponent wins';
      return s;
    };
    const yourMove = formatEval(position.score_after);
    const bestMove = formatEval(position.score_after_best || position.score_before);
    console.log(`[showFeedback] evals: your_move=${yourMove}, best_move=${bestMove}`);
    evalSummaryEl.textContent = `Your move: ${yourMove}\nBest move: ${bestMove}`;
    evalSummaryEl.classList.remove('hidden');
  } else if (evalSummaryEl) {
    evalSummaryEl.classList.add('hidden');
  }

  // Show "See moves" deep link
  _showSeeMovesLink(position);

  // Show PV line if available
  const pvLineEl = document.getElementById('pv-line');
  const playLineBtn = document.getElementById('play-line-btn');
  const pvMoves = position.pv || [];
  if (pvMoves.length > 1) {
    pvLineEl.textContent = 'Best line: ' + pvMoves.join(' ');
    pvLineEl.classList.remove('hidden');
    playLineBtn.classList.remove('hidden');
  } else {
    pvLineEl.classList.add('hidden');
    playLineBtn.classList.add('hidden');
  }

  // Disable further moves
  if (cg) {
    cg.set({ movable: { dests: new Map() } });
  }

  // Toggle between original position and best move
  let showingOriginal = false;
  showPosBtn.textContent = 'Show original position';
  showPosBtn.onclick = () => {
    if (!cg) return;
    showingOriginal = !showingOriginal;
    if (showingOriginal) {
      cg.set({
        fen: position.fen,
        lastMove: undefined,
        movable: { dests: new Map() },
      });
      showPosBtn.textContent = 'Show best move';
    } else {
      if (bestMoveFen) {
        cg.set({
          fen: bestMoveFen,
          lastMove: bestMoveSquares,
          movable: { dests: new Map() },
        });
      } else {
        cg.set({
          fen: position.fen,
          lastMove: undefined,
          movable: { dests: new Map() },
        });
      }
      showPosBtn.textContent = 'Show original position';
    }
  };

  // Play line: animate PV moves on the board
  playLineBtn.onclick = () => {
    if (!cg || pvMoves.length === 0) return;
    playLineBtn.disabled = true;
    const chess = new Chess(position.fen);
    let step = 0;
    const interval = setInterval(() => {
      if (step >= pvMoves.length) {
        clearInterval(interval);
        playLineBtn.disabled = false;
        return;
      }
      const move = chess.move(pvMoves[step]);
      if (!move) {
        clearInterval(interval);
        playLineBtn.disabled = false;
        return;
      }
      cg.set({
        fen: chess.fen(),
        lastMove: [move.from, move.to],
        movable: { dests: new Map() },
      });
      step++;
    }, 800);
  };
}

function showTryAgain() {
  const feedbackEl = document.getElementById('feedback');
  const feedbackText = document.getElementById('feedback-text');
  const remaining = 3 - attempts;

  feedbackEl.classList.remove('hidden');
  feedbackText.textContent = `Not quite. Try again. (${remaining} attempt${remaining !== 1 ? 's' : ''} left)`;
  feedbackText.className = 'try-again';
  document.getElementById('dismiss-btn').classList.remove('hidden');
  document.getElementById('explanation').textContent = '';

  // Show "See moves" after 2 wrong attempts (helps understand the position)
  if (attempts >= 2) {
    const position = session[currentIndex];
    _showSeeMovesLink(position);
  }
}

/**
 * Show the Retry button after a punishment move. Clicking resets the board.
 * @param {Object} position - The current training position.
 */
function showRetryButton(position) {
  console.log('[showRetryButton] Showing retry');
  const retryBtn = document.getElementById('retry-btn');
  retryBtn.classList.remove('hidden');
  retryBtn.onclick = () => {
    console.log('[showRetryButton] Retry clicked');
    retryBtn.classList.add('hidden');
    setupBoard(position);
  };
}

/**
 * Record the result of a position attempt. Updates SRS state and saves to localStorage.
 * @param {boolean} correct - Whether the answer was correct.
 */
function recordResult(correct) {
  console.log(`[recordResult] correct=${correct}, position=${session[currentIndex].id}`);
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

  const appearances = sessionAppearances.get(position.id) || 1;

  // Decide whether to reinsert for intra-session repetition
  let shouldReinsert = false;
  if (correct && appearances === 1) {
    // First success: reinsert to confirm learning
    shouldReinsert = true;
  } else if (!correct) {
    // Failed: reinsert for retry
    shouldReinsert = true;
  }
  // 2nd+ success: position is acquired, don't reinsert

  if (shouldReinsert) {
    const offset = correct ? 5 : 3;
    const insertAt = Math.min(currentIndex + 1 + offset, session.length);
    session.splice(insertAt, 0, position);
  } else {
    completedCount++;
  }
}

/**
 * Permanently dismiss a position — it will never appear again.
 * Sets an extremely long SRS interval so it's never selected.
 */
function dismissPosition() {
  console.log(`[dismissPosition] id=${session[currentIndex].id}`);
  const position = session[currentIndex];
  srsState[position.id] = {
    interval: 99999,
    ease: 2.5,
    repetitions: 0,
    next_review: '9999-12-31',
    history: [{ date: new Date().toISOString().split('T')[0], correct: false, dismissed: true }],
  };
  saveSRSState();

  // Remove all future occurrences of this position from the session
  for (let i = session.length - 1; i > currentIndex; i--) {
    if (session[i].id === position.id) {
      session.splice(i, 1);
    }
  }
  completedCount++;
  showPosition(currentIndex + 1);
}

// --- Session flow ---

/**
 * Display a position in the session. Sets up the board, prompt, and game info.
 * If index exceeds session length, shows the session summary.
 * @param {number} index - Position index in the session array.
 */
function showPosition(index) {
  if (index >= session.length) {
    showSummary();
    return;
  }

  // Cancel any in-progress animation from a previous position
  if (animationTimer) {
    clearTimeout(animationTimer);
    animationTimer = null;
  }

  currentIndex = index;
  attempts = 0;
  const position = session[index];
  console.log(`[showPosition] index=${index}, id=${position.id}, color=${position.player_color}, best=${position.best_move}`);

  // Track appearances
  const count = (sessionAppearances.get(position.id) || 0) + 1;
  sessionAppearances.set(position.id, count);

  document.getElementById('progress').textContent = `${completedCount + 1} / ${sessionOriginalSize}`;
  document.getElementById('prompt').textContent = position.context || '';
  document.getElementById('game-info').textContent = '';

  document.getElementById('feedback').classList.add('hidden');
  document.getElementById('next-btn').classList.add('hidden');
  document.getElementById('show-position-btn').classList.add('hidden');
  document.getElementById('play-line-btn').classList.add('hidden');
  document.getElementById('pv-line').classList.add('hidden');
  document.getElementById('eval-summary').classList.add('hidden');
  document.getElementById('dismiss-btn').classList.add('hidden');
  document.getElementById('retry-btn').classList.add('hidden');
  const seeMoves = document.getElementById('see-moves');
  if (seeMoves) seeMoves.classList.add('hidden');

  setupBoard(position);
  updateClocks(position);
  animateWrongMove(position);
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

/**
 * Start a new training session. Selects positions via SRS priority,
 * resets session state, and shows the first position.
 */
function startSession() {
  console.log('[startSession] Starting new session');
  const settings = loadSettings();
  session = selectPositions(trainingData.positions, settings.sessionSize);
  console.log(`[startSession] Selected ${session.length} position(s)`);
  sessionResults = [];
  sessionAppearances = new Map();
  completedCount = 0;
  sessionOriginalSize = session.length;

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

/**
 * Initialize the PWA. Loads dependencies from CDN, fetches training data,
 * restores SRS state from localStorage, wires up UI controls, registers
 * the service worker, and starts the first session.
 * @async
 */
async function init() {
  console.log('[init] Chess Self-Coach PWA starting...');

  // Detect app mode: try /api/status to see if FastAPI backend is running
  try {
    const statusResp = await fetch('/api/status');
    if (statusResp.ok) {
      const statusData = await statusResp.json();
      appMode = 'app';
      appVersion = statusData.version || '';
      console.log(`[init] App mode detected: v${appVersion}, SF: ${statusData.stockfish_version}`);

      // Hide demo banner
      const banner = document.getElementById('demo-banner');
      if (banner) banner.classList.add('hidden');

      // Show app-only menu items (greyed out for now)
      document.querySelectorAll('.nav-app-only').forEach((el) => {
        el.classList.remove('hidden');
        el.classList.add('disabled');
      });

      // Set version in menu
      document.getElementById('nav-version').textContent = 'v' + appVersion;
    }
  } catch {
    // No backend — demo mode (GitHub Pages)
    console.log('[init] Demo mode (no backend)');
  }

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
    console.log(`[init] Loaded ${trainingData.positions.length} position(s)`);
  } catch (err) {
    document.getElementById('prompt').textContent =
      'Could not load training data. Run: chess-self-coach train --prepare';
    console.error('Training data load failed:', err);
    return;
  }

  // Load SRS state
  srsState = loadSRSState();
  console.log(`[init] SRS state: ${Object.keys(srsState).length} position(s) tracked`);

  // Wire up controls
  document.getElementById('next-btn').addEventListener('click', () => {
    showPosition(currentIndex + 1);
  });

  document.getElementById('dismiss-btn').addEventListener('click', () => {
    dismissPosition();
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

  // Wire up navigation menu
  const menuBtn = document.getElementById('menu-btn');
  const navMenu = document.getElementById('nav-menu');
  const navOverlay = document.getElementById('nav-overlay');

  function openMenu() {
    navMenu.classList.add('nav-open');
    navMenu.classList.remove('nav-closed');
    navOverlay.classList.remove('hidden');
  }

  function closeMenu() {
    navMenu.classList.remove('nav-open');
    navMenu.classList.add('nav-closed');
    navOverlay.classList.add('hidden');
  }

  menuBtn.addEventListener('click', openMenu);
  navOverlay.addEventListener('click', closeMenu);

  // Set version in menu header (populated later by mode detection)
  if (appVersion) {
    document.getElementById('nav-version').textContent = 'v' + appVersion;
  }

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
