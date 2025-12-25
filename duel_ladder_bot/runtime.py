from typing import Optional

from .config import DB_PATH, TMA_URL
from .db import DB


db = DB(DB_PATH)

# Set in `commands.post_init()`
BOT_USERNAME: Optional[str] = None

# TMA URL can be dynamic (useful when you use a tunnel like cloudflared/ngrok).
_tma_url_override: Optional[str] = None


def set_tma_url(url: Optional[str]) -> None:
    global _tma_url_override
    url = (url or "").strip()
    _tma_url_override = url.rstrip("/") if url else None


def get_tma_url() -> str:
    return _tma_url_override or TMA_URL


