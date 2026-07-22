import logging
import signal
import sys
import threading
from multiprocessing import Pipe, Process

import uvicorn

from app.api.server import create_app
from app.config import settings
from app.orchestrator.runtime import run_orchestrator

logger = logging.getLogger(__name__)

_RESTART_DELAY = 2.0


def _setup_logging():
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )


def _monitor_orchestrator(orchestrator_process: Process, child_conn):
    while True:
        orchestrator_process.join()
        exit_code = orchestrator_process.exitcode
        logger.error(
            "Launcher: orchestrator died pid=%d exitcode=%s, restarting in %.0fs",
            orchestrator_process.pid,
            exit_code,
            _RESTART_DELAY,
        )
        orchestrator_process = Process(
            target=run_orchestrator,
            args=(child_conn,),
            name="orchestrator",
        )
        orchestrator_process.start()
        logger.info("Launcher: orchestrator restarted pid=%d", orchestrator_process.pid)


def main():
    _setup_logging()

    parent_conn, child_conn = Pipe()

    orchestrator_process = Process(
        target=run_orchestrator,
        args=(child_conn,),
        name="orchestrator",
    )
    orchestrator_process.start()
    logger.info("Launcher: orchestrator spawned pid=%d", orchestrator_process.pid)

    monitor_thread = threading.Thread(
        target=_monitor_orchestrator,
        args=(orchestrator_process, child_conn),
        daemon=True,
    )
    monitor_thread.start()

    def _shutdown(signum, frame):
        logger.info("Launcher: received signal %d, shutting down", signum)
        orchestrator_process.terminate()
        orchestrator_process.join(timeout=5)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    app = create_app(parent_conn)

    logger.info("Launcher: starting HTTP API on %s:%d", settings.http_host, settings.http_port)
    uvicorn.run(app, host=settings.http_host, port=settings.http_port, log_level=settings.log_level.lower())


if __name__ == "__main__":
    main()
