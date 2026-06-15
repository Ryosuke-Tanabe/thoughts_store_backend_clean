from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Iterable, List, Dict, Any, Optional

# P2-CORE（確定済み）を利用
from .build_memory_map_from_events import (
    build_thread_states,
    to_memory_map_records,
    write_ndjson,
)

# jsonschema はあれば使う。無い場合は明示的にエラーにする（監査観点で曖昧にしない）
try:
    import jsonschema  # type: ignore
except Exception as e:  # pragma: no cover
    jsonschema = None
    _jsonschema_import_error = e


def iter_journal_files(journal_root: Path, start: dt.date, end: dt.date) -> List[Path]:
    """
    journal_by_day/YYYY/MM/YYYY-MM-DD.ndjson を列挙。
    end は含む。存在しない日はスキップ（欠損補完しない）。
    """
    out: List[Path] = []
    cur = start
    one = dt.timedelta(days=1)
    while cur <= end:
        p = (
            journal_root
            / f"{cur.year:04d}"
            / f"{cur.month:02d}"
            / f"{cur.year:04d}-{cur.month:02d}-{cur.day:02d}.ndjson"
        )
        if p.exists():
            out.append(p)
        cur += one
    return out


def _parse_real_date(s: str) -> dt.date:
    # schema の format:"date" を「実在日付」として扱う（READMEの注意に沿う） :contentReference[oaicite:3]{index=3}
    return dt.date.fromisoformat(s)


def validate_memory_map_records(
    records: List[Dict[str, Any]], schema_path: Path
) -> None:
    """
    1) JSON Schema で全行 validate
    2) start_date_local <= last_date_local を追加で必ず検証（READMEの注意） :contentReference[oaicite:4]{index=4}
    Fail-Fast: 1件でも不正なら例外で停止。
    """
    if jsonschema is None:  # pragma: no cover
        raise RuntimeError(
            "jsonschema package is required for validation, but it could not be imported."
        ) from _jsonschema_import_error

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)

    for idx, rec in enumerate(records, start=1):
        # 1) schema validate
        errors = sorted(validator.iter_errors(rec), key=lambda e: e.path)
        if errors:
            e0 = errors[0]
            path = ".".join(str(p) for p in e0.path) or "<root>"
            raise RuntimeError(
                f"memory_map schema validation failed at record #{idx} "
                f"(thread_id={rec.get('thread_id')!r}) path={path}: {e0.message}"
            )

        # 2) start <= last の追加検証（schema説明にある “tooling enforce”） :contentReference[oaicite:5]{index=5}
        s = rec.get("start_date_local")
        l = rec.get("last_date_local")
        if not isinstance(s, str) or not isinstance(l, str):
            raise RuntimeError(
                f"memory_map date fields must be strings at record #{idx} "
                f"(thread_id={rec.get('thread_id')!r})"
            )
        sd = _parse_real_date(s)
        ld = _parse_real_date(l)
        if sd > ld:
            raise RuntimeError(
                f"memory_map invariant violated (start_date_local > last_date_local) "
                f"at record #{idx} (thread_id={rec.get('thread_id')!r}): {s} > {l}"
            )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal-root", type=str, required=True)
    ap.add_argument("--out", type=str, required=True)
    ap.add_argument("--schema", type=str, required=True)
    ap.add_argument("--start", type=str, required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", type=str, required=True, help="YYYY-MM-DD (inclusive)")
    args = ap.parse_args()

    journal_root = Path(args.journal_root)
    out_path = Path(args.out)
    schema_path = Path(args.schema)

    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)

    files = iter_journal_files(journal_root, start, end)
    states = build_thread_states(files)
    records = to_memory_map_records(states)

    # P3: validate before write（書き込み前検証を必須化）
    validate_memory_map_records(records, schema_path)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_ndjson(out_path, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
