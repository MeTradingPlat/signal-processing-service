from array import array
from dataclasses import dataclass
from datetime import datetime

from app.scanner.session_clock import session_slot


@dataclass(slots=True)
class VolumeProfile:
    slot_minutes: int
    cumulative: array

    def expected_through(self, bar_start: datetime) -> float | None:
        slot = session_slot(bar_start)
        if slot is None:
            return None
        index = slot[1] // self.slot_minutes
        if index >= len(self.cumulative):
            return None
        return self.cumulative[index]


def profile_from_response(raw: dict) -> VolumeProfile:
    return VolumeProfile(slot_minutes=raw["slotMinutes"], cumulative=array("f", raw["cumulative"]))
