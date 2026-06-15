# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from thoughts_store.reflection_layer import run_reflection


def _extract_date_from_thoughts_path(thoughts_path: str) -> str:
    """
    thoughts NDJSON パスから YYYY-MM-DD を推定する。
    - ファイル名が '2025-11-12.ndjson' のような場合はその日付を採用
    - それ以外の場合は「今日」の日付を使う
    """
    stem = Path(thoughts_path).stem  # 例: 2025-11-12
    try:
        datetime.strptime(stem, "%Y-%m-%d")
        return stem
    except ValueError:
        # ファイル名から取れない場合は今日の日付でフォールバック
        return datetime.today().strftime("%Y-%m-%d")


def _normalize_reflections(outputs: Any) -> list[dict]:
    """
    run_reflection の戻り値を NDJSON 用の「list[dict]」に正規化する。

    想定するパターン（ゆるく対応）:
    - dict で `outputs["reflections"]` が list の場合 → それを使う
    - dict で `outputs["items"]` が list の場合 → それを使う
    - list[dict or str] の場合 → そのまま
    - それ以外 → 1要素だけの list として { "raw": ... } に包む
    """
    if isinstance(outputs, dict):
        if isinstance(outputs.get("reflections"), list):
            return list(outputs["reflections"])
        if isinstance(outputs.get("items"), list):
            return list(outputs["items"])
        # dict 単体の場合もとりあえず1件として扱う
        return [outputs]

    if isinstance(outputs, list):
        # list の中身が dict/str ならそのまま、それ以外は raw 包装
        normalized: list[dict] = []
        for item in outputs:
            if isinstance(item, dict):
                normalized.append(item)
            elif isinstance(item, str):
                normalized.append({"raw": item})
            else:
                normalized.append({"raw": item})
        return normalized

    # どのパターンでもない場合は raw として1件にまとめる
    return [{"raw": outputs}]


def _write_reflection_ndjson(
    out_dir: str, date_str: str, reflections: list[dict]
) -> str:
    """
    generate_today_theme.py が読む前提のパス構造で NDJSON を書き出す。

    - out_dir/
        reflection_{YYYY-MM-DD}_{HHMMSS}/
            reflection_thought.ndjson
    """
    base = Path(out_dir)
    timestamp = datetime.now().strftime("%H%M%S")
    target_dir = base / f"reflection_{date_str}_{timestamp}"
    target_dir.mkdir(parents=True, exist_ok=True)

    ndjson_path = target_dir / "reflection_thought.ndjson"
    with ndjson_path.open("w", encoding="utf-8") as f:
        for r in reflections:
            # 念のため str が混じる場合もカバー
            if isinstance(r, str):
                obj = {"raw": r}
            else:
                obj = r
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    return str(ndjson_path)


def main() -> None:
    p = argparse.ArgumentParser(description="Self-Reflective Layer v0.1 CLI")
    p.add_argument(
        "--thoughts",
        required=True,
        help="NDJSON path (ThoughtStore sample)",
    )
    p.add_argument(
        "--alpha",
        required=False,
        help="alpha_state.json path",
    )
    p.add_argument(
        "--out",
        required=True,
        help="output dir (reflection_* ディレクトリを作るルート)",
    )
    args = p.parse_args()

    # 1) もともとの reflection 実行
    outputs = run_reflection(args.thoughts, args.alpha, args.out)

    # 2) NDJSON 用の日付を決める（基本は thoughts ファイル名の YYYY-MM-DD）
    date_str = _extract_date_from_thoughts_path(args.thoughts)

    # 3) run_reflection の結果を list[dict] に正規化
    reflections = _normalize_reflections(outputs)

    # 4) generate_today_theme.py が読む形式で NDJSON を書き出す
    ndjson_path = _write_reflection_ndjson(args.out, date_str, reflections)

    # 5) メタ情報を JSON で標準出力（従来の「print(outputs)」互換＋α）
    meta = {
        "date": date_str,
        "ndjson_path": ndjson_path,
        "reflections_count": len(reflections),
        "raw": outputs,
    }
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
