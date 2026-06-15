#!/usr/bin/env python3
# search.py
import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional


@dataclass(frozen=True)
class Hit:
    date: str
    file: str
    line_no: int
    thread_id: Optional[str]
    text: str
    raw: dict


def date_from_filename(path: Path) -> str:
    m = re.search(r"\d{4}-\d{2}-\d{2}", path.stem)
    return m.group(0) if m else path.stem


def iter_ndjson_files(root: Path) -> Iterator[Path]:
    if not root.exists():
        raise FileNotFoundError(f"root not found: {root}")

    files = [p for p in root.rglob("*.ndjson") if p.is_file()]
    files.sort(key=lambda p: date_from_filename(p))
    for p in files:
        yield p


def safe_json_loads(line: str) -> Optional[dict]:
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def extract_hits_by_query(root: Path, query: str, *, limit: int) -> List[Hit]:
    hits: List[Hit] = []
    for file_path in iter_ndjson_files(root):
        date = date_from_filename(file_path)
        with file_path.open("r", encoding="utf-8") as f:
            for idx, line in enumerate(f, start=1):
                rec = safe_json_loads(line)
                if not rec:
                    continue
                record = rec.get("record", {})
                if not isinstance(record, dict):
                    continue

                text = record.get("text", "") or ""
                if not isinstance(text, str):
                    continue

                if query in text:
                    thread = record.get("thread", {})
                    thread_id = (
                        thread.get("thread_id") if isinstance(thread, dict) else None
                    )
                    hits.append(
                        Hit(
                            date=date,
                            file=str(file_path),
                            line_no=idx,
                            thread_id=thread_id,
                            text=text,
                            raw=rec,
                        )
                    )
                    if len(hits) >= limit:
                        return hits
    return hits


def extract_records_by_thread(root: Path, thread_id: str, *, limit: int) -> List[Hit]:
    out: List[Hit] = []
    for file_path in iter_ndjson_files(root):
        date = date_from_filename(file_path)
        with file_path.open("r", encoding="utf-8") as f:
            for idx, line in enumerate(f, start=1):
                rec = safe_json_loads(line)
                if not rec:
                    continue
                record = rec.get("record", {})
                if not isinstance(record, dict):
                    continue
                thread = record.get("thread", {})
                if not isinstance(thread, dict):
                    continue

                if thread.get("thread_id") != thread_id:
                    continue

                text = record.get("text", "") or ""
                if not isinstance(text, str):
                    text = ""

                out.append(
                    Hit(
                        date=date,
                        file=str(file_path),
                        line_no=idx,
                        thread_id=thread_id,
                        text=text,
                        raw=rec,
                    )
                )
                if len(out) >= limit:
                    return out
    return out


DEFAULT_PROMPT_GREP = (
    "以下はSSOT（journal_by_day/*.ndjson）から抽出したログ断片です。\n"
    "断片間の関係（同一論点・同一判断・因果）を推定し、当時の決定事項/未決事項/次の一手を箇条書きで出してください。"
)

DEFAULT_PROMPT_THREAD = (
    "以下は同一thread_idの時系列ログです。\n"
    "目的/制約/決定/未完了を復元し、今このスレッドを再開するなら『次にやる1手』を具体的に提案してください。"
)


def render_grep(hits: List[Hit]) -> str:
    lines: List[str] = []
    for i, h in enumerate(hits, start=1):
        lines.append(f"--- HIT {i} ---")
        lines.append(f"date: {h.date}")
        lines.append(f"file: {h.file}")
        lines.append(f"line: {h.line_no}")
        if h.thread_id:
            lines.append(f"thread_id: {h.thread_id}")
        lines.append("")
        lines.append(h.text)
        lines.append("")
    lines.append("=== PROMPT ===")
    lines.append(DEFAULT_PROMPT_GREP)
    return "\n".join(lines)


def render_thread(records: List[Hit]) -> str:
    records = sorted(records, key=lambda h: (h.date, h.line_no))
    tid = records[0].thread_id if records else None

    lines: List[str] = [f"# THREAD: {tid or '(unknown)'}", ""]
    for h in records:
        lines.append(f"- {h.date} {os.path.basename(h.file)}:{h.line_no}")
        lines.append(h.text)
        lines.append("")
    lines.append("=== PROMPT ===")
    lines.append(DEFAULT_PROMPT_THREAD)
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--root", required=True, help="journal_by_day directory (recursively scanned)"
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--query", help="substring query against record.text")
    g.add_argument("--thread", help="thread_id to assemble")
    ap.add_argument("--limit", type=int, default=200, help="max hits/records")
    args = ap.parse_args()

    root = Path(args.root)

    if args.query:
        hits = extract_hits_by_query(root, args.query, limit=args.limit)
        print(render_grep(hits))
    else:
        records = extract_records_by_thread(
            root, args.thread, limit=max(args.limit, 5000)
        )
        print(render_thread(records))


if __name__ == "__main__":
    main()
