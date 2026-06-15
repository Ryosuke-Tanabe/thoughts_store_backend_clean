import os
#!/usr/bin/env python3
# start_thread.py
"""
スレッド開始を自動化するユーティリティ。
- スタートログをテンプレートから生成
- 置換トークンを埋め込み
- （任意）log_index.md に1行追記

想定テンプレ： rules/templates/start_log_template_v1.1.md
利用例:
  python start_thread.py --thread-id T0001 --title "my first thread" \
    --templates-dir templates \
    --logs-dir logs \
    --work-id my-project --edition-id v1 \
    --update-index --index-path logs/log_index.md
"""

from __future__ import annotations
import argparse
from pathlib import Path
from datetime import datetime

DEFAULT_OWNER = os.getenv("THREAD_OWNER", "your-name")
DEFAULT_TEMPLATE_NAME = "start_log_template_v1.1.md"

def load_template(templates_dir: Path, name: str) -> str:
    p = templates_dir / name
    if not p.exists():
        raise SystemExit(f"❌ Template not found: {p}")
    return p.read_text(encoding="utf-8")

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def render(content: str, ctx: dict) -> str:
    # 代表的なトークンを置換（テンプレ側で未使用でも安全）
    for k, v in ctx.items():
        content = content.replace("{" + k + "}", v)
    # バックアップとして、プレーンなヘッダが無い場合は先頭に差し込むことも可能
    return content

def append_index(index_path: Path, row: str) -> None:
    ensure_dir(index_path.parent)
    if index_path.exists():
        existing = index_path.read_text(encoding="utf-8")
        if row.strip() in existing:
            print("ℹ log_index: 同一行が既に存在します（重複追記をスキップ）")
            return
    with index_path.open("a", encoding="utf-8") as f:
        if index_path.stat().st_size > 0:
            f.write("\n")
        f.write(row)
    print(f"✅ log_index 追記: {index_path}")

def main():
    parser = argparse.ArgumentParser(description="Start a new thread: generate start log and optionally update index.")
    parser.add_argument("--thread-id", required=True, help="例: T0151")
    parser.add_argument("--title", required=True, help="スレッドタイトル（引用符で囲む）")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="YYYY-MM-DD（省略時は今日）")
    parser.add_argument("--owner", default=DEFAULT_OWNER)
    parser.add_argument("--templates-dir", default=os.getenv("TEMPLATES_DIR", "templates"))
    parser.add_argument("--template-name", default=DEFAULT_TEMPLATE_NAME)
    parser.add_argument("--logs-dir", default=os.getenv("LOGS_DIR", "logs"))
    parser.add_argument("--work-id", default="time-structure-book")
    parser.add_argument("--edition-id", default="v1")

    # index オプション
    parser.add_argument("--update-index", action="store_true", help="log_index に1行追記する")
    parser.add_argument("--index-path", default=os.getenv("LOG_INDEX_PATH", "logs/log_index.md"))

    args = parser.parse_args()

    templates_dir = Path(args.templates_dir)
    logs_dir = Path(args.logs_dir)
    ensure_dir(logs_dir)

    # 置換コンテキスト
    d = args.date.split("-")
    YYYY, MM, DD = (d + ["", "", ""])[0:3]
    ctx = {
        "thread_id": args.thread_id,
        "title": args.title,
        "date": args.date,
        "YYYY": YYYY,
        "MM": MM,
        "DD": DD,
        "work_id": args.work_id,
        "edition_id": args.edition_id,
        "owner": args.owner,
        # よく使う派生値
        "file_name": f"log_{args.date}_start_{args.thread_id}.md",
        "path": f"logs/log_{args.date}_start_{args.thread_id}.md",
        "work_ref": f"{args.work_id}@{args.edition_id}",
    }

    # テンプレ読み込み＆レンダリング
    tpl = load_template(templates_dir, args.template_name)
    body = render(tpl, ctx)

    # 出力
    out_path = logs_dir / f"log_{args.date}_start_{args.thread_id}.md"
    out_path.write_text(body, encoding="utf-8")
    print(f"✅ Start log created: {out_path}")

    if args.update_index:
        # index 追記形式（テンプレに合わせて必要なら調整）
        index_row = f"| {args.thread_id} | {args.date} | Start | {args.title} | logs/log_{args.date}_start_{args.thread_id}.md | {args.work_id}@{args.edition_id} |"
        append_index(Path(args.index_path), index_row)

if __name__ == "__main__":
    main()
