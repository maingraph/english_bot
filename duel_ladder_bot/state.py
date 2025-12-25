from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class GlobalEventState:
    event_id: int
    ends_at: int
    phase_seconds: int
    task_idx: int = 0
    queue: list[int] = field(default_factory=list)
    phase_job: Any = None
    end_job: Any = None


@dataclass
class DuelState:
    duel_id: int
    event_id: int
    p1_id: int
    p2_id: int
    task_type: str
    rounds_total: int
    round_seconds: int
    round_idx: int = 0
    p1_score: int = 0
    p2_score: int = 0
    active_question: Optional[dict] = None
    round_started_at: float = 0.0
    answers: dict[int, dict] = field(default_factory=dict)
    msg_id_by_user: dict[int, int] = field(default_factory=dict)
    timer_job: Any = None
    is_done: bool = False


global_event: Optional[GlobalEventState] = None
active_duels: dict[int, DuelState] = {}
user_to_duel: dict[int, int] = {}

_duel_seq = 4000


def next_duel_id() -> int:
    global _duel_seq
    _duel_seq += 1
    return _duel_seq


