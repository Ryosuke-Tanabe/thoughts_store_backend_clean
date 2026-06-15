from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from thoughts_store.settings import DISPLAY_TZ


def _safe_zone(name: str):
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        # よく使うTZの簡易フォールバック（最小限）
        if name in ("Asia/Tokyo", "JST", "JP"):
            return timezone(timedelta(hours=9))
        return timezone.utc


def display_time(utc_iso: str, tz: str | None = None) -> str:
    tz = tz or DISPLAY_TZ
    dt = datetime.fromisoformat(utc_iso)
    return dt.astimezone(_safe_zone(tz)).strftime("%Y-%m-%d %H:%M:%S")
