from __future__ import annotations

from pathlib import Path
from typing import Iterator, Tuple

from .safe_ndjson_reader import safe_ndjson_reader


def iter_events_journal_by_day(journal_root: Path) -> Iterator[Tuple[Path, int, dict]]:
    """
    Walk journal_by_day and yield (file_path, line_no, event_dict).

    Invariants:
    - Files are processed in deterministic order (date asc).
    - Any error inside safe_ndjson_reader MUST stop the whole iteration.
    """
    if not journal_root.exists():
        raise FileNotFoundError(f"journal root not found: {journal_root}")

    for year_dir in sorted(p for p in journal_root.iterdir() if p.is_dir()):
        for month_dir in sorted(p for p in year_dir.iterdir() if p.is_dir()):
            for ndjson_file in sorted(month_dir.glob("*.ndjson")):
                for line_no, event in safe_ndjson_reader(ndjson_file):
                    yield ndjson_file, line_no, event
