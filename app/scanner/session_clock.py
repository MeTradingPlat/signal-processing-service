from datetime import date, datetime
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
_SESSION_OPEN_MINUTE = 4 * 60
SESSION_SLOTS = 960


def today_et() -> date:
    return datetime.now(_ET).date()


def session_slot(ts: datetime) -> tuple[int, int] | None:
    et = ts.astimezone(_ET)
    minute = et.hour * 60 + et.minute - _SESSION_OPEN_MINUTE
    if not 0 <= minute < SESSION_SLOTS:
        return None
    return et.year * 10000 + et.month * 100 + et.day, minute
