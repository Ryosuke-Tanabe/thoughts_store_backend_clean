#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚠️ DEPRECATED / SEALED ⚠️

This script is deprecated under GENESIS 2.0 SSOT rules.
memory_map.md is a derived artifact and MUST NOT be updated directly.

Use ssot/gate.py and rebuild scripts instead.
"""

"""
update_memory_map.py
Append (or upsert) Thought entries into memory_map.md.
- Targets ONLY the Thought Archive table (| Date | Tags | Author | Path | 概要 |)
- Idempotent: replaces existing row with the same Path or Date (prefers Path match).
- Creates a timestamped backup before modifying the file, unless --dry-run.
Usage:
  python update_memory_map.py --memory-map /path/to/memory_map.md --ndjson /path/to/2025-11-10.ndjson [--date 2025-11-10] [--tags "a,b,c"] [--author <name>] [--summary "short desc"] [--dry-run]
  python update_memory_map.py --memory-map /path/to/memory_map.md --scan-dir /path/to/journal_by_day/2025/11
"""
import argparse, os, re, json, shutil
from datetime import datetime
from typing import List, Optional, Tuple
import io, tempfile
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.service_account import Credentials

THOUGHT_HEADER_REGEX = re.compile(r"^#{2,3}\s*Thought Archive\s*$", re.IGNORECASE)
TABLE_HEADER_REGEX = re.compile(
    r"^\|\s*Date\s*\|\s*Tags\s*\|\s*Author\s*\|\s*Path\s*\|\s*概要\s*\|\s*$"
)
# log_index.md (minimal) table format:
# | Date | Task ID | Phase | Summary | Drive Ref |
LOG_INDEX_HEADER_REGEX = re.compile(
    r"^\|\s*Date\s*\|\s*Task\s*ID\s*\|\s*Phase\s*\|\s*Summary\s*\|\s*Drive\s*Ref\s*\|\s*$",
    re.IGNORECASE,
)
LOG_INDEX_SECTION_REGEX = re.compile(r"^#{2,3}\s*log_index\s*$", re.IGNORECASE)


def download_ndjson_from_drive(file_id: str) -> List[dict]:
    sa = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not sa:
        raise SystemExit("Missing env: GOOGLE_SERVICE_ACCOUNT_JSON")
    scopes = ["https://www.googleapis.com/auth/drive"]

    if sa.strip().startswith("{"):
        tmpf = tempfile.NamedTemporaryFile(delete=False, suffix="_sa.json")
        tmpf.write(sa.encode("utf-8"))
        tmpf.flush()
        sa = tmpf.name

    creds = Credentials.from_service_account_file(sa, scopes=scopes)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    req = drive.files().get_media(fileId=file_id, supportsAllDrives=True)
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()

    buf.seek(0)
    items = []
    for line in buf.read().decode("utf-8").splitlines():
        if line.strip():
            items.append(json.loads(line))
    return items


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def backup(path: str) -> str:
    backup_path = f"{path}.bak"
    shutil.copy2(path, backup_path)
    return backup_path


def find_thought_table_bounds(text: str) -> Optional[Tuple[int, int]]:
    """
    Returns (start_idx, end_idx) of the table (inclusive start, exclusive end) in lines.
    Looks for "### Thought Archive" section first; if absent, falls back to the first matching table header.
    """
    lines = text.splitlines()
    # First, try to find "Thought Archive" section and then the table header after it.
    section_start = None
    for i, line in enumerate(lines):
        if THOUGHT_HEADER_REGEX.match(line.strip()):
            section_start = i
            break
    if section_start is not None:
        # search header from section_start+1
        for j in range(section_start + 1, len(lines)):
            if TABLE_HEADER_REGEX.match(lines[j].strip()):
                # table begins at j
                start = j
                # table ends when a non-table line appears (not starting with '|') or end of file
                k = j + 1
                while k < len(lines) and lines[k].lstrip().startswith("|"):
                    k += 1
                return (start, k)
        # Thought Archive section exists but no header found; we will create one.
        return (section_start + 1, section_start + 1)

    # Fallback: find the first Date/Tags table header anywhere
    for i, line in enumerate(lines):
        if TABLE_HEADER_REGEX.match(line.strip()):
            start = i
            k = i + 1
            while k < len(lines) and lines[k].lstrip().startswith("|"):
                k += 1
            return (start, k)

    return None


def ensure_thought_section(text: str) -> str:
    """If neither a 'Thought Archive' header nor the Date/Tags table exists, create a section at the end."""
    if find_thought_table_bounds(text) is not None:
        return text
    # Append a new section with header + empty table
    addition = "\n\n### Thought Archive\n\n| Date | Tags | Author | Path | 概要 |\n|------|------|---------|------|------|\n"
    return text.rstrip() + addition + "\n"


def find_log_index_table_bounds(text: str) -> Optional[Tuple[int, int]]:
    """
    Returns (start_idx, end_idx) of the log_index table in lines.
    Prefers a "##/### log_index" section if present; otherwise finds the first matching header.
    """
    lines = text.splitlines()
    section_start = None
    for i, line in enumerate(lines):
        if LOG_INDEX_SECTION_REGEX.match(line.strip()):
            section_start = i
            break

    if section_start is not None:
        for j in range(section_start + 1, len(lines)):
            if LOG_INDEX_HEADER_REGEX.match(lines[j].strip()):
                start = j
                k = j + 1
                while k < len(lines) and lines[k].lstrip().startswith("|"):
                    k += 1
                return (start, k)
        # section exists but no header
        return (section_start + 1, section_start + 1)

    for i, line in enumerate(lines):
        if LOG_INDEX_HEADER_REGEX.match(line.strip()):
            start = i
            k = i + 1
            while k < len(lines) and lines[k].lstrip().startswith("|"):
                k += 1
            return (start, k)

    return None


def ensure_log_index_section(text: str) -> str:
    """Create a log_index section + empty table if not present."""
    if find_log_index_table_bounds(text) is not None:
        return text
    addition = (
        "\n\n### log_index\n\n"
        "| Date | Task ID | Phase | Summary | Drive Ref |\n"
        "|------|---------|-------|---------|----------|\n"
    )
    return text.rstrip() + addition + "\n"


def is_end_thought(target: dict) -> bool:
    """
    True if this thought represents an 'end' phase.
    Priority:
      1) record.thread.phase == 'end'
      2) record.title startswith 'エンドログ｜'
    """
    record = target.get("record") or {}
    thread = record.get("thread")
    if isinstance(thread, dict) and thread.get("phase"):
        return str(thread.get("phase")).strip().lower() == "end"

    title = record.get("title", "")
    return isinstance(title, str) and title.startswith("エンドログ｜")


def extract_task_id(target: dict) -> str:
    """Extract Txxxx from record.title or fallback to 'N/A'."""
    record = target.get("record") or {}
    title = record.get("title", "") or ""
    m = re.search(r"\bT\d{4}\b", title)
    return m.group(0) if m else "N/A"


def sanitize_md_cell(s: str, max_len: int = 80) -> str:
    """Prevent markdown table breakage; keep it short."""
    s = (s or "").replace("|", "／").strip()
    if len(s) > max_len:
        return s[:max_len] + "…"
    return s


def build_log_index_row(target: dict, date_str: str, drive_ref: str) -> Tuple[str, str]:
    """
    Returns (task_id, row_line)
    """
    task_id = extract_task_id(target)
    phase = "end"

    # Prefer lifted 'summary' (your script already lifts record.body.summary into target['summary'])
    summary = target.get("summary") or target.get("title") or ""
    summary = sanitize_md_cell(str(summary), max_len=80)

    row = f"| {date_str} | {task_id} | {phase} | {summary} | {drive_ref} |"
    return task_id, row


def upsert_log_index_row(text: str, new_row: str, task_id: str) -> str:
    """
    Upsert by Task ID. If a row with same Task ID exists, replace it. Otherwise append.
    """
    lines = text.splitlines()
    bounds = find_log_index_table_bounds(text)
    if bounds is None:
        text = ensure_log_index_section(text)
        lines = text.splitlines()
        bounds = find_log_index_table_bounds(text)
        assert bounds is not None, "Failed to create log_index section."

    start, end = bounds

    # Ensure header + divider exists
    if end - start < 2:
        header = "| Date | Task ID | Phase | Summary | Drive Ref |"
        divider = "|------|---------|-------|---------|----------|"
        lines[start:start] = [header, divider]
        end += 2

    # Match by Task ID column (2nd column)
    # e.g. | 2026-01-20 | T0164 | end | ... | ... |
    task_pattern = re.compile(rf"^\|\s*[^|]+\|\s*{re.escape(task_id)}\s*\|")

    replaced = False
    for i in range(start + 2, end):
        if task_pattern.match(lines[i]):
            lines[i] = new_row
            replaced = True
            break

    if not replaced:
        lines.insert(end, new_row)
        end += 1

    return "\n".join(lines) + ("\n" if not text.endswith("\n") else "")


def format_row(
    date_str: str, tags: List[str], author: str, path: str, summary: str
) -> str:
    return f"| {date_str} | {', '.join(tags)} | {author} | {path} | {summary} |"


def upsert_row(text: str, new_row: str, date_str: str, path: str) -> str:
    """
    Replace an existing row that matches Path or Date; otherwise append at end of the table.
    """
    lines = text.splitlines()
    bounds = find_thought_table_bounds(text)
    if bounds is None:
        text = ensure_thought_section(text)
        lines = text.splitlines()
        bounds = find_thought_table_bounds(text)
        assert bounds is not None, "Failed to create Thought Archive section."

    start, end = bounds
    # Ensure the table has at least header + divider lines
    if end - start < 2:
        # Insert the header & divider lines
        header = "| Date | Tags | Author | Path | 概要 |"
        divider = "|------|------|---------|------|------|"
        lines[start:start] = [header, divider]
        # adjust indices
        end += 2

    # Try to find an existing row to replace
    path_pattern = re.compile(
        rf"^\|\s*{re.escape(date_str)}\s*\|.*\|\s*{re.escape(path)}\s*\|", re.UNICODE
    )
    any_path_pattern = re.compile(
        rf"\|\s*[^|]*\|\s*[^|]*\|\s*[^|]*\|\s*{re.escape(path)}\s*\|"
    )
    date_pattern = re.compile(rf"^\|\s*{re.escape(date_str)}\s*\|")

    replaced = False
    for i in range(start + 2, end):  # skip header + divider
        line = lines[i]
        if any_path_pattern.search(line):
            lines[i] = new_row
            replaced = True
            break
    if not replaced:
        # second pass: match by date
        for i in range(start + 2, end):
            if date_pattern.match(lines[i]):
                lines[i] = new_row
                replaced = True
                break
    if not replaced:
        # append just before 'end' (which is first non-table line)
        lines.insert(end, new_row)
        end += 1

    return "\n".join(lines) + ("\n" if not text.endswith("\n") else "")


def parse_ndjson(ndjson_path: str) -> List[dict]:
    """Parse .ndjson into a list of dicts. Tolerant to plain JSON arrays or single JSON."""
    items = []
    with open(ndjson_path, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict):
                    items.append(obj)
                elif isinstance(obj, list):
                    items.extend(x for x in obj if isinstance(x, dict))
            except json.JSONDecodeError:
                # fallback: treat line as raw text
                items.append({"text": raw})
    return items


def summarize_from_item(item: dict, max_len: int = 80) -> str:
    """
    AI検索用のインデックス文字列を生成する。
    - summary があればそれを優先
    - なければ text の1行目（最初の非空行）を使う
    - Markdownテーブルを壊さないように '|' は全角に変換
    """
    # 1. summary/title/text のどれかをベース文字列として取る
    base = None
    for key in ("summary", "title", "text"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            base = val
            break
    if not base:
        return ""

    # 2. 最初の非空行を抽出
    first_line = ""
    for line in base.splitlines():
        line = line.strip()
        if line:
            first_line = line
            break
    if not first_line:
        first_line = base.strip()

    # 3. テーブル崩壊する文字を潰す
    s = first_line.replace("|", "／")

    # 4. 長さ制限
    return s[:max_len] + ("…" if len(s) > max_len else "")


def infer_date_from_filename(path: str) -> Optional[str]:
    base = os.path.basename(path)
    m = re.search(r"(\d{4}-\d{2}-\d{2})", base)
    return m.group(1) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--memory-map", required=True, help="Path to memory_map.md")
    ap.add_argument("--ndjson", help="Path to a single NDJSON file")
    ap.add_argument("--scan-dir", help="Scan a directory for *.ndjson files")
    ap.add_argument("--date", help="Override date (YYYY-MM-DD)")
    ap.add_argument("--tags", help="Comma-separated tags")
    ap.add_argument("--author", default=os.getenv("THOUGHT_AUTHOR", ""))
    ap.add_argument("--summary", help="Override summary text")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--drive-file-id", help="Google Drive NDJSON file ID")
    ap.add_argument("--log-index", help="Path to log_index.md (optional)")
    ap.add_argument("--hash", help="Target hash to identify the record")
    args = ap.parse_args()

    if not os.path.exists(args.memory_map):
        raise SystemExit(f"memory_map not found: {args.memory_map}")

    original = read_text(args.memory_map)
    text = original

    # =========================
    # Drive SSOT mode
    # =========================
    if args.drive_file_id:
        # DriveからNDJSONを取得
        items = download_ndjson_from_drive(args.drive_file_id)

        # 対象レコードを特定（hash指定があればそれ、なければ末尾）
        target = None
        if args.hash:
            for obj in reversed(items):
                if isinstance(obj, dict) and obj.get("hash") == args.hash:
                    target = obj
                    break
        if target is None:
            target = items[-1] if items else {}

        if not target:
            raise SystemExit("No valid thought found in Drive file.")

        # date_str を決める
        # Drive経由だとファイル名から日付推定できないので、--date優先、なければ t_utc から切る
        date_str = args.date or (
            target.get("t_utc", "")[:10] if isinstance(target, dict) else None
        )
        if not date_str:
            raise SystemExit(
                "Date is required for Drive mode (pass --date or ensure target has t_utc)."
            )

        # このスクリプトが期待していた ndjson_path 変数を「擬似パス」にする
        # （path_field生成で使うので）
        ndjson_path = f"drive://{args.drive_file_id}"

        # --- v1.3.4 signed wrapper support: lift fields from target["record"] ---
        if isinstance(target, dict):
            record = target.get("record")
            if isinstance(record, dict):
                if "tags" not in target and "tags" in record:
                    target["tags"] = record.get("tags")
                if "author" not in target and "author" in record:
                    target["author"] = record.get("author")
                if "title" not in target and "title" in record:
                    target["title"] = record.get("title")
                body = record.get("body")
                if isinstance(body, dict):
                    if "summary" not in target and "summary" in body:
                        target["summary"] = body.get("summary")

        tags = args.tags.split(",") if args.tags else (target.get("tags") or [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        tags = [str(t).strip() for t in tags if str(t).strip()]

        author = args.author or target.get("author") or ""
        summary = args.summary or summarize_from_item(target) or date_str

        # Driveの場合は journal_by_day 形式に寄せて書く（file_idが実体）
        y, m = date_str[:4], date_str[5:7]
        path_field = (
            f"journal_by_day/{y}/{m}/{date_str}.ndjson#drive:{args.drive_file_id}"
        )

        new_row = format_row(date_str, tags, author, path_field, summary)
        text = upsert_row(text, new_row, date_str, path_field)
        print(f"[ok] upserted {date_str} -> {path_field}")

    # =========================
    # Local mode (existing)
    # =========================
    else:
        targets = []
        if args.ndjson:
            targets.append(args.ndjson)
        if args.scan_dir:
            for name in os.listdir(args.scan_dir):
                if name.lower().endswith(".ndjson"):
                    targets.append(os.path.join(args.scan_dir, name))
        if not targets:
            raise SystemExit("Specify --ndjson, --scan-dir, or --drive-file-id")

        for ndjson_path in targets:
            if not os.path.exists(ndjson_path):
                print(f"[warn] ndjson missing: {ndjson_path}")
                continue

            items = parse_ndjson(ndjson_path)
            target = items[-1] if items else {}
            date_str = (
                args.date or target.get("date") or infer_date_from_filename(ndjson_path)
            )
            if not date_str:
                raise SystemExit(
                    "Date is required (pass --date or include YYYY-MM-DD in filename or 'date' field)."
                )

            # --- v1.3.4 signed wrapper support: lift fields from target["record"] ---
            if isinstance(target, dict):
                record = target.get("record")
                if isinstance(record, dict):
                    if "tags" not in target and "tags" in record:
                        target["tags"] = record.get("tags")
                    if "author" not in target and "author" in record:
                        target["author"] = record.get("author")
                    if "title" not in target and "title" in record:
                        target["title"] = record.get("title")
                    body = record.get("body")
                    if isinstance(body, dict):
                        if "summary" not in target and "summary" in body:
                            target["summary"] = body.get("summary")

            tags = args.tags.split(",") if args.tags else (target.get("tags") or [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            tags = [str(t).strip() for t in tags if str(t).strip()]

            author = args.author or target.get("author") or ""
            summary = (
                args.summary
                or summarize_from_item(target)
                or os.path.splitext(os.path.basename(ndjson_path))[0]
            )

            if "journal_by_day" in ndjson_path.replace("\\", "/"):
                rel = ndjson_path.replace("\\", "/")
                rel = rel[rel.find("journal_by_day/") :]
                path_field = rel
            else:
                y, m = date_str[:4], date_str[5:7]
                path_field = f"journal_by_day/{y}/{m}/{os.path.basename(ndjson_path)}"

            new_row = format_row(date_str, tags, author, path_field, summary)
            text = upsert_row(text, new_row, date_str, path_field)
            print(f"[ok] upserted {date_str} -> {path_field}")

    # =========================
    # log_index.md upsert (end only) - shared for Drive/Local
    # =========================
    if args.log_index and is_end_thought(target):
        if not os.path.exists(args.log_index):
            raise SystemExit(f"log_index not found: {args.log_index}")

        log_original = read_text(args.log_index)
        task_id, log_row = build_log_index_row(target, date_str, path_field)
        log_text = upsert_log_index_row(log_original, log_row, task_id)

        if args.dry_run:
            print("[dry-run] log_index.md would be updated:")
            print(log_text)
        else:
            backup_path = backup(args.log_index)
            write_text(args.log_index, log_text)
            print(f"[done] log_index updated. Backup saved to: {backup_path}")

    if args.dry_run:
        print("[dry-run] No changes written.")
        print(text)
        return

    # Create backup and write
    backup_path = backup(args.memory_map)
    write_text(args.memory_map, text)
    print(f"[done] memory_map updated. Backup saved to: {backup_path}")


if __name__ == "__main__":
    main()
