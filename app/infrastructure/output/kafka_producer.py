import json
import logging
from datetime import datetime, timezone

from app.config import settings
from app.scanner.symbols import _minutos_to_label
from app.scanner.timeframe import extraer_timeframe_minutos

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


def publish_signals(scanner_id: int, scanner_name: str, signals: dict, nuevos: set):
    producer = _get_producer()
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # El tab "Señales" del frontend lee de log-service (categoria=SIGNAL) --
    # es un log historico append-only, a diferencia del extinto topico
    # "signals" (estado actual, se limpiaba cada ciclo) que solo alimentaba
    # la pestaña "Activos" ya eliminada junto con asset-management-service.
    signal_count = 0
    for symbol, passed_matches in signals.items():
        filtros_nombres = ", ".join([sm.filtro.enumFiltro.name for sm in passed_matches])
        # Sin matches tecnicos (escaner armado solo con pre-filtros, ver
        # runner.py) "cumple " quedaria colgado sin nada despues.
        detalle_filtros = f": cumple {filtros_nombres}" if filtros_nombres else ""
        # "precio" es el de la vela del ULTIMO grupo evaluado (el que de
        # verdad confirmo la senal, ya que evaluar_tecnicos va reduciendo
        # candidatos grupo a grupo) -- es el precio mas cercano al momento
        # real en que la senal se genero. Usado por el frontend para dibujar
        # una linea horizontal de "precio de entrada simulado" en el grafico.
        precio_senal = passed_matches[-1].precio if passed_matches else None
        metadatos_json = json.dumps({
            "precio": precio_senal,
            "matches": [
                {
                    "filtro": sm.filtro.enumFiltro.name,
                    "timeframe": _minutos_to_label(extraer_timeframe_minutos(sm.filtro)),
                    "velaTimestamp": sm.vela_timestamp.replace(tzinfo=None).isoformat(),
                }
                for sm in passed_matches
            ],
        })
        log_event = {
            "servicioOrigen": settings.servicio_origen,
            "nivel": "INFO",
            "mensaje": f"Señal generada para {symbol} en '{scanner_name}'{detalle_filtros}",
            "idEscaner": scanner_id,
            "symbol": symbol,
            "categoria": "SIGNAL",
            "timestamp": now,
            "metadatos": metadatos_json,
            "esSenalNueva": symbol in nuevos,
        }
        try:
            if producer and producer is not False:
                producer.send("logs", key=symbol, value=log_event)
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
