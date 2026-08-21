from datetime import time

from app.models.enums import EnumEstadoEscaner, EnumFiltro, EnumTipoEjecucion
from app.models.escaner import Escaner, EstadoEscaner, TipoEjecucion
from app.models.filtro import Filtro
from app.scanner.symbols import SymbolPipeline


def _escaner_solo_dinamicos() -> Escaner:
    return Escaner(
        idEscaner=1,
        nombre="test",
        horaInicio=time(9, 30, 0),
        horaFin=time(16, 0, 0),
        objEstado=EstadoEscaner(enumEstadoEscaner=EnumEstadoEscaner.INICIADO),
        objTipoEjecucion=TipoEjecucion(enumTipoEjecucion=EnumTipoEjecucion.DIARIA),
        filtros=[Filtro(enumFiltro=EnumFiltro.CHANGE), Filtro(enumFiltro=EnumFiltro.GAP_FROM_CLOSE)],
    )


def test_aplicar_estaticos_resets_filtrados_to_todos_when_no_static_filters():
    # Regression: sin filtros estaticos, _aplicar_estaticos retornaba sin
    # tocar _filtrados, asi que _aplicar_dinamicos filtraba sobre su propio
    # resultado del ciclo anterior en vez del universo completo -- un
    # simbolo que un ciclo no pasaba el filtro dinamico quedaba excluido
    # para siempre, convergiendo a lista vacia y quedandose ahi (confirmado
    # en vivo: 'TEST POST MARKET', solo CHANGE + GAP_FROM_CLOSE, 3+ horas
    # seguidas en count=0).
    pipeline = SymbolPipeline(_escaner_solo_dinamicos())
    assert pipeline.pre_estaticos == []
    pipeline._todos = ["AAPL", "MSFT", "GOOG"]
    pipeline._filtrados = ["AAPL"]  # simula el pool ya angostado por un ciclo previo

    pipeline._aplicar_estaticos()

    assert pipeline.filtrados == ["AAPL", "MSFT", "GOOG"]
