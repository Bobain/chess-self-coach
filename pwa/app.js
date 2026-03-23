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
/** @type {string} Stockfish version (populated from /api/status in app mode) */
let stockfishVersion = '';

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

// --- Analysis mode state ---
/** @type {string} Current view: 'training' or 'analysis' */
let appView = 'training';
/** @type {?Object} Parsed analysis_data.json */
let analysisData = null;
/** @type {?Object} Currently selected game for review */
let reviewGame = null;
/** @type {number} Current ply in review (0 = starting position) */
let currentPly = 0;
/** @type {?Object} Second chessground instance for review board */
let reviewCg = null;
/** @type {string} Review board orientation */
let reviewOrientation = 'white';
/** @type {?number} Auto-play interval ID */
let autoPlayTimer = null;
/** @type {?Array} Classified moves for current game */
let classifiedMoves = null;

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

/** @type {{sessionSize: number, difficulty: string, analysisDepth: number}} */
const DEFAULT_SETTINGS = { sessionSize: 10, difficulty: 'all', analysisDepth: 12 };

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
 * Show the "Analyzing..." thinking indicator.
 */
function showThinking() {
  const el = document.getElementById('thinking-indicator');
  if (el) el.classList.remove('hidden');
}

/**
 * Hide the thinking indicator.
 */
function hideThinking() {
  const el = document.getElementById('thinking-indicator');
  if (el) el.classList.add('hidden');
}

/**
 * Get Stockfish's best move, using backend API in [app] mode or WASM in [demo].
 * Falls back to WASM if the API call fails (e.g. server restarted).
 * @param {string} fen - Position in FEN notation.
 * @returns {Promise<string|null>} Best move in UCI notation or null.
 */
async function getStockfishBestMove(fen) {
  const settings = loadSettings();
  const depth = settings.analysisDepth || (appMode === 'app' ? 18 : 12);

  if (appMode === 'app') {
    try {
      const resp = await fetch('/api/stockfish/bestmove', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fen, depth }),
      });
      if (resp.ok) {
        const data = await resp.json();
        console.log(`[getStockfishBestMove] API response: ${data.bestmove} (depth ${depth})`);
        return data.bestmove;
      }
      console.log('[getStockfishBestMove] API error, falling back to WASM');
    } catch (err) {
      console.log(`[getStockfishBestMove] API unreachable, WASM fallback: ${err.message}`);
    }
  }
  // Demo mode or API fallback → use WASM
  return getBestMove(fen, depth);
}

/**
 * Handle a move made on the board. Validates with chess.js, compares to
 * acceptable moves, and shows feedback. Player can retry until correct or dismiss.
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
  } else {
    // Wrong — show opponent response, then let the player retry
    console.log('[handleMove] → WRONG, try again');
    showTryAgain();
    showThinking();
    try {
      const chessAfter = new Chess(position.fen);
      chessAfter.move(san);
      const bestUci = await getStockfishBestMove(chessAfter.fen());
      hideThinking();
      if (bestUci) {
        const from = bestUci.slice(0, 2);
        const to = bestUci.slice(2, 4);
        console.log(`[handleMove] Opponent response: ${from}→${to}`);
        // Show the player's wrong move, then animate the opponent's response
        cg.set({ fen: chessAfter.fen(), lastMove: [orig, dest], movable: { dests: new Map() } });
        setTimeout(() => {
          cg.move(from, to);
          setTimeout(() => showRetryButton(position), 1000);
        }, 800);
      } else {
        setTimeout(() => setupBoard(position), 400);
      }
    } catch (err) {
      hideThinking();
      console.log('[handleMove] Stockfish unavailable, fallback:', err.message);
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

  feedbackEl.classList.remove('hidden');
  feedbackText.textContent = 'Not quite. Try again.';
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

// --- Modal data helper ---

/**
 * Show a modal, fetch data from an API, and build content via callback.
 * Handles loading state, error responses, and connection failures.
 * @param {string} modalId - ID of the modal element.
 * @param {string} contentId - ID of the content div inside the modal.
 * @param {string} apiUrl - API endpoint to fetch.
 * @param {Function} buildFn - Callback receiving (contentEl, data) to build DOM.
 * @param {Object} [fetchOpts] - Optional fetch options (e.g. { method: 'POST' }).
 * @async
 */
async function showModalWithData(modalId, contentId, apiUrl, buildFn, fetchOpts) {
  const modal = document.getElementById(modalId);
  const content = document.getElementById(contentId);
  if (!modal || !content) {
    console.error(`[showModalWithData] ${modalId} elements not found`);
    return;
  }
  content.textContent = 'Loading...';
  modal.classList.remove('hidden');
  try {
    const resp = await fetch(apiUrl, fetchOpts);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
      console.log(`[showModalWithData] ${modalId} API error:`, resp.status, err.detail);
      content.textContent = err.detail || 'Failed to load.';
      return;
    }
    const data = await resp.json();
    content.textContent = '';
    buildFn(content, data);
  } catch (err) {
    console.error(`[showModalWithData] ${modalId} fetch failed:`, err);
    content.textContent = 'Failed to connect to server.';
  }
}

// --- Stats modal ---

/**
 * Show the Raw Data Summary modal.
 * Computed entirely client-side from trainingData + srsState.
 */
