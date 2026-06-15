# -*- coding: utf-8 -*-
# thought_store.py (fixed)
import io, json, hashlib, datetime as dt
import os, tempfile, random
from typing import Optional, Dict, Any, List, Tuple
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from google.oauth2.service_account import Credentials
from typing import Union

UTC = dt.timezone.utc


def utc_now_iso() -> str:
    return dt.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


class ThoughtStore:
    """
    Google Drive に思想(thought)を NDJSON 追記で保存するストア。
    - 保存先: <ROOT_FOLDER>/<YYYY>/<MM>/<YYYY-MM-DD>.ndjson
    - 連鎖: prev_hash -> hash の一方向鎖を強制
    - 冪等: 同一 hash の重複保存を拒否
    """

    def __init__(
        self,
        service_account_json_path: Optional[str] = None,
        root_folder_id: Optional[str] = None,
        scopes: Optional[List[str]] = None,
    ):
        # If args are omitted, read from environment:
        # - GOOGLE_SERVICE_ACCOUNT_JSON: path to SA json or raw JSON string
        # - GOOGLE_DRIVE_ROOT_ID: root folder id
        scopes = scopes or ["https://www.googleapis.com/auth/drive"]
        service_account_json_path = service_account_json_path or os.getenv(
            "GOOGLE_SERVICE_ACCOUNT_JSON"
        )
        root_folder_id = root_folder_id or os.getenv("GOOGLE_DRIVE_ROOT_ID")
        if not service_account_json_path or not root_folder_id:
            raise ValueError(
                "Missing creds or root. Set GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_DRIVE_ROOT_ID, or pass args."
            )
        # Allow raw JSON injected via env; persist to a temp file for the SDK
        if service_account_json_path.strip().startswith("{"):
            tmpf = tempfile.NamedTemporaryFile(delete=False, suffix="_sa.json")
            tmpf.write(service_account_json_path.encode("utf-8"))
            tmpf.flush()
            service_account_json_path = tmpf.name
        creds = Credentials.from_service_account_file(
            service_account_json_path, scopes=scopes
        )
        self.drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        self.root = root_folder_id

    # ---------- Drive utilities ----------
    def _ensure_folder(self, name: str, parent_id: str) -> str:
        q = (
            "mimeType='application/vnd.google-apps.folder' and "
            f"name='{name}' and '{parent_id}' in parents and trashed=false"
        )
        res = (
            self.drive.files()
            .list(
                q=q,
                spaces="drive",
                fields="files(id,name)",
                includeItemsFromAllDrives=True,  # ★追加
                supportsAllDrives=True,  # ★追加
                corpora="allDrives",  # ★追加（推奨）
            )
            .execute()
        )
        if res.get("files"):
            return res["files"][0]["id"]

        meta = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = (
            self.drive.files()
            .create(body=meta, fields="id", supportsAllDrives=True)  # ★追加
            .execute()
        )
        return folder["id"]

    def _find_file(self, name: str, parent_id: str) -> Optional[str]:
        q = f"name='{name}' and '{parent_id}' in parents and trashed=false"
        res = (
            self.drive.files()
            .list(
                q=q,
                spaces="drive",
                fields="files(id,name)",
                includeItemsFromAllDrives=True,  # ★共有ドライブを見る
                supportsAllDrives=True,  # ★共有ドライブ対応
                corpora="allDrives",  # ★検索対象を全ドライブに
            )
            .execute()
        )
        files = res.get("files", [])
        return files[0]["id"] if files else None

    def _download_text(self, file_id: str) -> str:
        req = self.drive.files().get_media(fileId=file_id, supportsAllDrives=True)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, req)
        done = False
        while not done:
            _status, done = downloader.next_chunk()
        buf.seek(0)
        return buf.read().decode("utf-8")

    def _upload_text_new(self, parent_id: str, name: str, text: str) -> str:
        meta = {"name": name, "parents": [parent_id]}
        media = MediaIoBaseUpload(
            io.BytesIO(text.encode("utf-8")),
            mimetype="application/x-ndjson",
            resumable=True,
        )
        created = (
            self.drive.files()
            .create(
                body=meta,
                media_body=media,
                fields="id",
                supportsAllDrives=True,  # ★追加
            )
            .execute()
        )
        return created["id"]

    def _update_text(self, file_id: str, text: str) -> None:
        media = MediaIoBaseUpload(
            io.BytesIO(text.encode("utf-8")),
            mimetype="application/x-ndjson",
            resumable=True,
        )
        self.drive.files().update(
            fileId=file_id,
            media_body=media,
            supportsAllDrives=True,  # ★追加
        ).execute()

    # ---------- Chain helpers ----------
    @staticmethod
    def _parse_last_line(
        ndjson_text: str,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        if not ndjson_text.strip():
            return None, None
        *_, last = ndjson_text.strip().splitlines()
        try:
            obj = json.loads(last)
            return obj, last
        except Exception:
            return None, last

    @staticmethod
    def _build_record(
        text: str,
        author: str,
        prev_hash: Optional[str],
        record: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        v1.3.4準拠: record引数を追加し、ハッシュ連鎖に含める
        """
        t_utc = utc_now_iso()
        # ハッシュ計算用のペイロード構築
        payload_obj = {
            "t_utc": t_utc,
            "prev_hash": prev_hash,
            "record": (
                record if record else {"text": text}
            ),  # recordがない場合は互換性のためtextを入れる
        }
        payload_for_hash = json.dumps(
            payload_obj,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,  # キー順を固定してハッシュの不一致を防ぐ
        )

        h = sha256_hex(payload_for_hash)
        return {
            "id": h[:12],
            "t_utc": t_utc,
            "author": author,
            "prev_hash": prev_hash,
            "hash": h,
            "algo": "sha256({t_utc,prev_hash,record})",
            "v": 1,
            "record": record if record else payload_obj["record"],
        }

    # ---------- Public API ----------
    def save_thought(
        self,
        text: str,
        author: str,
        save_date: Optional[Union[str, dt.date]] = None,
        record: Optional[Dict[str, Any]] = None,  # ★引数を追加
    ) -> Dict[str, Any]:
        """
        Official save flow (primary Thought only).
        Gravity Freeze Policy:
        - MUST NOT read/write/init gravity files.
        - MUST NOT compute center_gravity/assignments/etc.
        - keep gravity_refs=[] for compatibility.
        """

        # 1) path resolve
        if save_date is None:
            now = dt.datetime.now(UTC)
            yyyy = f"{now.year:04d}"
            mm = f"{now.month:02d}"
            ymd = f"{now.year:04d}-{now.month:02d}-{now.day:02d}"
        else:
            if isinstance(save_date, str):
                ymd = save_date.strip()
                parts = ymd.split("-")
                if len(parts) != 3 or any(not p.isdigit() for p in parts):
                    raise ValueError(
                        f"save_date must be YYYY-MM-DD, got: {save_date!r}"
                    )
                yyyy, mm, _ = parts
            else:
                yyyy = f"{save_date.year:04d}"
                mm = f"{save_date.month:02d}"
                ymd = f"{save_date.year:04d}-{save_date.month:02d}-{save_date.day:02d}"

        year_id = self._ensure_folder(yyyy, self.root)
        month_id = self._ensure_folder(mm, year_id)
        filename = f"{ymd}.ndjson"

        # 2) get current text & last record
        file_id = self._find_file(filename, month_id)
        current = ""
        if file_id:
            for attempt in range(3):
                try:
                    current = self._download_text(file_id)
                    break
                except Exception:
                    import time as _t

                    _t.sleep((0.5 + 0.2 * random.random()) * (2**attempt))

        last_obj, _ = self._parse_last_line(current)
        prev_hash = last_obj.get("hash") if last_obj else None

        # ★ _build_record 呼び出し時に record を渡す
        record_obj = self._build_record(
            text=text, author=author, prev_hash=prev_hash, record=record
        )

        # idempotency (record_obj を使用)
        if last_obj and last_obj.get("hash") == record_obj["hash"]:
            if file_id is None:
                file_id = self._find_file(filename, month_id)
            return {
                "status": "noop",
                "file": filename,
                "file_id": file_id,  # ★追加
                "hash": record_obj["hash"],
                "prev_hash": record_obj["prev_hash"],
            }

        # 3) append 用の文字列生成（ここで確実に record_obj をシリアライズする）
        serialized_record = json.dumps(record_obj, ensure_ascii=False)
        new_text = (
            (current + ("\n" if current and not current.endswith("\n") else ""))
            + serialized_record
            + "\n"
        )

        def try_commit():
            nonlocal file_id

            # 1. ファイルを再検索
            file_id = self._find_file(filename, month_id)

            if file_id is None:
                # 新規作成
                file_id = self._upload_text_new(month_id, filename, new_text)
                return record_obj  # 👈 OK
            else:
                # 既存ファイルあり
                latest_content = self._download_text(file_id)
                if not latest_content.strip():
                    # 0KB の場合は上書きして終了
                    self._update_text(file_id, new_text)
                    return record_obj  # 👈 ここが重要！

                # 既存の中身がある場合のマージ処理
                latest_last, _ = self._parse_last_line(latest_content)
                latest_prev = latest_last.get("hash") if latest_last else None

                if latest_prev != prev_hash:
                    # コンフリクト（マージ）
                    fixed = self._build_record(
                        text=text, author=author, prev_hash=latest_prev, record=record
                    )
                    merged = (
                        latest_content.rstrip()
                        + "\n"
                        + json.dumps(fixed, ensure_ascii=False)
                        + "\n"
                    )
                    self._update_text(file_id, merged)
                    return fixed  # 👈 OK
                else:
                    # 通常追記
                    self._update_text(file_id, new_text)
                    return record_obj

        # commit loop
        for attempt in range(3):
            try:
                committed = try_commit()
                saved = committed if isinstance(committed, dict) else record_obj

                return {
                    "status": "ok",
                    "file": filename,
                    "file_id": file_id,
                    "hash": saved["hash"],
                    "prev_hash": saved["prev_hash"],
                }

            except Exception as e:
                print("save_thought retryable error:", repr(e))
                import time as _t

                _t.sleep((0.7 + 0.3 * random.random()) * (2**attempt))

        raise RuntimeError("Failed to save thought after retries.")


# NOTE: Legacy standalone helpers and save_thought() have been removed.
# The class-based implementation above is the single source of truth.
