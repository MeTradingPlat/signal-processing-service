import logging
import os
import time as _time
from datetime import datetime, timezone

from app.models.enums import EnumTipoEjecucion
from app.models.escaner import Escaner
from app.models.filtro import Filtro
from app.scanner.calendar import effective_end, is_within_window, next_trading_window
from app.scanner.symbols import SymbolPipeline
from app.scanner.timeframe import agrupar_por_timeframe

logger = logging.getLogger(__name__)

_LONG_SLEEP_SECONDS = 5.0
_CYCLE_SECONDS = 60.0
_REALTIME_SECONDS = 1.0


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
        _run_once(escaner, pipeline)
    else:
        _run_daily(escaner, pipeline, orchestrator_pid)


def _run_once(escaner: Escaner, _now: datetime | None = None, pipeline: SymbolPipeline | None = None):
    if pipeline is None:
        pipeline = SymbolPipeline(escaner)
        pipeline.cargar_todos()
    now = _now or datetime.now(timezone.utc)
    window_start = next_trading_window(escaner.horaInicio, now)
    _sleep_until(window_start, _now)

    logger.info("ScannerRunner: UNA_VEZ active id=%d", escaner.idEscaner)
    _run_loop_until_end(escaner, pipeline, _now)

    logger.info("ScannerRunner: UNA_VEZ completed id=%d", escaner.idEscaner)


def _do_cycle(escaner: Escaner, pipeline: SymbolPipeline, first_cycle_of_day: bool = False):
    logger.debug("ScannerRunner: cycle id=%d symbols=%d", escaner.idEscaner, len(pipeline.filtrados))
    pipeline.aplicar_pre_filtros(first_cycle_of_day=first_cycle_of_day)

    if pipeline.tecnicos:
        grupos = agrupar_por_timeframe(pipeline.tecnicos)
        signals = pipeline.evaluar_tecnicos(grupos)
        if signals:
            _publish_signals(escaner, signals)
            logger.info("ScannerRunner: id=%d signals=%d symbols=%s",
                        escaner.idEscaner, len(signals), list(signals.keys())[:5])


def _publish_signals(escaner: Escaner, signals: dict):
    from app.infrastructure.output.kafka_producer import publish_signals as kafka_publish
    _clear_old_signals(escaner.idEscaner)
    logger.info("SIGNALS: scanner='%s' id=%d count=%d",
                escaner.nombre, escaner.idEscaner, len(signals))
    kafka_publish(escaner.idEscaner, escaner.nombre, signals)


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
            end = effective_end(escaner.horaFin, now.date())
            if is_within_window(now, escaner.horaInicio, end):
                if last_date != now.date():
                    if last_date is not None:
                        pipeline.renovar_si_nuevo_dia()
                    last_date = now.date()
                    _do_cycle(escaner, pipeline, first_cycle_of_day=True)
                else:
                    _do_cycle(escaner, pipeline)
                _time.sleep(_CYCLE_SECONDS)
            else:
                last_date = None
                next_run = next_trading_window(escaner.horaInicio, now)
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


def _run_loop_until_end(escaner: Escaner, pipeline: SymbolPipeline, _now: datetime | None = None):
    while True:
        now = _now or datetime.now(timezone.utc)
        end = effective_end(escaner.horaFin, now.date())
        if now.time() >= end or not is_within_window(now, escaner.horaInicio, end):
            return
        _do_cycle(escaner, pipeline)
        if _now is not None:
            return
        _time.sleep(_CYCLE_SECONDS)

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
