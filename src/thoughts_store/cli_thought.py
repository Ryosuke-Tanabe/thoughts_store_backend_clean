from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import jsonschema

from thoughts_store.ssot.gate import write_events_atomic
from thoughts_store.ssot.safe_ndjson_reader import safe_ndjson_reader


# ---------
# helpers
# ---------


def _today_local() -> str:
    return dt.date.today().isoformat()


def _read_text_arg_or_stdin(text_arg: Optional[str]) -> str:
    if text_arg is not None and text_arg.strip():
        return text_arg.strip()
    # stdin から読む（複数行可）
    import sys

    data = sys.stdin.read()
    if not data or not data.strip():
        raise SystemExit("E: thought text is empty. Provide --text or pipe stdin.")
    return data.strip()


def _parse_tags_csv(tags_csv: Optional[str]) -> List[str]:
    if tags_csv is None or not tags_csv.strip():
        return []
    parts = [p.strip() for p in tags_csv.split(",")]
    return [p for p in parts if p]


def _journal_path(journal_root: Path, date_local: str) -> Path:
    d = dt.date.fromisoformat(date_local)
    return journal_root / f"{d.year:04d}" / f"{d.month:02d}" / f"{d:%Y-%m-%d}.ndjson"


def _find_date_range_from_files(journal_root: Path) -> Tuple[dt.date, dt.date]:
    """
    journal_by_day 以下を走査して最小/最大の日付を推定する。
    重すぎる場合は、CLI引数で start/end を固定して回避可能。
    """
    files = list(journal_root.rglob("*.ndjson"))
    dates: List[dt.date] = []
    for p in files:
        try:
            # .../YYYY/MM/YYYY-MM-DD.ndjson
            name = p.stem  # YYYY-MM-DD
            dates.append(dt.date.fromisoformat(name))
        except Exception:
            continue
    if not dates:
        raise SystemExit("E: No journal files found under --journal-root")
    return min(dates), max(dates)


def _validate_schema_preflight(event: Dict[str, Any], schema_path: Path) -> None:
    """
    v1.5.0: Schema Preflight は必須。
    Gate に渡す前に必ず Schema 検証で検疫する。
    """
    if not schema_path.exists():
        raise SystemExit(f"E: schema file not found: {schema_path}")

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(instance=event, schema=schema)
    except jsonschema.ValidationError as e:
        # できるだけ短く・位置付きで返す
        path = ".".join([str(x) for x in e.path]) if e.path else "(root)"
        raise SystemExit(f"SchemaError at {path}: {e.message}") from e


def _build_thoughts_no_thread_md(
    *,
    journal_root: Path,
    out_md: Path,
    start: dt.date,
    end: dt.date,
) -> List[str]:
    """
    Full Rebuild 前提の派生物生成。
    indexes/thoughts_no_thread.md を作る（thread_id なし thought のみ）。
    """
    out_md.parent.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    lines.append("# thoughts_no_thread")
    lines.append("")
    lines.append(f"- range: {start.isoformat()} .. {end.isoformat()}")
    lines.append("")

    cur = start
    one = dt.timedelta(days=1)
    count = 0

    while cur <= end:
        p = (
            journal_root
            / f"{cur.year:04d}"
            / f"{cur.month:02d}"
            / f"{cur:%Y-%m-%d}.ndjson"
        )
        if p.exists():
            for line_no, obj in safe_ndjson_reader(p):
                record = obj.get("record") if isinstance(obj, dict) else None
                if not isinstance(record, dict):
                    continue
                if record.get("type") != "thought":
                    continue

                # NoThread 条件：record.thread が存在しない（or None）
                if record.get("thread") is not None:
                    continue

                text = record.get("text")
                if not isinstance(text, str) or not text.strip():
                    continue

                title = record.get("title")
                if not isinstance(title, str) or not title.strip():
                    title = "(no title)"

                tags = record.get("tags")
                if not isinstance(tags, list):
                    tags = []
                tags_str = ", ".join(
                    [t for t in tags if isinstance(t, str) and t.strip()]
                )

                summary = text.strip().splitlines()[0]
                if len(summary) > 120:
                    summary = summary[:117] + "..."

                date_local = record.get("date_local")
                if not isinstance(date_local, str) or not date_local.strip():
                    date_local = cur.isoformat()

                lines.append(f"## {title}")
                lines.append(f"- date_local: {date_local}")
                lines.append(f"- tags: {tags_str if tags_str else '(none)'}")
                lines.append(f"- refs: {p}#L{line_no}")
                lines.append("")
                lines.append(summary)
                lines.append("")
                count += 1
        cur += one

    if count == 0:
        lines.append("_No thoughts found in range._")
        lines.append("")

    out_md.write_text("\n".join(lines), encoding="utf-8")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal-root", required=True, help="journal_by_day root")
    ap.add_argument("--schema", required=True, help="SSOT event JSON schema path")
    ap.add_argument("--author", required=True)
    ap.add_argument("--date-local", default=_today_local())
    ap.add_argument("--text", default=None, help="thought body; if omitted, read stdin")
    ap.add_argument("--title", default=None)
    ap.add_argument(
        "--tags", default=None, help='comma separated, e.g. "Thought,Capture,NoThread"'
    )
    ap.add_argument("--quick", action="store_true", help="apply Quick Capture defaults")
    ap.add_argument("--rebuild-start", default=None, help="YYYY-MM-DD (optional)")
    ap.add_argument("--rebuild-end", default=None, help="YYYY-MM-DD (optional)")
    ap.add_argument("--out-md", default="indexes/thoughts_no_thread.md")

    args = ap.parse_args()

    journal_root = Path(args.journal_root)
    schema_path = Path(args.schema)
    out_md = Path(args.out_md)

    text = _read_text_arg_or_stdin(args.text)

    tags = _parse_tags_csv(args.tags)
    title = args.title

    if args.quick:
        if not tags:
            tags = ["Thought", "Capture", "NoThread"]
        if title is None or not title.strip():
            title = "(quick capture)"

    # v1.5.0 (3.10.2) 最小契約：text 必須、tags >= 1
    if not tags:
        raise SystemExit("E: thought tags is empty. Provide --tags or use --quick.")
    if title is None or not title.strip():
        title = "(no title)"

    date_local = args.date_local

    event: Dict[str, Any] = {
        "v": 1,
        "record": {
            "schema_version": "1.5.0",
            "type": "thought",
            "author": args.author,
            "date_local": date_local,
            "title": title,
            "tags": tags,
            "text": text,
            # T0177: thread は付与しない（文脈遮断）
        },
    }

    # 1) Schema Preflight（必須）
    _validate_schema_preflight(event, schema_path)

    # 2) Gate write（Fail-Fast / atomic）
    events_path = _journal_path(journal_root, date_local)
    events_path.parent.mkdir(parents=True, exist_ok=True)
    write_events_atomic(events_path, [event])

    # 3) Full Rebuild（thoughts_no_thread.md）
    if args.rebuild_start and args.rebuild_end:
        start = dt.date.fromisoformat(args.rebuild_start)
        end = dt.date.fromisoformat(args.rebuild_end)
    else:
        # 自動推定（重いなら引数で固定して回避できる）
        start, end = _find_date_range_from_files(journal_root)

    lines = _build_thoughts_no_thread_md(
        journal_root=journal_root,
        out_md=out_md,
        start=start,
        end=end,
    )

    # 4) 視覚フィードバック（先頭だけ表示）
    preview = "\n".join(lines[:40])
    print("OK: thought saved")
    print(f"- wrote: {events_path}")
    print(f"- rebuilt: {out_md}")
    print("")
    print(preview)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
