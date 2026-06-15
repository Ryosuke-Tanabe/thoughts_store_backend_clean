# src/thoughts_store/cli/version_check.py
"""
version_check.py
----------------
仕様ファイル群のバージョン整合と依存関係を検証するCLI。

機能:
  --init       : templates から rules/manifest.json を生成
  --validate   : rules/schema.json による manifest のスキーマ検証
  --check      : rules/spec_versions.yml と manifest の依存条件を突き合わせ
  --graph      : 予約（将来実装）
  --impact     : 予約（将来実装）

使い方例:
  python -m src.thoughts_store.cli.version_check --init
  python -m src.thoughts_store.cli.version_check --validate
  python -m src.thoughts_store.cli.version_check --check
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, Tuple

# Optional deps
try:
    from jsonschema import validate as jsonschema_validate  # type: ignore
except Exception:
    jsonschema_validate = None  # pragma: no cover

try:
    import yaml  # type: ignore
except Exception:
    yaml = None  # pragma: no cover


# ----------------------------
# Helpers
# ----------------------------
def load_json(path: Path) -> Dict:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(text)


def parse_ver(v: str) -> Tuple[int, int, int]:
    nums = re.findall(r"\d+", str(v))
    parts = [int(x) for x in nums[:3]] + [0] * (3 - len(nums[:3]))
    return tuple(parts)  # type: ignore[return-value]


def meet(rule: str, current: str) -> bool:
    """
    現在値 current が rule（例: '>=1.2'）を満たすかを返す。
    サポート: >=, >, ==, =, <=, <
    """
    rule = rule.strip()
    ops = [">=", "<=", "==", "=", ">", "<"]
    for op in ops:
        if op in rule:
            req = rule.split(op, 1)[1].strip()
            c, r = parse_ver(current), parse_ver(req)
            if   op == ">=": return c >= r
            elif op == "<=": return c <= r
            elif op in ("==", "="): return c == r
            elif op == ">": return c > r
            elif op == "<": return c < r
    # オペレータが無い場合は true（互換）
    return True


# ----------------------------
# Core features
# ----------------------------
def cmd_init(template_path: Path, dest_path: Path) -> int:
    if not template_path.exists():
        print(f"❌ Template not found: {template_path}")
        return 1
    write_text(dest_path, template_path.read_text(encoding="utf-8"))
    print(f"✅ Created {dest_path} from {template_path}")
    return 0


def cmd_validate(manifest_path: Path, schema_path: Path) -> int:
    if jsonschema_validate is None:
        print("⚠ jsonschema が未インストールです。`pip install jsonschema` を実行してください。")
        return 1
    manifest = load_json(manifest_path)
    schema = load_json(schema_path)
    jsonschema_validate(instance=manifest, schema=schema)
    print(f"✅ Schema valid: {manifest_path}")
    return 0


def cmd_check(manifest_path: Path, versions_path: Path) -> int:
    if yaml is None:
        print("⚠ PyYAML が未インストールです。`pip install pyyaml` を実行してください。")
        return 1

    manifest = load_json(manifest_path)
    versions = yaml.safe_load(Path(versions_path).read_text(encoding='utf-8')) or {}
    deps: Dict[str, str] = manifest.get("spec_dependencies", {}) or {}

    print("\n=== Spec Dependencies Check ===")
    failed = []
    for spec, rule in deps.items():
        # ルールの右辺（例: 'recall_config >=1.2'）からオペレータ以降だけを抽出
        # 'X >=1.2' or '>=1.2' の両方に対応
        rhs = rule
        if " " in rule:
            rhs = rule.split(" ", 1)[-1]
        current = str(versions.get(spec, "0.0"))
        ok = meet(rhs, current)
        status = "OK" if ok else "NG"
        print(f"- {spec}: need {rhs} | current {current} -> {status}")
        if not ok:
            failed.append(spec)

    print("================================\n")
    if failed:
        print(f"❌ Not satisfied: {', '.join(failed)}")
        return 2
    print("✅ All constraints satisfied.")
    return 0


# ----------------------------
# Entry point
# ----------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Spec version dependency checker")
    p.add_argument("--manifest", type=str, default=str(Path("rules/manifest.json")),
                   help="Path to rules/manifest.json (or templates file)")
    p.add_argument("--schema", type=str, default=str(Path("rules/schema.json")),
                   help="Path to rules/schema.json")
    p.add_argument("--versions", type=str, default=str(Path("rules/spec_versions.yml")),
                   help="Path to rules/spec_versions.yml")

    p.add_argument("--init", action="store_true",
                   help="Create rules/manifest.json from rules/templates/manifest_template.json")
    p.add_argument("--validate", action="store_true",
                   help="Validate manifest by schema.json")
    p.add_argument("--check", action="store_true",
                   help="Check dependencies against spec_versions.yml")

    # reserved
    p.add_argument("--graph", action="store_true", help="Show dependency graph (planned)")
    p.add_argument("--impact", action="store_true", help="Analyze impact scope (planned)")
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest)
    schema_path = Path(args.schema)
    versions_path = Path(args.versions)

    if args.init:
        template_path = Path("rules/templates/manifest_template.json")
        return cmd_init(template_path, Path("rules/manifest.json"))

    if not manifest_path.exists():
        print(f"❌ Manifest not found: {manifest_path}")
        return 1

    if args.validate:
        return cmd_validate(manifest_path, schema_path)

    if args.check:
        return cmd_check(manifest_path, versions_path)

    if args.graph:
        print("Graph view (future implementation)")
        return 0

    if args.impact:
        print("Impact analysis (future implementation)")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
