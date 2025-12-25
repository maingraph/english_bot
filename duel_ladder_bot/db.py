import html
import json
import random
import sqlite3
import time
from typing import Any, Optional


class DB:
    def __init__(self, path: str):
        self.path = path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        conn = self._connect()
        cur = conn.cursor()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS vocab (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              word TEXT NOT NULL,
              definition TEXT DEFAULT '',
              translation TEXT DEFAULT '',
              synonyms_json TEXT DEFAULT '[]',
              antonyms_json TEXT DEFAULT '[]',
              example TEXT DEFAULT ''
            );
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
              user_id INTEGER PRIMARY KEY,
              username TEXT DEFAULT '',
              full_name TEXT DEFAULT '',
              last_chat_id INTEGER DEFAULT NULL,
              updated_at INTEGER NOT NULL
            );
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              chat_id INTEGER NOT NULL,
              started_at INTEGER NOT NULL,
              ends_at INTEGER NOT NULL,
              phase_seconds INTEGER NOT NULL,
              is_active INTEGER NOT NULL DEFAULT 1
            );
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS event_players (
              event_id INTEGER NOT NULL,
              chat_id INTEGER NOT NULL,
              user_id INTEGER NOT NULL,
              joined_at INTEGER NOT NULL,
              wins INTEGER NOT NULL DEFAULT 0,
              losses INTEGER NOT NULL DEFAULT 0,
              points INTEGER NOT NULL DEFAULT 0,
              correct INTEGER NOT NULL DEFAULT 0,
              wrong INTEGER NOT NULL DEFAULT 0,
              PRIMARY KEY (event_id, user_id)
            );
            """
        )

        # Per-event preference: auto queue for nonstop mode (1=yes, 0=pause)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS player_prefs (
              event_id INTEGER NOT NULL,
              user_id INTEGER NOT NULL,
              auto_queue INTEGER NOT NULL DEFAULT 1,
              PRIMARY KEY (event_id, user_id)
            );
            """
        )

        conn.commit()
        conn.close()

    # ---- users ----
    def upsert_user(
        self, user_id: int, username: str, full_name: str, last_chat_id: int
    ) -> None:
        now = int(time.time())
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users(user_id, username, full_name, last_chat_id, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
              username=excluded.username,
              full_name=excluded.full_name,
              last_chat_id=excluded.last_chat_id,
              updated_at=excluded.updated_at
            """,
            (user_id, username or "", full_name or "", last_chat_id, now),
        )
        conn.commit()
        conn.close()

    def get_user(self, user_id: int) -> Optional[sqlite3.Row]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        conn.close()
        return row

    # ---- vocab ----
    def add_word(
        self,
        word: str,
        definition: str,
        translation: str,
        synonyms: list[str],
        antonyms: list[str],
        example: str,
    ) -> int:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO vocab(word, definition, translation, synonyms_json, antonyms_json, example)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                word.strip(),
                definition.strip(),
                translation.strip(),
                json.dumps([s.strip() for s in synonyms if s.strip()]),
                json.dumps([a.strip() for a in antonyms if a.strip()]),
                example.strip(),
            ),
        )
        conn.commit()
        vid = int(cur.lastrowid)
        conn.close()
        return vid

    def count_words(self) -> int:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS c FROM vocab")
        c = int(cur.fetchone()["c"])
        conn.close()
        return c

    def wipe_words(self) -> None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM vocab")
        conn.commit()
        conn.close()

    def _random_vocab_row_for_task(self, task_type: str) -> Optional[sqlite3.Row]:
        conn = self._connect()
        cur = conn.cursor()
        if task_type == "SYNONYM":
            where = "synonyms_json IS NOT NULL AND synonyms_json != '[]'"
        elif task_type == "ANTONYM":
            where = "antonyms_json IS NOT NULL AND antonyms_json != '[]'"
        elif task_type == "TRANSLATE":
            where = "translation IS NOT NULL AND TRIM(translation) != ''"
        elif task_type == "DEFINITION":
            where = "definition IS NOT NULL AND TRIM(definition) != ''"
        elif task_type == "GAPFILL":
            where = "example IS NOT NULL AND TRIM(example) != ''"
        else:
            where = "1=1"

        cur.execute(f"SELECT * FROM vocab WHERE {where} ORDER BY RANDOM() LIMIT 1")
        row = cur.fetchone()
        conn.close()
        return row

    def _random_field_values(
        self, field: str, limit: int, exclude_vocab_id: int
    ) -> list[str]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT {field} AS v
            FROM vocab
            WHERE id != ?
            ORDER BY RANDOM()
            LIMIT ?
            """,
            (exclude_vocab_id, limit * 6),
        )
        rows = cur.fetchall()
        conn.close()
        out: list[str] = []
        for r in rows:
            v = (r["v"] or "").strip()
            if v and v not in out:
                out.append(v)
            if len(out) >= limit:
                break
        return out

    def _random_words(self, limit: int, exclude_vocab_id: int) -> list[str]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT word
            FROM vocab
            WHERE id != ?
            ORDER BY RANDOM()
            LIMIT ?
            """,
            (exclude_vocab_id, limit * 6),
        )
        rows = cur.fetchall()
        conn.close()
        out: list[str] = []
        for r in rows:
            w = (r["word"] or "").strip()
            if w and w not in out:
                out.append(w)
            if len(out) >= limit:
                break
        return out

    def build_question(self, task_type: str, k_options: int = 4) -> Optional[dict[str, Any]]:
        row = self._random_vocab_row_for_task(task_type)
        if not row:
            return None

        vocab_id = int(row["id"])
        word = (row["word"] or "").strip()
        definition = (row["definition"] or "").strip()
        translation = (row["translation"] or "").strip()
        example = (row["example"] or "").strip()
        synonyms = json.loads(row["synonyms_json"] or "[]")
        antonyms = json.loads(row["antonyms_json"] or "[]")

        correct: Optional[str] = None
        distractors: list[str] = []
        prompt: str = ""

        if task_type == "SYNONYM":
            if not synonyms:
                return None
            correct = random.choice(synonyms).strip()
            prompt = f"Pick a <b>synonym</b> for:\n<b>{html.escape(word)}</b>"
            distractors = self._random_words(k_options - 1, exclude_vocab_id=vocab_id)

        elif task_type == "ANTONYM":
            if not antonyms:
                return None
            correct = random.choice(antonyms).strip()
            prompt = f"Pick an <b>antonym</b> for:\n<b>{html.escape(word)}</b>"
            distractors = self._random_words(k_options - 1, exclude_vocab_id=vocab_id)

        elif task_type == "TRANSLATE":
            if not translation:
                return None
            correct = translation
            prompt = f"Pick the <b>translation</b> for:\n<b>{html.escape(word)}</b>"
            distractors = self._random_field_values(
                "translation", k_options - 1, exclude_vocab_id=vocab_id
            )

        elif task_type == "DEFINITION":
            if not definition:
                return None
            correct = definition
            prompt = f"Pick the <b>definition</b> of:\n<b>{html.escape(word)}</b>"
            distractors = self._random_field_values(
                "definition", k_options - 1, exclude_vocab_id=vocab_id
            )

        elif task_type == "GAPFILL":
            if not example:
                return None
            blanked = example
            if word and word.lower() in blanked.lower():
                blanked = blanked.replace(word, "____").replace(word.capitalize(), "____")
            else:
                blanked = blanked + " (____)"
            correct = word
            prompt = f"Fill the blank:\n<blockquote>{html.escape(blanked)}</blockquote>"
            distractors = self._random_words(k_options - 1, exclude_vocab_id=vocab_id)
        else:
            return None

        options = [correct] + [d for d in distractors if d and d != correct]
        options = list(dict.fromkeys([o.strip() for o in options if o and o.strip()]))

        if len(options) < k_options:
            pad = self._random_words(k_options - len(options), exclude_vocab_id=vocab_id)
            for p in pad:
                if p not in options:
                    options.append(p)

        if len(options) < 2:
            return None

        options = options[:k_options]
        random.shuffle(options)
        correct_idx = options.index(correct)

        return {
            "task_type": task_type,
            "vocab_id": vocab_id,
            "prompt": prompt,
            "options": options,
            "correct_idx": correct_idx,
        }

    # ---- events ----
    def create_event(self, minutes: int, phase_seconds: int, *, chat_id: int) -> int:
        now = int(time.time())
        ends_at = now + minutes * 60
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO events(chat_id, started_at, ends_at, phase_seconds, is_active)
            VALUES (?, ?, ?, ?, 1)
            """,
            (chat_id, now, ends_at, phase_seconds),
        )
        conn.commit()
        eid = int(cur.lastrowid)
        conn.close()
        return eid

    def deactivate_events(self, *, chat_id: int) -> None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "UPDATE events SET is_active = 0 WHERE chat_id = ? AND is_active = 1",
            (chat_id,),
        )
        conn.commit()
        conn.close()

    def get_active_event(self, *, chat_id: int) -> Optional[sqlite3.Row]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM events
            WHERE chat_id = ? AND is_active = 1
            ORDER BY id DESC
            LIMIT 1
            """,
            (chat_id,),
        )
        row = cur.fetchone()
        conn.close()
        return row

    def ensure_player(self, event_id: int, user_id: int, *, chat_id: int) -> None:
        now = int(time.time())
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO event_players(event_id, chat_id, user_id, joined_at)
            VALUES (?, ?, ?, ?)
            """,
            (event_id, chat_id, user_id, now),
        )
        cur.execute(
            """
            INSERT OR IGNORE INTO player_prefs(event_id, user_id, auto_queue)
            VALUES (?, ?, 1)
            """,
            (event_id, user_id),
        )
        conn.commit()
        conn.close()

    def remove_player(self, event_id: int, user_id: int) -> None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM event_players WHERE event_id = ? AND user_id = ?",
            (event_id, user_id),
        )
        cur.execute(
            "DELETE FROM player_prefs WHERE event_id = ? AND user_id = ?",
            (event_id, user_id),
        )
        conn.commit()
        conn.close()

    def set_auto_queue(self, event_id: int, user_id: int, auto_queue: int) -> None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO player_prefs(event_id, user_id, auto_queue)
            VALUES (?, ?, ?)
            ON CONFLICT(event_id, user_id) DO UPDATE SET auto_queue=excluded.auto_queue
            """,
            (event_id, user_id, int(auto_queue)),
        )
        conn.commit()
        conn.close()

    def get_auto_queue(self, event_id: int, user_id: int) -> int:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT auto_queue FROM player_prefs WHERE event_id = ? AND user_id = ?",
            (event_id, user_id),
        )
        row = cur.fetchone()
        conn.close()
        return int(row["auto_queue"]) if row else 1

    def record_round_result(
        self, event_id: int, user_id: int, points: int, is_correct: bool
    ) -> None:
        conn = self._connect()
        cur = conn.cursor()
        if is_correct:
            cur.execute(
                """
                UPDATE event_players
                SET points = points + ?, correct = correct + 1
                WHERE event_id = ? AND user_id = ?
                """,
                (points, event_id, user_id),
            )
        else:
            cur.execute(
                """
                UPDATE event_players
                SET points = points + ?, wrong = wrong + 1
                WHERE event_id = ? AND user_id = ?
                """,
                (points, event_id, user_id),
            )
        conn.commit()
        conn.close()

    def record_duel_win_loss(
        self, event_id: int, winner_id: Optional[int], loser_id: Optional[int]
    ) -> None:
        conn = self._connect()
        cur = conn.cursor()
        if winner_id is not None:
            cur.execute(
                "UPDATE event_players SET wins = wins + 1 WHERE event_id = ? AND user_id = ?",
                (event_id, winner_id),
            )
        if loser_id is not None:
            cur.execute(
                "UPDATE event_players SET losses = losses + 1 WHERE event_id = ? AND user_id = ?",
                (event_id, loser_id),
            )
        conn.commit()
        conn.close()

    def leaderboard(self, event_id: int, limit: int = 10) -> list[sqlite3.Row]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT user_id, wins, losses, points, correct, wrong
            FROM event_players
            WHERE event_id = ?
            ORDER BY wins DESC, points DESC, correct DESC
            LIMIT ?
            """,
            (event_id, limit),
        )
        rows = cur.fetchall()
        conn.close()
        return rows

    def leaderboard_all(self, event_id: int) -> list[sqlite3.Row]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT user_id, wins, losses, points, correct, wrong
            FROM event_players
            WHERE event_id = ?
            ORDER BY wins DESC, points DESC, correct DESC
            """,
            (event_id,),
        )
        rows = cur.fetchall()
        conn.close()
        return rows

    def get_player_stats(self, event_id: int, user_id: int) -> Optional[sqlite3.Row]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT user_id, wins, losses, points, correct, wrong
            FROM event_players
            WHERE event_id = ? AND user_id = ?
            """,
            (event_id, user_id),
        )
        row = cur.fetchone()
        conn.close()
        return row


