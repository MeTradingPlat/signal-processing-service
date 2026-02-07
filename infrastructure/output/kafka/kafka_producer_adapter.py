"""Adaptador de salida: producer de Kafka usando confluent-kafka."""

import json
import logging
from datetime import datetime

from confluent_kafka import Producer

from application.output.kafka_producer_int_port import KafkaProducerIntPort

logger = logging.getLogger(__name__)


class KafkaProducerAdapter(KafkaProducerIntPort):

    TOPIC_SIGNALS = "signals"
    TOPIC_ASSET_STATE = "asset-state"
    TOPIC_LOGS = "logs"
    TOPIC_SCANNER_STATE = "scanner.state"

    def __init__(self, bootstrap_servers: str):
        self._producer = Producer({
            "bootstrap.servers": bootstrap_servers,
            "client.id": "signal-processing-service",
        })
        logger.info(f"Kafka producer configurado: {bootstrap_servers}")

    def _delivery_callback(self, err, msg):
        if err:
            logger.error(f"Error enviando mensaje a {msg.topic()}: {err}")
        else:
            logger.debug(f"Mensaje enviado a {msg.topic()} [{msg.partition()}]")

    def _serializar(self, mensaje: dict) -> bytes:
        return json.dumps(mensaje, default=str).encode("utf-8")

    def _enviar(self, topic: str, mensaje: dict) -> None:
        self._producer.produce(
            topic=topic,
            value=self._serializar(mensaje),
            callback=self._delivery_callback,
        )
        self._producer.poll(0)

    def publicar_senal(self, mensaje: dict) -> None:
        self._enviar(self.TOPIC_SIGNALS, mensaje)
        logger.debug(f"Senal publicada: {mensaje.get('symbol')}")

    def publicar_estado_activo(self, mensaje: dict) -> None:
        self._enviar(self.TOPIC_ASSET_STATE, mensaje)
        logger.debug(f"Estado activo publicado: {mensaje.get('symbol')}")

    def publicar_log(self, mensaje: dict) -> None:
        self._enviar(self.TOPIC_LOGS, mensaje)

    def publicar_escaner_completado(self, mensaje: dict) -> None:
        self._enviar(self.TOPIC_SCANNER_STATE, mensaje)
        logger.info(f"Evento escaner completado publicado: escaner_id={mensaje.get('idEscaner')}")

    def flush(self) -> None:
        """Fuerza el envio de mensajes pendientes."""
        self._producer.flush()
