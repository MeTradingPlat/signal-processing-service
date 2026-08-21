from datetime import datetime, time, timezone

from app.models.enums import EnumEstadoEscaner, EnumFiltro, EnumParametro, EnumTipoEjecucion
from app.models.escaner import Escaner, EstadoEscaner, TipoEjecucion
from app.models.filtro import Filtro
from app.models.parametro import Parametro
from app.models.valor import ValorString
from app.scanner.runner import _CYCLE_SECONDS, _BAR_CLOSE_BUFFER_SECONDS, _next_cycle_delay
from app.scanner.symbols import SymbolPipeline


def _escaner(filtros: list[Filtro]) -> Escaner:
    return Escaner(
        idEscaner=1,
        nombre="test",
        horaInicio=time(9, 30, 0),
        horaFin=time(16, 0, 0),
        objEstado=EstadoEscaner(enumEstadoEscaner=EnumEstadoEscaner.INICIADO),
        objTipoEjecucion=TipoEjecucion(enumTipoEjecucion=EnumTipoEjecucion.DIARIA),
        filtros=filtros,
    )


def _relative_volume_filtro(timeframe: str) -> Filtro:
    return Filtro(
        enumFiltro=EnumFiltro.RELATIVE_VOLUME,
        parametros=[
            Parametro(
                enumParametro=EnumParametro.TIMEFRAME_RELATIVE_VOLUME_PERCENT,
                objValorSeleccionado=ValorString(valor=timeframe),
            )
        ],
    )


def _pipeline(timeframe: str) -> SymbolPipeline:
    pipeline = SymbolPipeline(_escaner([_relative_volume_filtro(timeframe)]))
    assert len(pipeline.tecnicos) == 1
    return pipeline


def _at(epoch_seconds: int) -> datetime:
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)


def test_no_technical_filters_uses_flat_cycle():
    pipeline = SymbolPipeline(_escaner([]))
    assert _next_cycle_delay(pipeline, _at(0)) == _CYCLE_SECONDS


def test_m5_far_from_close_uses_flat_cycle():
    # Regression: antes esto SIEMPRE devolvia el flat de 60s para cualquier
    # timeframe mayor a M1 (period > _CYCLE_SECONDS), sin importar que tan
    # cerca estuviera el cierre real -- confirmado en vivo: una senal M5
    # disparo con casi 2 minutos de atraso sobre el cierre de su vela.
    pipeline = _pipeline("5M")
    # 60s dentro del periodo de 300s -- faltan 240s para cerrar, muy lejos
    # del proximo tick normal de 60s.
    now = _at(1000 * 300 + 60)
    assert _next_cycle_delay(pipeline, now) == _CYCLE_SECONDS


def test_m5_close_to_close_aligns_to_bar_boundary():
    pipeline = _pipeline("5M")
    # 250s dentro del periodo de 300s -- faltan 50s para cerrar, dentro del
    # proximo tick normal: debe alinearse al cierre real en vez de seguir
    # con el flat de 60s (que lo dejaria evaluando la vela vieja).
    now = _at(1000 * 300 + 250)
    assert _next_cycle_delay(pipeline, now) == 50.0 + _BAR_CLOSE_BUFFER_SECONDS


def test_m1_always_aligns_to_bar_boundary():
    pipeline = _pipeline("1M")
    now = _at(1000 * 60 + 10)
    assert _next_cycle_delay(pipeline, now) == 50.0 + _BAR_CLOSE_BUFFER_SECONDS
