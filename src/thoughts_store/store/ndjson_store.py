# src/thoughts_store/store/ndjson_store.py
import os, portalocker, orjson
from pathlib import Path
from typing import Iterable, Iterator
from thoughts_store.util.hashing import compute_record_hash


class NdjsonStore:
    def __init__(self, journal_path: str):
        self.path = Path(journal_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def iter_records(self) -> Iterator[dict]:
        if self.path.stat().st_size == 0:
            return iter(())
        with self.path.open("rb") as f:
            for line in f:
                if line.strip():
                    yield orjson.loads(line)

    def _tail_record_hash(self) -> str | None:
        tail = None
        for rec in self.iter_records():
            tail = rec.get("record_hash")
        return tail

    def append(self, record: dict) -> dict:
        prev = self._tail_record_hash()
        record["prev_hash"] = prev
        record["record_hash"] = compute_record_hash(record)
        # 排他ロックして追記
        with portalocker.Lock(self.path, mode="ab", flags=portalocker.LOCK_EX) as f:
            f.write(orjson.dumps(record))
            f.write(b"\n")
        return record

    def verify_chain(self) -> bool:
        prev = None
        for rec in self.iter_records():
            # prev_hash チェック
            if rec.get("prev_hash") != prev:
                return False
            # record_hash チェック
            calc = compute_record_hash(rec)
            if rec.get("record_hash") != calc:
                return False
            prev = rec.get("record_hash")
        return True

    def rebuild_to(self, output_path: str) -> str:
        """
        現在のファイルを読み、prev_hash/record_hash を再計算して
        別ファイルに書き出す（元ファイルは不変）。戻り値は出力パス。
        """
        from pathlib import Path

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        prev = None
        with out.open("wb") as w:
            for rec in self.iter_records():
                # 既存の prev_hash/record_hash は無視して上書き
                rec["prev_hash"] = prev
                rec["record_hash"] = compute_record_hash(rec)
                w.write(orjson.dumps(rec))
                w.write(b"\n")
                prev = rec["record_hash"]
        return str(out)
