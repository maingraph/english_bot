/**
 * Netlify Function (Node.js) for the TMA API.
 *
 * Why JS: Netlify Functions do NOT run Python. Python files in netlify/functions
 * won't execute, which is why your "Join Game" was failing after deploy.
 *
 * Endpoints (via redirects):
 * - POST /api/join
 * - GET  /api/state
 * - POST /api/answer
 * - POST /api/admin/open
 * - POST /api/admin/start
 * - POST /api/admin/reset
 * - POST /api/admin/next
 */

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const BOT_TOKEN = process.env.BOT_TOKEN || "";
const ADMIN_TOKEN = process.env.ADMIN_TOKEN || "classroom2024";
const ADMIN_IDS = (process.env.ADMIN_IDS || "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

// Load vocab once (bundled from public/vocab.json)
let VOCAB = [];
try {
  const vocabPath = path.join(process.cwd(), "public", "vocab.json");
  VOCAB = JSON.parse(fs.readFileSync(vocabPath, "utf8"));
} catch (e) {
  VOCAB = [];
}

// In-memory game (persists only while the function instance stays warm)
const game = global.__TMA_GAME__ || {
  isOpen: false,
  isRunning: false,
  isFinished: false,
  players: new Map(), // userId -> {name, score, correct, wrong}
  currentRound: 0,
  totalRounds: 10,
  roundSeconds: 12,
  roundStartMs: 0,
  question: null, // {taskType, prompt, options, correctIndex}
  answers: new Map(), // userId -> {choice, ms}
};
global.__TMA_GAME__ = game;

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
  if (!ADMIN_IDS.length) return true; // if not configured, allow (safe for single-teacher demos)
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

function leaderboard(limit) {
  const arr = Array.from(game.players.entries()).map(([userId, p]) => ({
    user_id: userId,
    name: p.name,
    score: p.score,
    correct: p.correct,
    wrong: p.wrong,
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

function buildQuestion() {
  if (!VOCAB.length) return null;

  // Prefer synonym questions for your lists.
  const candidates = VOCAB.filter((v) => (v.synonyms || []).length >= 1);
  const base = candidates.length ? pickRandom(candidates) : pickRandom(VOCAB);

  const correct = (base.synonyms && base.synonyms[0]) || base.word;
  const distractPool = VOCAB.flatMap((v) => (v.synonyms || []).slice(0, 2)).filter(Boolean);

  const options = new Set([correct]);
  while (options.size < 4 && distractPool.length) options.add(pickRandom(distractPool));
  while (options.size < 4) options.add(`${pickRandom(VOCAB).word}`); // fallback

  const optsArr = Array.from(options);
  // shuffle
  for (let i = optsArr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [optsArr[i], optsArr[j]] = [optsArr[j], optsArr[i]];
  }

  return {
    taskType: "SYNONYM",
    prompt: `Choose a synonym for <b>${escapeHtml(base.word)}</b>`,
    options: optsArr,
    correctIndex: optsArr.findIndex((x) => x === correct),
  };
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function endRoundIfNeeded() {
  if (!game.isRunning || !game.question) return;
  if (timeRemainingSeconds() > 0 && game.answers.size < game.players.size) return;

  // score
  for (const [userId, ans] of game.answers.entries()) {
    const p = game.players.get(userId);
    if (!p) continue;
    const correct = ans.choice === game.question.correctIndex;
    if (correct) {
      p.correct += 1;
      // simple scoring: 2 points fast, else 1
      p.score += ans.ms <= 4000 ? 2 : 1;
    } else {
      p.wrong += 1;
    }
  }

  // next
  game.answers = new Map();
  game.currentRound += 1;
  if (game.currentRound > game.totalRounds) {
    game.isRunning = false;
    game.isFinished = true;
    game.question = null;
    return;
  }
  game.question = buildQuestion();
  game.roundStartMs = nowMs();
}

exports.handler = async (event) => {
  const method = event.httpMethod || "GET";
  const headers = event.headers || {};
  const p = event.path || "";
  const body = event.body ? JSON.parse(event.body) : {};

  // route extraction:
  // /.netlify/functions/tma-api/join OR /api/join (after redirects)
  const routePart = p.split("/").slice(-2).join("/"); // e.g. "api/join" or "tma-api/join"
  const isJoin = routePart.endsWith("/join");
  const isState = routePart.endsWith("/state");
  const isAnswer = routePart.endsWith("/answer");
  const isAdmin = p.includes("/admin/");

  // auth
  const initData = header(headers, "X-Telegram-Init-Data");
  const user = parseInitData(initData);
  const userId = user && user.id;
  const name = user
    ? `${user.first_name || "Player"}${user.last_name ? " " + user.last_name : ""}`.trim()
    : "Player";

  // allow CORS preflight
  if (method === "OPTIONS") return json(200, { ok: true });

  // Admin endpoints
  if (isAdmin) {
    const adminToken = header(headers, "X-Admin-Token");
    if (!BOT_TOKEN) {
      return json(500, { ok: false, error: "Server misconfigured: BOT_TOKEN is missing in Netlify env vars." });
    }
    if (!userId) {
      return json(401, { ok: false, error: "Invalid auth: open this inside Telegram (initData missing/invalid)." });
    }
    if (!isTelegramAdmin(userId)) {
      return json(403, { ok: false, error: "Admins only (your Telegram user_id is not in ADMIN_IDS)." });
    }
    if (adminToken !== ADMIN_TOKEN) {
      return json(403, { ok: false, error: "Unauthorized (bad admin token)." });
    }

    if (method !== "POST") return json(405, { ok: false, error: "Method not allowed" });

    if (p.endsWith("/admin/open")) {
      game.isOpen = true;
      game.isRunning = false;
      game.isFinished = false;
      game.players = new Map();
      game.answers = new Map();
      game.currentRound = 0;
      game.totalRounds = Number(body.rounds || 10);
      game.roundSeconds = Number(body.seconds || 12);
      game.question = null;
      game.roundStartMs = 0;
      return json(200, { ok: true });
    }

    if (p.endsWith("/admin/start")) {
      if (!game.isOpen) return json(400, { ok: false, error: "Lobby not open" });
      if (game.players.size < 1) return json(400, { ok: false, error: "Need at least 1 player" });
      game.isOpen = false;
      game.isRunning = true;
      game.isFinished = false;
      game.currentRound = 1;
      game.question = buildQuestion();
      game.roundStartMs = nowMs();
      game.answers = new Map();
      return json(200, { ok: true });
    }

    if (p.endsWith("/admin/next")) {
      if (!game.isRunning) return json(400, { ok: false, error: "Game not running" });
      // Force end current round and move on
      game.roundStartMs = 0;
      endRoundIfNeeded();
      return json(200, { ok: true });
    }

    if (p.endsWith("/admin/reset")) {
      game.isOpen = false;
      game.isRunning = false;
      game.isFinished = false;
      game.players = new Map();
      game.answers = new Map();
      game.currentRound = 0;
      game.question = null;
      game.roundStartMs = 0;
      return json(200, { ok: true });
    }

    return json(404, { ok: false, error: "Unknown admin route" });
  }

  // Player endpoints
  if (isJoin && method === "POST") {
    if (!BOT_TOKEN) {
      return json(500, { ok: false, error: "Server misconfigured: BOT_TOKEN is missing in Netlify env vars." });
    }
    if (!userId) {
      return json(401, {
        ok: false,
        error:
          "Invalid auth. Open the Mini App from the bot button inside Telegram (not a browser link).",
      });
    }
    if (!game.isOpen || game.isRunning || game.isFinished) {
      return json(400, { ok: false, error: "Lobby not open (host must press Open)." });
    }
    if (!game.players.has(userId)) {
      game.players.set(userId, { name, score: 0, correct: 0, wrong: 0 });
    }
    return json(200, { ok: true });
  }

  if (isState && method === "GET") {
    // tick
    endRoundIfNeeded();
    const lb = leaderboard(5);
    const me = userId ? game.players.get(userId) : null;
    return json(200, {
      is_open: game.isOpen,
      is_running: game.isRunning,
      is_finished: game.isFinished,
      player_count: game.players.size,
      current_round: game.currentRound,
      total_rounds: game.totalRounds,
      time_remaining: timeRemainingSeconds(),
      leaderboard: lb,
      my_rank: userId ? myRank(userId) : null,
      my_score: me ? me.score : 0,
      my_correct: me ? me.correct : 0,
      already_answered: userId ? game.answers.has(userId) : false,
      question: game.isRunning && game.question
        ? { task_type: game.question.taskType, prompt: game.question.prompt, options: game.question.options }
        : null,
      final_leaderboard: game.isFinished ? leaderboard(999) : null,
    });
  }

  if (isAnswer && method === "POST") {
    if (!BOT_TOKEN) {
      return json(500, { ok: false, error: "Server misconfigured: BOT_TOKEN is missing in Netlify env vars." });
    }
    if (!userId) return json(401, { ok: false, error: "Invalid auth" });
    if (!game.isRunning || !game.question) return json(400, { ok: false, error: "No active round" });
    if (!game.players.has(userId)) return json(400, { ok: false, error: "Not joined" });
    if (game.answers.has(userId)) return json(400, { ok: false, error: "Already answered" });

    const choice = Number(body.choice);
    const ms = Math.max(0, nowMs() - game.roundStartMs);
    game.answers.set(userId, { choice, ms });
    // maybe end early
    endRoundIfNeeded();
    return json(200, { ok: true });
  }

  return json(404, { ok: false, error: `Not found: ${method} ${p}` });
};


