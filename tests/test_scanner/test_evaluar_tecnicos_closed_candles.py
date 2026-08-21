from datetime import datetime, time, timedelta, timezone
from unittest.mock import patch

from app.models.enums import EnumEstadoEscaner, EnumFiltro, EnumParametro, EnumTipoEjecucion
from app.models.escaner import Escaner, EstadoEscaner, TipoEjecucion
from app.models.filtro import Filtro
from app.models.parametro import Parametro
from app.models.valor import ValorString
from app.scanner.marketdata_models import CandleResponse
from app.scanner.symbols import SymbolPipeline


def _escaner() -> Escaner:
    return Escaner(
        idEscaner=1,
        nombre="test",
        horaInicio=time(9, 30, 0),
        horaFin=time(16, 0, 0),
        objEstado=EstadoEscaner(enumEstadoEscaner=EnumEstadoEscaner.INICIADO),
        objTipoEjecucion=TipoEjecucion(enumTipoEjecucion=EnumTipoEjecucion.DIARIA),
    )


def _relative_volume_m5_filtro() -> Filtro:
    return Filtro(
        enumFiltro=EnumFiltro.RELATIVE_VOLUME,
        parametros=[
            Parametro(
                enumParametro=EnumParametro.TIMEFRAME_RELATIVE_VOLUME_PERCENT,
                objValorSeleccionado=ValorString(valor="5M"),
            )
        ],
    )


def test_signal_price_and_timestamp_come_from_last_closed_candle_not_forming_one():
    # Regression: marketdata-service agrega M5 en vivo sobre M1 sin cerrar
    # todavia -- una senal generada sobre esa vela en formacion registraba un
    # precio/hora que dejaba de coincidir con cualquier vela real del grafico
    # una vez que terminaba de cerrar (confirmado en vivo con SUGP). La vela
    # "en formacion" de abajo tiene un close/volume absurdo (999.0) que NUNCA
    # deberia terminar en el SignalMatch.
    now = datetime.now(timezone.utc)
    closed_older = CandleResponse(
        symbol="AAPL", timestamp=now - timedelta(minutes=15),
        open=10.0, high=10.0, low=10.0, close=10.0, volume=100,
    )
    closed_last = CandleResponse(
        symbol="AAPL", timestamp=now - timedelta(minutes=10),
        open=11.0, high=11.0, low=11.0, close=11.0, volume=100,
    )
    forming = CandleResponse(
        symbol="AAPL", timestamp=now - timedelta(minutes=2),
        open=999.0, high=999.0, low=999.0, close=999.0, volume=99999,
    )

    pipeline = SymbolPipeline(_escaner())
    pipeline._filtrados = ["AAPL"]
    filtro = _relative_volume_m5_filtro()

    with patch.object(pipeline._client, "fetch_candles",
                       return_value={"AAPL": [closed_older, closed_last, forming]}):
        signals = pipeline.evaluar_tecnicos({5: [filtro]})

    assert "AAPL" in signals
    match = signals["AAPL"][0]
    assert match.vela_timestamp == closed_last.timestamp
    assert match.precio == 11.0


def test_last_candle_kept_when_already_closed():
    now = datetime.now(timezone.utc)
    older = CandleResponse(
        symbol="AAPL", timestamp=now - timedelta(minutes=20),
        open=10.0, high=10.0, low=10.0, close=10.0, volume=100,
    )
    already_closed = CandleResponse(
        symbol="AAPL", timestamp=now - timedelta(minutes=10),
        open=12.0, high=12.0, low=12.0, close=12.0, volume=100,
    )

    pipeline = SymbolPipeline(_escaner())
    pipeline._filtrados = ["AAPL"]
    filtro = _relative_volume_m5_filtro()

    with patch.object(pipeline._client, "fetch_candles",
                       return_value={"AAPL": [older, already_closed]}):
        signals = pipeline.evaluar_tecnicos({5: [filtro]})

    assert "AAPL" in signals
    match = signals["AAPL"][0]
    assert match.vela_timestamp == already_closed.timestamp
    assert match.precio == 12.0
