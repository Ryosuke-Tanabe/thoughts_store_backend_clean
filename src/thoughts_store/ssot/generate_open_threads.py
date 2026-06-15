#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate Open Threads view from SSOT (journal_by_day/**/*.ndjson).

目的（現場の視界回復）:
- log_index（Closed）だけでは「今なにが走っているか」が見えない
- SSOTを物理走査して、Open（phase=endが無い）を視覚化する
- SSOTは正、派生ビューはFull Rebuild可能

出力（--out-dir に出す）:
- open_threads.md      : 人間の視界（最優先）
- open_threads.json    : 機械用
- threads_catalog.json : 全体カタログ（監査/分析用）
- anomalies.md         : 破損/欠損など
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from collections import defaultdict
from datetime import datetime, date


# ---------------------------
# Utilities
# ---------------------------
def parse_date_local(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def compact(s: Any, max_len: int = 160) -> str:
    if s is None:
        return ""
    text = str(s)
    text = " ".join(text.split())
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def iter_ndjson_files(root: Path) -> List[Path]:
    return sorted(root.glob("**/*.ndjson"))


def iter_lines(fp: Path) -> Iterable[Tuple[int, str]]:
    with fp.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if line:
                yield i, line


@dataclass
class Evidence:
    file: str
    line: int


@dataclass
class ThreadState:
    thread_id: str
    has_start: bool = False
    has_end: bool = False

    last_date_local: Optional[str] = None
    last_phase: Optional[str] = None
    last_title: Optional[str] = None

    last_text: Optional[str] = None
    last_summary: Optional[str] = None
    last_next_actions: Optional[List[str]] = None

    start_evidence: Optional[Evidence] = None
    end_evidence: Optional[Evidence] = None
    last_evidence: Optional[Evidence] = None

    counts: Dict[str, int] = None

    def __post_init__(self):
        if self.counts is None:
            self.counts = defaultdict(int)


def extract_thread_event(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    record = obj.get("record", {})
    if record.get("type") != "thread_event":
        return None

    th = record.get("thread", {}) or {}
    thread_id = th.get("thread_id")
    phase = th.get("phase")
    if not thread_id or not phase:
        return None

    return {
        "thread_id": thread_id,
        "phase": phase,
        "date_local": th.get("date_local"),
        "title": th.get("title"),
        "text": record.get("text"),
        "payload": record.get("json") or {},
    }


def extract_summary(payload: Dict[str, Any]) -> Optional[str]:
    for k in ("result_summary", "summary", "thread_summary"):
        v = payload.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def extract_next_actions(payload: Dict[str, Any]) -> Optional[List[str]]:
    # 最小で「人間が見て次が分かる」を優先
    for k in ("next_actions", "followup", "actions"):
        v = payload.get(k)
        if isinstance(v, list):
            items = [compact(x, 200) for x in v if compact(x, 200)]
            return items or None
        if isinstance(v, str) and v.strip():
            return [compact(v, 200)]
    return None


def label_open(last_date: Optional[date], today: date, stale_days: int) -> str:
    if not last_date:
        return "OPEN/UNKNOWN_DATE"
    delta = (today - last_date).days
    return "OPEN/STALE" if delta > stale_days else "OPEN/ACTIVE"


# ---------------------------
# Scan
# ---------------------------
def scan_threads(
    ssot_root: Path,
    since: Optional[date],
    until: Optional[date],
) -> Tuple[Dict[str, ThreadState], List[str]]:
    threads: Dict[str, ThreadState] = {}
    anomalies: List[str] = []

    files = iter_ndjson_files(ssot_root)
    if not files:
        anomalies.append(f"[FATAL] no ndjson found under {ssot_root}")
        return threads, anomalies

    for fp in files:
        for line_no, line in iter_lines(fp):
            try:
                obj = json.loads(line)
            except Exception as e:
                anomalies.append(
                    f"[JSON_DECODE] {fp}:{line_no} {e.__class__.__name__}: {compact(e, 200)}"
                )
                continue

            ev = extract_thread_event(obj)
            if ev is None:
                continue

            d_local = parse_date_local(ev.get("date_local"))
            if since and d_local and d_local < since:
                continue
            if until and d_local and d_local > until:
                continue

            thread_id = ev["thread_id"]
            phase = ev["phase"]
            title = ev.get("title")
            text = ev.get("text")
            payload = ev.get("payload") or {}

            st = threads.get(thread_id)
            if st is None:
                st = ThreadState(thread_id=thread_id)
                threads[thread_id] = st

            st.counts[phase] += 1

            if phase == "start":
                st.has_start = True
                if st.start_evidence is None:
                    st.start_evidence = Evidence(file=str(fp), line=line_no)

            if phase == "end":
                if st.has_end:
                    anomalies.append(
                        f"[MULTI_END] {thread_id} extra end at {fp}:{line_no}"
                    )
                st.has_end = True
                if st.end_evidence is None:
                    st.end_evidence = Evidence(file=str(fp), line=line_no)

            # last event 更新: date_local優先、同日なら後勝ち
            st_last = parse_date_local(st.last_date_local)
            should_update = False

            if st_last is None and ev.get("date_local"):
                should_update = True
            elif d_local is None:
                should_update = False
            else:
                should_update = (st_last is None) or (d_local >= st_last)

            if should_update:
                st.last_date_local = ev.get("date_local")
                st.last_phase = phase
                st.last_title = title
                st.last_text = compact(text, 240) if isinstance(text, str) else None

                s = extract_summary(payload)
                st.last_summary = compact(s, 240) if s else None
                st.last_next_actions = extract_next_actions(payload)

                st.last_evidence = Evidence(file=str(fp), line=line_no)

            # 軽い異常検知
            if phase not in ("start", "update", "end"):
                anomalies.append(
                    f"[UNKNOWN_PHASE] {thread_id} phase={phase} at {fp}:{line_no}"
                )

            if not ev.get("date_local"):
                anomalies.append(
                    f"[MISSING_DATE] {thread_id} phase={phase} at {fp}:{line_no}"
                )

    return threads, anomalies


# ---------------------------
# Writers (human-first)
# ---------------------------
def write_open_threads_md(
    out_path: Path, threads: Dict[str, ThreadState], stale_days: int
) -> None:
    today = date.today()
    open_threads = [st for st in threads.values() if not st.has_end]

    def sort_key(st: ThreadState):
        d = parse_date_local(st.last_date_local)
        return (d is not None, d or date.min, st.thread_id)

    open_threads.sort(key=sort_key, reverse=True)

    lines: List[str] = []
    lines.append("# Open Threads (No phase=end)\n\n")
    lines.append(f"- Generated: {today.isoformat()}\n")
    lines.append(f"- Stale threshold: {stale_days} days\n")
    lines.append(f"- Total open threads: {len(open_threads)}\n\n")

    lines.append(
        "| State | Thread | Last | Phase | Title | Summary/Text | Next actions | Evidence |\n"
    )
    lines.append("|---|---:|---:|---:|---|---|---|---|\n")

    for st in open_threads:
        d = parse_date_local(st.last_date_local)
        state = label_open(d, today, stale_days)
        thread_id = st.thread_id
        last = st.last_date_local or ""
        phase = st.last_phase or ""
        title = compact(st.last_title, 80)

        msg = st.last_summary or st.last_text or ""
        msg = compact(msg, 120)

        na = ""
        if st.last_next_actions:
            na = "; ".join([compact(x, 60) for x in st.last_next_actions[:3]])
            if len(st.last_next_actions) > 3:
                na += " …"

        ev = ""
        if st.last_evidence:
            ev = f"{Path(st.last_evidence.file).as_posix()}:{st.last_evidence.line}"

        lines.append(
            f"| {state} | {thread_id} | {last} | {phase} | {title} | {msg} | {na} | {ev} |\n"
        )

    lines.append("\n## Reading guide\n")
    lines.append(
        "- This is a derived view (Full Rebuildable). Truth remains in SSOT NDJSON.\n"
    )
    lines.append(
        "- Any thread here is *open* strictly because no `phase=end` exists.\n"
    )

    out_path.write_text("".join(lines), encoding="utf-8")


def write_open_threads_json(
    out_path: Path, threads: Dict[str, ThreadState], stale_days: int
) -> None:
    today = date.today()
    open_threads = [st for st in threads.values() if not st.has_end]

    payload: List[Dict[str, Any]] = []
    for st in open_threads:
        d = parse_date_local(st.last_date_local)
        payload.append(
            {
                "thread_id": st.thread_id,
                "status": "open",
                "label": label_open(d, today, stale_days),
                "last_date_local": st.last_date_local,
                "last_phase": st.last_phase,
                "title": st.last_title,
                "last_summary": st.last_summary,
                "last_text": st.last_text,
                "last_next_actions": st.last_next_actions,
                "evidence": {
                    "start": asdict(st.start_evidence) if st.start_evidence else None,
                    "last": asdict(st.last_evidence) if st.last_evidence else None,
                },
                "counts": dict(st.counts),
            }
        )

    payload.sort(
        key=lambda x: (x.get("last_date_local") or "", x["thread_id"]), reverse=True
    )
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def write_threads_catalog_json(out_path: Path, threads: Dict[str, ThreadState]) -> None:
    payload = {}
    for tid, st in threads.items():
        d = asdict(st)
        d["counts"] = dict(st.counts)
        payload[tid] = d
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def write_anomalies_md(out_path: Path, anomalies: List[str]) -> None:
    lines = ["# Anomalies\n\n"]
    if not anomalies:
        lines.append("- None\n")
    else:
        for a in anomalies:
            lines.append(f"- {a}\n")
    out_path.write_text("".join(lines), encoding="utf-8")


# ---------------------------
# CLI
# ---------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Generate Open Threads view from SSOT NDJSON."
    )
    ap.add_argument(
        "--ssot-root",
        required=True,
        help="SSOT root directory (the folder that contains year/month/day ndjson files)",
    )
    ap.add_argument(
        "--out-dir",
        required=True,
        help="Output directory for generated reports",
    )
    ap.add_argument(
        "--since", default=None, help="Filter events since YYYY-MM-DD (optional)"
    )
    ap.add_argument(
        "--until", default=None, help="Filter events until YYYY-MM-DD (optional)"
    )
    ap.add_argument(
        "--stale-days",
        type=int,
        default=14,
        help="Stale threshold in days (for visual label)",
    )
    args = ap.parse_args()

    ssot_root = Path(args.ssot_root).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    since = parse_date_local(args.since) if args.since else None
    until = parse_date_local(args.until) if args.until else None

    threads, anomalies = scan_threads(ssot_root=ssot_root, since=since, until=until)

    # Human-first outputs
    write_open_threads_md(out_dir / "open_threads.md", threads, args.stale_days)
    write_open_threads_json(out_dir / "open_threads.json", threads, args.stale_days)
    write_threads_catalog_json(out_dir / "threads_catalog.json", threads)
    write_anomalies_md(out_dir / "anomalies.md", anomalies)

    total = len(threads)
    open_n = sum(1 for st in threads.values() if not st.has_end)
    closed_n = total - open_n

    print(f"[OK] threads total={total} open={open_n} closed={closed_n}")
    print(f"[OK] wrote: {out_dir / 'open_threads.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
