from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple, Any
import json

# P1を必ず通す
from .safe_ndjson_reader import safe_ndjson_reader


@dataclass
class ThreadState:
    thread_id: str

    title: Optional[str] = None
    status: Optional[str] = None
    last_phase: Optional[str] = None

    # date_local は “補完”せず、観測した範囲で min/max を集約する
    start_date_local: Optional[str] = None
    last_date_local: Optional[str] = None

    summary: Optional[str] = None

    tags: Set[str] = field(default_factory=set)
    canonical_ids: Set[str] = field(default_factory=set)
    generations: Set[int] = field(default_factory=set)
    audit_status: Optional[str] = None

    # 監査・追跡用（最小）
    first_source: Optional[dict] = None  # {"file":..., "line":...}
    last_source: Optional[dict] = None


def _as_str(x: Any) -> Optional[str]:
    return x if isinstance(x, str) and x.strip() else None


def _as_int(x: Any) -> Optional[int]:
    return x if isinstance(x, int) else None


def _normalize_status(x: Any) -> str:
    """
    memory_map schema の enum: active/ended/paused/unknown に正規化する。 :contentReference[oaicite:5]{index=5}
    """
    s = _as_str(x)
    if s is None:
        return "unknown"
    t = s.strip().lower()
    if t in {"active", "in_progress", "inprogress", "running", "open"}:
        return "active"
    if t in {"ended", "done", "closed", "complete", "completed"}:
        return "ended"
    if t in {"paused", "hold", "on_hold"}:
        return "paused"
    return "unknown"


def _update_min_max_date(st: ThreadState, date_local: Optional[str]) -> None:
    if date_local is None:
        return
    # safe_ndjson_reader 側で YYYY-MM-DD 実在日付を検証済み（thread_event 最低限） :contentReference[oaicite:6]{index=6}
    if st.start_date_local is None or date_local < st.start_date_local:
        st.start_date_local = date_local
    if st.last_date_local is None or st.last_date_local < date_local:
        st.last_date_local = date_local


def _extract_summary(record: dict) -> Optional[str]:
    """
    schema では summary が必須かつ minLength 1。 :contentReference[oaicite:7]{index=7}
    推測補完はせず、イベント内の既存フィールドからのみ採用する。
    優先順位:
      1) record.json.context.summary
      2) record.text
    """
    rjson = record.get("json")
    if isinstance(rjson, dict):
        ctx = rjson.get("context")
        if isinstance(ctx, dict):
            s = _as_str(ctx.get("summary"))
            if s:
                return s
    s = _as_str(record.get("text"))
    if s:
        return s
    return None


def _iter_thread_events_from_file(path: Path):
    # safe_ndjson_reader は (line_no, obj) を返す :contentReference[oaicite:1]{index=1}
    for line_no, obj in safe_ndjson_reader(path, enforce_event_minimum=True):
        record = obj.get("record")
        if not isinstance(record, dict):
            continue

        # thread_event 限定
        rtype = record.get("type") or obj.get("type")
        if rtype != "thread_event":
            continue

        thread = record.get("thread")
        if not isinstance(thread, dict):
            continue

        tid = thread.get("thread_id")
        if not isinstance(tid, str) or not tid.strip():
            # P1で落ちる想定だが、二重防御
            continue

        yield {
            "file": str(path),
            "line": line_no,
            "record": record,
            "thread": thread,
        }


def build_thread_states(event_files: Iterable[Path]) -> Dict[str, ThreadState]:
    states: Dict[str, ThreadState] = {}

    for path in event_files:
        for ev in _iter_thread_events_from_file(path):
            thread = ev["thread"]
            record = ev["record"]
            tid = thread["thread_id"].strip()

            st = states.get(tid)
            if st is None:
                st = ThreadState(thread_id=tid)
                states[tid] = st

            src = {"file": ev["file"], "line": ev["line"]}
            if st.first_source is None:
                st.first_source = src
            st.last_source = src

            # 取りうる情報だけ機械的に反映（欠損補完はしない）
            # 先勝ち/後勝ちルールは最小で「後勝ち」に寄せる（最後の記録が最新という前提）
            title = _as_str(thread.get("title"))
            if title is not None:
                st.title = title

            last_phase = _as_str(thread.get("phase"))
            if last_phase is not None:
                st.last_phase = last_phase

            st.status = _normalize_status(thread.get("status"))

            date_local = _as_str(thread.get("date_local"))
            _update_min_max_date(st, date_local)

            # summary（イベント内の既存文字列のみから採用）
            s = _extract_summary(record)
            if s is not None:
                st.summary = s

            # record側のメタ
            tags = record.get("tags")
            if isinstance(tags, list):
                for t in tags:
                    ts = _as_str(t)
                    if ts is not None:
                        st.tags.add(ts)

            canonical_id = _as_str(record.get("canonical_id"))
            if canonical_id is not None:
                st.canonical_ids.add(canonical_id)

            gen = _as_int(record.get("generation"))
            if gen is not None:
                st.generations.add(gen)

            audit_status = _as_str(record.get("audit_status"))
            if audit_status is not None:
                st.audit_status = audit_status

    return states


def to_memory_map_records(states: Dict[str, ThreadState]) -> List[dict]:
    # memory_map.ndjson へ出す形（schema準拠）
    # 必須: v, thread_id, title, start_date_local, last_date_local, status, last_phase, summary, refs.primary :contentReference[oaicite:8]{index=8}
    out: List[dict] = []
    for tid, st in states.items():
        # Fail-Fast（派生でも「壊れたスナップショット」を出さない）
        if st.title is None:
            raise RuntimeError(
                f"memory_map requires title but missing: {tid} (last_source={st.last_source})"
            )
        if st.start_date_local is None or st.last_date_local is None:
            raise RuntimeError(
                f"memory_map requires start/last_date_local but missing: {tid} (last_source={st.last_source})"
            )
        if st.last_phase is None:
            raise RuntimeError(
                f"memory_map requires last_phase but missing: {tid} (last_source={st.last_source})"
            )
        if st.summary is None:
            raise RuntimeError(
                f"memory_map requires summary but missing: {tid} (last_source={st.last_source})"
            )
        if (
            st.last_source is None
            or not isinstance(st.last_source.get("file"), str)
            or not st.last_source.get("file")
        ):
            raise RuntimeError(
                f"memory_map requires refs.primary but missing last_source.file: {tid} (last_source={st.last_source})"
            )

        refs = {
            "primary": st.last_source[
                "file"
            ],  # パスを一次参照として固定（推測リンク生成を避ける）
            "last_event": f'{st.last_source["file"]}:{st.last_source["line"]}',
        }

        out.append(
            {
                "v": 1,
                "thread_id": tid,
                "title": st.title,
                "status": st.status,
                "last_phase": st.last_phase,
                "start_date_local": st.start_date_local,
                "last_date_local": st.last_date_local,
                "summary": st.summary,
                "tags": sorted(st.tags),
                "refs": refs,
                # 以下は schema 上 additionalProperties:true なので保持してOK :contentReference[oaicite:9]{index=9}
                "canonical_ids": sorted(st.canonical_ids),
                "generations": sorted(st.generations),
                "audit_status": st.audit_status,
                "first_source": st.first_source,  # 任意：監査トレース用
                "last_source": st.last_source,  # 任意：監査トレース用
            }
        )
    # 出力順を固定（監査・diffのため）
    out.sort(key=lambda r: r["thread_id"])
    return out


def write_ndjson(path: Path, records: List[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
