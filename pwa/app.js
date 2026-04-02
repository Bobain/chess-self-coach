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
    sfWorker.postMessage('go depth ' + depth + ' movetime 1000');
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
/** @type {?number} Interval ID for the play-best-line animation */
let playLineInterval = null;

// --- Analysis mode state ---
/** @type {string} Current view: 'games' (game list), 'review', or 'training' */
let appView = 'games';
/** @type {Set<string>} Selected game IDs for batch analysis */
let selectedGameIds = new Set();
/** @type {Set<string>} Game IDs in the current analysis job */
let analyzingGameIds = new Set();
/** @type {Set<string>} Game IDs queued for the next analysis batch */
let pendingGameIds = new Set();
/** @type {number} Games completed in previous batches (for unified counter) */
let analysisOffset = 0;
/** @type {number} Total games across all batches */
let analysisTotalAll = 0;
/** @type {number} How many games to show per page */
let gameListLimit = 20;
/** @type {number} Current page (0-based) */
let gameListPage = 0;
/** @type {string} Active result filter: 'all', 'win', 'loss', 'draw' */
let resultFilter = 'all';
/** @type {string} Active color filter: 'all', 'white', 'black' */
let colorFilter = 'all';
/** @type {string} Active opening filter: 'all' or opening name */
let openingFilter = 'all';
/** @type {string} Active status filter: 'all', 'analyzed', 'not-analyzed' */
let statusFilter = 'all';
/** @type {?string} When training on a specific game, its ID; null = all positions */
let trainingGameFilter = null;
/** @type {?Object} Parsed analysis_data.json */
let analysisData = null;
/** @type {?Object} Parsed classifications_data.json — pre-computed move categories */
let classificationsData = null;
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

// --- Analysis presets (Quick / Balanced / Deep) ---

const ANALYSIS_PRESETS = {
  quick: {
    kings_pawns_le7: { depth: 40, time: 2 },
    pieces_le7: { depth: 30, time: 2 },
    pieces_le12: { depth: 25, time: 1.5 },
    default: { depth: 14 },
  },
  balanced: {
    kings_pawns_le7: { depth: 60, time: 5 },
    pieces_le7: { depth: 50, time: 5 },
    pieces_le12: { depth: 40, time: 5 },
    default: { depth: 18 },
  },
  deep: {
    kings_pawns_le7: { depth: 80, time: 15 },
    pieces_le7: { depth: 70, time: 12 },
    pieces_le12: { depth: 55, time: 10 },
    default: { depth: 24 },
  },
};

/**
 * Populate the limit form fields from a limits object.
 * @param {Object} limits - Limits keyed by bracket name.
 */
function populateLimitFields(limits) {
  const lim = limits || {};
  if (lim.kings_pawns_le7) {
    document.getElementById('limit-kp-depth').value = lim.kings_pawns_le7.depth || 60;
    document.getElementById('limit-kp-time').value = lim.kings_pawns_le7.time || 5;
  }
  if (lim.pieces_le7) {
    document.getElementById('limit-eg-depth').value = lim.pieces_le7.depth || 50;
    document.getElementById('limit-eg-time').value = lim.pieces_le7.time || 5;
  }
  if (lim.pieces_le12) {
    document.getElementById('limit-mg-depth').value = lim.pieces_le12.depth || 40;
    document.getElementById('limit-mg-time').value = lim.pieces_le12.time || 5;
  }
  if (lim.default) {
    document.getElementById('limit-default-depth').value = lim.default.depth || 18;
  }
}

/**
 * Read limit values from the form fields.
 * @returns {Object} Limits object keyed by bracket name.
 */
function readLimitFields() {
  return {
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
  };
}

/**
 * Detect which preset matches the current limit field values and update buttons.
 */
function detectPreset() {
  const current = readLimitFields();
  let matched = null;
  for (const [name, preset] of Object.entries(ANALYSIS_PRESETS)) {
    if (
      current.kings_pawns_le7.depth === preset.kings_pawns_le7.depth &&
      current.kings_pawns_le7.time === preset.kings_pawns_le7.time &&
      current.pieces_le7.depth === preset.pieces_le7.depth &&
      current.pieces_le7.time === preset.pieces_le7.time &&
      current.pieces_le12.depth === preset.pieces_le12.depth &&
      current.pieces_le12.time === preset.pieces_le12.time &&
      current.default.depth === preset.default.depth
    ) {
      matched = name;
      break;
    }
  }
  document.querySelectorAll('.preset-btn').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.preset === matched);
  });
}

/**
 * Wire preset buttons: click applies preset values, field changes detect preset.
 */
function wirePresets() {
  document.querySelectorAll('.preset-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const preset = ANALYSIS_PRESETS[btn.dataset.preset];
      if (!preset) return;
      console.log('[wirePresets] Applying preset:', btn.dataset.preset);
      populateLimitFields(preset);
      document.querySelectorAll('.preset-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
    });
  });

  // When any advanced field changes, re-detect preset
  document.querySelectorAll('#analysis-threads, #analysis-hash, [id^="limit-"]').forEach((input) => {
    input.addEventListener('input', () => detectPreset());
  });
}

/**
 * Open the unified settings modal, populating all fields.
 * @async
 */
