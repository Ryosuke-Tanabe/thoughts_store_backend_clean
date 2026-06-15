import os
#!/usr/bin/env python3
# src/thoughts_store/cli/update_thread.py
"""
アップデートログをテンプレートから生成するユーティリティ。
既定では log_index.md を更新しない（従来運用）。
必要なときだけ --update-index を付けて追記する。

例:
  python -m src.thoughts_store.cli.update_thread \
    --thread-id T0001 \
    --title "my update" \
    --templates-dir templates \
    --template-name "update_log_template_v1.1.md" \
    --logs-dir logs \
    --update-index \
    --index-path logs/log_index.md
"""

from __future__ import annotations
import argparse
from pathlib import Path
from datetime import datetime

DEFAULT_OWNER = os.getenv("THREAD_OWNER", "your-name")
DEFAULT_TEMPLATE = "update_log_template_v1.1.md"

def load_template(templates_dir: Path, name: str) -> str:
    p = templates_dir / name
    if not p.exists():
        raise SystemExit(f"❌ Template not found: {p}")
    return p.read_text(encoding="utf-8")

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def render(content: str, ctx: dict) -> str:
    for k, v in ctx.items():
        content = content.replace("{" + k + "}", v)
    return content

def append_line(path: Path, line: str) -> None:
    ensure_dir(path.parent)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if line.strip() in existing:
            print(f"ℹ {path.name}: 同一行が既に存在します（重複追記をスキップ）")
            return
    with path.open("a", encoding="utf-8") as f:
        if path.exists() and path.stat().st_size > 0:
            f.write("\n")
        f.write(line)
    print(f"✅ 追記: {path}")

def main():
    parser = argparse.ArgumentParser(description="Generate update log (optionally append to log_index).")
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--owner", default=DEFAULT_OWNER)
    parser.add_argument("--work-id", default="time-structure-book")
    parser.add_argument("--edition-id", default="v1")
    parser.add_argument("--templates-dir", default=os.getenv("TEMPLATES_DIR", "templates"))
    parser.add_argument("--template-name", default=DEFAULT_TEMPLATE)
    parser.add_argument("--logs-dir", default=os.getenv("LOGS_DIR", "logs"))
    # 追記はオプション（既定は False）
    parser.add_argument("--update-index", action="store_true", help="log_index.md に1行追記する")
    parser.add_argument("--index-path", default=os.getenv("LOG_INDEX_PATH", "logs/log_index.md"))
    args = parser.parse_args()

    YYYY, MM, DD = args.date.split("-")
    ctx = {
        "thread_id": args.thread_id,
        "title": args.title,
        "date": args.date,
        "YYYY": YYYY, "MM": MM, "DD": DD,
        "work_id": args.work_id, "edition_id": args.edition_id,
        "owner": args.owner,
        "file_name": f"log_{args.date}_update_{args.thread_id}.md",
        "path": f"logs/log_{args.date}_update_{args.thread_id}.md",
        "work_ref": f"{args.work_id}@{args.edition_id}",
        "summary": "（ここにSummaryを入れてください）",
    }

    tpl = load_template(Path(args.templates_dir), args.template_name)
    body = render(tpl, ctx)

    out_path = Path(args.logs_dir) / f"log_{args.date}_update_{args.thread_id}.md"
    ensure_dir(out_path.parent)
    out_path.write_text(body, encoding="utf-8")
    print(f"✅ Update log created: {out_path}")

    if args.update_index:
        index_row = f"| {args.thread_id} | {args.date} | 更新 | {args.title} | logs/log_{args.date}_update_{args.thread_id}.md | {args.work_id}@{args.edition_id} |"
        append_line(Path(args.index_path), index_row)

if __name__ == "__main__":
    main()
