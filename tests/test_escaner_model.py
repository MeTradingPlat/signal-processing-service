"""Tests for Escaner domain model parsing (desde_dict, Filtro, Parametro)."""
import pytest
from datetime import time

from app.domain.models.escaner import (
    Escaner,
    Filtro,
    Parametro,
    ValorCondicional,
    _parsear_hora,
)


# ──────────────────────────────────────────────────────────────────────────────
# _parsear_hora
# ──────────────────────────────────────────────────────────────────────────────

class TestParsearHora:
    def test_hora_completa(self):
        assert _parsear_hora("09:30:00") == time(9, 30, 0)

    def test_hora_con_segundos(self):
        assert _parsear_hora("16:00:30") == time(16, 0, 30)

    def test_hora_solo_hm(self):
        assert _parsear_hora("14:45") == time(14, 45, 0)

    def test_medianoche(self):
        assert _parsear_hora("00:00:00") == time(0, 0, 0)

    def test_fin_de_dia(self):
        assert _parsear_hora("23:59:59") == time(23, 59, 59)


# ──────────────────────────────────────────────────────────────────────────────
# Parametro
# ──────────────────────────────────────────────────────────────────────────────

class TestParametro:
    def test_obtener_condicional_con_tipo_condicional(self):
        p = Parametro(
            enum_parametro="RSI_UMBRAL",
            obj_valor_seleccionado={
                "enumTipoValor": "CONDICIONAL",
                "enumCondicional": "MENOR_QUE",
                "isInteger": False,
                "valor1": 30.0,
                "valor2": None,
            },
        )
        c = p.obtener_condicional()
        assert c is not None
        assert c.enum_condicional == "MENOR_QUE"
        assert c.valor1 == 30.0
        assert c.is_integer is False

    def test_obtener_condicional_retorna_none_si_no_condicional(self):
        p = Parametro(
            enum_parametro="RSI_PERIODO",
            obj_valor_seleccionado={"enumTipoValor": "INTEGER", "valor": 14},
        )
        assert p.obtener_condicional() is None

    def test_obtener_condicional_retorna_none_si_sin_valor(self):
        p = Parametro(enum_parametro="X")
        assert p.obtener_condicional() is None

    def test_obtener_valor_numerico_integer(self):
        p = Parametro(
            enum_parametro="PERIODO",
            obj_valor_seleccionado={"enumTipoValor": "INTEGER", "valor": 14},
        )
        assert p.obtener_valor_numerico() == 14

    def test_obtener_valor_numerico_float(self):
        p = Parametro(
            enum_parametro="UMBRAL",
            obj_valor_seleccionado={"enumTipoValor": "FLOAT", "valor": 1.5},
        )
        assert p.obtener_valor_numerico() == 1.5

    def test_obtener_valor_numerico_retorna_none_si_no_numerico(self):
        p = Parametro(
            enum_parametro="TF",
            obj_valor_seleccionado={"enumTipoValor": "STRING", "valor": "1d"},
        )
        assert p.obtener_valor_numerico() is None

    def test_obtener_valor_string_con_tipo_string(self):
        p = Parametro(
            enum_parametro="TIMEFRAME",
            obj_valor_seleccionado={"enumTipoValor": "STRING", "valor": "1d"},
        )
        assert p.obtener_valor_string() == "1d"

    def test_obtener_valor_string_via_etiqueta(self):
        p = Parametro(
            enum_parametro="TIMEFRAME",
            obj_valor_seleccionado={"enumTipoValor": "ENUM", "etiqueta": "1h"},
        )
        assert p.obtener_valor_string() == "1h"

    def test_obtener_valor_string_retorna_none_si_sin_valor(self):
        p = Parametro(enum_parametro="X")
        assert p.obtener_valor_string() is None


# ──────────────────────────────────────────────────────────────────────────────
# Filtro
# ──────────────────────────────────────────────────────────────────────────────

