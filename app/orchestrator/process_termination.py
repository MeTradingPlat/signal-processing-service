import logging
from multiprocessing import Process

logger = logging.getLogger(__name__)


def terminate_and_reap(process: Process, timeout: float) -> None:
    process.terminate()
    try:
        process.join(timeout=timeout)
    except AssertionError:
        pass
    if process.is_alive():
        logger.warning(
            "ProcessTermination: pid=%s ignored SIGTERM after %.0fs, sending SIGKILL",
            process.pid,
            timeout,
        )
        process.kill()
        try:
            process.join(timeout=3)
        except AssertionError:
            pass
