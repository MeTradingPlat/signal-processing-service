import logging
import os
import time as _time
from datetime import datetime, timezone

from app.models.enums import EnumTipoEjecucion
from app.models.escaner import Escaner
from app.models.filtro import Filtro
from app.scanner.calendar import effective_end, effective_start, is_within_window, next_trading_window
from app.scanner.symbols import SymbolPipeline
from app.scanner.timeframe import agrupar_por_timeframe

logger = logging.getLogger(__name__)

_LONG_SLEEP_SECONDS = 5.0
_CYCLE_SECONDS = 60.0
_REALTIME_SECONDS = 1.0
_BAR_CLOSE_BUFFER_SECONDS = 1.0


def _next_cycle_delay(pipeline: SymbolPipeline, now: datetime) -> float:
    """Seconds to sleep before the next cycle.

    Defaults to the flat _CYCLE_SECONDS cadence, but when the tightest
    technical filter's timeframe closes within that same window (in
    practice only M1), sleeps until _BAR_CLOSE_BUFFER_SECONDS after that
    bar's close instead. Without this, a plain 60s-after-last-cycle sleep
    drifts against wall-clock minute boundaries and can poll marketdata a
    couple of seconds before the bar closes, silently working with a
    minute-old bar until the next cycle picks it up.
    """
    if not pipeline.tecnicos:
        return _CYCLE_SECONDS
    min_minutos = min(agrupar_por_timeframe(pipeline.tecnicos))
    period = min_minutos * 60.0
    if period > _CYCLE_SECONDS:
        return _CYCLE_SECONDS
    seconds_into_period = now.timestamp() % period
    return (period - seconds_into_period) + _BAR_CLOSE_BUFFER_SECONDS


def run_scanner(escaner: Escaner):
    orchestrator_pid = os.getppid()
    pipeline = SymbolPipeline(escaner)

    logger.info(
        "ScannerRunner: started id=%d name='%s' pid=%d type=%s window=%s-%s pre=%d tec=%d",
        escaner.idEscaner, escaner.nombre, os.getpid(),
        escaner.objTipoEjecucion.enumTipoEjecucion,
        escaner.horaInicio, escaner.horaFin,
        len(pipeline.pre_filtros), len(pipeline.tecnicos),
    )

    pipeline.cargar_todos()

    if escaner.objTipoEjecucion.enumTipoEjecucion == EnumTipoEjecucion.UNA_VEZ:
        _run_once(escaner, pipeline=pipeline, orchestrator_pid=orchestrator_pid)
    else:
        _run_daily(escaner, pipeline, orchestrator_pid)


def _run_once(escaner: Escaner, _now: datetime | None = None, pipeline: SymbolPipeline | None = None,
              orchestrator_pid: int | None = None):
    if pipeline is None:
        pipeline = SymbolPipeline(escaner)
        pipeline.cargar_todos()
    now = _now or datetime.now(timezone.utc)
    start = effective_start(escaner.horaInicio, now.date())
    end = effective_end(escaner.horaFin, now.date())
    if not is_within_window(now, start, end):
        window_start = next_trading_window(start, now)
        _sleep_until(window_start, _now)

    logger.info("ScannerRunner: UNA_VEZ active id=%d", escaner.idEscaner)
    _run_loop_until_end(escaner, pipeline, _now, orchestrator_pid)

    logger.info("ScannerRunner: UNA_VEZ completed id=%d", escaner.idEscaner)


def _reintentar_carga_si_vacia(pipeline: SymbolPipeline):
    """cargar_todos() ya reintenta unas pocas veces con backoff corto por su
    cuenta, pero si la caida de marketdata-service dura mas que eso, sin
    esto el escaner se quedaba evaluando una lista vacia de simbolos el
    resto del dia -- confirmado en vivo: un restart de marketdata-service
    dejo un escaner sin escanear nada por horas, hasta que se reinicio el
    proceso a mano. Reintentar en cada ciclo (~60s) mientras siga vacia se
    recupera solo apenas el servicio vuelva."""
    if not pipeline.todos:
        pipeline.cargar_todos()


def _do_cycle(escaner: Escaner, pipeline: SymbolPipeline):
    logger.debug("ScannerRunner: cycle id=%d symbols=%d", escaner.idEscaner, len(pipeline.filtrados))
    pipeline.aplicar_pre_filtros()

    # Antes esto vivia detras de "if pipeline.tecnicos:" -- un escaner armado
    # solo con pre-filtros (precio/volumen/fundamentales, sin ningun filtro
    # que necesite velas) nunca llegaba a evaluar_tecnicos ni a publicar,
    # sin importar cuantos simbolos pasaran los pre-filtros. evaluar_tecnicos
    # ya maneja bien grupos={} (devuelve los candidatos tal cual, sin
    # matches tecnicos) -- el problema era que el caller ni lo intentaba.
    grupos = agrupar_por_timeframe(pipeline.tecnicos)
    signals = pipeline.evaluar_tecnicos(grupos)
    nuevos = pipeline.nuevos_symbols(signals)
    _publish_signals(escaner, signals, nuevos)
    if signals:
        logger.info("ScannerRunner: id=%d signals=%d symbols=%s",
                    escaner.idEscaner, len(signals), list(signals.keys())[:5])