function showRawDataSummary() {
  console.log('[showRawDataSummary] Building summary...');
  const modal = document.getElementById('stats-modal');
  const content = document.getElementById('stats-content');
  while (content.firstChild) content.firstChild.remove();

  const positions = (trainingData && trainingData.positions) || [];
  const total = positions.length;

  // Group positions by game.id
  const games = new Map();
  for (const pos of positions) {
    const gid = (pos.game && pos.game.id) || 'unknown';
    if (!games.has(gid)) {
      games.set(gid, {
        id: gid,
        opponent: (pos.game && pos.game.opponent) || '?',
        source: (pos.game && pos.game.source) || '',
        date: (pos.game && pos.game.date) || '',
        positions: 0,
        positionIds: [],
      });
    }
    const g = games.get(gid);
    g.positions++;
    g.positionIds.push(pos.id);
  }

  // Compute SRS stats per game
  let totalLessons = 0;
  let totalDismissed = 0;
  for (const game of games.values()) {
    let gameLessons = 0;
    let gameDismissed = 0;
    for (const pid of game.positionIds) {
      const state = srsState[pid];
      if (state && state.history) {
        gameLessons += state.history.length;
        for (const h of state.history) {
          if (h.dismissed) gameDismissed++;
        }
      }
    }
    game.lessons = gameLessons;
    game.dismissed = gameDismissed;
    totalLessons += gameLessons;
    totalDismissed += gameDismissed;
  }

  // Integrity check
  const sumPositions = [...games.values()].reduce((s, g) => s + g.positions, 0);
  if (sumPositions !== total) {
    const warn = document.createElement('p');
    warn.className = 'raw-data-warning';
    warn.textContent = `⚠ Integrity error: sum of per-game positions (${sumPositions}) ≠ total (${total})`;
    content.appendChild(warn);
  }

  // Header
  const header = document.createElement('p');
  header.className = 'raw-data-header';
  header.textContent = `${total} positions from ${games.size} game${games.size !== 1 ? 's' : ''}`;
  content.appendChild(header);

  // Global SRS stats
  const srsLine = document.createElement('p');
  srsLine.className = 'stats-label';
  srsLine.textContent = `${totalLessons} lesson${totalLessons !== 1 ? 's' : ''} taken · ${totalDismissed} dismissed`;
  content.appendChild(srsLine);

  // Game list
  const table = document.createElement('table');
  table.className = 'raw-data-table';
  const thead = document.createElement('thead');
  thead.innerHTML = '<tr><th>Opponent</th><th>Positions</th><th>Lessons</th><th>Dismissed</th></tr>';
  table.appendChild(thead);

  const tbody = document.createElement('tbody');
  for (const game of games.values()) {
    const tr = document.createElement('tr');

    // Opponent cell with link
    const tdOpp = document.createElement('td');
    if (game.id && game.id.startsWith('http')) {
      const a = document.createElement('a');
      a.href = game.id;
      a.target = '_blank';
      a.rel = 'noopener';
      a.textContent = game.opponent;
      tdOpp.appendChild(a);
    } else {
      tdOpp.textContent = game.opponent;
    }
    tr.appendChild(tdOpp);

    const tdPos = document.createElement('td');
    tdPos.textContent = game.positions;
    tr.appendChild(tdPos);

    const tdLes = document.createElement('td');
    tdLes.textContent = game.lessons;
    tr.appendChild(tdLes);

    const tdDis = document.createElement('td');
    tdDis.textContent = game.dismissed;
    tr.appendChild(tdDis);

    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  content.appendChild(table);

  console.log(`[showRawDataSummary] ${total} positions, ${games.size} games, ${totalLessons} lessons, ${totalDismissed} dismissed`);
  modal.classList.remove('hidden');
}

// --- Cleanup modal ---

/**
 * Trigger study cleanup via the API and display results in a modal.
 * Only available in [App] mode.
 * @async
 */
async function showCleanup() {
  console.log('[showCleanup] Triggering study cleanup...');
  await showModalWithData('cleanup-modal', 'cleanup-content', '/api/pgn/cleanup', (content, data) => {
    console.log('[showCleanup] Results:', data.total_deleted, 'deleted');

    if (data.total_deleted === 0) {
      content.textContent = 'No empty default chapters found.';
      return;
    }

    const summary = document.createElement('p');
    summary.className = 'stats-value';
    summary.textContent = 'Cleaned up ' + data.total_deleted + ' empty chapter(s).';
    content.appendChild(summary);

    for (const r of data.results) {
      if (r.deleted > 0) {
        const p = document.createElement('p');
        p.style.paddingLeft = '1rem';
        p.textContent = r.study + ': ' + r.deleted + ' removed';
        content.appendChild(p);
      }
    }
  }, { method: 'POST' });
}

// --- Status modal ---

/**
 * Fetch project status from the API and display in a modal.
 * Only available in [App] mode.
 * @async
 */
async function showProjectStatus() {
  console.log('[showProjectStatus] Fetching project status...');
  await showModalWithData('status-modal', 'status-content', '/api/pgn/status', (content, data) => {
    console.log('[showProjectStatus] Status received, config_ok:', data.config_ok);

    if (!data.config_ok) {
      content.textContent = 'config.json not found. Run chess-self-coach setup.';
      return;
    }

    // Stockfish
    const sfSection = document.createElement('div');
    sfSection.className = 'status-section';
    const sfTitle = document.createElement('p');
    sfTitle.className = 'status-section-title';
    sfTitle.textContent = 'Stockfish:';
    sfSection.appendChild(sfTitle);
    const sfStatus = document.createElement('p');
    sfStatus.style.paddingLeft = '1rem';
    sfStatus.className = data.stockfish.available ? 'status-ok' : 'status-warn';
    sfStatus.textContent = data.stockfish.available ? data.stockfish.version : 'Not found';
    sfSection.appendChild(sfStatus);
    content.appendChild(sfSection);

    // Token
    const tokenSection = document.createElement('div');
    tokenSection.className = 'status-section';
    const tokenTitle = document.createElement('p');
    tokenTitle.className = 'status-section-title';
    tokenTitle.textContent = 'Lichess token:';
    tokenSection.appendChild(tokenTitle);
    const tokenStatus = document.createElement('p');
    tokenStatus.style.paddingLeft = '1rem';
    tokenStatus.className = data.has_token ? 'status-ok' : 'status-warn';
    tokenStatus.textContent = data.has_token ? 'Configured' : 'Not configured';
    tokenSection.appendChild(tokenStatus);
    content.appendChild(tokenSection);

    // Files
    if (data.files.length > 0) {
      const filesSection = document.createElement('div');
      filesSection.className = 'status-section';
      const filesTitle = document.createElement('p');
      filesTitle.className = 'status-section-title';
      filesTitle.textContent = 'PGN files:';
      filesSection.appendChild(filesTitle);
      for (const f of data.files) {
        const p = document.createElement('p');
        p.className = 'status-file';
        const icon = f.study_configured ? '\u2713' : '\u26A0';
        p.textContent = icon + ' ' + f.file + ' (' + f.chapters + ' chapters, ' + f.modified + ')';
        filesSection.appendChild(p);
      }
      content.appendChild(filesSection);
    }

    // Suggestions
    if (data.suggestions.length > 0) {
      const sugSection = document.createElement('div');
      sugSection.className = 'status-section';
      const sugTitle = document.createElement('p');
      sugTitle.className = 'status-section-title';
      sugTitle.textContent = 'Suggestions:';
      sugSection.appendChild(sugTitle);
      for (const s of data.suggestions) {
        const p = document.createElement('p');
        p.style.paddingLeft = '1rem';
        p.className = 'status-warn';
        p.textContent = s;
        sugSection.appendChild(p);
      }
      content.appendChild(sugSection);
    }
  });
}

// --- Validate modal ---

/**
 * Fetch PGN validation results from the API and display in a modal.
 * Only available in [App] mode.
 * @async
 */
async function showValidate() {
  console.log('[showValidate] Fetching PGN validation...');
  await showModalWithData('validate-modal', 'validate-content', '/api/pgn/validate', (content, data) => {
    console.log('[showValidate] Results received:', data.files.length, 'file(s)');

    for (const file of data.files) {
      const fileEl = document.createElement('p');
      fileEl.className = 'validate-file';
      fileEl.textContent = file.file;
      content.appendChild(fileEl);

      for (const ch of file.chapters) {
        const hasErrors = ch.errors.length > 0;
        const hasWarnings = ch.warnings.length > 0;
        const status = hasErrors ? 'ERROR' : hasWarnings ? 'WARN' : 'OK';
        const cls = hasErrors ? 'validate-error' : hasWarnings ? 'validate-warn' : 'validate-ok';

        const chEl = document.createElement('p');
        chEl.className = 'validate-chapter ' + cls;
        chEl.textContent = '[' + status + '] ' + ch.name;
        content.appendChild(chEl);

        for (const e of ch.errors) {
          const d = document.createElement('p');
          d.className = 'validate-detail validate-error';
          d.textContent = e;
          content.appendChild(d);
        }
        for (const w of ch.warnings) {
          const d = document.createElement('p');
          d.className = 'validate-detail validate-warn';
          d.textContent = w;
          content.appendChild(d);
        }
      }
    }
  }, { method: 'POST' });
}

// --- Analysis settings modal ---

/**
 * Show the analysis settings modal, populated from the API.
 * @async
 */
async function showAnalysisSettings() {
  console.log('[showAnalysisSettings] Loading settings...');
  const modal = document.getElementById('analysis-modal');
  const statusEl = document.getElementById('analysis-status');
  if (!modal) {
    console.error('[showAnalysisSettings] Modal not found');
    return;
  }

  modal.classList.remove('hidden');
  if (statusEl) statusEl.textContent = '';

  try {
    const resp = await fetch('/api/analysis/settings');
    if (!resp.ok) {
      if (statusEl) statusEl.textContent = 'Failed to load settings.';
      return;
    }
    const data = await resp.json();
    console.log('[showAnalysisSettings] Settings loaded:', data);

    document.getElementById('analysis-threads').value = data.threads;
    document.getElementById('analysis-hash').value = data.hash_mb;

    const lim = data.limits || {};
    if (lim.kings_pawns_le7) {
      document.getElementById('limit-kp-depth').value = lim.kings_pawns_le7.depth || 60;
      document.getElementById('limit-kp-time').value = lim.kings_pawns_le7.time || 6;
    }
    if (lim.pieces_le7) {
      document.getElementById('limit-eg-depth').value = lim.pieces_le7.depth || 50;
      document.getElementById('limit-eg-time').value = lim.pieces_le7.time || 5;
    }
    if (lim.pieces_le12) {
      document.getElementById('limit-mg-depth').value = lim.pieces_le12.depth || 40;
      document.getElementById('limit-mg-time').value = lim.pieces_le12.time || 4;
    }
    if (lim.default) {
      document.getElementById('limit-default-depth').value = lim.default.depth || 18;
    }
  } catch (err) {
    console.error('[showAnalysisSettings] Error:', err);
    if (statusEl) statusEl.textContent = 'Connection failed.';
  }
}

/**
 * Read settings from the modal form, save them, then start analysis.
 * @param {boolean} reanalyzeAll - If true, re-analyze all games.
 * @async
 */
async function startAnalysis(reanalyzeAll = false) {
  console.log('[startAnalysis] reanalyzeAll:', reanalyzeAll);
  const statusEl = document.getElementById('analysis-status');

  // Read form values
  const settings = {
    threads: parseInt(document.getElementById('analysis-threads').value, 10),
    hash_mb: parseInt(document.getElementById('analysis-hash').value, 10),
    limits: {
      kings_pawns_le7: {
        depth: parseInt(document.getElementById('limit-kp-depth').value, 10),
        time: parseFloat(document.getElementById('limit-kp-time').value),
      },
      pieces_le7: {
        depth: parseInt(document.getElementById('limit-eg-depth').value, 10),
        time: parseFloat(document.getElementById('limit-eg-time').value),
      },
      pieces_le12: {
        depth: parseInt(document.getElementById('limit-mg-depth').value, 10),
        time: parseFloat(document.getElementById('limit-mg-time').value),
      },
      default: {
        depth: parseInt(document.getElementById('limit-default-depth').value, 10),
      },
    },
  };
  const maxGames = parseInt(document.getElementById('analysis-max-games').value, 10);

  // Save settings
  try {
    const saveResp = await fetch('/api/analysis/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    });
    if (!saveResp.ok) {
      if (statusEl) statusEl.textContent = 'Failed to save settings.';
      return;
    }
  } catch (err) {
    console.error('[startAnalysis] Save settings failed:', err);
    if (statusEl) statusEl.textContent = 'Connection failed.';
    return;
  }

  // Hide analysis modal, start analysis job
  document.getElementById('analysis-modal').classList.add('hidden');

  // Start analysis via the existing refresh progress modal
  try {
    const resp = await fetch('/api/analysis/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ max_games: maxGames, reanalyze_all: reanalyzeAll }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      console.error('[startAnalysis] API error:', resp.status, err.detail);
      return;
    }
    const { job_id: jobId } = await resp.json();
    console.log('[startAnalysis] Job started:', jobId);

    // Reuse the refresh modal for progress display
    showAnalysisProgress(jobId);
  } catch (err) {
    console.error('[startAnalysis] Fetch failed:', err);
  }
}

/**
 * Display analysis job progress in the refresh modal.
 * @param {string} jobId - The job ID to track.
 */
function showAnalysisProgress(jobId) {
  const modal = document.getElementById('refresh-modal');
  const stepsContainer = document.getElementById('refresh-steps');
  const interruptBtn = document.getElementById('interrupt-refresh');
  if (!modal || !stepsContainer) return;

  modal.classList.remove('hidden');
  stepsContainer.innerHTML = '<div class="refresh-step">Starting analysis...</div>';
  if (interruptBtn) {
    interruptBtn.classList.remove('hidden');
    interruptBtn.onclick = async () => {
      try {
        await fetch(`/api/jobs/${jobId}/cancel`, { method: 'POST' });
      } catch (err) {
        console.error('[showAnalysisProgress] Cancel failed:', err);
      }
    };
  }

  const evtSource = new EventSource(`/api/jobs/${jobId}/events`);
  evtSource.onmessage = (e) => {
    const event = JSON.parse(e.data);
    console.log('[showAnalysisProgress] Event:', event.phase, event.percent);

    const stepEl = document.createElement('div');
    stepEl.className = 'refresh-step';
    stepEl.textContent = event.message || event.phase;
    if (event.percent != null) {
      stepEl.textContent += ` (${event.percent}%)`;
    }
    stepsContainer.appendChild(stepEl);
    stepsContainer.scrollTop = stepsContainer.scrollHeight;

    if (event.phase === 'done' || event.phase === 'error' || event.phase === 'interrupted') {
      evtSource.close();
      if (interruptBtn) interruptBtn.classList.add('hidden');
    }
  };
  evtSource.onerror = () => {
    evtSource.close();
    if (interruptBtn) interruptBtn.classList.add('hidden');
  };
}

// --- Refresh training ---

/**
 * Start a training refresh job and display progress in a modal.
 * POSTs to /api/train/prepare, then opens an EventSource on
 * /api/jobs/{id}/events to stream progress updates.
 * @async
 */
async function refreshTraining() {
  console.log('[refreshTraining] Starting refresh...');
  const modal = document.getElementById('refresh-modal');
  const stepsContainer = document.getElementById('refresh-steps');
  const interruptBtn = document.getElementById('interrupt-refresh');
  if (!modal || !stepsContainer) {
    console.error('[refreshTraining] Modal elements not found');
    return;
  }

  // Step definitions: id, default text
  const STEPS = [
    { id: 'init', text: 'Detecting Stockfish...' },
    { id: 'fetch', text: 'Fetching games...' },
    { id: 'analyze', text: 'Analyzing games...' },
    { id: 'finalize', text: 'Generating training data' },
  ];

  // Render initial step list (all pending) using safe DOM methods
  while (stepsContainer.firstChild) stepsContainer.firstChild.remove();
  const stepEls = {};
  for (const step of STEPS) {
    const div = document.createElement('div');
    div.className = 'refresh-step step-pending';
    const icon = document.createElement('span');
    icon.className = 'step-icon';
    icon.textContent = '\u25CB';
    const text = document.createElement('span');
    text.className = 'step-text';
    text.textContent = step.text;
    div.appendChild(icon);
    div.appendChild(text);
    stepsContainer.appendChild(div);
    stepEls[step.id] = div;
  }

  let sawAnalyze = false;

  /**
   * Update a step's visual state and text.
   * @param {string} id - Step id
   * @param {'done'|'active'|'pending'|'error'} state
   * @param {string} [text] - Optional new text
   * @param {number|null} [progressValue] - If set, add/update progress bar
   */
  function setStep(id, state, text, progressValue) {
    const el = stepEls[id];
    if (!el) return;
    const icons = { done: '\u2713', active: '\u27F3', pending: '\u25CB', error: '\u2717' };
    el.className = 'refresh-step step-' + state;
    el.querySelector('.step-icon').textContent = icons[state];
    if (text) el.querySelector('.step-text').textContent = text;

    // Progress bar for active analyze step
    let bar = el.querySelector('.step-progress');
    if (progressValue != null && state === 'active') {
      if (!bar) {
        bar = document.createElement('progress');
        bar.className = 'step-progress';
        bar.max = 100;
        el.appendChild(bar);
      }
      bar.value = progressValue;
    } else if (bar) {
      bar.remove();
    }
  }

  /** Mark all steps up to (but not including) targetId as done. */
  function markPriorDone(targetId) {
    for (const step of STEPS) {
      if (step.id === targetId) break;
      const el = stepEls[step.id];
      if (el && !el.classList.contains('step-done')) {
        setStep(step.id, 'done');
      }
    }
  }

  modal.classList.remove('hidden');

  try {
    const resp = await fetch('/api/train/prepare', { method: 'POST' });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
      console.log('[refreshTraining] API error:', resp.status, err.detail);
      setStep('init', 'error', err.detail || 'Failed to start refresh.');
      return;
    }
    const data = await resp.json();
    const jobId = data.job_id;
    console.log('[refreshTraining] Job started:', jobId);

    // Show interrupt button and wire cancel
    if (interruptBtn) {
      interruptBtn.classList.remove('hidden');
      interruptBtn.disabled = false;
      interruptBtn.textContent = 'Interrupt';
      interruptBtn.addEventListener('click', async () => {
        console.log('[refreshTraining] Interrupt requested');
        interruptBtn.disabled = true;
        interruptBtn.textContent = 'Stopping\u2026';
        try {
          await fetch('/api/jobs/' + jobId + '/cancel', { method: 'POST' });
        } catch (err) {
          console.error('[refreshTraining] Cancel request failed:', err);
        }
      }, { once: true });
    }

    const eventSource = new EventSource('/api/jobs/' + jobId + '/events');
    eventSource.onmessage = async (e) => {
      const event = JSON.parse(e.data);
      console.log('[refreshTraining] Event:', event.phase, event.percent, event.current, event.total);

      if (event.phase === 'init') {
        setStep('init', 'active', event.message);
      } else if (event.phase === 'fetch') {
        markPriorDone('fetch');
        if (event.percent <= 5) {
          setStep('fetch', 'active', 'Fetching games...');
        } else {
          setStep('fetch', 'active', event.message);
        }
      } else if (event.phase === 'analyze') {
        sawAnalyze = true;
        markPriorDone('analyze');
        const label = event.current + '/' + event.total;
        setStep('analyze', 'active', 'Analyzing games  ' + label, event.percent);
      } else if (event.phase === 'done') {
        eventSource.close();
        if (interruptBtn) interruptBtn.classList.add('hidden');
        // If no analyze events were received, remove the analyze step
        if (!sawAnalyze) {
          stepEls.analyze.remove();
        } else {
          setStep('analyze', 'done', 'Analysis complete');
        }
        markPriorDone('finalize');
        setStep('finalize', 'done', 'Training data saved');
        const summary = document.createElement('p');
        summary.className = 'refresh-summary';
        summary.textContent = event.message;
        stepsContainer.after(summary);

        // Reload training data and restart session
        try {
          const tdResp = await fetch('training_data.json');
          if (tdResp.ok) {
            trainingData = await tdResp.json();
            console.log('[refreshTraining] Reloaded training data:', trainingData.positions.length, 'positions');
            srsState = loadSRSState();
            startSession();
          }
        } catch (err) {
          console.error('[refreshTraining] Failed to reload training data:', err);
        }
      } else if (event.phase === 'interrupted') {
        eventSource.close();
        if (interruptBtn) interruptBtn.classList.add('hidden');
        if (!sawAnalyze) {
          stepEls.analyze.remove();
        } else {
          setStep('analyze', 'done', 'Analysis interrupted \u2014 partial results saved');
        }
        markPriorDone('finalize');
        setStep('finalize', 'done', 'Training data saved');
        const intSummary = document.createElement('p');
        intSummary.className = 'refresh-summary';
        intSummary.textContent = event.message;
        stepsContainer.after(intSummary);

        // Reload partial training data
        try {
          const tdResp = await fetch('training_data.json');
          if (tdResp.ok) {
            trainingData = await tdResp.json();
            console.log('[refreshTraining] Reloaded partial training data:', trainingData.positions.length, 'positions');
            srsState = loadSRSState();
            startSession();
          }
        } catch (err) {
          console.error('[refreshTraining] Failed to reload training data:', err);
        }
      } else if (event.phase === 'error') {
        eventSource.close();
        if (interruptBtn) interruptBtn.classList.add('hidden');
        // Mark current active step as error, or init if none active
        let marked = false;
        for (const step of STEPS) {
          if (stepEls[step.id] && stepEls[step.id].classList.contains('step-active')) {
            setStep(step.id, 'error', event.message);
            marked = true;
            break;
          }
        }
        if (!marked) setStep('init', 'error', event.message);
      }
    };
    eventSource.onerror = () => {
      console.log('[refreshTraining] EventSource error');
      eventSource.close();
      if (interruptBtn) interruptBtn.classList.add('hidden');
      // Mark active step as error
      for (const step of STEPS) {
        if (stepEls[step.id] && stepEls[step.id].classList.contains('step-active')) {
          setStep(step.id, 'error', 'Connection lost. Check server logs.');
          return;
        }
      }
      setStep('init', 'error', 'Connection lost. Check server logs.');
    };
  } catch (err) {
    console.error('[refreshTraining] Fetch failed:', err);
    setStep('init', 'error', 'Failed to connect to server.');
  }
}

// --- Config modal ---

/**
 * Fetch config from backend and populate the config modal.
 * @async
 */
async function showConfig() {
  console.log('[showConfig] Fetching config...');
  const modal = document.getElementById('config-modal');
  const statusEl = document.getElementById('config-status');
  statusEl.textContent = '';
  modal.classList.remove('hidden');

  try {
    const resp = await fetch('/api/config');
    if (!resp.ok) {
      statusEl.textContent = 'Failed to load config.';
      return;
    }
    const data = await resp.json();
    console.log('[showConfig] Config loaded');

    document.getElementById('config-lichess').value = data.players.lichess || '';
    document.getElementById('config-chesscom').value = data.players.chesscom || '';
    document.getElementById('config-depth').value = data.analysis.default_depth || 18;
    document.getElementById('config-threshold').value = data.analysis.blunder_threshold || 1.0;
  } catch (err) {
    console.error('[showConfig] Fetch failed:', err);
    statusEl.textContent = 'Failed to connect to server.';
  }
}

/**
 * Save config modal values to backend.
 * @async
 */
async function saveConfig() {
  console.log('[saveConfig] Saving config...');
  const statusEl = document.getElementById('config-status');
  statusEl.textContent = 'Saving...';

  const body = {
    players: {
      lichess: document.getElementById('config-lichess').value.trim(),
      chesscom: document.getElementById('config-chesscom').value.trim(),
    },
    analysis: {
      default_depth: parseInt(document.getElementById('config-depth').value) || 18,
      blunder_threshold: parseFloat(document.getElementById('config-threshold').value) || 1.0,
    },
  };

  try {
    const resp = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (resp.ok) {
      console.log('[saveConfig] Config saved');
      statusEl.textContent = 'Saved!';
    } else {
      statusEl.textContent = 'Failed to save.';
    }
  } catch (err) {
    console.error('[saveConfig] Fetch failed:', err);
    statusEl.textContent = 'Failed to connect to server.';
  }
}

// --- Journal modal ---

/**
 * Strip YAML front matter from markdown content.
 * @param {string} text - Full file content with optional --- front matter ---.
 * @returns {string} Body text without front matter.
 */
function stripFrontmatter(text) {
  if (!text.startsWith('---')) return text;
  const end = text.indexOf('---', 3);
  if (end === -1) return text;
  return text.slice(end + 3).trim();
}

/**
 * Fetch and display the coaching journal topic list in a modal.
 * @async
 */
async function showJournal() {
  console.log('[showJournal] Fetching coaching topics...');
  const modal = document.getElementById('journal-modal');
  const content = document.getElementById('journal-content');
  const title = document.getElementById('journal-title');
  const backBtn = document.getElementById('journal-back');
  if (!modal || !content) {
    console.error('[showJournal] Modal elements not found');
    return;
  }

  title.textContent = 'Coaching Journal';
  backBtn.classList.add('hidden');
  content.textContent = 'Loading...';
  modal.classList.remove('hidden');

  try {
    const resp = await fetch('/api/coaching/topics');
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
      console.log('[showJournal] API error:', resp.status, err.detail);
      content.textContent = err.detail || 'Failed to load journal.';
      return;
    }
    const data = await resp.json();
    console.log('[showJournal] Topics received:', data.topics.length);

    content.textContent = '';

    if (data.topics.length === 0) {
      content.textContent = 'No coaching topics yet.';
      return;
    }

    for (const topic of data.topics) {
      const div = document.createElement('div');
      div.className = 'journal-topic';
      div.addEventListener('click', () => showJournalTopic(topic.slug));

      const titleLine = document.createElement('div');
      titleLine.textContent = topic.topic;
      if (topic.status) {
        const badge = document.createElement('span');
        badge.className = 'journal-topic-status ' + topic.status;
        badge.textContent = topic.status;
        titleLine.appendChild(badge);
      }
      div.appendChild(titleLine);

      const dateLine = document.createElement('div');
      dateLine.className = 'journal-topic-date';
      dateLine.textContent = topic.date;
      div.appendChild(dateLine);

      content.appendChild(div);
    }
  } catch (err) {
    console.error('[showJournal] Fetch failed:', err);
    content.textContent = 'Failed to connect to server.';
  }
}

