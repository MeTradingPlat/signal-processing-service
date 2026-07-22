from app.models.enums import (
    EnumCategoriaFiltro,
    EnumEstadoEscaner,
    EnumFiltro,
    EnumMercado,
    EnumParametro,
    EnumTipoEjecucion,
    EnumTipoValor,
)
from app.models.escaner import Escaner
from app.models.valor import ValorFloat, ValorInteger


def test_parses_full_java_escaner_json():
    json_data = {
        "idEscaner": 42,
        "nombre": "Test Scanner",
        "descripcion": "A test scanner",
        "horaInicio": "09:30:00",
        "horaFin": "16:00:00",
        "fechaCreacion": "2025-01-15",
        "objEstado": {"enumEstadoEscaner": "INICIADO"},
        "objTipoEjecucion": {"etiqueta": "execution.daily", "enumTipoEjecucion": "DIARIA"},
        "mercados": [
            {"etiqueta": "market.nasdaq", "enumMercado": "NASDAQ"},
            {"etiqueta": "market.nyse", "enumMercado": "NYSE"},
        ],
        "filtros": [
            {
                "enumFiltro": "RSI",
                "etiquetaNombre": "filter.rsi.name",
                "etiquetaDescripcion": "filter.rsi.description",
                "objCategoria": {
                    "etiqueta": "category.momentum",
                    "enumCategoriaFiltro": "MOMENTUM_E_INDICADORES_TECNICOS",
                },
                "parametros": [
                    {
                        "enumParametro": "PERIODO_RSI",
                        "etiqueta": "parameter.rsi.periodoRsi",
                        "objValorSeleccionado": {
                            "etiqueta": "",
                            "enumTipoValor": "INTEGER",
                            "valor": 14,
                        },
                        "opciones": [
                            {"etiqueta": "7", "enumTipoValor": "INTEGER", "valor": 7},
                            {"etiqueta": "14", "enumTipoValor": "INTEGER", "valor": 14},
                        ],
                    },
                ],
            },
        ],
    }

    escaner = Escaner.model_validate(json_data)

    assert escaner.idEscaner == 42
    assert escaner.nombre == "Test Scanner"
    assert escaner.objEstado.enumEstadoEscaner == EnumEstadoEscaner.INICIADO
    assert escaner.objTipoEjecucion.enumTipoEjecucion == EnumTipoEjecucion.DIARIA
    assert len(escaner.mercados) == 2
    assert escaner.mercados[0].enumMercado == EnumMercado.NASDAQ
    filtro = escaner.filtros[0]
    assert filtro.enumFiltro == EnumFiltro.RSI
    assert filtro.objCategoria.enumCategoriaFiltro == EnumCategoriaFiltro.MOMENTUM_E_INDICADORES_TECNICOS
    parametro = filtro.parametros[0]
    assert parametro.enumParametro == EnumParametro.PERIODO_RSI
    assert isinstance(parametro.objValorSeleccionado, ValorInteger)
    assert parametro.objValorSeleccionado.valor == 14


def test_parses_minimal_escaner():
    json_data = {
        "idEscaner": 1,
        "nombre": "Minimal",
        "horaInicio": "09:30:00",
        "horaFin": "16:00:00",
        "objEstado": {"enumEstadoEscaner": "DETENIDO"},
        "filtros": [],
        "mercados": [],
    }

    escaner = Escaner.model_validate(json_data)

    assert escaner.idEscaner == 1
    assert escaner.objEstado.enumEstadoEscaner == EnumEstadoEscaner.DETENIDO
    assert escaner.filtros == []
    assert escaner.mercados == []


def test_valor_float_discriminated():
    from app.models.valor import ValorFloat

    data = {"etiqueta": "test", "enumTipoValor": "FLOAT", "valor": 3.14}
    v = ValorFloat.model_validate(data)
    assert v.enumTipoValor == EnumTipoValor.FLOAT
    assert v.valor == 3.14
