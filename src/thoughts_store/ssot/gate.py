from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import datetime
import json
import os
import re
import tempfile
from typing import Iterable, Callable, Any


# --- Error Contract (P3) ---
@dataclass
class SsotWriteError(Exception):
    code: str  # e.g. "E1301"
    rule: str  # e.g. "WRITE_SCHEMA_INVALID"
    where: str  # e.g. "events[3].record.thread.date_local"
    what: str
    file: str

    def __post_init__(self) -> None:
        self.args = (str(self),)

    def __str__(self) -> str:
        return f"[{self.code} {self.rule}] {self.what} @ {self.file} ({self.where})"


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _assert_real_date(date_str: str, *, where: str, file: Path) -> None:
    if not DATE_RE.fullmatch(date_str):
        raise SsotWriteError(
            code="E1310",
            rule="DATE_FORMAT_INVALID",
            where=where,
            what=f"invalid date format: {date_str!r}",
            file=str(file),
        )
    try:
        datetime.date.fromisoformat(date_str)
    except ValueError:
        raise SsotWriteError(
            code="E1311",
            rule="DATE_NONEXISTENT",
            where=where,
            what=f"nonexistent date: {date_str!r}",
            file=str(file),
        )


# ---- Schema validation hooks (replace with jsonschema/pydantic) ----
def _validate_schema_event(obj: dict, *, idx: int, file: Path) -> None:
    """
    events行のスキーマ検証をここに統合する（P3）。
    - 例：required keys, types, enum etc.
    - format:"date" はこの層で実在日付も必須化
    """
    record = obj.get("record")
    if not isinstance(record, dict):
        raise SsotWriteError(
            "E1301",
            "WRITE_SCHEMA_INVALID",
            f"events[{idx}].record",
            "record must be object",
            str(file),
        )

    rtype = record.get("type")

    # --- thread_event: date_local の実在日付を厳格化 ---
    if rtype == "thread_event":
        thread = record.get("thread")
        if not isinstance(thread, dict):
            raise SsotWriteError(
                "E1302",
                "WRITE_SCHEMA_INVALID",
                f"events[{idx}].record.thread",
                "thread must be object",
                str(file),
            )
        dl = thread.get("date_local")
        if isinstance(dl, str):
            _assert_real_date(
                dl, where=f"events[{idx}].record.thread.date_local", file=file
            )

    # --- thought: 最小契約（意味解釈なし）---
    if rtype == "thought":
        text = record.get("text")
        if not isinstance(text, str) or not text.strip():
            raise SsotWriteError(
                "E1303",
                "WRITE_SCHEMA_INVALID",
                f"events[{idx}].record.text",
                "thought record.text must be non-empty string",
                str(file),
            )

        tags = record.get("tags")
        if (
            not isinstance(tags, list)
            or len(tags) < 1
            or not all(isinstance(t, str) and t.strip() for t in tags)
        ):
            raise SsotWriteError(
                "E1305",
                "WRITE_SCHEMA_INVALID",
                f"events[{idx}].record.tags",
                "thought record.tags must be list[str] with >= 1 non-empty item",
                str(file),
            )

        # thread は「持たない」方針だが、強制は Launcher 側に置く（ここでは形だけ）
        thread = record.get("thread")
        if thread is not None and not isinstance(thread, dict):
            raise SsotWriteError(
                "E1304",
                "WRITE_SCHEMA_INVALID",
                f"events[{idx}].record.thread",
                "thread must be object when provided",
                str(file),
            )

    _scan_and_validate_dates(obj, file=file, where_prefix=f"events[{idx}]")


def _validate_schema_memory_map(obj: dict, *, idx: int, file: Path) -> None:
    """
    memory_map行のスキーマ検証をここに統合する（P3）。
    - format:"date" を含むなら実在日付をここで検証
    """
    # 例：date_local があるなら検証
    dl = obj.get("date_local")
    if isinstance(dl, str):
        _assert_real_date(dl, where=f"memory_map[{idx}].date_local", file=file)
    _scan_and_validate_dates(obj, file=file, where_prefix=f"memory_map[{idx}]")


def _atomic_write_lines(path: Path, lines: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = None
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
        )
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            for line in lines:
                f.write(line)
                if not line.endswith("\n"):
                    f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)  # atomic on same filesystem
        tmp_path = None
    finally:
        if tmp_path is not None:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def write_events_atomic(events_path: Path, new_events: list[dict]) -> None:
    # 1) validate all (Fail-Fast, write前)
    for i, ev in enumerate(new_events):
        if not isinstance(ev, dict):
            raise SsotWriteError(
                "E1300",
                "WRITE_NOT_OBJECT",
                f"events[{i}]",
                f"got {type(ev).__name__}",
                str(events_path),
            )
        _validate_schema_event(ev, idx=i, file=events_path)

    # 2) load old + append in-memory (still no write)
    existing_lines: list[str] = []
    if events_path.exists():
        existing_lines = events_path.read_text(encoding="utf-8").splitlines()

    out_lines = existing_lines + [
        json.dumps(ev, ensure_ascii=False, separators=(",", ":")) for ev in new_events
    ]

    # 3) atomic replace (部分成功禁止)
    _atomic_write_lines(events_path, out_lines)


def write_memory_map_atomic(memory_map_path: Path, new_rows: list[dict]) -> None:
    for i, row in enumerate(new_rows):
        if not isinstance(row, dict):
            raise SsotWriteError(
                "E1320",
                "WRITE_NOT_OBJECT",
                f"memory_map[{i}]",
                f"got {type(row).__name__}",
                str(memory_map_path),
            )
        _validate_schema_memory_map(row, idx=i, file=memory_map_path)

    existing_lines: list[str] = []
    if memory_map_path.exists():
        existing_lines = memory_map_path.read_text(encoding="utf-8").splitlines()

    out_lines = existing_lines + [
        json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in new_rows
    ]
    _atomic_write_lines(memory_map_path, out_lines)


def append_event_and_derived(
    *,
    events_path: Path,
    memory_map_path: Path,
    event: dict,
    expand_event_to_memory_map_rows: Callable[[dict], list[dict]],
) -> None:
    """
    SSOT書き込みの唯一入口（推奨）。
    - event を write前に validate
    - event から memory_map rows を生成（副作用なし）
    - rows を write前に validate
    - 両方 atomic replace（部分成功確率を最小化）
    """
    rows = expand_event_to_memory_map_rows(event)

    # validate + write (order is explicit)
    write_events_atomic(events_path, [event])
    write_memory_map_atomic(memory_map_path, rows)


def _scan_and_validate_dates(obj: Any, *, file: Path, where_prefix: str) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            w = f"{where_prefix}.{k}" if where_prefix else k
            if isinstance(v, str) and (
                k.endswith("_date") or k.endswith("_date_local") or k == "date_local"
            ):
                _assert_real_date(v, where=w, file=file)
            else:
                _scan_and_validate_dates(v, file=file, where_prefix=w)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _scan_and_validate_dates(v, file=file, where_prefix=f"{where_prefix}[{i}]")
