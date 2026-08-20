import logging
import signal
import sys
import threading
import time
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


def _monitor_orchestrator(process_holder: list, child_conn):
    # process_holder es una caja mutable de 1 elemento, no un Process suelto
    # -- _shutdown() en main() lee process_holder[0] para saber a que
    # proceso mandarle la señal. Con un parametro Process comun, reasignar
    # la variable local aca adentro despues de un reinicio no cambiaba lo
    # que _shutdown() seguia viendo (closure atado al objeto ORIGINAL, ya
    # muerto) -- terminate()/join() quedaban apuntando a un proceso zombie
    # y el orquestador real (mas los escaneres que tiene activos) nunca
    # recibia la señal de apagado.
    while True:
        process_holder[0].join()
        exit_code = process_holder[0].exitcode
        logger.error(
            "Launcher: orchestrator died pid=%d exitcode=%s, restarting in %.0fs",
            process_holder[0].pid,
            exit_code,
            _RESTART_DELAY,
        )
        time.sleep(_RESTART_DELAY)
        new_process = Process(
            target=run_orchestrator,
            args=(child_conn,),
            name="orchestrator",
        )
        new_process.start()
        process_holder[0] = new_process
        logger.info("Launcher: orchestrator restarted pid=%d", new_process.pid)


def main():
    _setup_logging()

    from app.adapters.readiness import wait_for_dependencies
    logger.info("Launcher: waiting for scanner-management and marketdata to be reachable...")
    wait_for_dependencies()

    parent_conn, child_conn = Pipe()

    orchestrator_process = Process(
        target=run_orchestrator,
        args=(child_conn,),
        name="orchestrator",
    )
    orchestrator_process.start()
    logger.info("Launcher: orchestrator spawned pid=%d", orchestrator_process.pid)

    process_holder = [orchestrator_process]
    monitor_thread = threading.Thread(
        target=_monitor_orchestrator,
        args=(process_holder, child_conn),
        daemon=True,
    )
    monitor_thread.start()

    def _shutdown(signum, frame):
        logger.info("Launcher: received signal %d, shutting down", signum)
        process_holder[0].terminate()
        process_holder[0].join(timeout=5)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    app = create_app(parent_conn)

    logger.info("Launcher: starting HTTP API on %s:%d", settings.http_host, settings.http_port)
    uvicorn.run(app, host=settings.http_host, port=settings.http_port, log_level=settings.log_level.lower())


if __name__ == "__main__":
    main()
