#!/usr/bin/env python3
# src/thoughts_store/cli/end_thread.py
"""
終了ログの生成（プレビュー）と保存（索引反映）を行うCLI。
- v2行（| Thread | Date | 状況 | 概要 | 関連 | Path | work_ref |）を作成時に確定
- 保存(--save)時に log_index.md と memory_map.md を同時更新
- テンプレートの探索パスを自動探索（--templates-dir / ./rules/templates）

使い方:
  # プレビュー（作成のみ）
  python -m src.thoughts_store.cli.end_thread \
    --thread-id T0001 \
    --title "task complete" \
    --related "T0000" \
    --work-ref "my-project@v1"

  # 保存（確定 & 索引反映）
  python -m src.thoughts_store.cli.end_thread \
    --thread-id T0001 \
    --title "task complete" \
    --save \
    --index-path logs/log_index.md \
    --memory-map logs/memory_map.md
"""

from __future__ import annotations
import argparse
from pathlib import Path
from datetime import datetime
import sys

DEFAULT_OWNER = os.getenv("THREAD_OWNER", "your-name")
DEFAULT_TEMPLATE_NAME = "end_log_template_v1.1.md"
DEFAULT_STATUS = "✅ 完了"
DEFAULT_WORK_REF = "time-structure-book@v1"

import os
DEFAULT_LOGS_DIR = os.getenv("LOGS_DIR", "logs")
DEFAULT_TEMPLATES_DIR = os.getenv("TEMPLATES_DIR", "templates")

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def debug(msg: str, enabled: bool) -> None:
    if enabled:
        print(f"[DEBUG] {msg}")

def find_template(template_name: str, prefer_dir: Path | None, debug_on: bool = False) -> Path:
    candidates = []
    if prefer_dir:
        candidates.append(prefer_dir / template_name)
    # repo ローカル相対
    candidates.append(Path("rules") / "templates" / template_name)
    # 既定の G: ドライブ
    candidates.append(Path(DEFAULT_TEMPLATES_DIR) / template_name)
    tried = []
    for c in candidates:
        tried.append(str(c))
        if c.exists():
            debug(f"Using template: {c}", debug_on)
            return c
    # 見つからない場合は丁寧に案内
    print("❌ Template not found.")
    print("Tried:")
    for t in tried:
        print(f"  - {t}")
    print("対処: --templates-dir を明示、または上記いずれかにテンプレートを配置してください。")
    sys.exit(2)

def load_template(templates_dir: Path | None, template_name: str, debug_on: bool) -> str:
    p = find_template(template_name, templates_dir, debug_on)
    return p.read_text(encoding="utf-8")

def render(content: str, ctx: dict) -> str:
    # シンプル置換（未使用トークンがあってもそのまま）
    for k, v in ctx.items():
        content = content.replace("{" + k + "}", v)
    return content

def append_line(path: Path, line: str) -> None:
    ensure_dir(path.parent)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if line.strip() in existing:
            print(f"ℹ {path.name}: 同一行が既に存在します（追記スキップ）")
            return
    with path.open("a", encoding="utf-8") as f:
        if path.exists() and path.stat().st_size > 0:
            f.write("\n")
        f.write(line)
    print(f"✅ 追記: {path}")

def ensure_file(path: Path, default_text: str = "") -> None:
    ensure_dir(path.parent)
    if not path.exists():
        path.write_text(default_text, encoding="utf-8")

def build_v2_row(thread_id: str, date: str, status: str, title: str, related: str, rel_path: str, work_ref: str) -> str:
    return f"| {thread_id} | {date} | {status} | {title} | {related} | {rel_path} | {work_ref} |"

def main():
    parser = argparse.ArgumentParser(description="Generate & save END log (with log_index v2 row).")
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--owner", default=DEFAULT_OWNER)
    parser.add_argument("--work-id", default="time-structure-book")
    parser.add_argument("--edition-id", default="v1")

    parser.add_argument("--templates-dir", default=None, help="テンプレートディレクトリ（未指定なら自動探索）")
    parser.add_argument("--template-name", default=DEFAULT_TEMPLATE_NAME)

    parser.add_argument("--logs-dir", default=DEFAULT_LOGS_DIR)
    parser.add_argument("--preview-dir", default=None, help="省略時は logs/_preview")

    parser.add_argument("--status", default=DEFAULT_STATUS)
    parser.add_argument("--related", default="")
    parser.add_argument("--work-ref", default=DEFAULT_WORK_REF)

    parser.add_argument("--save", action="store_true", help="保存＆索引反映を実行する")
    parser.add_argument("--index-path", default=os.getenv("LOG_INDEX_PATH", "logs/log_index.md"))
    parser.add_argument("--memory-map", default=os.getenv("MEMORY_MAP_MD", "logs/memory_map.md"))

    parser.add_argument("--debug", action="store_true", help="デバッグ出力")
    args = parser.parse_args()

    # 構築
    logs_dir = Path(args.logs_dir)
    ensure_dir(logs_dir)
    preview_dir = Path(args.preview_dir) if args.preview_dir else (logs_dir / "_preview")
    ensure_dir(preview_dir)

    YYYY, MM, DD = args.date.split("-")
    file_stub = f"log_{args.date}_end_{args.thread_id}.md"
    rel_path = f"logs/{file_stub}"

    # テンプレロード
    tdir = Path(args.templates_dir) if args.templates_dir else None
    tpl_text = load_template(tdir, args.template_name, args.debug)

    body = render(tpl_text, {
        "thread_id": args.thread_id,
        "title": args.title,
        "date": args.date,
        "YYYY": YYYY, "MM": MM, "DD": DD,
        "work_id": args.work_id, "edition_id": args.edition_id,
        "owner": args.owner,
        "file_name": file_stub,
        "path": rel_path,
        "work_ref": args.work_ref,
    })

    v2_row = build_v2_row(args.thread_id, args.date, args.status, args.title, args.related, rel_path, args.work_ref)
    v2_row_file = preview_dir / (file_stub + ".indexv2")
    preview_file = preview_dir / file_stub
    final_file = logs_dir / file_stub

    if not args.save:
        # プレビュー出力
        preview_file.write_text(body, encoding="utf-8")
        v2_row_file.write_text(v2_row, encoding="utf-8")
        print(f"📝 Preview created: {preview_file}")
        print(f"🧾 v2 row saved: {v2_row_file}")
        debug(f"index path: {args.index-path if hasattr(args,'index-path') else args.index_path}", args.debug)
        debug(f"memory map: {args.memory-map if hasattr(args,'memory-map') else args.memory_map}", args.debug)
        return

    # 保存（確定）
    # 本文
    final_file.write_text(body, encoding="utf-8")
    print(f"✅ End log saved: {final_file}")

    # 索引 v2（プレビュー保存済みを優先、無ければ再計算の行を使用）
    if v2_row_file.exists():
        v2_row = v2_row_file.read_text(encoding="utf-8").strip()

    # memory_map の自動生成（無ければ空で作る）
    ensure_file(Path(args.memory_map), default_text="# memory_map\n")

    append_line(Path(args.index_path), v2_row)
    append_line(Path(args.memory_map), f"| {args.thread_id} | {args.date} | {args.title} | end | {rel_path} |")
    print("✅ 索引更新完了（v2 + memory）")

if __name__ == "__main__":
    main()
