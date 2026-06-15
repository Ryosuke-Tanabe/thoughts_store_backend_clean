# -*- coding: utf-8 -*-
import json
import os
import sys
import datetime
from typing import Optional
import subprocess
import re
from pathlib import Path

# ===== T0172 SSOT Quarantine Layer =====


class QuarantineError(Exception):
    def __init__(self, code, rule, where, what, how_to_fix, snippet=None):
        self.code = code
        self.rule = rule
        self.where = where
        self.what = what
        self.how_to_fix = how_to_fix
        self.snippet = snippet
        super().__init__(f"[{code}] {what}")


def _safe_snippet(s: str, max_len: int = 180) -> str:
    s = s.replace("\r", "\\r").replace("\n", "\\n")
    return s[:max_len] + ("..." if len(s) > max_len else "")


def print_quarantine_error(e: QuarantineError) -> None:
    print(f"❌ [{e.code}]")
    print(f"Rule : {e.rule}")
    print(f"Where: {e.where}")
    print(f"What : {e.what}")
    print("Fix  :")
    for i, step in enumerate(e.how_to_fix, 1):
        print(f"  {i}) {step}")
    if e.snippet:
        print("Snippet:")
        print(f"  {e.snippet}")


def quarantine_parse_and_validate(raw_input: str) -> dict:
    """
    SSOT検疫（入口で不純物を遮断）:
    - 禁止トークン
    - JSON構文（Extra data含む）
    - top-level object
    - author 必須（一般向け前提）
    - text 必須（空保存防止）
    - thread_event の最低限整合（phase/tags/thread/date）
    - date_local 実在日付
    """
    if not raw_input.strip():
        raise QuarantineError(
            code="E1001 NDJSON_EMPTY_INPUT",
            rule="Input must not be empty",
            where="stdin",
            what="empty input",
            how_to_fix=["Paste a single JSON object (no blank input)."],
        )

    forbidden = ["\ufeff", "...", "START_LOG_JSON", "Next JSON Wait", "DEBUG"]
    for tok in forbidden:
        if tok in raw_input:
            raise QuarantineError(
                code="E1005 NDJSON_FORBIDDEN_TOKEN",
                rule="Forbidden token must not appear in saved JSON (Launcher preflight rule).",
                where="stdin / before json.loads",
                what=f'forbidden token detected: "{tok}"',
                how_to_fix=[
                    "Paste ONLY the JSON object (no prompts/logs/ellipsis).",
                    "Remove DEBUG/Next JSON Wait/BOM/ellipsis from the pasted text.",
                    "Re-run Preflight and paste again.",
                ],
                snippet=_safe_snippet(raw_input),
            )

    try:
        data = json.loads(raw_input)
    except json.JSONDecodeError as je:
        code = (
            "E1004 NDJSON_EXTRA_DATA"
            if "Extra data" in str(je)
            else "E1003 NDJSON_JSON_DECODE_ERROR"
        )
        raise QuarantineError(
            code=code,
            rule="NDJSON must be exactly one JSON object (no concatenation, no prefixes).",
            where=f"stdin / json.loads (pos={je.pos})",
            what=str(je),
            how_to_fix=[
                "Ensure you pasted exactly ONE JSON object.",
                "Remove any extra text before/after JSON (including a second JSON).",
                "If you copied from chat, copy the JSON block only.",
            ],
            snippet=_safe_snippet(raw_input),
        )

    if not isinstance(data, dict):
        raise QuarantineError(
            code="E1002 NDJSON_NOT_OBJECT",
            rule="Top-level JSON must be an object.",
            where="stdin / after json.loads",
            what=f"got {type(data).__name__}",
            how_to_fix=["Paste a JSON object like { ... } (not a list/string/number)."],
            snippet=_safe_snippet(raw_input),
        )

    # author 必須（一般向け）
    record = data.get("record") if isinstance(data.get("record"), dict) else None

    author = data.get("author") or (record.get("author") if record else None)

    if not author or not isinstance(author, str) or not author.strip():
        raise QuarantineError(
            code="E3006 AUTHOR_MISSING",
            rule="author must be explicitly specified (no hardcoded personal fallback).",
            where="author / record.author",
            what="author is missing or empty",
            how_to_fix=[
                'Add "author": "<your_name_or_id>" to the JSON (top-level recommended).',
                'Or add "author" inside "record".',
                "Re-run Preflight and paste again.",
            ],
            snippet=_safe_snippet(raw_input),
        )

    # text 必須（空保存防止）
    text = data.get("text") or (record.get("text") if record else None)
    if text is None or not isinstance(text, str) or not text.strip():
        raise QuarantineError(
            code="E1010 TEXT_EMPTY",
            rule="text must not be empty (prevents empty-body save accidents).",
            where="text / record.text",
            what="text is missing or empty",
            how_to_fix=[
                'Add non-empty "text" (or record.text).',
                "Re-run Preflight and paste again.",
            ],
            snippet=_safe_snippet(raw_input),
        )

    # date_local 実在日付（threadにあれば）
    if record:
        thread = (
            record.get("thread") if isinstance(record.get("thread"), dict) else None
        )
        if thread:
            dl = thread.get("date_local")
            if isinstance(dl, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", dl):
                try:
                    datetime.date.fromisoformat(dl)
                except ValueError:
                    raise QuarantineError(
                        code="E3002 DATE_NONEXISTENT",
                        rule='format:"date" must be a real calendar date',
                        where="record.thread.date_local",
                        what=f'"{dl}" is not a real date',
                        how_to_fix=[
                            "Fix date_local to an existing date (YYYY-MM-DD).",
                            "Re-run Preflight and paste again.",
                        ],
                        snippet=f'"date_local":"{dl}"',
                    )

    # thread_event の最低限（一般向けSSOTの核）
    if data.get("type") == "thread_event":
        if not record:
            raise QuarantineError(
                code="E3004 THREAD_EVENT_MISSING_RECORD",
                rule="thread_event must include record object.",
                where="record",
                what="record is missing",
                how_to_fix=["Include record: { ... } for thread_event."],
                snippet=_safe_snippet(raw_input),
            )
        thread = (
            record.get("thread") if isinstance(record.get("thread"), dict) else None
        )
        if not thread:
            raise QuarantineError(
                code="E3004 THREAD_EVENT_MISSING_THREAD",
                rule="thread_event must include record.thread object.",
                where="record.thread",
                what="record.thread is missing",
                how_to_fix=[
                    "Include record.thread: {thread_id, phase, date_local, ...}."
                ],
                snippet=_safe_snippet(raw_input),
            )
        phase = thread.get("phase")
        if phase not in ("start", "update", "end"):
            raise QuarantineError(
                code="E3003 THREAD_PHASE_INVALID",
                rule='record.thread.phase must be one of ["start","update","end"].',
                where="record.thread.phase",
                what=f"invalid phase: {phase!r}",
                how_to_fix=['Set record.thread.phase to "start" or "update" or "end".'],
                snippet=_safe_snippet(raw_input),
            )
        tags = record.get("tags")
        if (
            not isinstance(tags, list)
            or not tags
            or not all(isinstance(t, str) and t.strip() for t in tags)
        ):
            raise QuarantineError(
                code="E2011 TAGS_INVALID",
                rule="record.tags must be a non-empty list of non-empty strings.",
                where="record.tags",
                what="tags missing/empty/invalid",
                how_to_fix=[
                    'Set record.tags like ["T0172","UpdateLog",...].',
                ],
                snippet=_safe_snippet(raw_input),
            )

    return data


# パス設定
sys.path.append(str(Path(__file__).resolve().parent.parent))
try:
    from thought_store.thought_store import ThoughtStore
except ImportError:
    print("❌ thought_store.py が見つかりません。")
    sys.exit(1)


def run_bridge():
    from dotenv import load_dotenv

    current_dir = Path(__file__).resolve().parent
    env_dir = current_dir.parent.parent.parent
    env_path = env_dir / ".env"
    load_dotenv(dotenv_path=env_path)

    # 秘密鍵パスの自動補正
    key_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if key_path:
        os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"] = str(
            env_dir / "secrets" / Path(key_path).name
        )

    store = ThoughtStore()
    update_memory_map_py = env_dir / "update_memory_map.py"

    print("=== Thoughts Store Bridge ===")
    print("JSON を 1 行で貼り付けて Enter。JSON 以外を混入させない。")

    while True:
        try:
            lines = []
            while True:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
                if not line:
                    break

            raw_input = "".join(lines).strip()
            if not raw_input:
                continue

            # ===== T0172 Quarantine START =====
            try:
                data = quarantine_parse_and_validate(raw_input)
            except QuarantineError as qe:
                print_quarantine_error(qe)
                print("-" * 45)
                continue
            # ===== T0172 Quarantine END =====

            # --- Extract record / author / text / date_local robustly ---
            record = (
                data.get("record") if isinstance(data.get("record"), dict) else None
            )
            author = data.get("author") or (record.get("author") if record else None)

            text = data.get("text") or (record.get("text") if record else "") or ""

            date_local: Optional[str] = None
            if record:
                thread = (
                    record.get("thread")
                    if isinstance(record.get("thread"), dict)
                    else {}
                )
                dl = thread.get("date_local")
                if isinstance(dl, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", dl):
                    datetime.date.fromisoformat(dl)
                    date_local = dl

            # 1. 思想としての保存（record構造体を含めて保存）
            # store.save_thought が内部で record を扱えるよう、data全体またはrecordを渡す
            result = store.save_thought(
                text=text,
                author=author,
                save_date=date_local,  # ★date_local があればそれに保存先を固定
                record=record,  # ★リッチな構造体
            )
            print(f"✅ Thought saved. Hash: {result['hash'][:8]}")

            # ==== v1.5.0-final: 保存＝即時 Full Rebuild ====
            try:
                # bridge/ → thoughts_store/ → ssot/
                anchor_path = (
                    Path(__file__).resolve().parent.parent
                    / "ssot"
                    / "skilldays_v150_final_anchor.py"
                )

                subprocess.run(
                    [sys.executable, str(anchor_path)],
                    check=True,
                    cwd=Path(__file__).resolve().parent.parent.parent.parent,
                )

                print("🔁 Full Rebuild completed (v1.5.0-final).")

            except subprocess.CalledProcessError as e:
                print(f"⚠️ Full Rebuild failed: {e}")
            # ==================================================

            # --- DEBUG: Drive上の実体を確認 ---
            try:
                meta = (
                    store.drive.files()
                    .get(
                        fileId=result["file_id"],
                        fields="id,name,size,parents,modifiedTime",
                        supportsAllDrives=True,
                    )
                    .execute()
                )
                print(
                )
                root_meta = (
                    store.drive.files()
                    .get(
                        fileId=store.root,
                        fields="id,name",
                        supportsAllDrives=True,
                    )
                    .execute()
                )
                print(
                )
            except Exception as e:

        except Exception as e:
            print(f"❌ Error: {e}")


if __name__ == "__main__":
    try:
        run_bridge()
    except KeyboardInterrupt:
        print("\n👋 Bridge を終了しました。")
        sys.exit(0)
