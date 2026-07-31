from unittest.mock import patch

from app.models.escaner import Escaner
from app.models.enums import EnumEstadoEscaner, EnumTipoEjecucion
from app.models.escaner import EstadoEscaner, TipoEjecucion
from app.scanner.symbols import SymbolPipeline
from datetime import time


def _escaner() -> Escaner:
    return Escaner(
        idEscaner=1,
        nombre="test",
        horaInicio=time(9, 30, 0),
        horaFin=time(16, 0, 0),
        objEstado=EstadoEscaner(enumEstadoEscaner=EnumEstadoEscaner.INICIADO),
        objTipoEjecucion=TipoEjecucion(enumTipoEjecucion=EnumTipoEjecucion.DIARIA),
    )


def test_cargar_todos_retries_on_transient_failure_then_succeeds():
    pipeline = SymbolPipeline(_escaner())
    calls = {"n": 0}

    def flaky_fetch(mercados):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionRefusedError("Connection refused")
        return ["AAPL", "MSFT"]

    with patch.object(pipeline._client, "fetch_symbols", side_effect=flaky_fetch), \
         patch("app.scanner.symbols.time.sleep"):
        pipeline.cargar_todos()

    assert calls["n"] == 3
    assert pipeline.todos == ["AAPL", "MSFT"]


def test_cargar_todos_gives_up_empty_after_exhausting_retries():
    pipeline = SymbolPipeline(_escaner())

    with patch.object(pipeline._client, "fetch_symbols", side_effect=ConnectionRefusedError("down")), \
         patch("app.scanner.symbols.time.sleep"):
        pipeline.cargar_todos()

    assert pipeline.todos == []
    assert pipeline.filtrados == []