async function openSettings() {
  console.log('[openSettings] Opening unified settings modal');
  const modal = document.getElementById('settings-modal');
  const statusEl = document.getElementById('settings-status');
  if (statusEl) statusEl.textContent = '';

  // 1. Populate training fields from localStorage
  const settings = loadSettings();
  document.getElementById('session-size').value = settings.sessionSize;
  document.getElementById('difficulty').value = settings.difficulty;
  const defaultDepth = appMode === 'app' ? 18 : 12;
  document.getElementById('analysis-depth').value = settings.analysisDepth || defaultDepth;

  // 2. Show/hide app-only sections
  document.querySelectorAll('.settings-app-only').forEach((el) => {
    el.classList.toggle('hidden', appMode !== 'app');
  });

  // 3. Populate max_games from localStorage
  const savedMaxGames = localStorage.getItem('analysis_max_games');
  if (savedMaxGames) {
    document.getElementById('analysis-max-games').value = savedMaxGames;
  }

  // 4. In app mode, fetch config + analysis settings from backend
  if (appMode === 'app') {
    try {
      const [configResp, analysisResp] = await Promise.all([
        fetch('/api/config'),
        fetch('/api/analysis/settings'),
      ]);
      if (configResp.ok) {
        const config = await configResp.json();
        document.getElementById('config-lichess').value = config.players.lichess || '';
        document.getElementById('config-chesscom').value = config.players.chesscom || '';
        document.getElementById('config-depth').value = config.analysis.default_depth || 18;
        document.getElementById('config-threshold').value = config.analysis.blunder_threshold || 1.0;
      }
      if (analysisResp.ok) {
        const data = await analysisResp.json();
        document.getElementById('analysis-threads').value = data.threads;
        document.getElementById('analysis-hash').value = data.hash_mb;
        populateLimitFields(data.limits);
        detectPreset();
      }
    } catch (err) {
      console.error('[openSettings] Failed to load backend settings:', err);
      if (statusEl) statusEl.textContent = 'Could not load server settings.';
    }
  }

  modal.classList.remove('hidden');
}

/**
 * Save all settings from the unified modal.
 * @async
 */
