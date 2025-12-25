import logging
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    # Optional dependency; env vars can be provided by the environment directly.
    pass

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
log = logging.getLogger("duel_ladder_bot")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
DB_PATH = os.environ.get("DB_PATH", "duel_ladder.sqlite3").strip()

# Telegram Mini App (TMA)
# Example: https://your-domain.example (must be HTTPS in real Telegram clients)
TMA_URL = os.environ.get("TMA_URL", "").strip().rstrip("/")
# Used for the admin panel in the TMA (matches duel_ladder_bot/tma_server.py)
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "classroom2024").strip()

ADMIN_IDS: set[int] = set()
_admin_raw = os.environ.get("ADMIN_IDS", "").strip()
if _admin_raw:
    for part in _admin_raw.split(","):
        part = part.strip()
        if part:
            ADMIN_IDS.add(int(part))

# Global (DM-first): store the event as chat_id=0
GLOBAL_CHAT_ID = 0

DEFAULT_PHASE_SECONDS = 120
DEFAULT_ROUNDS_PER_DUEL = 6
DEFAULT_ROUND_SECONDS = 12

# pacing controls
REST_BETWEEN_DUELS_SECONDS = 7
PRE_DUEL_COUNTDOWN_SECONDS = 5

TASK_TYPES = ["SYNONYM", "ANTONYM", "TRANSLATE", "DEFINITION", "GAPFILL"]


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


