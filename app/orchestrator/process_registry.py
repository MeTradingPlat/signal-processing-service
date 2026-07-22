import logging
from multiprocessing import Process
from typing import Dict, List

logger = logging.getLogger(__name__)


class ProcessRegistry:

    def __init__(self):
        self._processes: Dict[int, Process] = {}

    def pop(self, scanner_id: int) -> Process | None:
        return self._processes.pop(scanner_id, None)

    def add(self, scanner_id: int, process: Process):
        self._processes[scanner_id] = process
        logger.info(
            "Registry: added scanner_id=%d pid=%d total_active=%d",
            scanner_id,
            process.pid,
            len(self._processes),
        )

    def remove(self, scanner_id: int):
        process = self._processes.pop(scanner_id, None)
        if process is None:
            logger.warning("Registry: scanner_id=%d not found for removal", scanner_id)
            return
        if process.is_alive():
            process.terminate()
            try:
                process.join(timeout=3)
            except AssertionError:
                pass
            logger.info(
                "Registry: terminated scanner_id=%d pid=%d",
                scanner_id,
                process.pid,
            )
        logger.info(
            "Registry: removed scanner_id=%d total_active=%d",
            scanner_id,
            len(self._processes),
        )

    def collect_completed(self) -> List[int]:
        completed = [
            sid for sid, proc in self._processes.items()
            if not proc.is_alive()
        ]
        for sid in completed:
            proc = self._processes.pop(sid)
            try:
                proc.join()
            except AssertionError:
                pass
            logger.info(
                "Registry: process completed scanner_id=%d pid=%d total_active=%d",
                sid,
                proc.pid,
                len(self._processes),
            )
        return completed

    def shutdown_all(self):
        for scanner_id in list(self._processes.keys()):
            self.remove(scanner_id)
