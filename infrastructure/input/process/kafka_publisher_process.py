"""Proceso de publicacion Kafka y proxy de cola.

KafkaPublisherProcess: proceso OS dedicado que lee mensajes de una
multiprocessing.Queue y los publica en los topics de Kafka correspondientes.

QueueKafkaProxy: implementa KafkaProducerIntPort poniendo los mensajes
en la Queue en lugar de llamar a Kafka directamente. Es usado por los
ScannerProcess para enviar mensajes sin tener su propia conexion Kafka.
"""

import logging
import multiprocessing
import sys

logger = logging.getLogger(__name__)

# Tipos de mensaje en la queue
MSG_SENAL = "senal"
MSG_LOG = "log"
MSG_ESCANER_COMPLETADO = "escaner_completado"
MSG_ESTADO_ACTIVO = "estado_activo"
MSG_SENTINEL = "STOP"


class QueueKafkaProxy:
    """Proxy que pone mensajes en una multiprocessing.Queue.

    Implementa la misma interfaz que KafkaProducerAdapter para que
    ProcesarSenalesCUAdapter no sepa si esta hablando con Kafka directamente
    o con el proceso publicador.
    """

    def __init__(self, queue: multiprocessing.Queue):
        self._queue = queue

    def publicar_senal(self, mensaje: dict) -> None:
        self._queue.put((MSG_SENAL, mensaje))

    def publicar_estado_activo(self, mensaje: dict) -> None:
        self._queue.put((MSG_ESTADO_ACTIVO, mensaje))

    def publicar_log(self, mensaje: dict) -> None:
        self._queue.put((MSG_LOG, mensaje))

    def publicar_escaner_completado(self, mensaje: dict) -> None:
        self._queue.put((MSG_ESCANER_COMPLETADO, mensaje))

    def flush(self) -> None:
        pass  # El flush lo hace KafkaPublisherProcess al recibir el sentinel


class KafkaPublisherProcess(multiprocessing.Process):
    """Proceso OS dedicado a publicar mensajes en Kafka.

    Lee de la signal_queue compartida y enruta cada mensaje al metodo
    correcto del KafkaProducerAdapter. Un proceso unico centraliza la
    conexion Kafka para todos los ScannerProcess.
    """

    def __init__(self, signal_queue: multiprocessing.Queue, bootstrap_servers: str):
        super().__init__(daemon=True, name="KafkaPublisher")
        self._queue = signal_queue
        self._bootstrap_servers = bootstrap_servers

    def run(self):
        import os
        os.environ['TZ'] = 'UTC'

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(processName)s %(name)s - %(message)s",
            stream=sys.stdout,
        )
        log = logging.getLogger("KafkaPublisher")
        log.info("KafkaPublisherProcess iniciado")
        sys.stdout.flush()

        from infrastructure.output.kafka.kafka_producer_adapter import KafkaProducerAdapter
        producer = KafkaProducerAdapter(self._bootstrap_servers)

        routing = {
            MSG_SENAL: producer.publicar_senal,
            MSG_LOG: producer.publicar_log,
            MSG_ESCANER_COMPLETADO: producer.publicar_escaner_completado,
            MSG_ESTADO_ACTIVO: producer.publicar_estado_activo,
        }

        while True:
            try:
                item = self._queue.get(timeout=1.0)
            except Exception:
                continue

            if item == MSG_SENTINEL:
                log.info("Sentinel recibido, terminando")
                break

            msg_type, data = item
            handler = routing.get(msg_type)
            if handler:
                try:
                    handler(data)
                except Exception as e:
                    log.error(f"Error publicando mensaje tipo '{msg_type}': {e}")
            else:
                log.warning(f"Tipo de mensaje desconocido: {msg_type}")

        producer.flush()
        log.info("KafkaPublisherProcess terminado")
        sys.stdout.flush()

    def detener(self):
        """Envia sentinel y espera al proceso."""
        self._queue.put(MSG_SENTINEL)
        self.join(timeout=15)
        if self.is_alive():
            logger.warning("KafkaPublisherProcess no termino en 15s, terminando forzosamente")
            self.terminate()
            self.join(timeout=5)
