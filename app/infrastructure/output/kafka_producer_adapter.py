import json
import logging
from datetime import datetime, timezone

from aiokafka import AIOKafkaProducer

logger = logging.getLogger(__name__)

SERVICIO_ORIGEN = "signal-processing-service"
TOPIC_SIGNALS = "signals"
TOPIC_LOGS = "logs"
TOPIC_SCANNER_STATE = "scanner.state"
TOPIC_FILTERED_SYMBOLS = "scanner.filtered_symbols"


class KafkaProducerAdapter:
    """Productor Kafka para señales, logs y estados de escáner."""

    def __init__(self, bootstrap_servers: str):
        self._producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
        )

    async def iniciar(self):
        await self._producer.start()
        logger.info("Kafka producer iniciado")

    async def detener(self):
        await self._producer.stop()
        logger.info("Kafka producer detenido")

    async def publicar_senal(self, senal_dict: dict):
        """Publica una señal al topic 'signals'."""
        try:
            await self._producer.send_and_wait(TOPIC_SIGNALS, value=senal_dict)
            logger.info(
                "*** SEÑAL  escaner='%s'  symbol=%s  filtros=%s",
                senal_dict.get("nombreEscaner"),
                senal_dict.get("symbol"),
                senal_dict.get("filtrosActivos", []),
            )
        except Exception as e:
            logger.error("Error publicando señal: %s", e)

    async def publicar_log(
        self,
        id_escaner: int,
        nivel: str,
        mensaje: str,
        categoria: str = "SCANNER",
        tipo: str = "SCANNER_STATE",
    ):
        """Publica un log al topic 'logs' para persistencia y SSE."""
        notificacion = {
            "servicioOrigen": SERVICIO_ORIGEN,
            "nivel": nivel,
            "mensaje": mensaje,
            "idEscaner": id_escaner,
            "categoria": categoria,
            "tipo": tipo,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        }
        try:
            await self._producer.send_and_wait(TOPIC_LOGS, value=notificacion)
        except Exception as e:
            logger.error("Error publicando log: %s", e)

    async def publicar_cambio_estado(
        self,
        id_escaner: int,
        nombre_escaner: str,
        estado_anterior: str,
        estado_nuevo: str,
        razon: str,
    ):
        """Publica cambio de estado al topic 'scanner.state'."""
        evento = {
            "idEscaner": id_escaner,
            "nombreEscaner": nombre_escaner,
            "estadoAnterior": estado_anterior,
            "estadoNuevo": estado_nuevo,
            "razon": razon,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "servicioOrigen": SERVICIO_ORIGEN,
        }
        try:
            await self._producer.send_and_wait(TOPIC_SCANNER_STATE, value=evento)
            logger.info(
                "Cambio de estado publicado: escaner=%d, %s -> %s",
                id_escaner, estado_anterior, estado_nuevo,
            )
        except Exception as e:
            logger.error("Error publicando cambio de estado: %s", e)
    async def publicar_simbolos_filtrados(
        self,
        id_escaner: int,
        simbolos: list[str],
    ):
        """Publica la lista actual de símbolos que pasaron los filtros."""
        evento = {
            "idEscaner": id_escaner,
            "simbolos": simbolos,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "servicioOrigen": SERVICIO_ORIGEN,
        }
        try:
            await self._producer.send_and_wait(TOPIC_FILTERED_SYMBOLS, value=evento)
        except Exception as e:
            logger.error("Error publicando símbolos filtrados: %s", e)
