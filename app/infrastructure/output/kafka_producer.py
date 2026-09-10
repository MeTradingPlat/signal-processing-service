import json
import logging
from datetime import datetime, timezone

from app.config import settings
from app.scanner.timeframe import extraer_timeframe_minutos, minutos_to_label

logger = logging.getLogger(__name__)

_FLUSH_TIMEOUT_SECONDS = 10

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
    # Publicar solo `nuevos` (no todo `signals`) -- antes esto confiaba en
    # que _excluir_ya_senializados_hoy siempre hubiera sacado de `signals`
    # cualquier simbolo ya logueado hoy, lo cual dejo de ser cierto con
    # Escaner.permitirMultiplesSenales=true (ver symbols.py): sin este
    # filtro, un simbolo que sigue calificando ciclo tras ciclo publicaria
    # un log nuevo cada ~60-70s indefinidamente en vez de solo cuando
    # vuelve a calificar tras haber dejado de hacerlo.
    signal_count = 0
    for symbol in nuevos:
        passed_matches = signals.get(symbol)
        if not passed_matches:
            continue
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
                    "timeframe": minutos_to_label(extraer_timeframe_minutos(sm.filtro)),
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
            # Siempre True: el bucle de arriba ya itera solo sobre `nuevos`.
            "esSenalNueva": True,
        }
        try:
            if producer and producer is not False:
                producer.send("logs", key=symbol, value=log_event)
            signal_count += 1
            logger.debug("SIGNAL: scanner='%s' symbol=%s filters=%s", scanner_name, symbol, filtros_nombres)
        except Exception as e:
            logger.error("Failed to publish signal for %s: %s", symbol, e)

    if producer and producer is not False:
        # timeout explicito -- flush(timeout=None) espera indefinido a que
        # el broker confirme, y un cuelgue de red (no un rechazo limpio,
        # que fallaria rapido) congelaba el proceso del escaner entero para
        # siempre, sin log ni forma de recuperarse (el ciclo nunca vuelve a
        # correr). Un timeout vencido no debe tumbar el ciclo -- las señales
        # ya se intentaron enviar arriba, solo falta la confirmacion.
        try:
            producer.flush(timeout=_FLUSH_TIMEOUT_SECONDS)
        except Exception as e:
            logger.error("Kafka flush failed or timed out: %s", e)

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
