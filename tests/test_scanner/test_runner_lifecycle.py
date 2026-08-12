from datetime import datetime, time, timezone
from multiprocessing import Process
from unittest.mock import patch

from app.models.enums import EnumEstadoEscaner, EnumTipoEjecucion
from app.models.escaner import Escaner, EstadoEscaner, TipoEjecucion
from app.orchestrator.process_registry import ProcessRegistry
from app.scanner.runner import _run_once, run_scanner
from app.scanner.symbols import SymbolPipeline


def test_run_scanner_pasa_pipeline_como_keyword_a_run_once():
    # Regresion: run_scanner llamaba _run_once(escaner, pipeline) posicional,
    # y como el segundo parametro posicional de _run_once es _now (no
    # pipeline), el SymbolPipeline terminaba metido en _now -- explotaba con
    # AttributeError apenas next_trading_window intentaba leer .date() de
    # el, y por eso NINGUN escaner UNA_VEZ podia arrancar (confirmado en
    # vivo: crash inmediato en cada intento de iniciar "test 33").
    escaner = Escaner(
        idEscaner=99,
        nombre="test-regresion",
        horaInicio=time(9, 30, 0),
        horaFin=time(10, 0, 0),
        objEstado=EstadoEscaner(enumEstadoEscaner=EnumEstadoEscaner.INICIADO),
        objTipoEjecucion=TipoEjecucion(enumTipoEjecucion=EnumTipoEjecucion.UNA_VEZ),
    )

    with patch("app.scanner.runner._run_once") as mock_run_once, \
         patch.object(SymbolPipeline, "cargar_todos"):
        run_scanner(escaner)

    args, kwargs = mock_run_once.call_args
    assert len(args) == 1, "el pipeline no debe ir posicional (choca con _now)"
    assert isinstance(kwargs.get("pipeline"), SymbolPipeline)


def test_una_vez_scanner_completes_when_hora_fin_passed():
    now = datetime(2026, 7, 17, 15, 0, 0, tzinfo=timezone.utc)
    escaner = Escaner(
        idEscaner=1,
        nombre="test-una-vez",
        horaInicio=time(9, 30, 0),
        horaFin=time(10, 0, 0),
        objEstado=EstadoEscaner(enumEstadoEscaner=EnumEstadoEscaner.INICIADO),
        objTipoEjecucion=TipoEjecucion(enumTipoEjecucion=EnumTipoEjecucion.UNA_VEZ),
    )

    _run_once(escaner, _now=now)


def test_una_vez_registry_detects_completion():
    registry = ProcessRegistry()

    now = datetime(2026, 7, 17, 15, 0, 0, tzinfo=timezone.utc)
    escaner = Escaner(
        idEscaner=2,
        nombre="test-completion",
        horaInicio=time(9, 30, 0),
        horaFin=time(10, 0, 0),
        objEstado=EstadoEscaner(enumEstadoEscaner=EnumEstadoEscaner.INICIADO),
        objTipoEjecucion=TipoEjecucion(enumTipoEjecucion=EnumTipoEjecucion.UNA_VEZ),
    )

    process = Process(target=_run_once, args=(escaner, now), daemon=False)
    process.start()
    registry.add(2, process)

    # cargar_todos() ahora reintenta con backoff antes de rendirse (hasta
    # ~9s sin red, ver test_symbols_retry.py) -- el timeout de join tiene
    # que cubrir eso, no solo el tiempo de un fetch que falla al instante.
    process.join(timeout=15)

    completed = registry.collect_completed()
    assert 2 in completed
