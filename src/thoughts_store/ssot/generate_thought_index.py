from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Dict, Any, Optional, List

from .safe_ndjson_reader import safe_ndjson_reader


def _as_str(v: Any) -> Optional[str]:
    if isinstance(v, str) and v.strip():
        return v.strip()
    return None


def extract_summary(record: dict) -> Optional[str]:
    # 優先順位は「実在フィールドのみ」
    body = record.get("body")
    if isinstance(body, dict):
        s = _as_str(body.get("summary"))
        if s:
            return s

    rjson = record.get("json")
    if isinstance(rjson, dict):
        ctx = rjson.get("context")
        if isinstance(ctx, dict):
            s = _as_str(ctx.get("summary"))
            if s:
                return s

    payload = record.get("payload")
    if isinstance(payload, dict):
        s = _as_str(payload.get("summary")) or _as_str(payload.get("result_summary"))
        if s:
            return s

    return _as_str(record.get("text"))


def iter_journal_files(root: Path, start: dt.date, end: dt.date) -> List[Path]:
    out: List[Path] = []
    cur = start
    one = dt.timedelta(days=1)
    while cur <= end:
        p = root / f"{cur.year:04d}" / f"{cur.month:02d}" / f"{cur:%Y-%m-%d}.ndjson"
        if p.exists():
            out.append(p)
        cur += one
    return out


def build_thought_index(journal_root: Path, start: dt.date, end: dt.date):
    files = iter_journal_files(journal_root, start, end)
    if not files:
        raise RuntimeError("No journal files found for thought_index")

    for path in files:
        for line_no, obj in safe_ndjson_reader(path):
            record = obj.get("record") if isinstance(obj, dict) else None
            if not isinstance(record, dict):
                continue

            if record.get("type") != "thought":
                continue

            summary = extract_summary(record)
            if not summary:
                continue  # 空は索引しない（推測禁止）

            # thought は thread_id を持たない（T0177 契約）
            yield {
                "v": 1,
                "kind": "thought",
                "date_local": record.get("date_local"),
                "thread_id": None,
                "tags": record.get("tags", []),
                "summary": summary,
                "refs": {
                    "primary": str(path),
                    "line": line_no,
                },
            }


def write_ndjson(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal-root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    args = ap.parse_args()

    journal_root = Path(args.journal_root)
    out_path = Path(args.out)
    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)

    records = list(build_thought_index(journal_root, start, end))
    if not records:
        raise RuntimeError("No thought records indexed")

    write_ndjson(out_path, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
