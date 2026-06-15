import hashlib, orjson


def canonical_bytes(obj: dict) -> bytes:
    # record_hash 自身は除外してソート済JSONへ
    data = {k: v for k, v in obj.items() if k != "record_hash"}
    return orjson.dumps(data, option=orjson.OPT_SORT_KEYS)


def sha256_hex(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def compute_record_hash(record: dict) -> str:
    return sha256_hex(canonical_bytes(record))