async function saveAllSettings() {
  console.log('[saveAllSettings] Saving...');
  const statusEl = document.getElementById('settings-status');
  if (statusEl) statusEl.textContent = 'Saving...';

  // 1. Save training settings to localStorage (always)
  const defaultDepth = appMode === 'app' ? 18 : 12;
  const trainSettings = {
    sessionSize: parseInt(document.getElementById('session-size').value) || 10,
    difficulty: document.getElementById('difficulty').value,
    analysisDepth: parseInt(document.getElementById('analysis-depth').value) || defaultDepth,
  };
  saveSettings(trainSettings);

  // 2. Save max_games to localStorage
  localStorage.setItem('analysis_max_games', document.getElementById('analysis-max-games').value);

  // 3. In app mode, save config + analysis settings to backend
  if (appMode === 'app') {
    try {
      const configBody = {
        players: {
          lichess: document.getElementById('config-lichess').value.trim(),
          chesscom: document.getElementById('config-chesscom').value.trim(),
        },
        analysis: {
          default_depth: parseInt(document.getElementById('config-depth').value) || 18,
          blunder_threshold: parseFloat(document.getElementById('config-threshold').value) || 1.0,
        },
      };
      const analysisBody = {
        threads: parseInt(document.getElementById('analysis-threads').value, 10),
        hash_mb: parseInt(document.getElementById('analysis-hash').value, 10),
        limits: readLimitFields(),
      };

      const [configResp, analysisResp] = await Promise.all([
        fetch('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(configBody) }),
        fetch('/api/analysis/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(analysisBody) }),
      ]);

      if (!configResp.ok || !analysisResp.ok) {
        console.error('[saveAllSettings] Backend save failed:', configResp.status, analysisResp.status);
        if (statusEl) statusEl.textContent = 'Failed to save server settings.';
        return;
      }
    } catch (err) {
      console.error('[saveAllSettings] Backend save failed:', err);
      if (statusEl) statusEl.textContent = 'Connection failed.';
      return;
    }
  }

  console.log('[saveAllSettings] All settings saved');
  if (statusEl) statusEl.textContent = 'Saved!';
  setTimeout(() => {
    document.getElementById('settings-modal').classList.add('hidden');
  }, 600);
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
        animationTimer = setTimeout(() => {
          cg.move(from, to);
          animationTimer = setTimeout(() => showRetryButton(position), 1000);
        }, 800);
      } else {
        animationTimer = setTimeout(() => setupBoard(position), 400);
      }
    } catch (err) {
      hideThinking();
      console.log('[handleMove] Stockfish unavailable, fallback:', err.message);
      animationTimer = setTimeout(() => setupBoard(position), 400);
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
  document.getElementById('retry-btn').classList.add('hidden');
  document.getElementById('skip-btn').classList.add('hidden');
  document.getElementById('show-answer-btn').classList.add('hidden');

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
    playLineInterval = setInterval(() => {
      if (step >= pvMoves.length) {
        clearInterval(playLineInterval);
        playLineInterval = null;
        playLineBtn.disabled = false;
        return;
      }
      const move = chess.move(pvMoves[step]);
      if (!move) {
        clearInterval(playLineInterval);
        playLineInterval = null;
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
  document.getElementById('skip-btn').classList.remove('hidden');
  document.getElementById('explanation').textContent = '';

  // Show "See moves" after 2 wrong attempts (helps understand the position)
  if (attempts >= 2) {
    const position = session[currentIndex];
    _showSeeMovesLink(position);
  }

  // Show "Show answer" after 3 wrong attempts
  if (attempts >= 3) {
    document.getElementById('show-answer-btn').classList.remove('hidden');
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

/**
 * Skip a position — reinsert it later in the session for another try.
 * Does not affect SRS state.
 */
function skipPosition() {
  console.log(`[skipPosition] id=${session[currentIndex].id}`);
  const position = session[currentIndex];
  // Reinsert 3 positions later (or at the end)
  const insertAt = Math.min(currentIndex + 4, session.length);
  session.splice(insertAt, 0, position);
  showPosition(currentIndex + 1);
}

/**
 * Show the answer after 3+ failed attempts.
 * Displays the same feedback as a correct answer but records a failure in SRS.
 */
function showAnswer() {
  console.log(`[showAnswer] id=${session[currentIndex].id}`);
  const position = session[currentIndex];
  recordResult(false);
  showFeedback(false, position, true);
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
  if (playLineInterval) {
    clearInterval(playLineInterval);
    playLineInterval = null;
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
  document.getElementById('show-answer-btn').classList.add('hidden');
  document.getElementById('skip-btn').classList.add('hidden');
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
  console.log('[startSession] Starting new session, gameFilter:', trainingGameFilter);
  const settings = loadSettings();
  let positions = trainingData.positions;
  if (trainingGameFilter) {
    positions = positions.filter((p) => p.game && p.game.id === trainingGameFilter);
    console.log(`[startSession] Filtered to ${positions.length} position(s) for game ${trainingGameFilter}`);
  }
  session = selectPositions(positions, settings.sessionSize);
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

// --- Analysis settings modal ---


/**
 * Display analysis job progress in the refresh modal.
 * @param {string} jobId - The job ID to track.
 */
function showAnalysisProgress(jobId) {
  console.log('[showAnalysisProgress] Starting job:', jobId);
  const currentBatchSize = analyzingGameIds.size;

  const el = document.getElementById('analysis-progress');
  if (!el) return;
  el.textContent = `Analyzing ${analysisOffset}/${analysisTotalAll}`;
  el.classList.remove('hidden');

  // Click to cancel
  el.onclick = async () => {
    try {
      await fetch(`/api/jobs/${jobId}/cancel`, { method: 'POST' });
      console.log('[showAnalysisProgress] Cancel requested');
    } catch (err) {
      console.error('[showAnalysisProgress] Cancel failed:', err);
    }
  };

  const evtSource = new EventSource(`/api/jobs/${jobId}/events`);
  evtSource.onmessage = (e) => {
    const event = JSON.parse(e.data);
    console.log('[showAnalysisProgress] Event:', event.phase, event.percent);

    if (event.phase === 'fetch') {
      el.textContent = `Analyzing ${analysisOffset}/${analysisTotalAll}`;
    } else if (event.current != null && event.total != null) {
      el.textContent = `Analyzing ${analysisOffset + event.current}/${analysisTotalAll}`;
    } else if (event.phase === 'derive') {
      // Per-game derivation done — reload data so badges + review + train are available
      loadAnalysisData();
      loadTrainingData();
    } else if (event.phase === 'analyze') {
      if (event.waiting && event.message) {
        el.textContent = event.message;
      } else if (event.error && event.message) {
        el.textContent = `⚠ ${event.message}`;
      } else {
        el.textContent = `Analyzing ${analysisOffset}/${analysisTotalAll}`;
      }
    }

    if (event.phase === 'done' || event.phase === 'error' || event.phase === 'interrupted') {
      evtSource.close();
      analysisOffset += currentBatchSize;

      if (event.phase === 'done' && pendingGameIds.size > 0) {
        // Continue with pending queue
        analyzingGameIds = new Set(pendingGameIds);
        pendingGameIds.clear();
        showGameSelector();
        startAnalysisJob(Array.from(analyzingGameIds));
      } else {
        // All done — reset state and refresh
        analyzingGameIds.clear();
        pendingGameIds.clear();
        analysisOffset = 0;
        analysisTotalAll = 0;
        if (event.phase === 'error' || event.phase === 'interrupted') {
          console.error('[showAnalysisProgress] Job failed:', event.phase, event.message);
          el.textContent = event.message || 'Analysis failed';
          el.style.color = 'red';
          setTimeout(() => { el.classList.add('hidden'); el.style.color = ''; }, 8000);
          showGameSelector();
        } else {
          setTimeout(() => el.classList.add('hidden'), 2000);
          loadAnalysisData();  // reloads analysisData then calls showGameSelector
          loadTrainingData();
        }
      }
    }
  };
  evtSource.onerror = () => {
    evtSource.close();
    analyzingGameIds.clear();
    pendingGameIds.clear();
    analysisOffset = 0;
    analysisTotalAll = 0;
    el.classList.add('hidden');
  };
}


// --- View switching ---

/**
 * Show the game list view (default main view).
 */
function showGameList() {
  console.log('[showGameList] Switching to game list');
  appView = 'games';
  document.getElementById('training-view').classList.add('hidden');
  document.getElementById('analysis-view').classList.remove('hidden');
  document.getElementById('progress').textContent = '';
  if (autoPlayTimer) { clearInterval(autoPlayTimer); autoPlayTimer = null; }
  if (!analysisData) {
    loadAnalysisData();
  } else {
    showGameSelector();
  }
}

/**
 * Show the training view, optionally scoped to one game.
 * @param {?string} gameId - If set, train only on positions from this game.
 */
function showTrainingView(gameId = null) {
  console.log('[showTrainingView] gameId:', gameId);
  trainingGameFilter = gameId;
  appView = 'training';
  document.getElementById('training-view').classList.remove('hidden');
  document.getElementById('analysis-view').classList.add('hidden');
  if (autoPlayTimer) { clearInterval(autoPlayTimer); autoPlayTimer = null; }
  if (trainingData) startSession();
}

/**
 * Load analysis_data.json from server or static file.
 */
/**
 * Load training_data.json from server or static file.
 */
async function loadTrainingData() {
  console.log('[loadTrainingData] Fetching training data...');
  try {
    const resp = await fetch('training_data.json?t=' + Date.now());
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    trainingData = await resp.json();
    console.log(`[loadTrainingData] Loaded ${trainingData.positions.length} position(s)`);
  } catch (err) {
    const hint = appMode === 'app'
      ? 'No training data yet. Use menu ☰ → Analyse latest games to generate it.'
      : 'Could not load training data.';
    document.getElementById('prompt').textContent = hint;
    console.error('[loadTrainingData] Failed:', err);
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
    const resp = await fetch('analysis_data.json?t=' + Date.now());
    if (!resp.ok) {
      console.log('[loadAnalysisData] Not found:', resp.status);
      analysisData = { games: {} };
    } else {
      analysisData = await resp.json();
    }
    console.log(`[loadAnalysisData] Loaded ${Object.keys(analysisData.games || {}).length} game(s)`);
    await loadClassificationsData();
    await showGameSelector();
  } catch (err) {
    console.error('[loadAnalysisData] Failed:', err);
    analysisData = { games: {} };
    await showGameSelector();
  }
}

/**
 * Load classifications_data.json (pre-computed move categories).
 * Called after loadAnalysisData — classifications are keyed by game URL.
 */
async function loadClassificationsData() {
  console.log('[loadClassificationsData] Fetching...');
  try {
    const resp = await fetch('classifications_data.json?t=' + Date.now());
    if (!resp.ok) {
      console.log('[loadClassificationsData] Not found:', resp.status);
      classificationsData = null;
    } else {
      classificationsData = await resp.json();
      console.log(`[loadClassificationsData] Loaded for ${Object.keys(classificationsData.games || {}).length} game(s)`);
    }
  } catch (err) {
    console.error('[loadClassificationsData] Failed:', err);
    classificationsData = null;
  }
}

/**
 * Get pre-computed classifications for a game, or classify at runtime (fallback).
 * @param {string} gameId - Game URL (key in classificationsData).
 * @param {Array} moves - Move array from analysis_data.
 * @param {string} playerColor - 'white' or 'black'.
 * @returns {Array} Array of classification objects.
 */
function getClassifications(gameId, moves, playerColor) {
  // Prefer pre-computed classifications
  if (classificationsData && classificationsData.games && classificationsData.games[gameId]) {
    return classificationsData.games[gameId].map(cls => {
      if (!cls) return null;
      return { category: cls.c, symbol: cls.s, color: cls.co };
    });
  }
  // No pre-computed classifications — return null array (no classification display)
  console.warn('[getClassifications] No pre-computed data for', gameId);
  return moves.map(() => null);
}

/** Win probability from centipawn score (logistic model, used for accuracy). */
function winProb(cp) {
  return 1 / (1 + Math.pow(10, -cp / 400));
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
 * Update the "Analyze selected (N)" button text and disabled state.
 */
function updateAnalyzeButton() {
  const btn = document.getElementById('analyze-selected-btn');
  if (!btn) return;
  const n = selectedGameIds.size;
  btn.textContent = n > 0 ? `Analyze selected (${n})` : 'Analyze selected';
  btn.disabled = n === 0;
}

/**
 * Build pagination controls element.
 * @param {number} totalPages - Total number of pages.
 * @param {number} totalGames - Total number of filtered games.
 * @returns {HTMLDivElement}
 */
function _buildPagination(totalPages, totalGames) {
  const el = document.createElement('div');
  el.className = 'game-list-pagination';
  const prevBtn = document.createElement('button');
  prevBtn.textContent = '\u2190 Previous';
  prevBtn.disabled = gameListPage === 0;
  prevBtn.addEventListener('click', () => { gameListPage--; showGameSelector(); });
  const info = document.createElement('span');
  info.textContent = `Page ${gameListPage + 1} / ${totalPages} (${totalGames} games)`;
  const nextBtn = document.createElement('button');
  nextBtn.textContent = 'Next \u2192';
  nextBtn.disabled = gameListPage >= totalPages - 1;
  nextBtn.addEventListener('click', () => { gameListPage++; showGameSelector(); });
  el.appendChild(prevBtn);
  el.appendChild(info);
  el.appendChild(nextBtn);
  return el;
}

/**
 * Render the game selector list with checkboxes and analysis status.
 */
async function showGameSelector() {
  console.log('[showGameSelector] Rendering game list');
  const selector = document.getElementById('game-selector');
  const review = document.getElementById('game-review');
  const toolbar = document.getElementById('game-list-toolbar');
  selector.textContent = '';
  selector.classList.remove('hidden');
  review.classList.add('hidden');
  selectedGameIds.clear();

  // In app mode, use the unified API list (sorted by date, analyzed + cached)
  // In demo mode, use analysisData only
  let unifiedList = []; // [{gameId, analyzed, apiData, richData}]

  if (appMode === 'app') {
    try {
      const resp = await fetch('/api/games?limit=9999');
      if (resp.ok) {
        const data = await resp.json();
        for (const g of data.games) {
          const richData = analysisData?.games?.[g.game_id];
          unifiedList.push({ gameId: g.game_id, analyzed: !!richData || g.analyzed, apiData: g, richData });
        }
        console.log(`[showGameSelector] Unified list: ${unifiedList.length} games (${unifiedList.filter(g => !g.analyzed).length} unanalyzed)`);
      }
    } catch (err) {
      console.log('[showGameSelector] Could not fetch unified game list:', err);
    }
  }

  // Fallback (demo mode or API failure): use analysisData
  if (unifiedList.length === 0 && analysisData?.games) {
    const entries = Object.entries(analysisData.games);
    entries.sort((a, b) => (b[1].headers.date || '').localeCompare(a[1].headers.date || ''));
    for (const [gameId, game] of entries) {
      unifiedList.push({ gameId, analyzed: true, apiData: null, richData: game });
    }
  }

  // Helper: extract opening name from game moves (last known opening = most specific)
  function getEntryOpening(entry) {
    const game = entry.richData;
    if (!game || !game.moves) return '';
    let name = '';
    for (const m of game.moves) {
      if (m.opening_explorer && m.opening_explorer.moves) {
        for (const om of m.opening_explorer.moves) {
          if (om && om.opening && om.opening.name && om.uci === m.move_uci) {
            name = om.opening.name;
          }
        }
      }
    }
    // Fallback to PGN header opening name
    if (!name && game.headers) {
      name = game.headers.opening || game.headers.Opening || '';
    }
    // Truncate to opening family (before first colon)
    const colonIdx = name.indexOf(':');
    if (colonIdx > 0) name = name.slice(0, colonIdx).trim();
    return name;
  }

  // Cache opening names for all entries (used for filter + dropdown)
  const entryOpenings = new Map();
  const openingCounts = new Map();
  for (const entry of unifiedList) {
    const opening = getEntryOpening(entry);
    entryOpenings.set(entry.gameId, opening);
    if (opening) openingCounts.set(opening, (openingCounts.get(opening) || 0) + 1);
  }

  // Populate opening dropdown from ALL games (not just current page)
  const openingSelect = document.getElementById('opening-filter-select');
  if (openingSelect) {
    const currentVal = openingFilter;
    while (openingSelect.options.length > 1) openingSelect.remove(1);
    const sorted = [...openingCounts.entries()].sort((a, b) => b[1] - a[1]);
    for (const [name, count] of sorted) {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = `${name} (${count})`;
      openingSelect.appendChild(opt);
    }
    openingSelect.value = currentVal;
    if (openingSelect.value !== currentVal) openingFilter = 'all';
  }

  // Filter by result, color, opening, and analysis status
  const filteredList = unifiedList.filter((entry) => {
    const result = entry.richData ? entry.richData.headers.result : entry.apiData?.result;
    const pc = entry.richData ? entry.richData.player_color : entry.apiData?.player_color;
    // Result filter
    if (resultFilter !== 'all') {
      const isWin = (result === '1-0' && pc === 'white') || (result === '0-1' && pc === 'black');
      const isLoss = (result === '1-0' && pc === 'black') || (result === '0-1' && pc === 'white');
      if (resultFilter === 'win' && !isWin) return false;
      if (resultFilter === 'loss' && !isLoss) return false;
      if (resultFilter === 'draw' && (isWin || isLoss)) return false;
    }
    // Color filter
    if (colorFilter !== 'all' && pc !== colorFilter) return false;
    // Opening filter
    if (openingFilter !== 'all') {
      if (entryOpenings.get(entry.gameId) !== openingFilter) return false;
    }
    // Status filter
    if (statusFilter === 'analyzed' && !entry.analyzed) return false;
    if (statusFilter === 'not-analyzed' && entry.analyzed) return false;
    return true;
  });

  const totalPages = Math.max(1, Math.ceil(filteredList.length / gameListLimit));
  if (gameListPage >= totalPages) gameListPage = totalPages - 1;
  if (gameListPage < 0) gameListPage = 0;
  const start = gameListPage * gameListLimit;
  const limitedEntries = filteredList.slice(start, start + gameListLimit);

  if (filteredList.length === 0) {
    selector.textContent = appMode === 'app'
      ? 'No games yet. Use menu \u2630 \u2192 Fetch games to fetch your games.'
      : 'No analyzed games available.';
    if (toolbar) toolbar.classList.add('hidden');
    return;
  }

  // Show toolbar (select-all + analyze only in app mode)
  if (toolbar) {
    toolbar.classList.remove('hidden');
    const selectAllLabel = document.getElementById('select-all-label');
    const analyzeBtn = document.getElementById('analyze-selected-btn');
    if (appMode === 'app') {
      if (selectAllLabel) selectAllLabel.classList.remove('hidden');
      if (analyzeBtn) analyzeBtn.classList.remove('hidden');
    } else {
      if (selectAllLabel) selectAllLabel.classList.add('hidden');
      if (analyzeBtn) analyzeBtn.classList.add('hidden');
    }
  }

  // Top pagination
  if (totalPages > 1) {
    selector.appendChild(_buildPagination(totalPages, filteredList.length));
  }

  for (const entry of limitedEntries) {
    const gameId = entry.gameId;
    const game = entry.richData;  // null for unanalyzed
    const api = entry.apiData;    // null for demo mode

    const card = document.createElement('div');
    card.className = entry.analyzed ? 'game-card' : 'game-card game-card-unanalyzed';
    card.dataset.gameId = gameId;

    // Checkbox (app mode only, not for queued games — includes analyzed for re-analysis)
    const isQueued = analyzingGameIds.has(gameId) || pendingGameIds.has(gameId);
    if (appMode === 'app' && !isQueued) {
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.className = 'game-card-checkbox';
      cb.addEventListener('click', (e) => {
        e.stopPropagation();
        if (cb.checked) selectedGameIds.add(gameId);
        else selectedGameIds.delete(gameId);
        updateAnalyzeButton();
        const selectAll = document.getElementById('select-all-checkbox');
        const selectableCount = limitedEntries.filter(e => !analyzingGameIds.has(e.gameId) && !pendingGameIds.has(e.gameId)).length;
        if (selectAll) selectAll.checked = selectedGameIds.size > 0 && selectedGameIds.size === selectableCount;
      });
      card.appendChild(cb);
    }

    if (entry.analyzed) {
      card.addEventListener('click', () => selectGame(gameId));
    }

    // Result badge
    const resultEl = document.createElement('div');
    resultEl.className = 'game-card-result';
    const result = game ? game.headers.result : api.result;
    const playerColor = game ? game.player_color : api.player_color;
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
    let opponentName, dateStr, moveCountText;
    if (game) {
      opponentName = playerColor === 'white' ? game.headers.black : game.headers.white;
      dateStr = (game.headers.date || '').replace(/\./g, '-');
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
      moveCountText = `${game.moves.length} moves${openingName ? ' \u00b7 ' + openingName : ''}`;
    } else {
      opponentName = playerColor === 'white' ? api.black : api.white;
      dateStr = api.date || '';
      moveCountText = `${api.move_count} moves \u00b7 ${api.opening || api.source}`;
    }
    opponent.textContent = `vs ${opponentName}`;
    infoEl.appendChild(opponent);

    const meta = document.createElement('div');
    meta.className = 'game-card-meta';
    meta.textContent = moveCountText;
    infoEl.appendChild(meta);
    card.appendChild(infoEl);

    // Accuracy + classification badges (analyzed), "Queued", or "Not analyzed" badge
    if (!game) {
      const badge = document.createElement('div');
      if (isQueued) {
        badge.className = 'game-card-accuracy queued-badge';
        badge.textContent = 'Queued';
      } else if (entry.analyzed) {
        badge.className = 'game-card-accuracy unanalyzed-badge';
        badge.textContent = 'Analyzed';
      } else {
        badge.className = 'game-card-accuracy unanalyzed-badge';
        badge.textContent = 'Not analyzed';
      }
      card.appendChild(badge);
      selector.appendChild(card);
      continue;
    }

    const opponentColor = game.player_color === 'white' ? 'black' : 'white';
    const classified = getClassifications(gameId, game.moves, game.player_color);
    const playerAcc = computeAccuracy(game.moves, classified, game.player_color);
    const opponentAcc = computeAccuracy(game.moves, classified, opponentColor);
    // Badge categories in display order (positive → negative).
    // Priority badges are always shown first; fill badges take remaining slots.
    // Display order is always maintained regardless of priority vs fill.
    const allCategories = [
      { key: 'brilliant',   label: '!!',       color: '#1baca6', title: 'brilliant moves',       priority: true },
      { key: 'great',       label: '!',        color: '#5c9ced', title: 'great moves',           priority: true },
      { key: 'best',        label: '\u2605',   color: '#96bc4b', title: 'best moves',            priority: true },
      { key: 'excellent',   label: '\u2191',   color: '#96bc4b', title: 'excellent moves',       priority: false },
      { key: 'good',        label: '\u2713',   color: '#95b776', title: 'good moves',            priority: false },
      { key: 'miss',        label: '\u00d7',   color: '#e06666', title: 'missed opportunities',  priority: true },
      { key: 'inaccuracy',  label: '?!',       color: '#f7c631', title: 'inaccuracies',          priority: false },
      { key: 'mistake',     label: '?',        color: '#e6912a', title: 'mistakes',              priority: false },
      { key: 'blunder',     label: '??',       color: '#ca3431', title: 'blunders',              priority: true },
    ];
    const MAX_BADGES = 5;

    function buildAccuracyRow(color, acc, isOpponent) {
      const row = document.createElement('div');
      row.className = 'accuracy-row' + (isOpponent ? ' opponent' : '');
      const label = document.createElement('span');
      label.className = 'accuracy-label';
      label.textContent = isOpponent ? 'Opp:' : 'You:';
      row.appendChild(label);
      if (acc !== null) {
        const val = document.createElement('span');
        val.className = 'accuracy-value';
        val.textContent = `${acc}%`;
        row.appendChild(val);
      }
      const counts = {};
      for (let i = 0; i < game.moves.length; i++) {
        const cls = classified[i];
        if (cls && game.moves[i].side === color) {
          counts[cls.category] = (counts[cls.category] || 0) + 1;
        }
      }
      // Select which badges to show: priority first, then fill, up to MAX_BADGES.
      // All selected badges are rendered in the global display order (allCategories).
      const present = allCategories.filter(cat => (counts[cat.key] || 0) > 0);
      const selected = new Set();
      // Pass 1: pick priority badges
      for (const cat of present) {
        if (selected.size >= MAX_BADGES) break;
        if (cat.priority) selected.add(cat.key);
      }
      // Pass 2: fill remaining slots with non-priority badges
      for (const cat of present) {
        if (selected.size >= MAX_BADGES) break;
        if (!cat.priority) selected.add(cat.key);
      }
      // Render in display order
      for (const cat of present) {
        if (!selected.has(cat.key)) continue;
        const badge = document.createElement('span');
        badge.className = 'class-badge';
        badge.style.color = cat.color;
        badge.style.border = `1px solid ${cat.color}`;
        badge.textContent = `${counts[cat.key]}${cat.label}`;
        badge.title = `${counts[cat.key]} ${cat.title}`;
        row.appendChild(badge);
      }
      return row;
    }

    const accEl = document.createElement('div');
    accEl.className = 'game-card-accuracy';
    accEl.appendChild(buildAccuracyRow(game.player_color, playerAcc, false));
    accEl.appendChild(buildAccuracyRow(opponentColor, opponentAcc, true));
    card.appendChild(accEl);

    selector.appendChild(card);
  }

  // Pagination controls (bottom)
  if (totalPages > 1) {
    selector.appendChild(_buildPagination(totalPages, filteredList.length));
  }

  updateAnalyzeButton();
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
  classifiedMoves = getClassifications(reviewGame._id, reviewGame.moves, reviewGame.player_color);

  // Hide selector and toolbar, show review
  document.getElementById('game-selector').classList.add('hidden');
  document.getElementById('game-list-toolbar').classList.add('hidden');
  document.getElementById('game-review').classList.remove('hidden');

  // Game info bar — link to the original game on chess.com/lichess
  const infoEl = document.getElementById('review-game-info');
  const result = reviewGame.headers.result;
  const gameLink = reviewGame.headers.link || reviewGame.headers.Link || gameId;
  infoEl.textContent = '';
  const infoAnchor = document.createElement('a');
  infoAnchor.href = gameLink;
  infoAnchor.target = '_blank';
  infoAnchor.rel = 'noopener';
  infoAnchor.textContent = `${reviewGame.headers.white} vs ${reviewGame.headers.black}  ${result}`;
  infoEl.appendChild(infoAnchor);

  // Show/hide "Train on this game" button
  const trainBtn = document.getElementById('review-train-btn');
  if (trainBtn) {
    if (trainingData && trainingData.positions) {
      const matchingPositions = trainingData.positions.filter((p) => p.game && p.game.id === gameId);
      console.log(`[selectGame] Training positions for this game: ${matchingPositions.length} (gameId=${gameId})`);
      if (matchingPositions.length > 0) {
        trainBtn.classList.remove('hidden');
        trainBtn.onclick = () => showTrainingView(gameId);
      } else {
        trainBtn.classList.add('hidden');
      }
    } else {
      console.log('[selectGame] trainingData not loaded, hiding train button');
      trainBtn.classList.add('hidden');
    }
  }

  appView = 'review';

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
 * Render the game summary (player names).
 */
function renderGameSummary() {
  const el = document.getElementById('review-summary');
  el.textContent = '';

  for (const color of ['white', 'black']) {
    const block = document.createElement('div');
    block.className = 'accuracy-block';

    const label = document.createElement('div');
    label.className = 'accuracy-label';
    label.textContent = color === 'white' ? reviewGame.headers.white : reviewGame.headers.black;
    block.appendChild(label);

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
    fill.style.height = '50%';
    label.textContent = '—';
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
  if (cls && ['miss', 'inaccuracy', 'mistake', 'blunder'].includes(cls.category)) {
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

  const maxCp = 800; // clamp at ±8 pawns to avoid overflow
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
      if (cls && ['brilliant', 'miss', 'inaccuracy', 'mistake', 'blunder'].includes(cls.category)) {
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
    ctx.strokeStyle = 'rgba(76,175,80,0.8)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x, h * 0.25);
    ctx.lineTo(x, h * 0.75);
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

  const maxCp = 800; // clamp at ±8 pawns to avoid overflow
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

  // Build the eval path points
  const evalPoints = [];
  for (let i = 0; i < moves.length; i++) {
    evalPoints.push({ x: stepX * (i + 1), y: cpToY(getEval(moves[i])) });
  }

  // White area fill (above center line — favorable to White)
  ctx.save();
  ctx.beginPath();
  ctx.rect(0, 0, w, midY);
  ctx.clip();
  ctx.beginPath();
  ctx.moveTo(stepX, midY);
  for (const p of evalPoints) ctx.lineTo(p.x, p.y);
  ctx.lineTo(stepX * moves.length, midY);
  ctx.closePath();
  ctx.fillStyle = 'rgba(255,255,255,0.12)';
  ctx.fill();
  ctx.restore();

  // Black area fill (below center line — favorable to Black)
  ctx.save();
  ctx.beginPath();
  ctx.rect(0, midY, w, midY);
  ctx.clip();
  ctx.beginPath();
  ctx.moveTo(stepX, midY);
  for (const p of evalPoints) ctx.lineTo(p.x, p.y);
  ctx.lineTo(stepX * moves.length, midY);
  ctx.closePath();
  ctx.fillStyle = 'rgba(0,0,0,0.25)';
  ctx.fill();
  ctx.restore();

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
      if (cls && ['brilliant', 'miss', 'inaccuracy', 'mistake', 'blunder'].includes(cls.category)) {
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
      const refreshItem = document.getElementById('nav-fetch');
      if (refreshItem) refreshItem.classList.remove('disabled');

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
  await loadTrainingData();

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

  document.getElementById('skip-btn').addEventListener('click', () => {
    skipPosition();
  });

  document.getElementById('show-answer-btn').addEventListener('click', () => {
    showAnswer();
  });

  document.getElementById('nav-settings').addEventListener('click', () => {
    closeMenu();
    openSettings();
  });

  document.getElementById('save-settings').addEventListener('click', () => saveAllSettings());

  document.getElementById('close-settings').addEventListener('click', () => {
    document.getElementById('settings-modal').classList.add('hidden');
  });

  document.getElementById('reset-progress').addEventListener('click', () => {
    if (confirm('Erase all training progress? This cannot be undone.')) {
      localStorage.removeItem('train_srs');
      srsState = {};
      document.getElementById('settings-modal').classList.add('hidden');
      startSession();
    }
  });

  wirePresets();

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

  wireNavItem('nav-fetch', () => {
    document.getElementById('fetch-modal').classList.remove('hidden');
  });

  document.getElementById('close-fetch')?.addEventListener('click', () => {
    document.getElementById('fetch-modal').classList.add('hidden');
  });

  document.getElementById('fetch-latest-btn')?.addEventListener('click', async () => {
    await doFetchGames(200);
  });

  document.getElementById('fetch-count-btn')?.addEventListener('click', async () => {
    const count = parseInt(document.getElementById('fetch-count-input').value, 10) || 50;
    await doFetchGames(count);
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

  // Wire nav menu items
  wireNavItem('nav-games', () => showGameList());
  wireNavItem('nav-training', () => showTrainingView(null));

  // Wire game list toolbar
  const selectAllCb = document.getElementById('select-all-checkbox');
  if (selectAllCb) {
    selectAllCb.addEventListener('change', () => {
      const checkboxes = document.querySelectorAll('.game-card-checkbox');
      checkboxes.forEach((cb) => {
        cb.checked = selectAllCb.checked;
        const gameId = cb.closest('.game-card').dataset.gameId;
        if (selectAllCb.checked) selectedGameIds.add(gameId);
        else selectedGameIds.delete(gameId);
      });
      updateAnalyzeButton();
    });
  }

  const limitSelect = document.getElementById('game-limit-select');
  if (limitSelect) {
    limitSelect.addEventListener('change', () => {
      gameListLimit = parseInt(limitSelect.value, 10);
      gameListPage = 0;
      console.log('[init] Game list limit changed to', gameListLimit);
      showGameSelector();
    });
  }

  // Wire filter dropdowns
  const resultFilterSelect = document.getElementById('result-filter-select');
  if (resultFilterSelect) {
    resultFilterSelect.addEventListener('change', () => {
      resultFilter = resultFilterSelect.value;
      gameListPage = 0;
      console.log('[init] Result filter:', resultFilter);
      showGameSelector();
    });
  }
  const colorFilterSelect = document.getElementById('color-filter-select');
  if (colorFilterSelect) {
    colorFilterSelect.addEventListener('change', () => {
      colorFilter = colorFilterSelect.value;
      gameListPage = 0;
      showGameSelector();
    });
  }
  const openingFilterSelect = document.getElementById('opening-filter-select');
  if (openingFilterSelect) {
    openingFilterSelect.addEventListener('change', () => {
      openingFilter = openingFilterSelect.value;
      gameListPage = 0;
      showGameSelector();
    });
  }
  const statusFilterSelect = document.getElementById('status-filter-select');
  if (statusFilterSelect) {
    statusFilterSelect.addEventListener('change', () => {
      statusFilter = statusFilterSelect.value;
      gameListPage = 0;
      console.log('[init] Status filter:', statusFilter);
      showGameSelector();
    });
  }

  const analyzeSelBtn = document.getElementById('analyze-selected-btn');
  if (analyzeSelBtn) {
    analyzeSelBtn.addEventListener('click', () => analyzeSelectedGames());
  }

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
  document.getElementById('review-back-btn').addEventListener('click', (e) => {
    e.preventDefault();
    if (autoPlayTimer) { clearInterval(autoPlayTimer); autoPlayTimer = null; }
    showGameList();
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
    if (appView !== 'review' || !reviewGame) return;
    // Don't capture if user is typing in an input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.key === 'ArrowLeft') { e.preventDefault(); goToMove(currentPly - 1); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); goToMove(currentPly + 1); }
    else if (e.key === 'Home') { e.preventDefault(); goToMove(0); }
    else if (e.key === 'End') { e.preventDefault(); goToMove(reviewGame.moves.length); }
  });

  // Close modals on Escape key or backdrop click
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const open = document.querySelector('.modal:not(.hidden)');
      if (open) open.classList.add('hidden');
    }
  });
  document.querySelectorAll('.modal').forEach((modal) => {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.classList.add('hidden');
    });
  });

  // Resize handler for score chart
  window.addEventListener('resize', () => {
    if (appView === 'review' && reviewGame) renderScoreChart();
  });

  // Register service worker
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch((err) =>
      console.warn('SW registration failed:', err)
    );
  }

  // Default view: game list (load analysis data to populate it)
  showGameList();

  // In app mode, auto-fetch games and reconnect to running analysis job
  if (appMode === 'app') {
    autoFetchGames();
    reconnectToRunningJob();
  }
}

/**
 * Check for a running analysis job on the server and reconnect to its SSE stream.
 * Called at startup so the progress counter reappears after page refresh.
 */
async function reconnectToRunningJob() {
  try {
    const resp = await fetch('/api/jobs/current');
    if (!resp.ok) return;
    const { job_id: jobId, status, game_ids: gameIds } = await resp.json();
    if (jobId && status === 'running') {
      console.log('[reconnectToRunningJob] Reconnecting to job:', jobId, 'games:', gameIds?.length);
      analyzingGameIds = new Set(gameIds || []);
      analysisTotalAll = analyzingGameIds.size;
      showAnalysisProgress(jobId);
      showGameSelector();
    }
  } catch (e) {
    // Ignore — not in app mode or server unreachable
  }
}

/**
 * Auto-fetch games from Lichess/chess.com at startup.
 * Falls back to analysis_data.json on error.
 * @async
 */
async function autoFetchGames() {
  console.log('[autoFetchGames] Fetching games...');
  const selector = document.getElementById('game-selector');
  if (selector) selector.textContent = 'Fetching your games...';
  try {
    await fetch('/api/games/fetch', { method: 'POST' });
    await showGameSelector();
  } catch (err) {
    console.error('[autoFetchGames] Failed:', err);
  }
}

/**
 * Fetch games with a specific max_games parameter. Updates the modal status.
 * @param {number} maxGames - Maximum number of games to fetch per source.
 */
async function doFetchGames(maxGames) {
  const statusEl = document.getElementById('fetch-status');
  const btns = document.querySelectorAll('.fetch-option');
  btns.forEach(b => { b.disabled = true; });
  if (statusEl) statusEl.textContent = 'Fetching...';
  try {
    await fetch(`/api/games/fetch?max_games=${maxGames}`, { method: 'POST' });
    if (statusEl) statusEl.textContent = 'Done!';
    document.getElementById('fetch-modal').classList.add('hidden');
    if (statusEl) statusEl.textContent = '';
    await showGameSelector();
  } catch (err) {
    console.error('[doFetchGames] Failed:', err);
    if (statusEl) statusEl.textContent = 'Error: ' + err.message;
  } finally {
    btns.forEach(b => { b.disabled = false; });
  }
}

/**
 * Analyze the selected games (send game_ids to analysis API).
 * @async
 */
async function analyzeSelectedGames() {
  const ids = Array.from(selectedGameIds);
  console.log('[analyzeSelectedGames] Analyzing', ids.length, 'game(s)');
  if (ids.length === 0) return;

  // If a job is already running, queue these games for the next batch
  if (analyzingGameIds.size > 0) {
    console.log('[analyzeSelectedGames] Job running, queuing', ids.length, 'game(s)');
    for (const id of ids) pendingGameIds.add(id);
    analysisTotalAll += ids.length;
    selectedGameIds.clear();
    // Update progress text with new total
    const el = document.getElementById('analysis-progress');
    if (el && !el.classList.contains('hidden')) {
      el.textContent = el.textContent.replace(/\/\d+/, '/' + analysisTotalAll);
    }
    showGameSelector();
    return;
  }

  // Start a new job (reanalyze_all if any selected game is already analyzed)
  const hasAnalyzed = ids.some(id => analysisData?.games?.[id]);
  try {
    const resp = await fetch('/api/analysis/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ game_ids: ids, reanalyze_all: hasAnalyzed }),
    });
    if (resp.status === 409) {
      // Job already running (e.g. after page refresh) — queue and reconnect
      console.log('[analyzeSelectedGames] Job already running, queuing', ids.length, 'game(s)');
      for (const id of ids) pendingGameIds.add(id);
      analysisTotalAll += ids.length;
      selectedGameIds.clear();
      // Reconnect to the running job's SSE stream
      try {
        const jobResp = await fetch('/api/jobs/current');
        if (jobResp.ok) {
          const { job_id: runningJobId, status } = await jobResp.json();
          if (runningJobId && status === 'running') {
            analyzingGameIds = new Set();  // unknown which games, but job is running
            showAnalysisProgress(runningJobId);
          }
        }
      } catch (e) { /* ignore */ }
      showGameSelector();
      return;
    }
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      console.error('[analyzeSelectedGames] API error:', resp.status, err.detail);
      const el = document.getElementById('analysis-progress');
      if (el) { el.textContent = `Error: ${err.detail || resp.status}`; el.classList.remove('hidden'); }
      return;
    }
    const { job_id: jobId } = await resp.json();
    console.log('[analyzeSelectedGames] Job started:', jobId);

    analyzingGameIds = new Set(ids);
    analysisOffset = 0;
    analysisTotalAll = ids.length + pendingGameIds.size;
    selectedGameIds.clear();
    showGameSelector();
    showAnalysisProgress(jobId);
  } catch (err) {
    console.error('[analyzeSelectedGames] Fetch failed:', err);
    const el = document.getElementById('analysis-progress');
    if (el) { el.textContent = `Error: ${err.message}`; el.classList.remove('hidden'); }
  }
}

/**
 * Start an analysis job for the given game IDs (internal helper for queue continuation).
 * @param {string[]} ids - Game IDs to analyze.
 * @async
 */
async function startAnalysisJob(ids) {
  console.log('[startAnalysisJob] Starting batch of', ids.length, 'game(s)');
  const hasAnalyzed = ids.some(id => analysisData?.games?.[id]);
  try {
    const resp = await fetch('/api/analysis/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ game_ids: ids, reanalyze_all: hasAnalyzed }),
    });
    if (!resp.ok) {
      console.error('[startAnalysisJob] API error:', resp.status);
      analyzingGameIds.clear();
      return;
    }
    const { job_id: jobId } = await resp.json();
    console.log('[startAnalysisJob] Job started:', jobId);
    showAnalysisProgress(jobId);
  } catch (err) {
    console.error('[startAnalysisJob] Fetch failed:', err);
    analyzingGameIds.clear();
  }
}

init();
