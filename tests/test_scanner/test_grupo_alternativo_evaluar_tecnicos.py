from datetime import datetime, time, timedelta, timezone
from unittest.mock import patch

from app.models.enums import EnumCondicional, EnumEstadoEscaner, EnumFiltro, EnumParametro, EnumTipoEjecucion
from app.models.escaner import Escaner, EstadoEscaner, TipoEjecucion
from app.models.filtro import Filtro, Parametro
from app.models.valor import ValorCondicional, ValorFloat, ValorInteger, ValorString

# compute_value() de estas estrategias devuelve 0.0/1.0 -- sin esta
# condicion, evaluate_condition(None, ...) siempre da True sin importar el
# resultado real (ver app/strategies/condition.py), igual que exige el
# comentario en cada FiltroFactory* del lado Java.
_CONDICION_IGUAL_A_UNO = Parametro(
    enumParametro=EnumParametro.CONDICION,
    objValorSeleccionado=ValorCondicional(enumCondicional=EnumCondicional.IGUAL_A, valor1=1.0),
)
from app.scanner.marketdata_models import CandleResponse
from app.scanner.symbols import SymbolPipeline

_NOW = datetime.now(timezone.utc)


def _escaner() -> Escaner:
    return Escaner(
        idEscaner=1,
        nombre="test",
        horaInicio=time(9, 30, 0),
        horaFin=time(16, 0, 0),
        objEstado=EstadoEscaner(enumEstadoEscaner=EnumEstadoEscaner.INICIADO),
        objTipoEjecucion=TipoEjecucion(enumTipoEjecucion=EnumTipoEjecucion.DIARIA),
    )


def _filtro_accel_deceleracion(grupo_alternativo: int) -> Filtro:
    return Filtro(
        enumFiltro=EnumFiltro.ACCELERATION_DECELERATION,
        grupoAlternativo=grupo_alternativo,
        parametros=[
            Parametro(enumParametro=EnumParametro.VELAS_ACELERACION_ACCELERATION_DECELERATION,
                      objValorSeleccionado=ValorInteger(valor=2)),
            Parametro(enumParametro=EnumParametro.VELAS_DESACELERACION_ACCELERATION_DECELERATION,
                      objValorSeleccionado=ValorInteger(valor=1)),
            Parametro(enumParametro=EnumParametro.PROPORCION_DESACELERACION_ACCELERATION_DECELERATION,
                      objValorSeleccionado=ValorFloat(valor=0.4)),
            _CONDICION_IGUAL_A_UNO,
        ],
    )


def _filtro_liquidity_grab(grupo_alternativo: int) -> Filtro:
    return Filtro(
        enumFiltro=EnumFiltro.LIQUIDITY_GRAB_CANDLE,
        grupoAlternativo=grupo_alternativo,
        parametros=[
            Parametro(enumParametro=EnumParametro.LOOKBACK_VELAS_LIQUIDITY_GRAB_CANDLE,
                      objValorSeleccionado=ValorInteger(valor=2)),
            Parametro(enumParametro=EnumParametro.PROPORCION_MECHA_CUERPO_LIQUIDITY_GRAB_CANDLE,
                      objValorSeleccionado=ValorFloat(valor=2.0)),
            Parametro(enumParametro=EnumParametro.DIRECCION_LIQUIDITY_GRAB_CANDLE,
                      objValorSeleccionado=ValorString(valor="ALCISTA")),
            _CONDICION_IGUAL_A_UNO,
        ],
    )


def _velas_donde_solo_acelera_desacelera_pasa() -> list[CandleResponse]:
    # Aceleracion-Desaceleracion pasa (cuerpos grandes, luego uno chico).
    # Liquidity Grab Candle falla sobre las MISMAS velas: la ultima no
    # tiene mecha (open=112, close=112.5, high=112.5, low=112 -> mecha 0).
    return [
        CandleResponse(symbol="AAPL", timestamp=_NOW - timedelta(minutes=50),
                       open=100.0, high=105.0, low=100.0, close=105.0, volume=100),
        CandleResponse(symbol="AAPL", timestamp=_NOW - timedelta(minutes=35),
                       open=105.0, high=112.0, low=105.0, close=112.0, volume=100),
        CandleResponse(symbol="AAPL", timestamp=_NOW - timedelta(minutes=20),
                       open=112.0, high=112.5, low=112.0, close=112.5, volume=100),
    ]


def test_alternativa_que_pasa_alcanza_aunque_la_otra_falle():
    pipeline = SymbolPipeline(_escaner())
    pipeline._filtrados = ["AAPL"]
    filtros = [_filtro_accel_deceleracion(1), _filtro_liquidity_grab(1)]

    with patch.object(pipeline._client, "fetch_candles",
                       return_value={"AAPL": _velas_donde_solo_acelera_desacelera_pasa()}):
        signals = pipeline.evaluar_tecnicos({15: filtros})

    assert "AAPL" in signals
    # Solo el que de verdad matcheo queda registrado como match.
    matched_filters = {m.filtro.enumFiltro for m in signals["AAPL"]}
    assert matched_filters == {EnumFiltro.ACCELERATION_DECELERATION}


def test_sin_grupo_alternativo_ambos_deben_pasar_como_antes():
    # Mismas velas, mismos filtros, pero SIN grupoAlternativo (default) --
    # debe comportarse como el AND estricto de siempre y descartar AAPL,
    # porque Liquidity Grab Candle sigue fallando.
    pipeline = SymbolPipeline(_escaner())
    pipeline._filtrados = ["AAPL"]
    filtros = [_filtro_accel_deceleracion(None), _filtro_liquidity_grab(None)]

    with patch.object(pipeline._client, "fetch_candles",
                       return_value={"AAPL": _velas_donde_solo_acelera_desacelera_pasa()}):
        signals = pipeline.evaluar_tecnicos({15: filtros})

    assert "AAPL" not in signals
