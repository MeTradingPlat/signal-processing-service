from app.models.enums import EnumFiltro
from app.models.filtro import Filtro
from app.scanner.symbols import _todos_los_requeridos_pasan


def _filtro(grupo_alternativo=None) -> Filtro:
    return Filtro(enumFiltro=EnumFiltro.VOLUME, grupoAlternativo=grupo_alternativo)


def test_todos_requeridos_sin_grupo_deben_pasar_todos():
    filtros = [_filtro(), _filtro()]
    assert _todos_los_requeridos_pasan(filtros, [True, True]) is True
    assert _todos_los_requeridos_pasan(filtros, [True, False]) is False


def test_regresion_comportamiento_identico_al_and_de_siempre():
    # Sin ningun grupoAlternativo (el caso de todos los escaneres reales
    # hoy), el resultado debe ser EXACTAMENTE el AND de toda la vida.
    filtros = [_filtro(), _filtro(), _filtro()]
    assert _todos_los_requeridos_pasan(filtros, [True, True, True]) is True
    assert _todos_los_requeridos_pasan(filtros, [True, False, True]) is False
    assert _todos_los_requeridos_pasan(filtros, [False, False, False]) is False


def test_una_alternativa_de_dos_que_pasa_alcanza():
    filtros = [_filtro(grupo_alternativo=1), _filtro(grupo_alternativo=1)]
    assert _todos_los_requeridos_pasan(filtros, [True, False]) is True
    assert _todos_los_requeridos_pasan(filtros, [False, True]) is True


def test_ninguna_alternativa_pasa_no_alcanza():
    filtros = [_filtro(grupo_alternativo=1), _filtro(grupo_alternativo=1)]
    assert _todos_los_requeridos_pasan(filtros, [False, False]) is False


def test_mixto_requerido_y_alternativo():
    # El requerido SIEMPRE tiene que pasar, sin importar el resultado de
    # las alternativas -- solo estas ultimas se relajan a "al menos una".
    filtros = [_filtro(), _filtro(grupo_alternativo=1), _filtro(grupo_alternativo=1)]
    assert _todos_los_requeridos_pasan(filtros, [True, True, False]) is True
    assert _todos_los_requeridos_pasan(filtros, [True, False, False]) is False
    assert _todos_los_requeridos_pasan(filtros, [False, True, True]) is False


def test_dos_grupos_alternativos_distintos_deben_pasar_cada_uno():
    filtros = [
        _filtro(grupo_alternativo=1), _filtro(grupo_alternativo=1),
        _filtro(grupo_alternativo=2), _filtro(grupo_alternativo=2),
    ]
    # Grupo 1 tiene un pase, grupo 2 no tiene ninguno -> falla igual.
    assert _todos_los_requeridos_pasan(filtros, [True, False, False, False]) is False
    # Ambos grupos con al menos un pase -> pasa.
    assert _todos_los_requeridos_pasan(filtros, [True, False, False, True]) is True
