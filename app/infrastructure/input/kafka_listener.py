import json
import logging

from aiokafka import AIOKafkaConsumer

from app.core.gestor_escaneres import GestorEscaneres
from app.domain.models.escaner import Escaner
from app.infrastructure.output.escaner_rest_adapter import EscanerRestAdapter

logger = logging.getLogger(__name__)

SERVICIO_ORIGEN = "signal-processing-service"
TOPIC_SCANNER_STATE = "scanner.state"


class EstadoEscanerKafkaListener:
    """Consume el topic scanner.state para recibir cambios de estado."""

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        gestor: GestorEscaneres,
        escaner_rest: EscanerRestAdapter,
    ):
        self._consumer = AIOKafkaConsumer(
            TOPIC_SCANNER_STATE,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            auto_offset_reset="earliest",
            enable_auto_commit=True,
        )
        self._gestor = gestor
        self._escaner_rest = escaner_rest

    async def iniciar(self):
        """Inicia el consumer loop."""
        await self._consumer.start()
        logger.info("Kafka listener iniciado en topic '%s'", TOPIC_SCANNER_STATE)

        try:
            async for mensaje in self._consumer:
                try:
                    evento = mensaje.value
                    await self._procesar_evento(evento)
                except Exception as e:
                    logger.error("Error procesando evento Kafka: %s", e, exc_info=True)
        finally:
            await self._consumer.stop()
            logger.info("Kafka listener detenido")

    async def _procesar_evento(self, evento: dict):
        """Procesa un evento de cambio de estado de escáner."""
        servicio_origen = evento.get("servicioOrigen", "")

        # Prevención de auto-consumo
        if servicio_origen == SERVICIO_ORIGEN:
            return

        id_escaner = evento.get("idEscaner")
        estado_nuevo = evento.get("estadoNuevo", "")
        nombre = evento.get("nombreEscaner", "")

        logger.info(
            "Evento recibido: escaner=%s (id=%s), estado=%s, origen=%s",
            nombre, id_escaner, estado_nuevo, servicio_origen,
        )

        if id_escaner is None:
            return

        if estado_nuevo == "INICIADO":
            await self._iniciar_escaner(id_escaner)
        elif estado_nuevo in ("DETENIDO", "ARCHIVADO"):
            await self._gestor.detener_escaner(
                id_escaner,
                razon=evento.get("razon", f"Estado cambiado a {estado_nuevo}"),
            )

    async def _iniciar_escaner(self, id_escaner: int):
        """Obtiene datos completos del escáner y lo inicia."""
        escaner_data = await self._escaner_rest.obtener_escaner_por_id(id_escaner)
        if escaner_data is None:
            logger.error("No se pudo obtener datos del escaner %d", id_escaner)
            return

        filtros_data = await self._escaner_rest.obtener_filtros_escaner(id_escaner)
        escaner = Escaner.desde_dict(escaner_data, filtros_data)
        await self._gestor.iniciar_escaner(escaner)
