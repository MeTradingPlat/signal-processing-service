from datetime import time

from app.models.enums import EnumEstadoEscaner, EnumFiltro, EnumTipoEjecucion
from app.models.escaner import Escaner, EstadoEscaner, TipoEjecucion
from app.models.filtro import Filtro
from app.scanner.symbols import SymbolPipeline


def _escaner(filtros) -> Escaner:
    return Escaner(
        idEscaner=1,
        nombre="test",
        horaInicio=time(9, 30, 0),
        horaFin=time(16, 0, 0),
        objEstado=EstadoEscaner(enumEstadoEscaner=EnumEstadoEscaner.INICIADO),
        objTipoEjecucion=TipoEjecucion(enumTipoEjecucion=EnumTipoEjecucion.DIARIA),
        filtros=filtros,
    )


def test_fetch_fundamentals_from_cache_no_hace_ninguna_llamada_por_red():
    pipeline = SymbolPipeline(_escaner([Filtro(enumFiltro=EnumFiltro.MARKET_CAP)]), fundamentals_cache={
        "AAPL": {"symbol": "AAPL", "marketCap": 3_000_000_000},
    })
    pipeline._todos = ["AAPL", "MSFT"]

    pipeline._fetch_fundamentals()

    assert set(pipeline._fundamentals) == {"AAPL"}
    assert pipeline._fundamentals["AAPL"].marketCap == 3_000_000_000


def test_fetch_fundamentals_from_cache_ignora_simbolos_sin_dato_en_cache():
    pipeline = SymbolPipeline(_escaner([Filtro(enumFiltro=EnumFiltro.MARKET_CAP)]), fundamentals_cache={})
    pipeline._todos = ["AAPL"]

    pipeline._fetch_fundamentals()

    assert pipeline._fundamentals == {}


def test_aplicar_dinamicos_from_cache_usa_el_precio_del_snapshot_compartido():
    pipeline = SymbolPipeline(
        _escaner([Filtro(enumFiltro=EnumFiltro.PRECIO)]),
        fundamentals_cache={},
        snapshot_cache={"AAPL": {"currentPrice": 150.0}},
    )
    pipeline._todos = pipeline._filtrados = ["AAPL"]
    pipeline._fundamentals = {}

    pipeline._aplicar_dinamicos()

    assert pipeline.filtrados == ["AAPL"]


def test_aplicar_dinamicos_from_cache_descarta_un_simbolo_sin_precio_en_el_snapshot():
    pipeline = SymbolPipeline(
        _escaner([Filtro(enumFiltro=EnumFiltro.PRECIO)]),
        fundamentals_cache={},
        snapshot_cache={},
    )
    pipeline._todos = pipeline._filtrados = ["AAPL"]
    pipeline._fundamentals = {}

    pipeline._aplicar_dinamicos()

    assert pipeline.filtrados == []


def test_aplicar_dinamicos_from_cache_falla_con_gracia_si_la_cache_no_es_accesible():
    class _CacheRota:
        def keys(self):
            raise RuntimeError("manager process murio")

    pipeline = SymbolPipeline(
        _escaner([Filtro(enumFiltro=EnumFiltro.PRECIO)]),
        fundamentals_cache={},
        snapshot_cache=_CacheRota(),
    )
    pipeline._todos = pipeline._filtrados = ["AAPL"]
    pipeline._fundamentals = {}
    pipeline._ultimo_filtrado = ["AAPL"]

    pipeline._aplicar_dinamicos()

    assert pipeline.filtrados == ["AAPL"]