class TestFiltro:
    def _make_filtro(self):
        return Filtro(
            enum_filtro="RSI",
            parametros=[
                Parametro(enum_parametro="RSI_PERIODO", obj_valor_seleccionado={"enumTipoValor": "INTEGER", "valor": 14}),
                Parametro(enum_parametro="RSI_UMBRAL", obj_valor_seleccionado={"enumTipoValor": "CONDICIONAL", "enumCondicional": "MENOR_QUE", "valor1": 30.0}),
                Parametro(enum_parametro="RSI_TIMEFRAME", obj_valor_seleccionado={"enumTipoValor": "STRING", "valor": "1d"}),
            ],
        )

    def test_obtener_parametro_existente(self):
        f = self._make_filtro()
        p = f.obtener_parametro("RSI_PERIODO")
        assert p is not None
        assert p.enum_parametro == "RSI_PERIODO"

    def test_obtener_parametro_retorna_none_si_no_existe(self):
        f = self._make_filtro()
        assert f.obtener_parametro("NO_EXISTE") is None

    def test_obtener_timeframe_encuentra_parametro_con_timeframe(self):
        f = self._make_filtro()
        tf = f.obtener_timeframe()
        assert tf == "1d"

    def test_obtener_timeframe_retorna_none_si_no_tiene(self):
        f = Filtro(enum_filtro="RSI", parametros=[
            Parametro(enum_parametro="RSI_PERIODO"),
        ])
        assert f.obtener_timeframe() is None


# ──────────────────────────────────────────────────────────────────────────────
# Escaner.desde_dict
# ──────────────────────────────────────────────────────────────────────────────

class TestEscanerDesdeDict:
    def _escaner_data(self, **overrides):
        base = {
            "idEscaner": 10,
            "nombre": "Scanner de Prueba",
            "descripcion": "Descripcion test",
            "horaInicio": "09:30:00",
            "horaFin": "16:00:00",
            "objTipoEjecucion": {"enumTipoEjecucion": "DIARIA"},
            "mercados": [{"enumMercado": "NYSE"}, {"enumMercado": "NASDAQ"}],
        }
        base.update(overrides)
        return base

    def test_parsea_campos_basicos(self):
        e = Escaner.desde_dict(self._escaner_data())
        assert e.id_escaner == 10
        assert e.nombre == "Scanner de Prueba"
        assert e.descripcion == "Descripcion test"

    def test_parsea_horas(self):
        e = Escaner.desde_dict(self._escaner_data())
        assert e.hora_inicio == time(9, 30, 0)
        assert e.hora_fin == time(16, 0, 0)

    def test_parsea_tipo_ejecucion_diaria(self):
        e = Escaner.desde_dict(self._escaner_data())
        assert e.tipo_ejecucion == "DIARIA"

    def test_parsea_tipo_ejecucion_una_vez(self):
        data = self._escaner_data(objTipoEjecucion={"enumTipoEjecucion": "UNA_VEZ"})
        e = Escaner.desde_dict(data)
        assert e.tipo_ejecucion == "UNA_VEZ"

    def test_parsea_mercados_como_enum(self):
        e = Escaner.desde_dict(self._escaner_data())
        assert "NYSE" in e.mercados
        assert "NASDAQ" in e.mercados

    def test_parsea_mercados_como_string_directo(self):
        data = self._escaner_data(mercados=["NYSE", "CRYPTO"])
        e = Escaner.desde_dict(data)
        assert e.mercados == ["NYSE", "CRYPTO"]

    def test_sin_filtros_lista_vacia(self):
        e = Escaner.desde_dict(self._escaner_data())
        assert e.filtros == []

    def test_parsea_filtros(self):
        filtros_data = [
            {
                "enumFiltro": "RSI",
                "etiquetaNombre": "RSI Filter",
                "etiquetaDescripcion": "desc",
                "parametros": [
                    {
                        "enumParametro": "RSI_PERIODO",
                        "etiqueta": "Periodo",
                        "objValorSeleccionado": {"enumTipoValor": "INTEGER", "valor": 14},
                        "opciones": [],
                    }
                ],
            }
        ]
        e = Escaner.desde_dict(self._escaner_data(), filtros_data)
        assert len(e.filtros) == 1
        assert e.filtros[0].enum_filtro == "RSI"
        assert len(e.filtros[0].parametros) == 1
        assert e.filtros[0].parametros[0].enum_parametro == "RSI_PERIODO"

    def test_valores_por_defecto_si_campos_ausentes(self):
        e = Escaner.desde_dict({})
        assert e.id_escaner == 0
        assert e.nombre == ""
        assert e.tipo_ejecucion == "DIARIA"
        assert e.hora_inicio == time(0, 0, 0)
        assert e.hora_fin == time(23, 59, 0)

    def test_multiples_filtros(self):
        filtros_data = [
            {"enumFiltro": "RSI", "parametros": []},
            {"enumFiltro": "ATR", "parametros": []},
            {"enumFiltro": "EMA", "parametros": []},
        ]
        e = Escaner.desde_dict(self._escaner_data(), filtros_data)
        assert len(e.filtros) == 3
        tipos = [f.enum_filtro for f in e.filtros]
        assert "RSI" in tipos
        assert "ATR" in tipos
        assert "EMA" in tipos
