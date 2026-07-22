import logging
from multiprocessing.connection import Connection

from app.ipc.receiver import PipeReceiver
from app.orchestrator.dispatcher import Dispatcher
from app.orchestrator.process_registry import ProcessRegistry
from app.scanner.runner_completion import publish_scanner_completed

logger = logging.getLogger(__name__)

_POLL_SECONDS = 0.5


def run_orchestrator(connection: Connection):
    receiver = PipeReceiver(connection)
    registry = ProcessRegistry()
    dispatcher = Dispatcher(registry)

    _sync_active_scanners(registry)

    logger.info("Orchestrator: waiting for events on pipe")

    try:
        while True:
            message = receiver.poll(_POLL_SECONDS)
            if message is not None:
                logger.info("Orchestrator: received event type='%s'", message.type)
                dispatcher.dispatch(message)
            _check_completed(registry)
    except EOFError:
        logger.info("Orchestrator: pipe closed, shutting down")
    except KeyboardInterrupt:
        logger.info("Orchestrator: interrupted, shutting down")
    finally:
        registry.shutdown_all()
        receiver.close()
        logger.info("Orchestrator: stopped")


def _sync_active_scanners(registry: ProcessRegistry):
    from multiprocessing import Process
    from app.adapters.scanner_management_client import ScannerManagementClient
    from app.scanner.runner import run_scanner

    client = ScannerManagementClient()
    active = client.get_active_scanners()
    for escaner in active:
        process = Process(target=run_scanner, args=(escaner,), daemon=True)
        process.start()
        registry.add(escaner.idEscaner, process)
        logger.info("Sync: restored scanner id=%d name='%s' pid=%d",
                     escaner.idEscaner, escaner.nombre, process.pid)


def _check_completed(registry: ProcessRegistry):
    completed = registry.collect_completed()
    for scanner_id in completed:
        from app.adapters.scanner_management_client import ScannerManagementClient
        ScannerManagementClient().notify_scanner_stopped(scanner_id)
        publish_scanner_completed(scanner_id)

