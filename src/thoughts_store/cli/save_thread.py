#!/usr/bin/env python3
# src/thoughts_store/cli/save_thread.py
"""
保存専用ユーティリティ（log_index v2 対応版）

- 生成は start/update/end 各スクリプトが _preview に出力
- 本ツールは「保存のみ」担当（_preview → 本保存）
- type=end のとき：log_index.md（v2列）/ memory_map.md を同時更新（1行追記）
- type=start / update：既定は索引に追記しない（--update-index 指定で v2 形式追記）

log_index v2 の列：
| Thread | Date | 状況 | 概要 | 関連 | Path | work_ref |
"""

from __future__ import annotations
import argparse
from pathlib import Path
from datetime import datetime
import re

TYPE_CHOICES = ("start", "update", "end")
import os
DEFAULT_LOGS_DIR = os.getenv("LOGS_DIR", "logs")
DEFAULT_INDEX = os.getenv("LOG_INDEX_PATH", "logs/log_index.md")
DEFAULT_MEMORY = os.getenv("MEMORY_MAP_MD", "logs/memory_map.md")
DEFAULT_WORK_REF = "time-structure-book@v1"

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def append_line(path: Path, line: str) -> None:
    ensure_dir(path.parent)
    if path.exists() and line.strip() in path.read_text(encoding="utf-8"):
        print(f"ℹ {path.name}: 同一行が既に存在します（追記スキップ）")
        return
    with path.open("a", encoding="utf-8") as f:
        if path.exists() and path.stat().st_size > 0:
            f.write("\n")
        f.write(line)
    print(f"✅ 追記: {path}")

def infer_date_from_name(name: str) -> str | None:
    m = re.search(r"log_(\d{4}-\d{2}-\d{2})_", name)
    return m.group(1) if m else None

def build_filename(date: str, typ: str, thread_id: str) -> str:
    return f"log_{date}_{typ}_{thread_id}.md"

def default_status_for(typ: str) -> str:
    if typ == "end":
        return "✅ 完了"
    if typ == "start":
        return "🚧 進行中"
    return "🚧 進行中"  # update も進行中扱い

def main():
    parser = argparse.ArgumentParser(description="Save a preview log and update indexes (log_index v2).")
    parser.add_argument("--type", required=True, choices=TYPE_CHOICES, help="start / update / end")
    parser.add_argument("--thread-id", required=True, help="例: T0151")
    parser.add_argument("--title", required=True, help="索引用の概要欄に入るテキスト")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD（省略時は source 名から推定 or 今日）")

    parser.add_argument("--logs-dir", default=DEFAULT_LOGS_DIR, help="本保存のディレクトリ")
    parser.add_argument("--preview-dir", default=None, help="プレビュー置き場（省略時は logs/_preview）")
    parser.add_argument("--source", default=None, help="プレビューファイルを明示指定")
    parser.add_argument("--dest", default=None, help="保存先ファイルを明示指定")

    # v2 で増えた情報
    parser.add_argument("--status", default=None, help="状況（例: ✅ 完了 / 🚧 進行中 / ⏳ 予定）")
    parser.add_argument("--related", default="", help="関連（カンマ区切りでT番号等）")
    parser.add_argument("--work-ref", default=DEFAULT_WORK_REF, help="work_ref（例: time-structure-book@v1）")

    # 索引の反映（type=end は常に。start/update は任意）
    parser.add_argument("--update-index", action="store_true", help="（start/update 用）log_index.md にも反映する")
    parser.add_argument("--index-path", default=DEFAULT_INDEX)
    parser.add_argument("--memory-map", default=DEFAULT_MEMORY)

    args = parser.parse_args()
    logs_dir = Path(args.logs_dir)
    ensure_dir(logs_dir)

    # source 決定
    if args.source:
        src = Path(args.source)
    else:
        date = args.date
        if not date:
            preview_dir = Path(args.preview_dir) if args.preview_dir else (logs_dir / "_preview")
            if not preview_dir.exists():
                raise SystemExit(f"❌ Preview dir not found: {preview_dir}")
            cand = sorted(preview_dir.glob(f"log_*_{args.type}_{args.thread_id}.md"))
            if not cand:
                raise SystemExit(f"❌ Preview not found: {preview_dir} / log_*_{args.type}_{args.thread_id}.md")
            src = cand[-1]
            date = infer_date_from_name(src.name)
            if not date:
                date = datetime.now().strftime("%Y-%m-%d")
        else:
            preview_dir = Path(args.preview_dir) if args.preview_dir else (logs_dir / "_preview")
            src = preview_dir / build_filename(date, args.type, args.thread_id)

    if not src.exists():
        raise SystemExit(f"❌ Preview file not found: {src}")

    # date 最終決定
    date = args.date or infer_date_from_name(src.name) or datetime.now().strftime("%Y-%m-%d")

    # dest 決定
    dest = Path(args.dest) if args.dest else (logs_dir / build_filename(date, args.type, args.thread_id))

    # 保存
    content = src.read_text(encoding="utf-8")
    ensure_dir(dest.parent)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(dest)
    print(f"✅ Saved: {dest}")

    # v2 行生成の共通値
    rel_path = f"logs/{dest.name}"
    status = args.status or default_status_for(args.type)
    related = args.related
    work_ref = args.work_ref

    # 追記制御
    if args.type == "end":
        # log_index v2 行
        index_row  = f"| {args.thread_id} | {date} | {status} | {args.title} | {related} | {rel_path} | {work_ref} |"
        append_line(Path(args.index_path), index_row)
        # memory_map 行（従来形式のまま）
        memory_row = f"| {args.thread_id} | {date} | {args.title} | end | {rel_path} |"
        append_line(Path(args.memory_map), memory_row)
        print("✅ 索引更新完了（end: log_index v2 + memory_map）")
    else:
        if args.update_index:
            index_row  = f"| {args.thread_id} | {date} | {status} | {args.title} | {related} | {rel_path} | {work_ref} |"
            append_line(Path(args.index_path), index_row)
            print("✅ 索引更新完了（start/update: 任意反映・v2形式）")

if __name__ == "__main__":
    main()
