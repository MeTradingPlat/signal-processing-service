import logging
import time
from typing import Callable, Iterable

logger = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS = 600.0


class SignalBaseline:
    def __init__(self, signaled_today: set[str] | None = None, ttl_seconds: float = _DEFAULT_TTL_SECONDS,
                 clock: Callable[[], float] = time.monotonic):
        self._pending = set(signaled_today or ())
        self._deadline = clock() + ttl_seconds
        self._clock = clock

    @classmethod
    def load(cls, log_client, scanner_id: int, enabled: bool) -> "SignalBaseline":
        if not enabled:
            return cls()
        try:
            signaled = log_client.get_signaled_today(scanner_id)
        except Exception as e:
            logger.warning("SignalBaseline: signaled-today unavailable, restart may republish current signals: %s", e)
            return cls()
        logger.info("SignalBaseline: %d symbols already signaled today for scanner %d", len(signaled), scanner_id)
        return cls(signaled)

    def consume(self, symbol: str) -> bool:
        if self._clock() > self._deadline:
            self._pending.clear()
        if symbol not in self._pending:
            return False
        self._pending.discard(symbol)
        return True

    def consume_all(self, symbols: Iterable[str]) -> set[str]:
        return {symbol for symbol in list(symbols) if self.consume(symbol)}

    def expire(self) -> None:
        self._pending.clear()
