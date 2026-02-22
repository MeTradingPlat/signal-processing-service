"""Servicio para formato y emision de notificaciones Kafka de senales de signal-processing."""

import json
import logging
from datetime import datetime, timezone
import sys

from domain.models.escaner import Escaner
from domain.models.senal import Senal
from application.output.kafka_producer_int_port import KafkaProducerIntPort

logger = logging.getLogger(__name__)

class SignalNotificationService:
    """Encapsula el formato y envio de notificaciones a traves de Kafka / stdout."""

    def __init__(self, kafka_producer: KafkaProducerIntPort = None):
        self.kafka_producer = kafka_producer

    def emitir_senal(self, escaner: Escaner, symbol: str) -> None:
        """Genera el log de la senal en stdout y la publica a los topicos de Kafka."""
        senal = Senal(
            escaner_id=escaner.id_escaner,
            escaner_nombre=escaner.nombre,
            symbol=symbol,
            filtros_evaluados=[f.enum_filtro for f in escaner.filtros],
        )

        logger.info("=" * 80)
        logger.info(f"SENAL GENERADA: {symbol}")
        logger.info(f"  Escaner: {escaner.nombre} (ID: {escaner.id_escaner})")
        logger.info(f"  Filtros: {[f.enum_filtro for f in escaner.filtros]}")
        logger.info("=" * 80)
        print(senal)
        sys.stdout.flush()

        if not self.kafka_producer:
            logger.warning("NotificationService: Kafka producer no disponible, senal no publicada a Kafka")
            return

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        logger.info(f"NotificationService: Publicando senal a Kafka para {symbol}...")

        # Publicar senal
        self.kafka_producer.publicar_senal({
            "idEscaner": escaner.id_escaner,
            "nombreEscaner": escaner.nombre,
            "symbol": symbol,
            "tipoSenal": "ENTRADA",
            "filtrosAplicados": json.dumps([f.enum_filtro for f in escaner.filtros]),
            "precioDeteccion": None,
            "volumenDeteccion": None,
            "timestamp": now,
        })
        logger.info(f"  -> Topic 'signals': OK")

        # Publicar estado activo
        self.kafka_producer.publicar_estado_activo({
            "idEscaner": escaner.id_escaner,
            "nombreEscaner": escaner.nombre,
            "symbol": symbol,
            "estado": "ACTIVO",
            "metadatos": json.dumps({"filtros": [f.enum_filtro for f in escaner.filtros]}),
            "timestamp": now,
        })
        logger.info(f"  -> Topic 'asset-state': OK")

        # Publicar log
        self.kafka_producer.publicar_log({
            "servicioOrigen": "signal-processing-service",
            "nivel": "INFO",
            "mensaje": f"Senal generada para {symbol} en escaner {escaner.nombre}",
            "idEscaner": escaner.id_escaner,
            "symbol": symbol,
            "categoria": "SIGNAL",
            "timestamp": now,
            "metadatos": json.dumps({"filtros": [f.enum_filtro for f in escaner.filtros]}),
        })
        logger.info(f"  -> Topic 'logs': OK")
        logger.info(f"Senal publicada a Kafka exitosamente para {symbol}")

    def publicar_log_inicio_escaner(self, escaner: Escaner, simbolos: list[str]) -> None:
        """Publica log detallado al iniciar la ejecucion de un escaner."""
        if not self.kafka_producer:
            return

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        filtros_str = ", ".join([f.enum_filtro for f in escaner.filtros])
        mercados_str = ", ".join([m.enum_mercado for m in escaner.mercados])

        mensaje = (
            f"Escaner '{escaner.nombre}' iniciado\n"
            f"- Filtros: [{filtros_str}]\n"
            f"- Mercados: [{mercados_str}]\n"
            f"- Simbolos a evaluar: {len(simbolos)}\n"
            f"- Horario: {escaner.hora_inicio}-{escaner.hora_fin} UTC\n"
            f"- Tipo: {escaner.obj_tipo_ejecucion.enum_tipo_ejecucion}"
        )

        self.kafka_producer.publicar_log({
            "servicioOrigen": "signal-processing-service",
            "nivel": "INFO",
            "mensaje": mensaje,
            "idEscaner": escaner.id_escaner,
            "symbol": None,
            "categoria": "EXECUTION_START",
            "timestamp": now,
            "metadatos": json.dumps({
                "mercados": [m.enum_mercado for m in escaner.mercados],
                "numSimbolos": len(simbolos),
                "tipoSeco": escaner.obj_tipo_ejecucion.enum_tipo_ejecucion
            }),
        })

    def publicar_log_finalizacion_escaner(
        self, escaner: Escaner, simbolos: list[str], senales_generadas: int, sin_datos: int, errores: int
    ) -> None:
        """Publica log final detallado tras la evaluacion de los simbolos."""
        if not self.kafka_producer:
            return

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        mensaje = (
            f"Escaner '{escaner.nombre}' completado\n"
            f"- Total evaluados: {len(simbolos)}\n"
            f"- Senales: {senales_generadas}\n"
            f"- Sin datos: {sin_datos}\n"
            f"- Errores: {errores}"
        )

        self.kafka_producer.publicar_log({
            "servicioOrigen": "signal-processing-service",
            "nivel": "INFO",
            "mensaje": mensaje,
            "idEscaner": escaner.id_escaner,
            "symbol": None,
            "categoria": "EXECUTION_END",
            "timestamp": now,
            "metadatos": json.dumps({
                "numSimbolos": len(simbolos),
                "senales": senales_generadas,
                "errores": errores,
            }),
        })

    def publicar_log_mercado_cerrado(self, escaner: Escaner, razon: str) -> None:
        if not self.kafka_producer:
            return
            
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        self.kafka_producer.publicar_log({
            "servicioOrigen": "signal-processing-service",
            "nivel": "INFO",
            "mensaje": f"Escaner '{escaner.nombre}' omitido: {razon}",
            "idEscaner": escaner.id_escaner,
            "symbol": None,
            "categoria": "SCHEDULER",
            "timestamp": now,
            "metadatos": json.dumps({"razon": razon}),
        })
        
    def publicar_log_validacion_fallida_batch(
        self, timeframe: str, num_simbolos: int, max_reintentos: int
    ) -> None:
        """Publica log de validacion fallida a Kafka."""
        if not self.kafka_producer:
            return

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        self.kafka_producer.publicar_log({
            "servicioOrigen": "signal-processing-service",
            "nivel": "ERROR",
            "mensaje": (
                f"Validacion de barras fallida despues de {max_reintentos} "
                f"reintentos para tf={timeframe}, {num_simbolos} simbolos"
            ),
            "idEscaner": None,
            "symbol": None,
            "categoria": "DATA",
            "timestamp": now,
            "metadatos": json.dumps({
                "timeframe": timeframe,
                "numSimbolos": num_simbolos,
                "reintentos": max_reintentos,
            }),
        })