/**
 * Fetch and display one coaching topic in the journal modal.
 * @param {string} slug - Topic slug (filename without .md).
 * @async
 */
async function showJournalTopic(slug) {
  console.log('[showJournalTopic] Fetching:', slug);
  const content = document.getElementById('journal-content');
  const title = document.getElementById('journal-title');
  const backBtn = document.getElementById('journal-back');

  content.textContent = 'Loading...';
  backBtn.classList.remove('hidden');

  try {
    const resp = await fetch('/api/coaching/topics/' + slug);
    if (!resp.ok) {
      content.textContent = 'Failed to load topic.';
      return;
    }
    const data = await resp.json();
    console.log('[showJournalTopic] Content loaded:', slug);

    const body = stripFrontmatter(data.content);
    title.textContent = slug.replace(/^\d{4}-\d{2}-\d{2}-/, '').replace(/-/g, ' ');
    content.textContent = '';
    const pre = document.createElement('div');
    pre.className = 'journal-detail';
    pre.textContent = body;
    content.appendChild(pre);
  } catch (err) {
    console.error('[showJournalTopic] Fetch failed:', err);
    content.textContent = 'Failed to connect to server.';
  }
}

// --- Analysis mode ---

/**
 * Switch to training view.
 */
function showTrainingMode() {
  console.log('[showTrainingMode] Switching to training');
  appView = 'training';
  document.getElementById('training-view').classList.remove('hidden');
  document.getElementById('analysis-view').classList.add('hidden');
  document.getElementById('mode-training').classList.add('active');
  document.getElementById('mode-analysis').classList.remove('active');
  if (autoPlayTimer) { clearInterval(autoPlayTimer); autoPlayTimer = null; }
}

