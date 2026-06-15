from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import datetime
import json
import re
from typing import Iterator, Optional, Any, Tuple

# SSOT (events.ndjson) に混入してはいけない“非イベント文字列”やデバッグ痕跡。
# ※順序・語彙を含めて契約として凍結する。
FORBIDDEN_TOKENS = [
    "\ufeff",  # BOM
    "START_LOG_JSON=",
    "Next JSON Wait...",
    "[DEBUG]",
    "DEBUG:",
]
FORBIDDEN_PATTERN = re.compile("|".join(map(re.escape, FORBIDDEN_TOKENS)))

ELLIPSIS_VALUES = {"...", "…", "・・・"}


@dataclass(frozen=True)
class NdjsonSource:
    file: str  # e.g. ".../journal_by_day/2026/01/2026-01-23.ndjson"
    line_no: int  # 1-indexed


@dataclass
class NdjsonReadError(Exception):
    # 契約：機械が解析できるよう固定する（E番号とルール名は分離）。
    code: str  # e.g. "E1101"
    rule: str  # e.g. "NDJSON_EMPTY_LINE"
    where: str  # e.g. "line", "json.loads", "record.thread.date_local"
    what: str  # human readable
    source: NdjsonSource
    snippet: Optional[str] = None
    pos: Optional[int] = None  # JSON decode position (0-index)
    column: Optional[int] = None  # 1-indexed column (best-effort)

    def __post_init__(self) -> None:
        # Exceptionの標準挙動（args）を安定させる
        self.args = (str(self),)

    def __str__(self) -> str:
        loc = f"{self.source.file}:{self.source.line_no}"
        return f"[{self.code} {self.rule}] {self.what} @ {loc}"


def _safe_snippet(s: str, max_len: int = 180) -> str:
    s = s.replace("\r", "\\r").replace("\n", "\\n")
    return s[:max_len] + ("..." if len(s) > max_len else "")


def _calc_column_from_pos(line: str, pos: Optional[int]) -> Optional[int]:
    if pos is None:
        return None
    # posは0-index。columnは1-indexで返す。
    try:
        return int(pos) + 1
    except Exception:
        return None


def _raise(
    *,
    code: str,
    rule: str,
    where: str,
    what: str,
    source: NdjsonSource,
    raw_line: str,
    pos: Optional[int] = None,
    column: Optional[int] = None,
) -> None:
    raise NdjsonReadError(
        code=code,
        rule=rule,
        where=where,
        what=what,
        source=source,
        snippet=_safe_snippet(raw_line),
        pos=pos,
        column=column,
    )


def _contains_exact_ellipsis_value(x: Any) -> bool:
    if isinstance(x, str):
        return x.strip() in ELLIPSIS_VALUES
    if isinstance(x, dict):
        return any(_contains_exact_ellipsis_value(v) for v in x.values())
    if isinstance(x, list):
        return any(_contains_exact_ellipsis_value(v) for v in x)
    return False


def safe_ndjson_reader(
    file_path: Path, *, enforce_event_minimum: bool = True
) -> Iterator[Tuple[int, dict]]:
    """
    Fail-Fast NDJSON reader (SSOT events):
    - 1行ずつ読み取り
    - 1行でも壊れていたら即停止（例外送出）
    - file + line_no を必ずエラーに含める
    - エラー契約は NdjsonReadError に固定（E1xxx）
    """
    try:
        with file_path.open("r", encoding="utf-8") as f:
            for i, raw in enumerate(f, start=1):
                src = NdjsonSource(file=str(file_path), line_no=i)

                # 改行だけを落とし、他の空白はそのまま診断できるよう保持
                line = raw.rstrip("\n")

                if not line.strip():
                    _raise(
                        code="E1101",
                        rule="NDJSON_EMPTY_LINE",
                        where="line",
                        what="empty line",
                        source=src,
                        raw_line=line,
                    )

                m = FORBIDDEN_PATTERN.search(line)
                if m:
                    tok = m.group(0)
                    col = m.start()
                    _raise(
                        code="E1105",
                        rule="NDJSON_FORBIDDEN_TOKEN",
                        where="line",
                        what=f'forbidden token detected: "{tok}"',
                        source=src,
                        raw_line=line,
                        pos=col,
                        column=col + 1,
                    )

                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as e:
                    rule = (
                        "NDJSON_EXTRA_DATA"
                        if "Extra data" in str(e)
                        else "NDJSON_JSON_DECODE_ERROR"
                    )
                    _raise(
                        code="E1103" if rule == "NDJSON_JSON_DECODE_ERROR" else "E1104",
                        rule=rule,
                        where="json.loads",
                        what=str(e),
                        source=src,
                        raw_line=line,
                        pos=getattr(e, "pos", None),
                        column=_calc_column_from_pos(line, getattr(e, "pos", None)),
                    )

                if not isinstance(obj, dict):
                    _raise(
                        code="E1102",
                        rule="NDJSON_NOT_OBJECT",
                        where="json",
                        what=f"got {type(obj).__name__}",
                        source=src,
                        raw_line=line,
                    )

                # 省略記号そのもの（値が完全一致）だけ禁止
                if _contains_exact_ellipsis_value(obj):
                    _raise(
                        code="E1106",
                        rule="NDJSON_FORBIDDEN_ELLIPSIS",
                        where="json value",
                        what="forbidden ellipsis value detected: one of {..., …, ・・・}",
                        source=src,
                        raw_line=line,
                    )

                if enforce_event_minimum:
                    _validate_event_minimum(obj, src, line)

                yield i, obj

    except UnicodeDecodeError as e:
        src = NdjsonSource(file=str(file_path), line_no=0)
        raise NdjsonReadError(
            code="E1100",
            rule="NDJSON_DECODE_ERROR",
            where="file",
            what=str(e),
            source=src,
            snippet=None,
            pos=None,
            column=None,
        ) from e


