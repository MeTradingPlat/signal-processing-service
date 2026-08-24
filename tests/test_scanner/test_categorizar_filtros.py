from app.models.enums import EnumCategoriaFiltro, EnumFiltro
from app.models.filtro import CategoriaFiltro, Filtro
from app.scanner.symbols import categorizar_filtros


def _filtro(enum_filtro: EnumFiltro, categoria: EnumCategoriaFiltro | None) -> Filtro:
    return Filtro(
        enumFiltro=enum_filtro,
        objCategoria=None if categoria is None else CategoriaFiltro(enumCategoriaFiltro=categoria),
    )


def test_break_over_y_high_low_requieren_velas_pese_a_categoria_dinamica():
    filtros = [
        _filtro(EnumFiltro.BREAK_OVER_RECENT_HIGHS_LOWS, EnumCategoriaFiltro.PRECIO_Y_MOVIMIENTO),
        _filtro(EnumFiltro.HIGH_LOW_OF_DAY, EnumCategoriaFiltro.PRECIO_Y_MOVIMIENTO),
        _filtro(EnumFiltro.PERCENTAGE_PULLBACK_HIGHS_LOWS, EnumCategoriaFiltro.PRECIO_Y_MOVIMIENTO),
    ]
    estaticos, dinamicos, tecnicos = categorizar_filtros(filtros)
    assert estaticos == []
    assert dinamicos == []
    assert len(tecnicos) == 3


def test_volume_dinamico_se_mantiene():
    filtros = [_filtro(EnumFiltro.VOLUME, EnumCategoriaFiltro.VOLUMEN)]
    estaticos, dinamicos, tecnicos = categorizar_filtros(filtros)
    assert len(dinamicos) == 1
    assert tecnicos == []
