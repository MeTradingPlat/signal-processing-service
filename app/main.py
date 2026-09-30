import logging
import signal
import sys
import threading
import time
from multiprocessing import Manager, Pipe, Process

import uvicorn

from app.api.server import create_app
from app.config import settings
from app.marketfeed.service import run_market_feed
from app.orchestrator.process_termination import terminate_and_reap
from app.orchestrator.runtime import run_orchestrator

logger = logging.getLogger(__name__)

_RESTART_DELAY = 2.0


def _setup_logging():
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )


def _spawn_orchestrator(child_conn) -> Process:
    process = Process(target=run_orchestrator, args=(child_conn,), name="orchestrator")
    process.start()
    return process


def _monitor_orchestrator(process_holder: list, child_conn, spawn=_spawn_orchestrator,
                          restart_delay: float | None = None, stop: threading.Event | None = None):
    # process_holder es una caja mutable de 1 elemento, no un Process suelto
    # -- _shutdown() en main() lee process_holder[0] para saber a que
    # proceso mandarle la señal. Con un parametro Process comun, reasignar
    # la variable local aca adentro despues de un reinicio no cambiaba lo
    # que _shutdown() seguia viendo (closure atado al objeto ORIGINAL, ya
    # muerto) -- terminate()/join() quedaban apuntando a un proceso zombie
    # y el orquestador real (mas los escaneres que tiene activos) nunca
    # recibia la señal de apagado.
    delay = _RESTART_DELAY if restart_delay is None else restart_delay
    while stop is None or not stop.is_set():
        process_holder[0].join()
        if stop is not None and stop.is_set():
            return
        exit_code = process_holder[0].exitcode
        logger.error(
            "Launcher: orchestrator died pid=%d exitcode=%s, restarting in %.0fs",
            process_holder[0].pid,
            exit_code,
            delay,
        )
        time.sleep(delay)
        new_process = spawn(child_conn)
        process_holder[0] = new_process
        logger.info("Launcher: orchestrator restarted pid=%d", new_process.pid)


def _spawn_market_feed(fundamentals_cache, snapshot_cache) -> Process:
    process = Process(
        target=run_market_feed, args=(fundamentals_cache, snapshot_cache), name="market-feed", daemon=True,
    )
    process.start()
    return process


def _monitor_market_feed(process_holder: list, fundamentals_cache, snapshot_cache,
                         restart_delay: float | None = None, stop: threading.Event | None = None):
    """Mismo patron que _monitor_orchestrator (reinicia si muere), pero
    separado en vez de generalizar: spawn() de cada uno necesita argumentos
    distintos (child_conn vs las dos caches) y _monitor_orchestrator ya
    tiene tests propios atados a su firma actual."""
    delay = _RESTART_DELAY if restart_delay is None else restart_delay
    while stop is None or not stop.is_set():
        process_holder[0].join()
        if stop is not None and stop.is_set():
            return
        logger.error("Launcher: market-feed died pid=%d exitcode=%s, restarting in %.0fs",
                     process_holder[0].pid, process_holder[0].exitcode, delay)
        time.sleep(delay)
        process_holder[0] = _spawn_market_feed(fundamentals_cache, snapshot_cache)
        logger.info("Launcher: market-feed restarted pid=%d", process_holder[0].pid)


def main():
    _setup_logging()

    from app.adapters.readiness import wait_for_dependencies
    logger.info("Launcher: waiting for scanner-management and marketdata to be reachable...")
    wait_for_dependencies()

    # fundamentals_cache/snapshot_cache: memoria compartida entre TODOS los
    # procesos (orquestador, cada escaner, y este mismo) -- un solo feed
    # mantiene el universo completo al dia (ver run_market_feed), cada
    # escaner solo LEE de aca en vez de pedir lo mismo por REST (Fase 2 del
    # rediseño por eventos). manager.dict() es un proxy picklable: se puede
    # pasar como argumento a Process() igual que cualquier otro valor.
    manager = Manager()
    fundamentals_cache = manager.dict()
    snapshot_cache = manager.dict()

    market_feed_process = _spawn_market_feed(fundamentals_cache, snapshot_cache)
    logger.info("Launcher: market-feed spawned pid=%d", market_feed_process.pid)
    market_feed_holder = [market_feed_process]
    market_feed_monitor = threading.Thread(
        target=_monitor_market_feed,
        args=(market_feed_holder, fundamentals_cache, snapshot_cache),
        daemon=True,
    )
    market_feed_monitor.start()

    parent_conn, child_conn = Pipe()

    orchestrator_process = Process(
        target=run_orchestrator,
        args=(child_conn, fundamentals_cache, snapshot_cache),
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
        terminate_and_reap(process_holder[0], timeout=5)
        terminate_and_reap(market_feed_holder[0], timeout=5)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    app = create_app(parent_conn)

    logger.info("Launcher: starting HTTP API on %s:%d", settings.http_host, settings.http_port)
    uvicorn.run(app, host=settings.http_host, port=settings.http_port, log_level=settings.log_level.lower())


if __name__ == "__main__":
    main()
