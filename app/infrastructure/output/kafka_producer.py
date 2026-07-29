import json
import logging
from datetime import datetime, timezone

from app.config import settings

logger = logging.getLogger(__name__)

_producer = None


def _get_producer():
    global _producer
    if _producer is not None:
        return _producer
    try:
        from kafka import KafkaProducer
        _producer = KafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks=1,
            retries=3,
        )
        logger.info("Kafka producer connected to %s", settings.kafka_bootstrap_servers)
    except Exception as e:
        logger.warning("Kafka not available, signals will be logged only: %s", e)
        _producer = False
    return _producer


def publish_signals(scanner_id: int, scanner_name: str, signals: dict):
    producer = _get_producer()
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # El clear se manda siempre, incluso con signals vacio -- antes estaba
    # dentro del for de abajo, asi que un ciclo sin ningun candidato (0
    # signals) nunca lo disparaba, y los simbolos del ciclo anterior se
    # quedaban pegados para siempre en asset-management-service (nunca se
    # marcan como ya no vigentes, solo se upsertan/insertan nuevos).
    if producer and producer is not False:
        clear_event = {
            "type": "CLEAR_SCANNER_SIGNALS",
            "servicioOrigen": settings.servicio_origen,
            "idEscaner": scanner_id,
            "timestamp": now,
        }
        try:
            producer.send("signals", key=str(scanner_id), value=clear_event)
        except Exception as e:
            logger.error("Failed to publish clear event for scanner %d: %s", scanner_id, e)

    signal_count = 0
    for symbol, passed_filters in signals.items():
        filtros_json = json.dumps([f.enumFiltro.name for f in passed_filters])
        filtros_nombres = ", ".join([f.enumFiltro.name for f in passed_filters])
        signal_event = {
            "idEscaner": scanner_id,
            "nombreEscaner": scanner_name,
            "symbol": symbol,
            "tipoSenal": "SCANNER_SIGNAL",
            "filtrosAplicados": filtros_json,
            "timestamp": now,
            "servicioOrigen": settings.servicio_origen,
        }
        try:
            if producer and producer is not False:
                producer.send("signals", key=symbol, value=signal_event)
            signal_count += 1
            logger.debug("SIGNAL: scanner='%s' symbol=%s filters=%s", scanner_name, symbol, filtros_nombres)
        except Exception as e:
            logger.error("Failed to publish signal for %s: %s", symbol, e)

    if producer and producer is not False:
        producer.flush()

    logger.info("SIGNALS: scanner='%s' count=%d", scanner_name, signal_count)


def publish_scanner_state(scanner_id: int, estado_nuevo: str, razon: str):
    producer = _get_producer()
    event = {
        "idEscaner": scanner_id,
        "nombreEscaner": "",
        "estadoAnterior": "INICIADO",
        "estadoNuevo": estado_nuevo,
        "razon": razon,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "servicioOrigen": settings.servicio_origen,
    }
    try:
        if producer and producer is not False:
            producer.send("scanner.state", key=str(scanner_id), value=event)
        logger.info("KAFKA: published to scanner.state -> id=%d estado=%s", scanner_id, estado_nuevo)
    except Exception as e:
        logger.error("Failed to publish scanner state: %s", e)
