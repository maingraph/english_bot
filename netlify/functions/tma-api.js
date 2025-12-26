/**
 * Netlify Function (Node.js) for the TMA API - Battle Royale Duel System
 *
 * Game Flow:
 * 1. Players join lobby
 * 2. Admin starts game
 * 3. Each round: players randomly paired into duels (2 players per duel)
 * 4. Each duel gets a question (different task types rotate)
 * 5. Players answer, winner gets points
 * 6. After round ends, re-pair for next round
 * 7. After all rounds, show final leaderboard
 */

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const API_VERSION = "2025-12-25-battle-royale";

const BOT_TOKEN = process.env.BOT_TOKEN || "";
const ADMIN_TOKEN = process.env.ADMIN_TOKEN || "classroom2024";
const ADMIN_IDS = (process.env.ADMIN_IDS || "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

const TASK_TYPES = ["SYNONYM", "ANTONYM", "TRANSLATE", "DEFINITION", "GAPFILL"];
const DEFAULT_ROUNDS = 10;
const DEFAULT_ROUND_SECONDS = 12;
const REST_BETWEEN_ROUNDS_SECONDS = 5;

// Load vocab once (bundled from public/vocab.json)
let VOCAB = [];
let VOCAB_LOAD_ERROR = "";
try {
  const vocabPath = path.join(process.cwd(), "public", "vocab.json");
  VOCAB = JSON.parse(fs.readFileSync(vocabPath, "utf8"));
} catch (e) {
  VOCAB = [];
  VOCAB_LOAD_ERROR = String(e && e.message ? e.message : e);
}

// In-memory game state
const game = global.__TMA_GAME__ || {
  isOpen: false,
  isRunning: false,
  isFinished: false,
  players: new Map(), // userId -> {name, score, correct, wrong, wins, losses}
  currentRound: 0,
  totalRounds: DEFAULT_ROUNDS,
  roundSeconds: DEFAULT_ROUND_SECONDS,
  roundStartMs: 0,
  roundEndMs: 0, // when round ended (for rest period)
  duels: new Map(), // duelId -> {p1, p2, question, answers: Map(userId -> {choice, ms}), taskType}
  playerToDuel: new Map(), // userId -> duelId
  nextDuelId: 1,
  taskTypeIndex: 0, // rotates through TASK_TYPES
};
global.__TMA_GAME__ = game;

// Simple in-memory ring-buffer logs
const LOGS = global.__TMA_LOGS__ || [];
global.__TMA_LOGS__ = LOGS;
function log(level, message, extra = null) {
  const entry = { ts: new Date().toISOString(), level, message, extra };
  LOGS.push(entry);
  while (LOGS.length > 200) LOGS.shift();
  try {
    console.log(JSON.stringify(entry));
  } catch {
    console.log(level, message);
  }
}

function json(statusCode, data) {
  return {
    statusCode,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "Content-Type, X-Admin-Token, X-Telegram-Init-Data",
    },
    body: JSON.stringify(data),
  };
}

function parseInitData(initData) {
  if (!BOT_TOKEN || !initData) return null;

  const parsed = new URLSearchParams(initData);
  const receivedHash = parsed.get("hash");
  if (!receivedHash) return null;

  const keys = Array.from(parsed.keys()).filter((k) => k !== "hash").sort();
  const dataCheckString = keys.map((k) => `${k}=${parsed.get(k)}`).join("\n");

  const secretKey = crypto
    .createHmac("sha256", "WebAppData")
    .update(BOT_TOKEN)
    .digest();

  const computedHash = crypto
    .createHmac("sha256", secretKey)
    .update(dataCheckString)
    .digest("hex");

  if (computedHash !== receivedHash) return null;

  const userRaw = parsed.get("user");
  if (!userRaw) return null;
  try {
    return JSON.parse(userRaw);
  } catch {
    return null;
  }
}

function isTelegramAdmin(userId) {
  if (!userId) return false;
  if (!ADMIN_IDS.length) return true;
  return ADMIN_IDS.includes(String(userId));
}

function header(headers, name) {
  return (headers && (headers[name] || headers[name.toLowerCase()])) || "";
}

function nowMs() {
  return Date.now();
}

function timeRemainingSeconds() {
  if (!game.isRunning || !game.roundStartMs) return 0;
  const elapsed = (nowMs() - game.roundStartMs) / 1000;
  return Math.max(0, game.roundSeconds - elapsed);
}