/**
 * Switch to analysis view.
 */
function showAnalysisMode() {
  console.log('[showAnalysisMode] Switching to analysis');
  appView = 'analysis';
  document.getElementById('training-view').classList.add('hidden');
  document.getElementById('analysis-view').classList.remove('hidden');
  document.getElementById('mode-training').classList.remove('active');
  document.getElementById('mode-analysis').classList.add('active');
  document.getElementById('progress').textContent = '';
  if (!analysisData) {
    loadAnalysisData();
  } else {
    showGameSelector();
  }
}

/**
 * Load analysis_data.json from server or static file.
 */
async function loadAnalysisData() {
  console.log('[loadAnalysisData] Fetching analysis data...');
  const selector = document.getElementById('game-selector');
  selector.textContent = 'Loading analysis data...';
  try {
    const resp = await fetch('analysis_data.json');
    if (!resp.ok) {
      selector.textContent = appMode === 'app'
        ? 'No analysis data. Use menu → Analyse latest games.'
        : 'No analysis data available.';
      console.log('[loadAnalysisData] Not found:', resp.status);
      return;
    }
    analysisData = await resp.json();
    console.log(`[loadAnalysisData] Loaded ${Object.keys(analysisData.games || {}).length} game(s)`);
    showGameSelector();
  } catch (err) {
    console.error('[loadAnalysisData] Failed:', err);
    selector.textContent = 'Failed to load analysis data.';
  }
}