def _publish_signals(escaner: Escaner, signals: dict, nuevos: set):
    from app.infrastructure.output.kafka_producer import publish_signals as kafka_publish
    logger.info("SIGNALS: scanner='%s' id=%d count=%d",
                escaner.nombre, escaner.idEscaner, len(signals))
    kafka_publish(escaner.idEscaner, escaner.nombre, signals, nuevos)


def _clear_old_signals(scanner_id: int):
    try:
        import urllib.request, json
        from app.config import settings
        url = f"{settings.log_service_url}/logs/escaner/{scanner_id}"
        req = urllib.request.Request(url, headers={"X-Gateway-Passed": "true"}, method="DELETE")
        with urllib.request.urlopen(req, timeout=5) as resp:
            logger.debug("Cleared old signals for scanner %d: %s", scanner_id, resp.status)
    except Exception as e:
        logger.warning("Failed to clear old signals for scanner %d: %s", scanner_id, e)


def _run_daily(escaner: Escaner, pipeline: SymbolPipeline, orchestrator_pid: int):
    last_date = None
    try:
        while True:
            if os.getppid() != orchestrator_pid:
                logger.warning("ScannerRunner: orchestrator died id=%d", escaner.idEscaner)
                return
            now = datetime.now(timezone.utc)
            # effective_start SI depende de la fecha (conversion ET->UTC
            # consciente de horario de verano) -- recalcular en cada vuelta,
            # igual que effective_end, para no quedar con un valor obsoleto
            # si el proceso vive a traves de un cambio de horario.
            start = effective_start(escaner.horaInicio, now.date())
            end = effective_end(escaner.horaFin, now.date())
            if is_within_window(now, start, end):
                if last_date != now.date():
                    if last_date is not None:
                        pipeline.renovar_si_nuevo_dia()
                    last_date = now.date()
                _reintentar_carga_si_vacia(pipeline)
                _do_cycle(escaner, pipeline)
                _time.sleep(_next_cycle_delay(pipeline, datetime.now(timezone.utc)))
            else:
                if last_date is not None:
                    # La ventana recien cerro -- limpiar ahora en vez de
                    # dejar el ultimo resultado de la sesion mostrandose como
                    # "ACTIVO" toda la noche hasta el primer ciclo de manana.
                    _publish_signals(escaner, {}, set())
                last_date = None
                next_run = next_trading_window(start, now)
                wait = (next_run - now).total_seconds()
                logger.info(
                    "ScannerRunner: sleeping id=%d until %s (%.0f min)",
                    escaner.idEscaner, next_run.isoformat(), wait / 60,
                )
                while wait > 0:
                    _time.sleep(min(wait, _LONG_SLEEP_SECONDS))
                    wait = (next_run - datetime.now(timezone.utc)).total_seconds()
    except KeyboardInterrupt:
        logger.info("ScannerRunner: interrupted id=%d", escaner.idEscaner)


def _run_loop_until_end(escaner: Escaner, pipeline: SymbolPipeline, _now: datetime | None = None,
                         orchestrator_pid: int | None = None):
    while True:
        # Mismo chequeo que _run_daily -- sin esto, un escaner UNA_VEZ
        # sobrevive a la muerte del orquestador (que restaura su propio
        # escaner via _sync_active_scanners al reiniciar) y queda un
        # proceso huerfano duplicando señales el resto de su ventana.
        # orchestrator_pid es None en los tests (mismo criterio que _now),
        # asi que no cambia su comportamiento.
        if orchestrator_pid is not None and os.getppid() != orchestrator_pid:
            logger.warning("ScannerRunner: orchestrator died id=%d", escaner.idEscaner)
            return
        now = _now or datetime.now(timezone.utc)
        start = effective_start(escaner.horaInicio, now.date())
        end = effective_end(escaner.horaFin, now.date())
        if now.time() >= end or not is_within_window(now, start, end):
            return
        _reintentar_carga_si_vacia(pipeline)
        _do_cycle(escaner, pipeline)
        if _now is not None:
            return
        _time.sleep(_next_cycle_delay(pipeline, datetime.now(timezone.utc)))

def _sleep_until(target: datetime, _now: datetime | None = None):
    if _now is not None:
        return
    now = datetime.now(timezone.utc)
    delta = (target - now).total_seconds()
    if delta <= 0:
        return
    logger.info("ScannerRunner: sleeping %.0fs until %s", delta, target.isoformat())
    while delta > 0:
        _time.sleep(min(delta, _LONG_SLEEP_SECONDS))
        now = datetime.now(timezone.utc)
        delta = (target - now).total_seconds()
