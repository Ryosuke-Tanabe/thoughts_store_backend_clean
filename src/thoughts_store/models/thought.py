# src/thoughts_store/models/thought.py
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from thoughts_store.settings import SAVE_TZ


def _now_iso():
    if SAVE_TZ.upper() == "UTC":
        return datetime.now(timezone.utc).isoformat()
    return datetime.now(ZoneInfo(SAVE_TZ)).isoformat()


@dataclass
class Thought:
    id: str
    content: str
    author: str
    created_at: str = field(default_factory=_now_iso)
    tags: list[str] = field(default_factory=list)
    prev_hash: str | None = None
    record_hash: str | None = None
    signature: str | None = None
    source_ref: dict | None = None

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        if self.source_ref is None:
            d["source_ref"] = {"origin": "drive"}
        return d