/**
 * Compute win probability from centipawn score (chess.com model).
 * @param {number} cp - Centipawn score from white's perspective.
 * @returns {number} Win probability for the side (0-1).
 */
function winProb(cp) {
  return 1 / (1 + Math.pow(10, -cp / 400));
}

/**
 * Classify a move based on expected points lost.
 * @param {Object} move - Move data from analysis_data.json.
 * @param {string} playerColor - 'white' or 'black'.
 * @returns {{category: string, symbol: string, color: string, cssClass: string}}
 */
function classifyMove(move, playerColor) {
  // Book moves
  if (move.eval_source === 'opening_explorer') {
    return { category: 'book', symbol: '\u2657', color: '#a88764', cssClass: 'class-book' };
  }

  const evalBefore = move.eval_before;
  const evalAfter = move.eval_after;

  // No eval data available
  if (!evalBefore || evalBefore.score_cp == null || !evalAfter || evalAfter.score_cp == null) {
    return null;
  }

  // Mate detection
  if (evalBefore.is_mate && evalBefore.mate_in != null) {
    const mateForPlayer = (playerColor === 'white') ? evalBefore.mate_in > 0 : evalBefore.mate_in < 0;
    if (mateForPlayer) {
      // Player had mate, check if they played best
      if (evalAfter.is_mate && evalAfter.mate_in != null) {
        const stillMate = (playerColor === 'white') ? evalAfter.mate_in > 0 : evalAfter.mate_in < 0;
        if (!stillMate) {
          return { category: 'missed_win', symbol: '\u00d7', color: '#ca3431', cssClass: 'class-missed-win' };
        }
      } else {
        return { category: 'missed_win', symbol: '\u00d7', color: '#ca3431', cssClass: 'class-missed-win' };
      }
    }
  }

  // Win probability model
  const sign = playerColor === 'white' ? 1 : -1;
  const wpBefore = winProb(evalBefore.score_cp * sign);
  const wpAfter = winProb(evalAfter.score_cp * sign);
  const eplLost = wpBefore - wpAfter;

  if (eplLost <= 0) {
    return { category: 'best', symbol: '\u2605', color: '#96bc4b', cssClass: 'class-best' };
  } else if (eplLost <= 0.02) {
    return { category: 'excellent', symbol: '!', color: '#96bc4b', cssClass: 'class-excellent' };
  } else if (eplLost <= 0.05) {
    return { category: 'good', symbol: '', color: '#95b776', cssClass: 'class-good' };
  } else if (eplLost <= 0.10) {
    return { category: 'inaccuracy', symbol: '?!', color: '#f7c631', cssClass: 'class-inaccuracy' };
  } else if (eplLost <= 0.20) {
    return { category: 'mistake', symbol: '?', color: '#e6912a', cssClass: 'class-mistake' };
  } else {
    return { category: 'blunder', symbol: '??', color: '#ca3431', cssClass: 'class-blunder' };
  }
}

/**
 * Classify all moves in a game for both players.
 * @param {Array} moves - Array of move objects.
 * @param {string} playerColor - Player's color.
 * @returns {Array} Array of classification objects (one per move, null if unclassifiable).
 */
function classifyAllMoves(moves, playerColor) {
  return moves.map(move => {
    const color = move.side;
    return classifyMove(move, color);
  });
}

/**
 * Compute accuracy percentage for a color.
 * @param {Array} moves - All moves.
 * @param {Array} classifications - Classification for each move.
 * @param {string} color - 'white' or 'black'.
 * @returns {number} Accuracy 0-100.
 */
function computeAccuracy(moves, classifications, color) {
  let sum = 0;
  let count = 0;
  for (let i = 0; i < moves.length; i++) {
    const move = moves[i];
    if (move.side !== color) continue;
    if (move.eval_source === 'opening_explorer') continue;
    const eb = move.eval_before;
    const ea = move.eval_after;
    if (!eb || eb.score_cp == null || !ea || ea.score_cp == null) continue;

    const sign = color === 'white' ? 1 : -1;
    const wpBefore = winProb(eb.score_cp * sign);
    const wpAfter = winProb(ea.score_cp * sign);

    if (wpBefore <= 0) continue; // avoid division by zero
    const moveAcc = Math.min(wpAfter / wpBefore, 1.0);
    sum += moveAcc;
    count++;
  }
  return count > 0 ? Math.round((sum / count) * 100) : null;
}

/**
 * Render the game selector list.
 */
function showGameSelector() {
  console.log('[showGameSelector] Rendering game list');
  const selector = document.getElementById('game-selector');
  const review = document.getElementById('game-review');
  selector.textContent = '';
  selector.classList.remove('hidden');
  review.classList.add('hidden');

  if (!analysisData || !analysisData.games || Object.keys(analysisData.games).length === 0) {
    selector.textContent = 'No analyzed games available.';
    return;
  }

  // Sort games by date descending
  const gameEntries = Object.entries(analysisData.games);
  gameEntries.sort((a, b) => {
    const da = a[1].headers.date || '';
    const db = b[1].headers.date || '';
    return db.localeCompare(da);
  });

  for (const [gameId, game] of gameEntries) {
    const card = document.createElement('div');
    card.className = 'game-card';
    card.addEventListener('click', () => selectGame(gameId));

    // Result badge
    const resultEl = document.createElement('div');
    resultEl.className = 'game-card-result';
    const result = game.headers.result;
    const playerColor = game.player_color;
    const isWin = (result === '1-0' && playerColor === 'white') || (result === '0-1' && playerColor === 'black');
    const isLoss = (result === '1-0' && playerColor === 'black') || (result === '0-1' && playerColor === 'white');
    if (isWin) {
      resultEl.textContent = 'W';
      resultEl.classList.add('win');
    } else if (isLoss) {
      resultEl.textContent = 'L';
      resultEl.classList.add('loss');
    } else {
      resultEl.textContent = 'D';
      resultEl.classList.add('draw');
    }
    card.appendChild(resultEl);

    // Info
    const infoEl = document.createElement('div');
    infoEl.className = 'game-card-info';
    const opponent = document.createElement('div');
    opponent.className = 'game-card-opponent';
    const opponentName = playerColor === 'white' ? game.headers.black : game.headers.white;
    opponent.textContent = `vs ${opponentName}`;
    infoEl.appendChild(opponent);

    const meta = document.createElement('div');
    meta.className = 'game-card-meta';
    const dateStr = (game.headers.date || '').replace(/\./g, '-');
    // Find opening name from first opening_explorer move
    let openingName = '';
    for (const m of game.moves) {
      if (m.opening_explorer && m.opening_explorer.moves) {
        for (const om of m.opening_explorer.moves) {
          if (om.opening && om.opening.name && om.uci === m.move_uci) {
            openingName = om.opening.name;
            break;
          }
        }
        if (openingName) break;
      }
    }
    meta.textContent = `${dateStr} · ${game.moves.length} moves${openingName ? ' · ' + openingName : ''}`;
    infoEl.appendChild(meta);
    card.appendChild(infoEl);

    selector.appendChild(card);
  }
}

/**
 * Select a game for review.
 * @param {string} gameId - Game URL key.
 */
function selectGame(gameId) {
  console.log('[selectGame] Selected:', gameId);
  reviewGame = analysisData.games[gameId];
  reviewGame._id = gameId;
  currentPly = 0;
  reviewOrientation = reviewGame.player_color;

  // Classify all moves
  classifiedMoves = classifyAllMoves(reviewGame.moves, reviewGame.player_color);

  // Hide selector, show review
  document.getElementById('game-selector').classList.add('hidden');
  document.getElementById('game-review').classList.remove('hidden');

  // Game info bar
  const infoEl = document.getElementById('review-game-info');
  const result = reviewGame.headers.result;
  infoEl.textContent = `${reviewGame.headers.white} vs ${reviewGame.headers.black}  ${result}`;

  // Render components
  renderGameSummary();
  renderOpeningInfo();
  renderMoveList();
  setupReviewBoard();
  goToMove(0);
  renderScoreChart();
}

