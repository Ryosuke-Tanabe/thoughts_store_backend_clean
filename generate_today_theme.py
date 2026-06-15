# generate_today_theme.py
"""
T0156-C: 前日の reflection から「今日の思想テーマ」を作る v0.1

使い方:
  python generate_today_theme.py --base-dir BASE --today YYYY-MM-DD --reflection-out-dir PATH

動作:
- today の前日 prev_date を計算
- reflection_out_dir 配下から prev_date に対応する最新の reflection_* ディレクトリを探す
- その中の reflection_thought.ndjson の最後の1行を読み、
  簡易的な「今日のテーマ」テキストを生成して stdout に出力する
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import json


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--base-dir", required=True)
    p.add_argument("--today", required=True, help="YYYY-MM-DD")
    p.add_argument("--reflection-out-dir", required=True)
    return p.parse_args()


def find_latest_reflection_dir(root: Path, prev_date: str) -> Path | None:
    """
    reflection_out_dir 配下から
    reflection_YYYY-MM-DD_*.ndjson という名前のディレクトリを探し、
    prev_date に一致するもののうち「文字列ソートで最大」を返す
    """
    if not root.exists():
        return None

    candidates = []
    prefix = f"reflection_{prev_date}_"
    for p in root.iterdir():
        if p.is_dir() and p.name.startswith(prefix):
            candidates.append(p)

    if not candidates:
        return None

    # 名前順で最後のものを採用（タイムスタンプ付きなのでだいたい最新になる）
    return sorted(candidates)[-1]


def load_last_reflection_line(reflection_dir: Path) -> dict | None:
    ndjson_path = reflection_dir / "reflection_thought.ndjson"
    if not ndjson_path.exists():
        return None

    last_line = None
    with ndjson_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                last_line = line

    if not last_line:
        return None

    try:
        return json.loads(last_line)
    except json.JSONDecodeError:
        return {"raw": last_line}


def make_theme(prev_date: str, reflection_obj: dict | None) -> str:
    if reflection_obj is None:
        return f"{prev_date} のリフレクションは見つかりませんでした。今日は『最近の自分の状態を軽く振り返る』をテーマにしてみましょう。"

    # reflection の内容から、簡易サマリらしきものを拾う（v0.1）
    summary = None
    for key in ("summary", "short_summary", "theme", "title"):
        if isinstance(reflection_obj.get(key), str):
            summary = reflection_obj[key]
            break

    if not summary:
        # なければ source テキストの一部を使う
        src = reflection_obj.get("source") or reflection_obj.get("thought") or ""
        if isinstance(src, dict):
            src = src.get("text") or src.get("body") or ""
        if not isinstance(src, str):
            src = ""
        summary = src[:80] + ("..." if len(src) > 80 else "")

    if not summary:
        summary = "最近感じたことを一つだけ、丁寧に言語化してみる"

    return f"{prev_date} のリフレクションを踏まえて、今日は「{summary}」をテーマに過ごしてみましょう。"


def main():
    args = parse_args()

    today = datetime.strptime(args.today, "%Y-%m-%d").date()
    prev_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")

    reflection_root = Path(args.reflection_out_dir)
    ref_dir = find_latest_reflection_dir(reflection_root, prev_date)

    if ref_dir is None:
        theme = make_theme(prev_date, None)
        print(theme)
        return 0

    obj = load_last_reflection_line(ref_dir)
    theme = make_theme(prev_date, obj)
    print(theme)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
