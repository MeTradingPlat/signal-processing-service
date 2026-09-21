from dataclasses import dataclass

from app.scanner.buffered_candle import BufferedCandle
from app.scanner.session_clock import session_slot


@dataclass(slots=True)
class DaySummary:
    session: int
    first: BufferedCandle
    high: float | None
    low: float | None
    volume: float


def apply_bar(summary: DaySummary | None, candle: BufferedCandle) -> DaySummary | None:
    slot = session_slot(candle.timestamp)
    if slot is None:
        return summary
    session = slot[0]
    if summary is None or summary.session != session:
        return DaySummary(session=session, first=candle, high=candle.high, low=candle.low,
                          volume=candle.volume or 0)
    if candle.high is not None and (summary.high is None or candle.high > summary.high):
        summary.high = candle.high
    if candle.low is not None and (summary.low is None or candle.low < summary.low):
        summary.low = candle.low
    summary.volume += candle.volume or 0
    return summary
