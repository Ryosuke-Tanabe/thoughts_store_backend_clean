# -*- coding: utf-8 -*-
"""
run_official_save.py
正式保存フロー（ThoughtStore → memory_map更新）

環境変数:
  GOOGLE_SERVICE_ACCOUNT_JSON  サービスアカウントJSONのパス（またはJSON文字列）
  GOOGLE_DRIVE_ROOT_ID         DriveルートフォルダID
  MEMORY_MAP_MD                memory_map.mdのパス
  JOURNAL_BASE                 journal_by_dayのベースパス（省略可）
"""
import argparse, subprocess
from pathlib import Path
from datetime import datetime, date
import sys, os
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
SRC_PATH = BASE_DIR / "src"
sys.path.append(str(SRC_PATH))

from thoughts_store.settings import SAVE_TZ
from thoughts_store.thought_store.thought_store import ThoughtStore

SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
GOOGLE_DRIVE_ROOT_ID = os.environ["GOOGLE_DRIVE_ROOT_ID"]
MEMORY_MAP_MD        = os.environ["MEMORY_MAP_MD"]
UPDATE_MEMORY_MAP_PY = str(Path(__file__).resolve().parent / "update_memory_map.py")
DEFAULT_JOURNAL_BASE = os.getenv("JOURNAL_BASE", "journal_by_day")


def resolve_target_date(date_str: str | None) -> date:
    if date_str:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    return datetime.now(ZoneInfo(SAVE_TZ)).date()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="保存対象の日付 (YYYY-MM-DD)", required=False)
    parser.add_argument("--ndjson", help="保存先NDJSONのフルパス", required=False)
    parser.add_argument("--base", help="journal_by_day のベースパス", default=DEFAULT_JOURNAL_BASE)
    args = parser.parse_args()

    target_date = resolve_target_date(args.date)
    y = f"{target_date.year}"
    m = f"{target_date.month:02d}"
    d = f"{target_date.day:02d}"

    if args.ndjson:
        ndjson_path = args.ndjson
    else:
        p = Path(args.base) / y / m / f"{y}-{m}-{d}.ndjson"
        p.parent.mkdir(parents=True, exist_ok=True)
        ndjson_path = str(p)

    print("[target]", ndjson_path)

    Path(ndjson_path).parent.mkdir(parents=True, exist_ok=True)
    if not Path(ndjson_path).exists():
        Path(ndjson_path).touch()

    store = ThoughtStore(
        service_account_json_path=SERVICE_ACCOUNT_JSON,
        root_folder_id=GOOGLE_DRIVE_ROOT_ID,
    )
    res = store.save_thought(text="", author="", save_date=target_date)
    print("[save_thought]", res)

    cmd = [sys.executable, UPDATE_MEMORY_MAP_PY, "--memory-map", MEMORY_MAP_MD, "--ndjson", ndjson_path]
    print("[update_memory_map] running:", " ".join(cmd))
    cp = subprocess.run(cmd, capture_output=True, text=True)
    print(cp.stdout or "")
    if cp.returncode != 0:
        print(cp.stderr or "")
        raise SystemExit(f"update_memory_map.py failed with code {cp.returncode}")

    print("\n✅ Official save flow completed.")


if __name__ == "__main__":
    main()