/**
 * Find the opening name from the game moves.
 * @returns {string} Opening name or empty string.
 */
function getOpeningName() {
  let name = '';
  let eco = '';
  if (!reviewGame) return '';
  for (const m of reviewGame.moves) {
    if (m.opening_explorer && m.opening_explorer.moves) {
      for (const om of m.opening_explorer.moves) {
        if (om.opening && om.opening.name && om.uci === m.move_uci) {
          name = om.opening.name;
          eco = om.opening.eco || '';
        }
      }
    }
  }
  return eco ? `${eco}: ${name}` : name;
}

/**
 * Render the game summary (accuracy + classification counts).
 */
function renderGameSummary() {
  const el = document.getElementById('review-summary');
  el.textContent = '';

  const whiteAcc = computeAccuracy(reviewGame.moves, classifiedMoves, 'white');
  const blackAcc = computeAccuracy(reviewGame.moves, classifiedMoves, 'black');

  // Count classifications per color
  const counts = { white: {}, black: {} };
  for (let i = 0; i < reviewGame.moves.length; i++) {
    const cls = classifiedMoves[i];
    const side = reviewGame.moves[i].side;
    if (cls) {
      counts[side][cls.category] = (counts[side][cls.category] || 0) + 1;
    }
  }

  for (const color of ['white', 'black']) {
    const acc = color === 'white' ? whiteAcc : blackAcc;
    const block = document.createElement('div');
    block.className = 'accuracy-block';

    if (acc !== null) {
      const val = document.createElement('div');
      val.className = 'accuracy-value';
      val.textContent = `${acc}%`;
      block.appendChild(val);
    }

    const label = document.createElement('div');
    label.className = 'accuracy-label';
    label.textContent = color === 'white' ? reviewGame.headers.white : reviewGame.headers.black;
    block.appendChild(label);

    // Classification badges
    const badges = document.createElement('div');
    badges.className = 'classification-badges';
    const categories = [
      { key: 'best', label: '\u2605', color: '#96bc4b' },
      { key: 'excellent', label: '!', color: '#96bc4b' },
      { key: 'good', label: 'good', color: '#95b776' },
      { key: 'inaccuracy', label: '?!', color: '#f7c631' },
      { key: 'mistake', label: '?', color: '#e6912a' },
      { key: 'blunder', label: '??', color: '#ca3431' },
    ];
    for (const cat of categories) {
      const c = counts[color][cat.key] || 0;
      if (c > 0) {
        const badge = document.createElement('span');
        badge.className = 'class-badge';
        badge.style.color = cat.color;
        badge.style.border = `1px solid ${cat.color}`;
        badge.textContent = `${c}${cat.label}`;
        badges.appendChild(badge);
      }
    }
    block.appendChild(badges);
    el.appendChild(block);
  }
}

/**
 * Render opening info.
 */
function renderOpeningInfo() {
  const el = document.getElementById('review-opening');
  const name = getOpeningName();
  el.textContent = name || '';
}

/**
 * Render the two-column move list.
 */
function renderMoveList() {
  const el = document.getElementById('review-moves');
  el.textContent = '';

  const moves = reviewGame.moves;
  // Find theory departure point
  let theoryDeparture = -1;
  for (let i = 0; i < moves.length; i++) {
    if (i > 0 && moves[i].eval_source !== 'opening_explorer' && moves[i - 1].eval_source === 'opening_explorer') {
      theoryDeparture = i;
      break;
    }
  }

  for (let i = 0; i < moves.length; i += 2) {
    const moveNum = Math.floor(i / 2) + 1;

    // Move number
    const numEl = document.createElement('div');
    numEl.className = 'move-number';
    numEl.textContent = moveNum + '.';
    el.appendChild(numEl);

    // White move
    const whiteCell = createMoveCell(i, moves[i], classifiedMoves[i], theoryDeparture);
    el.appendChild(whiteCell);

    // Black move
    if (i + 1 < moves.length) {
      const blackCell = createMoveCell(i + 1, moves[i + 1], classifiedMoves[i + 1], theoryDeparture);
      el.appendChild(blackCell);
    } else {
      el.appendChild(document.createElement('div'));
    }
  }
}

/**
 * Create a move cell element for the move list.
 * @param {number} idx - Move index in the moves array.
 * @param {Object} move - Move data.
 * @param {?Object} cls - Classification data.
 * @param {number} theoryDep - Index of theory departure.
 * @returns {HTMLElement}
 */
function createMoveCell(idx, move, cls, theoryDep) {
  const cell = document.createElement('div');
  cell.className = 'move-cell';
  cell.dataset.ply = move.ply;
  if (idx === theoryDep) cell.classList.add('theory-marker');

  if (cls) {
    const dot = document.createElement('span');
    dot.className = 'class-dot';
    dot.style.backgroundColor = cls.color;
    cell.appendChild(dot);

    if (cls.symbol) {
      const sym = document.createElement('span');
      sym.className = 'class-symbol';
      sym.style.color = cls.color;
      sym.textContent = cls.symbol;
      cell.appendChild(sym);
    }
  }

  const san = document.createElement('span');
  san.textContent = move.move_san;
  cell.appendChild(san);

  cell.addEventListener('click', () => goToMove(move.ply));
  return cell;
}

/**
 * Navigate to a specific ply in the review.
 * @param {number} ply - Move ply (0 = starting position).
 */