def _validate_event_minimum(obj: dict, src: NdjsonSource, raw_line: str) -> None:
    # ここは“最小限”。P2で厳格な整合（phase例外など）をやる。
    record = obj.get("record")
    if record is None:
        _raise(
            code="E1110",
            rule="EVENT_MISSING_RECORD",
            where="record",
            what="record is missing",
            source=src,
            raw_line=raw_line,
        )
    if not isinstance(record, dict):
        _raise(
            code="E1111",
            rule="EVENT_RECORD_NOT_OBJECT",
            where="record",
            what=f"got {type(record).__name__}",
            source=src,
            raw_line=raw_line,
        )

    rtype = record.get("type")
    if not isinstance(rtype, str) or not rtype.strip():
        _raise(
            code="E1116",
            rule="EVENT_TYPE_MISSING",
            where="record.type",
            what="record.type is missing/empty",
            source=src,
            raw_line=raw_line,
        )

    # さらに硬くするなら既知集合を固定（仕様として凍結）
    # T0177: thought を第一級の記録単位として許可する（thread は要求しない）
    KNOWN_TYPES = {"thread_event", "thought"}  # 必要に応じて追加
    if rtype not in KNOWN_TYPES:
        _raise(
            code="E1117",
            rule="EVENT_TYPE_UNKNOWN",
            where="record.type",
            what=f"unknown record.type: {rtype!r}",
            source=src,
            raw_line=raw_line,
        )

    thread = record.get("thread")
    if thread is not None and not isinstance(thread, dict):
        _raise(
            code="E1112",
            rule="EVENT_THREAD_NOT_OBJECT",
            where="record.thread",
            what=f"got {type(thread).__name__}",
            source=src,
            raw_line=raw_line,
        )

    # thread_event だけは最低限チェック（他 type は将来拡張）
    if rtype == "thread_event":
        if thread is None:
            _raise(
                code="E1118",
                rule="EVENT_THREAD_MISSING",
                where="record.thread",
                what="thread is missing for thread_event",
                source=src,
                raw_line=raw_line,
            )

        if not isinstance(thread, dict):
            _raise(
                code="E1112",
                rule="EVENT_THREAD_NOT_OBJECT",
                where="record.thread",
                what=f"got {type(thread).__name__}",
                source=src,
                raw_line=raw_line,
            )

        if isinstance(thread, dict):
            tid = thread.get("thread_id")
            if not isinstance(tid, str) or not tid.strip():
                _raise(
                    code="E1113",
                    rule="EVENT_THREAD_ID_MISSING",
                    where="record.thread.thread_id",
                    what="thread_id missing/empty",
                    source=src,
                    raw_line=raw_line,
                )

            phase = thread.get("phase")
            if phase is not None and phase not in ("start", "update", "end"):
                _raise(
                    code="E1114",
                    rule="EVENT_PHASE_INVALID",
                    where="record.thread.phase",
                    what=f"invalid phase: {phase!r}",
                    source=src,
                    raw_line=raw_line,
                )

            dl = thread.get("date_local")
            if isinstance(dl, str):
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", dl):
                    _raise(
                        code="E1115",
                        rule="EVENT_DATE_LOCAL_INVALID",
                        where="record.thread.date_local",
                        what=f"invalid date format: {dl!r}",
                        source=src,
                        raw_line=raw_line,
                    )
                try:
                    datetime.date.fromisoformat(dl)
                except ValueError:
                    _raise(
                        code="E1115",
                        rule="EVENT_DATE_LOCAL_INVALID",
                        where="record.thread.date_local",
                        what=f"nonexistent date: {dl!r}",
                        source=src,
                        raw_line=raw_line,
                    )
