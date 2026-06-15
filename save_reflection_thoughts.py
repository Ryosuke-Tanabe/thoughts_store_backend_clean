# save_reflection_thoughts.py
import argparse
from pathlib import Path
import shutil


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--base-dir", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--date", required=True)
    p.add_argument(
        "--no-backup-guard",
        action="store_true",
        help="allow overwrite even if backup exists",
    )
    return p.parse_args()


def main():
    args = parse_args()

    base = Path(args.base_dir)
    src = Path(args.source)
    if not src.exists():
        print(f"[save_reflection] source not found: {src}")
        return 1

    yyyy, mm, _dd = args.date.split("-")
    target = base / "thoughts" / "journal_by_day" / yyyy / mm / f"{args.date}.ndjson"
    if not target.exists():
        print(f"[save_reflection] target not found: {target}")
        return 1

    # backup (guard)
    backup = target.with_suffix(".ndjson.ref_backup")
    if backup.exists() and not args.no_backup_guard:
        print(f"[save_reflection] backup already exists (guard stop): {backup}")
        print("[save_reflection] If you really want to proceed, pass --no-backup-guard")
        return 1

    shutil.copy2(target, backup)
    print(f"[save_reflection] backup: {backup}")

    # read all lines first (reduce partial append risk)
    to_append = []
    with src.open("r", encoding="utf-8") as in_f:
        for line in in_f:
            line = line.strip()
            if line:
                to_append.append(line)

    if not to_append:
        print("[save_reflection] source had no non-empty lines; nothing appended.")
        return 0

    with target.open("a", encoding="utf-8") as out_f:
        out_f.write("\n".join(to_append) + "\n")

    print(f"[save_reflection] appended {len(to_append)} line(s) to: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