function goToMove(ply) {
  if (!reviewGame) return;
  ply = Math.max(0, Math.min(ply, reviewGame.moves.length));
  currentPly = ply;

  // Determine FEN
  let fen;
  if (ply === 0) {
    fen = reviewGame.moves.length > 0 ? reviewGame.moves[0].fen_before : 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
  } else {
    fen = reviewGame.moves[ply - 1].fen_after;
  }

  // Determine last move highlight
  let lastMove = undefined;
  if (ply > 0) {
    const uci = reviewGame.moves[ply - 1].move_uci;
    lastMove = [uci.slice(0, 2), uci.slice(2, 4)];
  }

  // Update board
  if (reviewCg) {
    reviewCg.set({
      fen,
      lastMove,
      drawable: { autoShapes: [] },
    });
    updateBoardArrows(ply);
  }

  // Update eval bar
  updateEvalBar(ply);

  // Highlight active move in list
  const moveCells = document.querySelectorAll('#review-moves .move-cell');
  moveCells.forEach(cell => {
    cell.classList.toggle('active-move', parseInt(cell.dataset.ply) === ply);
  });

  // Auto-scroll move list to active move
  const activeCell = document.querySelector('#review-moves .move-cell.active-move');
  if (activeCell) {
    activeCell.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  // Update PV line
  updatePvLine(ply);

  // Update score chart cursor
  updateChartCursor();
}

/**
 * Set up the review board (second Chessground instance).
 */
function setupReviewBoard() {
  console.log('[setupReviewBoard] Creating review board');
  const boardEl = document.getElementById('review-board');
  if (reviewCg) reviewCg.destroy();

  reviewCg = Chessground(boardEl, {
    fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
    orientation: reviewOrientation,
    viewOnly: true,
    coordinates: true,
    highlight: { lastMove: true },
  });
}

/**
 * Update the eval bar for a given ply.
 * @param {number} ply - Current ply.
 */
function updateEvalBar(ply) {
  const fill = document.getElementById('eval-bar-fill');
  const label = document.getElementById('eval-bar-label');

  if (ply === 0 || !reviewGame) {
    fill.style.height = '50%';
    label.textContent = '0.0';
    return;
  }

  const move = reviewGame.moves[ply - 1];
  const evalData = move.eval_after;

  if (!evalData || evalData.score_cp == null) {
    // Book move or no eval
    fill.style.height = '50%';
    label.textContent = move.eval_source === 'opening_explorer' ? 'Book' : '—';
    return;
  }

  if (evalData.is_mate && evalData.mate_in != null) {
    const mateMoves = evalData.mate_in;
    fill.style.height = mateMoves > 0 ? '95%' : '5%';
    label.textContent = `M${Math.abs(mateMoves)}`;
    return;
  }

  const cp = evalData.score_cp;
  // Sigmoid mapping: 50 + 50 * (2/(1+exp(-cp/200)) - 1)
  const pct = 50 + 50 * (2 / (1 + Math.exp(-cp / 200)) - 1);
  const clamped = Math.max(3, Math.min(97, pct));
  fill.style.height = clamped + '%';

  const pawns = cp / 100;
  label.textContent = (pawns >= 0 ? '+' : '') + pawns.toFixed(1);
}

/**
 * Update board arrows showing best move and played move.
 * @param {number} ply - Current ply.
 */
function updateBoardArrows(ply) {
  if (!reviewCg || !reviewGame || ply === 0) {
    if (reviewCg) reviewCg.set({ drawable: { autoShapes: [] } });
    return;
  }

  const move = reviewGame.moves[ply - 1];
  const shapes = [];

  // Best move arrow (green) — from eval_before of current move
  const evalBefore = move.eval_before;
  if (evalBefore && evalBefore.best_move_uci) {
    const bestUci = evalBefore.best_move_uci;
    shapes.push({
      orig: bestUci.slice(0, 2),
      dest: bestUci.slice(2, 4),
      brush: 'green',
    });
  }

  // Played move arrow (red) if it's a mistake/blunder/inaccuracy
  const cls = classifiedMoves ? classifiedMoves[ply - 1] : null;
  if (cls && ['inaccuracy', 'mistake', 'blunder', 'missed_win'].includes(cls.category)) {
    const playedUci = move.move_uci;
    const bestUci = evalBefore ? evalBefore.best_move_uci : null;
    if (bestUci && playedUci !== bestUci) {
      shapes.push({
        orig: playedUci.slice(0, 2),
        dest: playedUci.slice(2, 4),
        brush: 'red',
      });
    }
  }

  reviewCg.set({ drawable: { autoShapes: shapes } });
}

/**
 * Update the PV line display.
 * @param {number} ply - Current ply.
 */
function updatePvLine(ply) {
  const el = document.getElementById('review-pv');
  if (ply === 0 || !reviewGame) {
    el.textContent = '';
    return;
  }

  const move = reviewGame.moves[ply - 1];
  const evalBefore = move.eval_before;
  if (evalBefore && evalBefore.pv_san && evalBefore.pv_san.length > 0) {
    const depth = evalBefore.depth ? ` (depth ${evalBefore.depth})` : '';
    el.textContent = `Best: ${evalBefore.pv_san.slice(0, 8).join(' ')}${depth}`;
  } else {
    el.textContent = '';
  }
}

/**
 * Render the score chart.
 */
function renderScoreChart() {
  const canvas = document.getElementById('score-chart');
  if (!canvas || !reviewGame) return;
  const ctx = canvas.getContext('2d');
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * devicePixelRatio;
  canvas.height = rect.height * devicePixelRatio;
  ctx.scale(devicePixelRatio, devicePixelRatio);
  const w = rect.width;
  const h = rect.height;

  ctx.clearRect(0, 0, w, h);

  const moves = reviewGame.moves;
  if (moves.length === 0) return;

  const maxCp = 1000; // clamp
  const midY = h / 2;

  /**
   * Get eval value for a move, clamped.
   * @param {Object} move
   * @returns {number} cp value, clamped.
   */
  function getEval(move) {
    const ea = move.eval_after;
    if (!ea || ea.score_cp == null) return 0;
    if (ea.is_mate && ea.mate_in != null) return ea.mate_in > 0 ? maxCp : -maxCp;
    return Math.max(-maxCp, Math.min(maxCp, ea.score_cp));
  }

  function cpToY(cp) {
    return midY - (cp / maxCp) * midY;
  }

  const stepX = w / (moves.length + 1);

  // Draw center line
  ctx.strokeStyle = 'rgba(255,255,255,0.2)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, midY);
  ctx.lineTo(w, midY);
  ctx.stroke();

  // Draw area fills
  ctx.beginPath();
  ctx.moveTo(stepX, midY);
  for (let i = 0; i < moves.length; i++) {
    const x = stepX * (i + 1);
    const cp = getEval(moves[i]);
    const y = cpToY(cp);
    ctx.lineTo(x, y);
  }
  ctx.lineTo(stepX * moves.length, midY);
  ctx.closePath();

  // Fill white area above, black area below
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, 'rgba(255,255,255,0.15)');
  grad.addColorStop(0.5, 'rgba(255,255,255,0.05)');
  grad.addColorStop(0.5, 'rgba(0,0,0,0.05)');
  grad.addColorStop(1, 'rgba(0,0,0,0.15)');
  ctx.fillStyle = grad;
  ctx.fill();

  // Draw eval line
  ctx.strokeStyle = 'rgba(255,255,255,0.6)';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  for (let i = 0; i < moves.length; i++) {
    const x = stepX * (i + 1);
    const cp = getEval(moves[i]);
    const y = cpToY(cp);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();

  // Draw colored dots for mistakes/blunders
  if (classifiedMoves) {
    for (let i = 0; i < moves.length; i++) {
      const cls = classifiedMoves[i];
      if (cls && ['inaccuracy', 'mistake', 'blunder', 'missed_win'].includes(cls.category)) {
        const x = stepX * (i + 1);
        const cp = getEval(moves[i]);
        const y = cpToY(cp);
        ctx.beginPath();
        ctx.arc(x, y, 3.5, 0, Math.PI * 2);
        ctx.fillStyle = cls.color;
        ctx.fill();
      }
    }
  }

  // Draw current ply indicator
  updateChartCursor();
}

/**
 * Update the score chart cursor for current ply.
 */
function updateChartCursor() {
  const canvas = document.getElementById('score-chart');
  if (!canvas || !reviewGame) return;

  // We redraw the chart and add cursor — for simplicity, store image and overlay
  // Actually, let's just draw a vertical line on top
  const ctx = canvas.getContext('2d');
  const rect = canvas.getBoundingClientRect();
  const w = rect.width;
  const h = rect.height;

  // Redraw full chart (simple approach)
  renderScoreChartBase(ctx, w, h);

  if (currentPly > 0 && currentPly <= reviewGame.moves.length) {
    const stepX = w / (reviewGame.moves.length + 1);
    const x = stepX * currentPly;
    ctx.strokeStyle = 'rgba(233,69,96,0.8)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
    ctx.stroke();
  }
}

/**
 * Render the score chart base (without cursor). Used for cursor updates.
 * @param {CanvasRenderingContext2D} ctx
 * @param {number} w - Canvas logical width.
 * @param {number} h - Canvas logical height.
 */
function renderScoreChartBase(ctx, w, h) {
  if (!reviewGame) return;
  const moves = reviewGame.moves;
  if (moves.length === 0) return;

  const maxCp = 1000;
  const midY = h / 2;

  function getEval(move) {
    const ea = move.eval_after;
    if (!ea || ea.score_cp == null) return 0;
    if (ea.is_mate && ea.mate_in != null) return ea.mate_in > 0 ? maxCp : -maxCp;
    return Math.max(-maxCp, Math.min(maxCp, ea.score_cp));
  }

  function cpToY(cp) {
    return midY - (cp / maxCp) * midY;
  }

  const stepX = w / (moves.length + 1);

  ctx.clearRect(0, 0, w, h);

  // Center line
  ctx.strokeStyle = 'rgba(255,255,255,0.2)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, midY);
  ctx.lineTo(w, midY);
  ctx.stroke();

  // Area fill
  ctx.beginPath();
  ctx.moveTo(stepX, midY);
  for (let i = 0; i < moves.length; i++) {
    ctx.lineTo(stepX * (i + 1), cpToY(getEval(moves[i])));
  }
  ctx.lineTo(stepX * moves.length, midY);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, 'rgba(255,255,255,0.15)');
  grad.addColorStop(0.5, 'rgba(255,255,255,0.05)');
  grad.addColorStop(0.5, 'rgba(0,0,0,0.05)');
  grad.addColorStop(1, 'rgba(0,0,0,0.15)');
  ctx.fillStyle = grad;
  ctx.fill();

  // Eval line
  ctx.strokeStyle = 'rgba(255,255,255,0.6)';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  for (let i = 0; i < moves.length; i++) {
    const x = stepX * (i + 1);
    const y = cpToY(getEval(moves[i]));
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();

  // Colored dots
  if (classifiedMoves) {
    for (let i = 0; i < moves.length; i++) {
      const cls = classifiedMoves[i];
      if (cls && ['inaccuracy', 'mistake', 'blunder', 'missed_win'].includes(cls.category)) {
        const x = stepX * (i + 1);
        const y = cpToY(getEval(moves[i]));
        ctx.beginPath();
        ctx.arc(x, y, 3.5, 0, Math.PI * 2);
        ctx.fillStyle = cls.color;
        ctx.fill();
      }
    }
  }
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
      stockfishVersion = statusData.stockfish_version || '';
      console.log(`[init] App mode detected: v${appVersion}, SF: ${stockfishVersion}`);

      // Hide demo banner
      const banner = document.getElementById('demo-banner');
      if (banner) banner.classList.add('hidden');

      // Show app-only menu items (greyed out for now)
      document.querySelectorAll('.nav-app-only').forEach((el) => {
        el.classList.remove('hidden');
        el.classList.add('disabled');
      });

      // Enable ready endpoints
      const refreshItem = document.getElementById('nav-refresh');
      if (refreshItem) refreshItem.classList.remove('disabled');
      const configItem = document.getElementById('nav-config');
      if (configItem) configItem.classList.remove('disabled');
      const comingSoonItem = document.getElementById('nav-coming-soon');
      if (comingSoonItem) comingSoonItem.classList.remove('disabled');

      // Set version in menu
      const versionText = stockfishVersion
        ? 'v' + appVersion + ' · SF ' + stockfishVersion
        : 'v' + appVersion;
      document.getElementById('nav-version').textContent = versionText;
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
    const hint = appMode === 'app'
      ? 'No training data yet. Use menu ☰ → Analyse latest games to generate it.'
      : 'Could not load training data.';
    document.getElementById('prompt').textContent = hint;
    console.error('[init] Training data load failed:', err);
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

  document.getElementById('nav-settings').addEventListener('click', () => {
    closeMenu();
    const modal = document.getElementById('settings-modal');
    const settings = loadSettings();
    document.getElementById('session-size').value = settings.sessionSize;
    document.getElementById('difficulty').value = settings.difficulty;
    const defaultDepth = appMode === 'app' ? 18 : 12;
    document.getElementById('analysis-depth').value = settings.analysisDepth || defaultDepth;
    modal.classList.remove('hidden');
  });

  document.getElementById('close-settings').addEventListener('click', () => {
    const defaultDepth = appMode === 'app' ? 18 : 12;
    const settings = {
      sessionSize: parseInt(document.getElementById('session-size').value) || 10,
      difficulty: document.getElementById('difficulty').value,
      analysisDepth: parseInt(document.getElementById('analysis-depth').value) || defaultDepth,
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

  /**
   * Wire a nav menu item: click → disabled check → closeMenu → show function.
   * Optionally wire the modal's close button.
   * @param {string} navId - ID of the nav <li> element.
   * @param {Function} showFn - Function to call when clicked.
   * @param {string} [modalId] - Modal ID; derives close button as "close-{name}".
   */
  function wireNavItem(navId, showFn, modalId) {
    const item = document.getElementById(navId);
    if (!item) { console.error(`[init] ${navId} not found`); return; }
    item.addEventListener('click', () => {
      if (item.classList.contains('disabled')) return;
      console.log(`[init] ${navId} clicked`);
      closeMenu();
      showFn();
    });
    if (modalId) {
      const closeId = 'close-' + modalId.replace('-modal', '');
      document.getElementById(closeId).addEventListener('click', () => {
        document.getElementById(modalId).classList.add('hidden');
      });
    }
  }

  wireNavItem('nav-stats', showRawDataSummary, 'stats-modal');
  wireNavItem('nav-refresh', showAnalysisSettings, 'analysis-modal');

  // Wire analysis modal buttons
  const startAnalysisBtn = document.getElementById('start-analysis');
  if (startAnalysisBtn) {
    startAnalysisBtn.addEventListener('click', () => startAnalysis(false));
  }
  const reanalyzeAllBtn = document.getElementById('reanalyze-all');
  if (reanalyzeAllBtn) {
    reanalyzeAllBtn.addEventListener('click', () => startAnalysis(true));
  }
  const closeAnalysisBtn = document.getElementById('close-analysis');
  if (closeAnalysisBtn) {
    closeAnalysisBtn.addEventListener('click', () => {
      document.getElementById('analysis-modal').classList.add('hidden');
    });
  }
  wireNavItem('nav-config', showConfig, 'config-modal');

  // Wire "Coming soon" submenu toggle
  const comingSoonToggle = document.getElementById('nav-coming-soon');
  const comingSoonItems = document.getElementById('nav-coming-soon-items');
  if (comingSoonToggle && comingSoonItems) {
    comingSoonToggle.addEventListener('click', () => {
      const expanded = !comingSoonItems.classList.contains('hidden');
      comingSoonItems.classList.toggle('hidden');
      comingSoonToggle.classList.toggle('expanded', !expanded);
      console.log('[nav] Coming soon', expanded ? 'collapsed' : 'expanded');
    });
    comingSoonItems.addEventListener('click', (e) => e.stopPropagation());
  }

  document.getElementById('save-config').addEventListener('click', () => {
    saveConfig();
  });

  // Wire up nav-about (both modes)
  document.getElementById('nav-about').addEventListener('click', () => {
    console.log('[init] nav-about clicked');
    closeMenu();
    const content = document.getElementById('about-content');
    content.textContent = '';

    const addLine = (text) => {
      const p = document.createElement('p');
      p.textContent = text;
      content.appendChild(p);
    };

    const addLink = (text, href) => {
      const p = document.createElement('p');
      const a = document.createElement('a');
      a.href = href;
      a.target = '_blank';
      a.rel = 'noopener';
      a.textContent = text;
      p.appendChild(a);
      content.appendChild(p);
    };

    addLine('Learn from your own mistakes.');
    if (appVersion) addLine('Version: ' + appVersion);
    if (stockfishVersion) addLine('Stockfish: ' + stockfishVersion);
    if (!appVersion) addLine('Mode: demo');
    addLink('GitHub', 'https://github.com/Bobain/chess-self-coach');

    document.getElementById('about-modal').classList.remove('hidden');
  });

  document.getElementById('close-about').addEventListener('click', () => {
    document.getElementById('about-modal').classList.add('hidden');
  });

  // Set version in menu header (populated earlier by mode detection)
  if (appVersion) {
    const versionText = stockfishVersion
      ? 'v' + appVersion + ' · SF ' + stockfishVersion
      : 'v' + appVersion;
    document.getElementById('nav-version').textContent = versionText;
  }

  // Wire mode toggle
  document.getElementById('mode-training').addEventListener('click', showTrainingMode);
  document.getElementById('mode-analysis').addEventListener('click', showAnalysisMode);

  // Wire review controls
  document.getElementById('review-first').addEventListener('click', () => goToMove(0));
  document.getElementById('review-prev').addEventListener('click', () => goToMove(currentPly - 1));
  document.getElementById('review-next').addEventListener('click', () => goToMove(currentPly + 1));
  document.getElementById('review-last').addEventListener('click', () => {
    if (reviewGame) goToMove(reviewGame.moves.length);
  });
  document.getElementById('review-play').addEventListener('click', () => {
    if (autoPlayTimer) {
      clearInterval(autoPlayTimer);
      autoPlayTimer = null;
      document.getElementById('review-play').textContent = '\u25b6';
    } else {
      document.getElementById('review-play').textContent = '\u23f8';
      autoPlayTimer = setInterval(() => {
        if (!reviewGame || currentPly >= reviewGame.moves.length) {
          clearInterval(autoPlayTimer);
          autoPlayTimer = null;
          document.getElementById('review-play').textContent = '\u25b6';
          return;
        }
        goToMove(currentPly + 1);
      }, 1000);
    }
  });
  document.getElementById('review-flip').addEventListener('click', () => {
    reviewOrientation = reviewOrientation === 'white' ? 'black' : 'white';
    if (reviewCg) reviewCg.set({ orientation: reviewOrientation });
  });
  document.getElementById('review-back-btn').addEventListener('click', () => {
    if (autoPlayTimer) { clearInterval(autoPlayTimer); autoPlayTimer = null; }
    showGameSelector();
  });

  // Score chart click handler
  document.getElementById('score-chart').addEventListener('click', (e) => {
    if (!reviewGame) return;
    const canvas = e.target;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const stepX = rect.width / (reviewGame.moves.length + 1);
    const ply = Math.round(x / stepX);
    goToMove(Math.max(0, Math.min(ply, reviewGame.moves.length)));
  });

  // Keyboard navigation for analysis mode
  document.addEventListener('keydown', (e) => {
    if (appView !== 'analysis' || !reviewGame) return;
    // Don't capture if user is typing in an input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.key === 'ArrowLeft') { e.preventDefault(); goToMove(currentPly - 1); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); goToMove(currentPly + 1); }
    else if (e.key === 'Home') { e.preventDefault(); goToMove(0); }
    else if (e.key === 'End') { e.preventDefault(); goToMove(reviewGame.moves.length); }
  });

  // Resize handler for score chart
  window.addEventListener('resize', () => {
    if (appView === 'analysis' && reviewGame) renderScoreChart();
  });

  // Register service worker
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch((err) =>
      console.warn('SW registration failed:', err)
    );
  }

  // Start first session (skip if no training data loaded)
  if (trainingData) startSession();
}

init();
