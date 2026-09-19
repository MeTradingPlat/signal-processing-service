import logging
import os
import threading
from typing import Callable

from app.scanner.process_memory import rss_mb

logger = logging.getLogger(__name__)

_INTERVAL_SECONDS = 180.0


def start_memory_stats_loop(escaner_id: int, buffer_stats: Callable[[], tuple[int, int]],
                            interval: float = _INTERVAL_SECONDS) -> threading.Event:
    stop = threading.Event()

    def _loop() -> None:
        while not stop.wait(interval):
            buffers, candles = buffer_stats()
            logger.info(
                "MemoryStats: escaner=%d pid=%d rssMB=%.1f buffers=%d candles=%d threads=%d",
                escaner_id, os.getpid(), rss_mb(), buffers, candles, threading.active_count(),
            )

    threading.Thread(target=_loop, daemon=True, name="memory-stats").start()
    return stop