function isInRestPeriod() {
  if (!game.isRunning || !game.roundEndMs) return false;
  const restElapsed = (nowMs() - game.roundEndMs) / 1000;
  return restElapsed < REST_BETWEEN_ROUNDS_SECONDS;
}

function leaderboard(limit) {
  const arr = Array.from(game.players.entries()).map(([userId, p]) => ({
    user_id: userId,
    name: p.name,
    score: p.score,
    correct: p.correct,
    wrong: p.wrong,
    wins: p.wins || 0,
    losses: p.losses || 0,
  }));
  arr.sort((a, b) => b.score - a.score);
  return arr.slice(0, limit).map((p, idx) => ({ ...p, rank: idx + 1 }));
}

function myRank(userId) {
  const arr = Array.from(game.players.entries()).map(([uid, p]) => ({
    user_id: uid,
    score: p.score,
  }));
  arr.sort((a, b) => b.score - a.score);
  const idx = arr.findIndex((x) => String(x.user_id) === String(userId));
  return idx >= 0 ? idx + 1 : null;
}

function pickRandom(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function shuffleArray(arr) {
  const shuffled = [...arr];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled;
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function buildQuestion(taskType) {
  if (!VOCAB.length) return null;

  const candidates = VOCAB.filter((v) => {
    if (taskType === "SYNONYM") return (v.synonyms || []).length >= 1;
    if (taskType === "ANTONYM") return (v.antonyms || []).length >= 1;
    if (taskType === "TRANSLATE") return v.translation && v.translation.trim();
    if (taskType === "DEFINITION") return v.definition && v.definition.trim();
    if (taskType === "GAPFILL") return v.example && v.example.trim();
    return true;
  });

  if (!candidates.length) return null;
  const base = pickRandom(candidates);

  let correct = "";
  let prompt = "";
  const distractors = [];

  if (taskType === "SYNONYM") {
    correct = pickRandom(base.synonyms || []);
    prompt = `Pick a <b>synonym</b> for:\n<b>${escapeHtml(base.word)}</b>`;
    // Get distractors from other words' synonyms
    for (const v of VOCAB) {
      if (v === base) continue;
      if (v.synonyms && v.synonyms.length) {
        distractors.push(...v.synonyms.slice(0, 2));
      }
    }
  } else if (taskType === "ANTONYM") {
    correct = pickRandom(base.antonyms || []);
    prompt = `Pick an <b>antonym</b> for:\n<b>${escapeHtml(base.word)}</b>`;
    for (const v of VOCAB) {
      if (v === base) continue;
      if (v.antonyms && v.antonyms.length) {
        distractors.push(...v.antonyms.slice(0, 2));
      }
    }
  } else if (taskType === "TRANSLATE") {
    correct = base.translation || "";
    prompt = `Pick the <b>translation</b> for:\n<b>${escapeHtml(base.word)}</b>`;
    for (const v of VOCAB) {
      if (v === base || !v.translation) continue;
      distractors.push(v.translation);
    }
  } else if (taskType === "DEFINITION") {
    correct = base.definition || "";
    prompt = `Pick the <b>definition</b> of:\n<b>${escapeHtml(base.word)}</b>`;
    for (const v of VOCAB) {
      if (v === base || !v.definition) continue;
      distractors.push(v.definition);
    }
  } else if (taskType === "GAPFILL") {
    correct = base.word;
    let blanked = base.example || "";
    if (base.word && blanked.toLowerCase().includes(base.word.toLowerCase())) {
      blanked = blanked.replace(new RegExp(base.word, "gi"), "____");
    } else {
      blanked = blanked + " (____)";
    }
    prompt = `Fill the blank:\n<blockquote>${escapeHtml(blanked)}</blockquote>`;
    for (const v of VOCAB) {
      if (v === base || !v.word) continue;
      distractors.push(v.word);
    }
  }

  if (!correct) return null;

  const options = new Set([correct]);
  const shuffledDistractors = shuffleArray(distractors);
  for (const d of shuffledDistractors) {
    if (options.size >= 4) break;
    if (d && d.trim() && d !== correct) options.add(d.trim());
  }

  // Fallback: use random words if not enough distractors
  while (options.size < 4 && VOCAB.length > 0) {
    const randomWord = pickRandom(VOCAB);
    if (randomWord.word && randomWord.word !== correct) {
      options.add(randomWord.word);
    }
  }

  const optsArr = Array.from(options);
  if (optsArr.length < 2) return null;

  shuffleArray(optsArr);
  const correctIndex = optsArr.indexOf(correct);

  return {
    taskType,
    prompt,
    options: optsArr,
    correctIndex,
  };
}

function pairPlayers() {
  // Clear old pairings
  game.duels.clear();
  game.playerToDuel.clear();

  const playerIds = Array.from(game.players.keys());
  if (playerIds.length < 2) return; // Need at least 2 players

  shuffleArray(playerIds);

  // Pair players
  for (let i = 0; i < playerIds.length; i += 2) {
    const p1 = playerIds[i];
    if (i + 1 >= playerIds.length) {
      // Odd player out - they get a "bye" (no opponent this round)
      continue;
    }
    const p2 = playerIds[i + 1];

    const duelId = game.nextDuelId++;
    const taskType = TASK_TYPES[game.taskTypeIndex % TASK_TYPES.length];
    const question = buildQuestion(taskType);

    if (!question) {
      log("warn", "pair_players_no_question", { task_type: taskType, vocab_count: VOCAB.length });
      continue;
    }

    game.duels.set(duelId, {
      p1,
      p2,
      question,
      answers: new Map(),
      taskType,
    });

    game.playerToDuel.set(p1, duelId);
    game.playerToDuel.set(p2, duelId);
  }

  // Rotate task type for next round
  game.taskTypeIndex = (game.taskTypeIndex + 1) % TASK_TYPES.length;
}

function endRound() {
  if (!game.isRunning) return;

  // Score all duels
  for (const [duelId, duel] of game.duels.entries()) {
    const p1 = game.players.get(duel.p1);
    const p2 = game.players.get(duel.p2);
    if (!p1 || !p2) continue;

    const a1 = duel.answers.get(duel.p1);
    const a2 = duel.answers.get(duel.p2);

    const p1Correct = a1 && a1.choice === duel.question.correctIndex;
    const p2Correct = a2 && a2.choice === duel.question.correctIndex;

    if (p1Correct) {
      p1.correct += 1;
      const points = a1.ms <= 4000 ? 2 : 1;
      p1.score += points;
    } else {
      p1.wrong += 1;
    }

    if (p2Correct) {
      p2.correct += 1;
      const points = a2.ms <= 4000 ? 2 : 1;
      p2.score += points;
    } else {
      p2.wrong += 1;
    }

    // Track wins/losses
    if (p1Correct && !p2Correct) {
      p1.wins = (p1.wins || 0) + 1;
      p2.losses = (p2.losses || 0) + 1;
    } else if (p2Correct && !p1Correct) {
      p2.wins = (p2.wins || 0) + 1;
      p1.losses = (p1.losses || 0) + 1;
    }
  }

  game.roundEndMs = nowMs();
  game.currentRound += 1;

  if (game.currentRound > game.totalRounds) {
    game.isRunning = false;
    game.isFinished = true;
    return;
  }

  // Re-pairing will happen automatically when rest period ends (checked in endRoundIfNeeded)
}

function endRoundIfNeeded() {
  if (!game.isRunning) return;

  // If in rest period, check if it's time to start next round
  if (isInRestPeriod()) {
    const restElapsed = (nowMs() - game.roundEndMs) / 1000;
    if (restElapsed >= REST_BETWEEN_ROUNDS_SECONDS) {
      // Rest period over, start next round
      pairPlayers();
      game.roundStartMs = nowMs();
      game.roundEndMs = 0;
    }
    return;
  }

  // Check if current round should end
  const timeUp = timeRemainingSeconds() <= 0;
  const allAnswered = Array.from(game.duels.values()).every(
    (duel) => duel.answers.has(duel.p1) && duel.answers.has(duel.p2)
  );

  if (timeUp || allAnswered) {
    endRound();
  }
}

exports.handler = async (event) => {
  const reqId =
    (event.headers && (event.headers["x-nf-request-id"] || event.headers["X-Nf-Request-Id"])) ||
    crypto.randomUUID();

  try {
    const method = event.httpMethod || "GET";
    const headers = event.headers || {};
    const p = event.path || "";
    const body = event.body ? JSON.parse(event.body) : {};

    const routePart = p.split("/").slice(-2).join("/");
    const isJoin = routePart.endsWith("/join");
    const isState = routePart.endsWith("/state");
    const isAnswer = routePart.endsWith("/answer");
    const isDebug = routePart.endsWith("/debug");
    const isAdmin = p.includes("/admin/");

    const initData = header(headers, "X-Telegram-Init-Data");
    const user = parseInitData(initData);
    const userId = user && user.id;
    const name = user
      ? `${user.first_name || "Player"}${user.last_name ? " " + user.last_name : ""}`.trim()
      : "Player";

    log("info", "request", {
      req_id: reqId,
      method,
      path: p,
      route: routePart,
      has_init_data: Boolean(initData),
      user_id: userId || null,
      vocab_count: VOCAB.length,
    });

    if (method === "OPTIONS") return json(200, { ok: true });

    // Debug endpoint
    if (isDebug) {
      const adminToken = header(headers, "X-Admin-Token");
      if (!BOT_TOKEN || !userId || !isTelegramAdmin(userId) || adminToken !== ADMIN_TOKEN) {
        return json(403, { ok: false, error: "Admins only.", req_id: reqId });
      }
      return json(200, {
        ok: true,
        req_id: reqId,
        version: API_VERSION,
        vocab_count: VOCAB.length,
        vocab_load_error: VOCAB_LOAD_ERROR || null,
        game: {
          is_open: game.isOpen,
          is_running: game.isRunning,
          is_finished: game.isFinished,
          player_count: game.players.size,
          current_round: game.currentRound,
          total_rounds: game.totalRounds,
          round_seconds: game.roundSeconds,
          time_remaining: timeRemainingSeconds(),
          duels_count: game.duels.size,
          in_rest_period: isInRestPeriod(),
        },
        logs: LOGS.slice(-120),
      });
    }

    // Admin endpoints
    if (isAdmin) {
      const adminToken = header(headers, "X-Admin-Token");
      if (!BOT_TOKEN || !userId || !isTelegramAdmin(userId) || adminToken !== ADMIN_TOKEN) {
        return json(403, { ok: false, error: "Admins only.", req_id: reqId });
      }

      if (method !== "POST") return json(405, { ok: false, error: "Method not allowed", req_id: reqId });

      if (p.endsWith("/admin/open")) {
        game.isOpen = true;
        game.isRunning = false;
        game.isFinished = false;
        game.players = new Map();
        game.duels = new Map();
        game.playerToDuel = new Map();
        game.currentRound = 0;
        game.totalRounds = Number(body.rounds || DEFAULT_ROUNDS);
        game.roundSeconds = Number(body.seconds || DEFAULT_ROUND_SECONDS);
        game.roundStartMs = 0;
        game.roundEndMs = 0;
        game.nextDuelId = 1;
        game.taskTypeIndex = 0;
        log("info", "admin_open", { req_id: reqId, rounds: game.totalRounds, seconds: game.roundSeconds });
        return json(200, { ok: true, req_id: reqId });
      }

      if (p.endsWith("/admin/start")) {
        if (!VOCAB.length) {
          return json(500, {
            ok: false,
            error: "No vocabulary loaded. Ensure public/vocab.json is bundled.",
            req_id: reqId,
            vocab_count: VOCAB.length,
          });
        }
        if (!game.isOpen) return json(400, { ok: false, error: "Lobby not open", req_id: reqId });
        if (game.players.size < 2) {
          return json(400, { ok: false, error: "Need at least 2 players", req_id: reqId });
        }

        game.isOpen = false;
        game.isRunning = true;
        game.isFinished = false;
        game.currentRound = 1;
        game.roundStartMs = nowMs();
        game.roundEndMs = 0;
        game.taskTypeIndex = 0;

        // Initialize player stats
        for (const [uid, p] of game.players.entries()) {
          p.score = 0;
          p.correct = 0;
          p.wrong = 0;
          p.wins = 0;
          p.losses = 0;
        }

        pairPlayers();
        log("info", "admin_start", { req_id: reqId, player_count: game.players.size, duels: game.duels.size });
        return json(200, { ok: true, req_id: reqId });
      }

      if (p.endsWith("/admin/next")) {
        if (!game.isRunning) return json(400, { ok: false, error: "Game not running", req_id: reqId });
        game.roundStartMs = 0; // Force end
        endRound();
        return json(200, { ok: true, req_id: reqId });
      }

      if (p.endsWith("/admin/reset")) {
        game.isOpen = false;
        game.isRunning = false;
        game.isFinished = false;
        game.players = new Map();
        game.duels = new Map();
        game.playerToDuel = new Map();
        game.currentRound = 0;
        game.roundStartMs = 0;
        game.roundEndMs = 0;
        game.nextDuelId = 1;
        game.taskTypeIndex = 0;
        log("info", "admin_reset", { req_id: reqId });
        return json(200, { ok: true, req_id: reqId });
      }

      return json(404, { ok: false, error: "Unknown admin route", req_id: reqId });
    }

    // Player endpoints
    if (isJoin && method === "POST") {
      if (!BOT_TOKEN || !userId) {
        return json(401, {
          ok: false,
          error: "Invalid auth. Open from Telegram bot button.",
          req_id: reqId,
        });
      }
      if (!game.isOpen || game.isRunning || game.isFinished) {
        return json(400, { ok: false, error: "Lobby not open", req_id: reqId });
      }
      if (!game.players.has(userId)) {
        game.players.set(userId, { name, score: 0, correct: 0, wrong: 0, wins: 0, losses: 0 });
        log("info", "player_join", { req_id: reqId, user_id: userId });
      }
      return json(200, { ok: true, req_id: reqId });
    }

    if (isState && method === "GET") {
      endRoundIfNeeded();

      const lb = leaderboard(5);
      const me = userId ? game.players.get(userId) : null;
      const myDuelId = userId ? game.playerToDuel.get(userId) : null;
      const myDuel = myDuelId ? game.duels.get(myDuelId) : null;

      let opponent = null;
      let myQuestion = null;
      let alreadyAnswered = false;

      if (myDuel && game.isRunning && !isInRestPeriod()) {
        const opponentId = myDuel.p1 === userId ? myDuel.p2 : myDuel.p1;
        const opponentPlayer = game.players.get(opponentId);
        if (opponentPlayer) {
          opponent = { user_id: opponentId, name: opponentPlayer.name };
        }
        myQuestion = {
          task_type: myDuel.question.taskType,
          prompt: myDuel.question.prompt,
          options: myDuel.question.options,
        };
        alreadyAnswered = myDuel.answers.has(userId);
      }

      return json(200, {
        ok: true,
        req_id: reqId,
        version: API_VERSION,
        is_open: game.isOpen,
        is_running: game.isRunning,
        is_finished: game.isFinished,
        player_count: game.players.size,
        current_round: game.currentRound,
        total_rounds: game.totalRounds,
        time_remaining: timeRemainingSeconds(),
        in_rest_period: isInRestPeriod(),
        rest_remaining: isInRestPeriod()
          ? Math.max(0, REST_BETWEEN_ROUNDS_SECONDS - (nowMs() - game.roundEndMs) / 1000)
          : 0,
        leaderboard: lb,
        my_rank: userId ? myRank(userId) : null,
        my_score: me ? me.score : 0,
        my_correct: me ? me.correct : 0,
        my_wins: me ? me.wins || 0 : 0,
        my_losses: me ? me.losses || 0 : 0,
        opponent: opponent,
        question: myQuestion,
        already_answered: alreadyAnswered,
        final_leaderboard: game.isFinished ? leaderboard(999) : null,
      });
    }

    if (isAnswer && method === "POST") {
      if (!BOT_TOKEN || !userId) {
        return json(401, { ok: false, error: "Invalid auth", req_id: reqId });
      }
      if (!game.isRunning || isInRestPeriod()) {
        return json(400, { ok: false, error: "No active round", req_id: reqId });
      }
      if (!game.players.has(userId)) {
        return json(400, { ok: false, error: "Not joined", req_id: reqId });
      }

      const myDuelId = game.playerToDuel.get(userId);
      if (!myDuelId) {
        return json(400, { ok: false, error: "Not paired (odd player out?)", req_id: reqId });
      }

      const myDuel = game.duels.get(myDuelId);
      if (!myDuel || !myDuel.question) {
        return json(400, { ok: false, error: "No active question", req_id: reqId });
      }
      if (myDuel.answers.has(userId)) {
        return json(400, { ok: false, error: "Already answered", req_id: reqId });
      }

      const choice = Number(body.choice);
      const ms = Math.max(0, nowMs() - game.roundStartMs);
      myDuel.answers.set(userId, { choice, ms });

      endRoundIfNeeded();
      return json(200, { ok: true, req_id: reqId });
    }

    return json(404, { ok: false, error: `Not found: ${method} ${p}`, req_id: reqId });
  } catch (err) {
    log("error", "handler_exception", {
      req_id: reqId,
      error: String(err && err.stack ? err.stack : err),
    });
    return json(500, { ok: false, error: "Server error", req_id: reqId });
  }
};
