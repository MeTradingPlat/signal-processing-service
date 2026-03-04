"""Gestor del ciclo de vida de todos los procesos del servicio.

ProcessManager crea y mantiene:
  - Un KafkaPublisherProcess (proceso unico para publicacion Kafka)
  - Un ScannerProcess por cada escaner activo

Todos los ScannerProcess comparten la misma multiprocessing.Queue
para enviar mensajes al KafkaPublisherProcess.
"""

import logging
import multiprocessing
import sys

from domain.models.escaner import Escaner

logger = logging.getLogger(__name__)


class ProcessManager:
    """Gestiona el ciclo de vida de los procesos del servicio."""

    def __init__(self):
        # Queue compartida: ScannerProcess -> KafkaPublisherProcess
        self._signal_queue: multiprocessing.Queue = multiprocessing.Queue()
        # {id_escaner: ScannerProcess}
        self._scanner_processes: dict[int, object] = {}
        self._kafka_process = None

    def iniciar(self, escaneres: list[Escaner]) -> None:
        """Inicia KafkaPublisherProcess y un ScannerProcess por escaner activo.

        IMPORTANTE: llamar ANTES de uvicorn.run() para que el fork ocurra
        cuando el proceso padre es todavia single-threaded.
        """
        from config import KAFKA_BOOTSTRAP_SERVERS
        from infrastructure.input.process.kafka_publisher_process import KafkaPublisherProcess
        from infrastructure.input.process.scanner_process import ScannerProcess

        # Iniciar proceso publicador Kafka
        self._kafka_process = KafkaPublisherProcess(
            self._signal_queue, KAFKA_BOOTSTRAP_SERVERS
        )
        self._kafka_process.start()
        logger.info(f"KafkaPublisherProcess iniciado PID={self._kafka_process.pid}")

        # Iniciar un proceso por escaner
        for escaner in escaneres:
            self._iniciar_proceso_escaner(escaner, ScannerProcess)

        logger.info(
            f"ProcessManager listo: {len(self._scanner_processes)} escaners activos"
        )
        sys.stdout.flush()

    def iniciar_escaner(self, escaner: Escaner) -> None:
        """Inicia un ScannerProcess para el escaner dado (llamado desde webhook)."""
        from infrastructure.input.process.scanner_process import ScannerProcess

        if escaner.id_escaner in self._scanner_processes:
            logger.warning(
                f"Scanner {escaner.id_escaner} ('{escaner.nombre}') "
                "ya tiene un proceso corriendo, ignorando solicitud"
            )
            return

        self._iniciar_proceso_escaner(escaner, ScannerProcess)
        sys.stdout.flush()

    def detener_escaner(self, id_escaner: int) -> None:
        """Detiene el ScannerProcess del escaner dado (llamado desde webhook)."""
        p = self._scanner_processes.pop(id_escaner, None)
        if p:
            p.detener()
            logger.info(f"ScannerProcess {id_escaner} detenido")
        else:
            logger.warning(
                f"No se encontro ScannerProcess activo para escaner {id_escaner}"
            )
        sys.stdout.flush()

    def shutdown(self) -> None:
        """Detiene todos los procesos de forma ordenada."""
        logger.info(
            f"Apagando ProcessManager: "
            f"{len(self._scanner_processes)} scanners, 1 kafka publisher"
        )

        # Detener todos los scanner processes
        for id_escaner, p in list(self._scanner_processes.items()):
            logger.info(f"Deteniendo ScannerProcess {id_escaner}...")
            p.detener()
        self._scanner_processes.clear()

        # Detener KafkaPublisherProcess
        if self._kafka_process:
            logger.info("Deteniendo KafkaPublisherProcess...")
            self._kafka_process.detener()
            self._kafka_process = None

        logger.info("Todos los procesos detenidos OK")
        sys.stdout.flush()

    # =========================================================================
    # Interno
    # =========================================================================

    def _iniciar_proceso_escaner(self, escaner: Escaner, ScannerProcess) -> None:
        """Crea e inicia un ScannerProcess."""
        p = ScannerProcess(escaner, self._signal_queue)
        p.start()
        self._scanner_processes[escaner.id_escaner] = p
        logger.info(
            f"ScannerProcess iniciado: '{escaner.nombre}' "
            f"(ID:{escaner.id_escaner}) PID={p.pid}"
        )
