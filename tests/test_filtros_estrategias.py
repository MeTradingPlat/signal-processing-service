"""Tests unitarios para todos los filtros/estrategias de worker_filtros.py.

Cada filtro tiene tests que verifican:
  - Caso positivo (condición se cumple → señal)
  - Caso negativo (condición no se cumple → sin señal)
  - Datos insuficientes → comportamiento permisivo (True)
  - Casos borde relevantes

Los filtros de indicadores técnicos (RSI, ATR, EMA, VWAP) usan mock_pandas_ta.
Los filtros de lógica pura (precio, volumen, patrones) no necesitan mocks.

Estandarización de valores (igual que scanner-management):
  - Porcentajes  : raw  (1 % → 1.0)
  - Dólares      : raw  ($1.50 → 1.5)
  - Volumen      : shares reales
  - Relativo vol.: % (150 → 1.5×)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.core.worker_filtros import evaluar_simbolos


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _barras(n=30, open_=100.0, close_=101.0, high_=102.0, low_=99.0,
            volume=1_000_000.0, delta_close=0.0) -> list[dict]:
    t = datetime(2025, 1, 6, 9, 30, tzinfo=timezone.utc)  # lunes
    rows = []
    c = close_
    for i in range(n):
        c += delta_close
        rows.append({
            "timestamp": (t + timedelta(minutes=i)).isoformat(),
            "open": open_, "high": max(high_, c + 0.5),
            "low": min(low_, c - 0.5), "close": round(c, 4),
            "volume": volume,
        })
    return rows


def _df(barras) -> pd.DataFrame:
    df = pd.DataFrame(barras)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _ctx(barras, symbol="SYM", fundamentales: dict | None = None) -> dict:
    df = _df(barras)
    return {symbol: {"symbol": symbol,
                     "barras_por_tf": {"M5": df.to_dict(orient="list")},
                     "fundamentales": fundamentales or {},
                     "halteado": False}}


def _filtro(enum_filtro, condicional=None, v1=None, v2=None, **extra_params):
    """Construye un dict de filtro serializado."""
    parametros = []
    if condicional and v1 is not None:
        parametros.append({"enum_parametro": "CONDICION", "obj_valor_seleccionado": {
            "enumTipoValor": "CONDICIONAL", "enumCondicional": condicional,
            "valor1": v1, "valor2": v2}})
    for k, v in extra_params.items():
        tipo = "INTEGER" if isinstance(v, int) else ("STRING" if isinstance(v, str) else "FLOAT")
        parametros.append({"enum_parametro": k, "obj_valor_seleccionado": {
            "enumTipoValor": tipo, "valor": v}})
    return {"enum_filtro": enum_filtro, "parametros": parametros}


def _senales(barras, filtros, symbol="SYM", fundamentales: dict | None = None):
    return evaluar_simbolos(_ctx(barras, symbol, fundamentales), filtros, 1, "Test")


# ═════════════════════════════════════════════════════════════════════════════
# VOLUMEN
# ═════════════════════════════════════════════════════════════════════════════

class TestVolume:
    def test_volume_mayor_que_cumple(self):
        bs = _barras(5, volume=2_000_000)
        assert len(_senales(bs, [_filtro("VOLUME", "MAYOR_QUE", 1_000_000)])) == 1

    def test_volume_mayor_que_no_cumple(self):
        bs = _barras(5, volume=500_000)
        assert len(_senales(bs, [_filtro("VOLUME", "MAYOR_QUE", 1_000_000)])) == 0

    def test_volume_menor_que_cumple(self):
        bs = _barras(5, volume=100_000)
        assert len(_senales(bs, [_filtro("VOLUME", "MENOR_QUE", 500_000)])) == 1

    def test_volume_entre_cumple(self):
        bs = _barras(5, volume=300_000)
        assert len(_senales(bs, [_filtro("VOLUME", "ENTRE", 100_000, 500_000)])) == 1

    def test_volume_entre_no_cumple(self):
        bs = _barras(5, volume=600_000)
        assert len(_senales(bs, [_filtro("VOLUME", "ENTRE", 100_000, 500_000)])) == 0


class TestAverageVolume:
    def test_average_volume_cumple(self):
        bs = _barras(10, volume=2_000_000)
        assert len(_senales(bs, [_filtro("AVERAGE_VOLUME", "MAYOR_QUE", 1_000_000)])) == 1

    def test_average_volume_no_cumple(self):
        bs = _barras(10, volume=200_000)
        assert len(_senales(bs, [_filtro("AVERAGE_VOLUME", "MAYOR_QUE", 1_000_000)])) == 0

    def test_average_es_promedio_de_todas_las_velas(self):
        # Primeras 9 velas vol=1M, última=3M → promedio ≠ última
        barras = _barras(9, volume=1_000_000) + _barras(1, volume=3_000_000)
        # Promedio = (9*1M + 3M) / 10 = 1.2M
        assert len(_senales(barras, [_filtro("AVERAGE_VOLUME", "MAYOR_QUE", 1_100_000)])) == 1
        assert len(_senales(barras, [_filtro("AVERAGE_VOLUME", "MAYOR_QUE", 1_300_000)])) == 0


class TestRelativeVolume:
    def test_relative_volume_150_pct_cumple(self):
        # Últimas 9 velas = 1M, última = 2M → relativo = 200%
        barras = _barras(9, volume=1_000_000) + _barras(1, volume=2_000_000)
        assert len(_senales(barras, [_filtro("RELATIVE_VOLUME", "MAYOR_QUE", 150)])) == 1

    def test_relative_volume_no_cumple(self):
        # Todas igual vol → relativo = 100%
        barras = _barras(10, volume=1_000_000)
        assert len(_senales(barras, [_filtro("RELATIVE_VOLUME", "MAYOR_QUE", 150)])) == 0

    def test_relative_volume_datos_insuficientes(self):
        bs = _barras(1, volume=5_000_000)
        assert len(_senales(bs, [_filtro("RELATIVE_VOLUME", "MAYOR_QUE", 50)])) == 1


class TestVolumeSpike:
    def test_volume_spike_detecta_pico(self):
        # Últimas 5 velas = 100k, última = 1M → ratio = 10×
        barras = _barras(5, volume=100_000) + _barras(1, volume=1_000_000)
        f = _filtro("VOLUME_SPIKE", "MAYOR_QUE", 5, **{"NUMERO_VELAS_VOLUME_SPIKE": 5})
        assert len(_senales(barras, [f])) == 1

    def test_volume_spike_no_detecta_sin_pico(self):
        barras = _barras(6, volume=100_000)
        f = _filtro("VOLUME_SPIKE", "MAYOR_QUE", 5, **{"NUMERO_VELAS_VOLUME_SPIKE": 5})
        assert len(_senales(barras, [f])) == 0


class TestVolumenPostPre:
    def test_sin_datos_en_cache_es_restrictivo(self):
        bs = _barras(5)
        # Sin datos en fundamentales → restrictivo (False)
        assert len(_senales(bs, [_filtro("VOLUMEN_POST_PRE", "MAYOR_QUE", 999_999_999)])) == 0

    def test_pre_market_volume_cumple(self):
        bs = _barras(5)
        fund = {"pre_market_volume": 500_000, "post_market_volume": 0}
        f = _filtro("VOLUMEN_POST_PRE", "MAYOR_QUE", 100_000, **{"SESION_VOLUMEN_POST_PRE": "PRE"})
        assert len(_senales(bs, [f], fundamentales=fund)) == 1

    def test_pre_market_volume_no_cumple(self):
        bs = _barras(5)
        fund = {"pre_market_volume": 50_000, "post_market_volume": 0}
        f = _filtro("VOLUMEN_POST_PRE", "MAYOR_QUE", 100_000, **{"SESION_VOLUMEN_POST_PRE": "PRE"})
        assert len(_senales(bs, [f], fundamentales=fund)) == 0

    def test_post_market_volume_cumple(self):
        bs = _barras(5)
        fund = {"pre_market_volume": 0, "post_market_volume": 200_000}
        f = _filtro("VOLUMEN_POST_PRE", "MAYOR_QUE", 100_000, **{"SESION_VOLUMEN_POST_PRE": "POST"})
        assert len(_senales(bs, [f], fundamentales=fund)) == 1

    def test_ambos_suma_pre_y_post(self):
        bs = _barras(5)
        fund = {"pre_market_volume": 300_000, "post_market_volume": 400_000}
        # AMBOS = 700_000 → MAYOR_QUE 500_000 cumple
        f = _filtro("VOLUMEN_POST_PRE", "MAYOR_QUE", 500_000)
        assert len(_senales(bs, [f], fundamentales=fund)) == 1

    def test_ambos_no_cumple(self):
        bs = _barras(5)
        fund = {"pre_market_volume": 100_000, "post_market_volume": 100_000}
        # AMBOS = 200_000 → MAYOR_QUE 500_000 no cumple
        f = _filtro("VOLUMEN_POST_PRE", "MAYOR_QUE", 500_000)
        assert len(_senales(bs, [f], fundamentales=fund)) == 0


# ═════════════════════════════════════════════════════════════════════════════
# PRECIO Y MOVIMIENTO
# ═════════════════════════════════════════════════════════════════════════════

class TestPrecio:
    def test_precio_mayor_que_cumple(self):
        bs = _barras(5, close_=150.0)
        assert len(_senales(bs, [_filtro("PRECIO", "MAYOR_QUE", 100)])) == 1

    def test_precio_menor_que_cumple(self):
        bs = _barras(5, close_=5.0)
        assert len(_senales(bs, [_filtro("PRECIO", "MENOR_QUE", 10)])) == 1

    def test_precio_entre_cumple(self):
        bs = _barras(5, close_=25.0)
        assert len(_senales(bs, [_filtro("PRECIO", "ENTRE", 10, 50)])) == 1

    def test_precio_no_cumple(self):
        bs = _barras(5, close_=5.0)
        assert len(_senales(bs, [_filtro("PRECIO", "MAYOR_QUE", 10)])) == 0


class TestChange:
    def test_change_porcentaje_positivo_cumple(self):
        # open[0]=100, close[-1]=110 → +10%
        bs = _barras(5, open_=100, close_=110)
        f = _filtro("CHANGE", "MAYOR_QUE", 5,
                    **{"PUNTO_REFERENCIA_CHANGE": "OPEN", "TIPO_MEDIDA_CHANGE": "PORCENTAJE"})
        assert len(_senales(bs, [f])) == 1

    def test_change_porcentaje_negativo_no_cumple(self):
        bs = _barras(5, open_=100, close_=110)
        f = _filtro("CHANGE", "MENOR_QUE", -5,
                    **{"PUNTO_REFERENCIA_CHANGE": "OPEN", "TIPO_MEDIDA_CHANGE": "PORCENTAJE"})
        assert len(_senales(bs, [f])) == 0

    def test_change_precio_dolares(self):
        bs = _barras(5, open_=100, close_=105)
        f = _filtro("CHANGE", "MAYOR_QUE", 3,
                    **{"PUNTO_REFERENCIA_CHANGE": "OPEN", "TIPO_MEDIDA_CHANGE": "PRECIO"})
        assert len(_senales(bs, [f])) == 1

    def test_change_referencia_close_anterior(self):
        # close[-2]=100, close[-1]=110 → +10 en dólares
        barras = _barras(4, close_=100) + _barras(1, close_=110)
        f = _filtro("CHANGE", "MAYOR_QUE", 5,
                    **{"PUNTO_REFERENCIA_CHANGE": "CLOSE", "TIPO_MEDIDA_CHANGE": "PRECIO"})
        assert len(_senales(barras, [f])) == 1


class TestPercentageChange:
    def test_percentage_change_positivo_cumple(self):
        # open[0]=100, close[-1]=120 → +20%
        bs = _barras(5, open_=100, close_=120)
        assert len(_senales(bs, [_filtro("PERCENTAGE_CHANGE", "MAYOR_QUE", 10)])) == 1

    def test_percentage_change_negativo(self):
        bs = _barras(5, open_=100, close_=80)
        assert len(_senales(bs, [_filtro("PERCENTAGE_CHANGE", "MENOR_QUE", -10)])) == 1

    def test_percentage_change_no_cumple(self):
        bs = _barras(5, open_=100, close_=102)
        assert len(_senales(bs, [_filtro("PERCENTAGE_CHANGE", "MAYOR_QUE", 10)])) == 0


class TestGapFromClose:
    def test_gap_positivo_en_dolares(self):
        # close[-2]=100, open[-1]=105 → gap = +5
        barras = _barras(4, close_=100, open_=100) + _barras(1, open_=105, close_=105)
        f = _filtro("GAP_FROM_CLOSE", "MAYOR_QUE", 3, **{"FORMATO_GAP_FROM_CLOSE": "PRECIO"})
        assert len(_senales(barras, [f])) == 1

    def test_gap_negativo_no_cumple(self):
        barras = _barras(4, close_=100, open_=100) + _barras(1, open_=95, close_=95)
        f = _filtro("GAP_FROM_CLOSE", "MAYOR_QUE", 3, **{"FORMATO_GAP_FROM_CLOSE": "PRECIO"})
        assert len(_senales(barras, [f])) == 0

    def test_gap_datos_insuficientes(self):
        bs = _barras(1)
        assert len(_senales(bs, [_filtro("GAP_FROM_CLOSE", "MAYOR_QUE", 1)])) == 1


class TestPositionInRange:
    def test_position_in_range_arriba(self):
        # high=110, low=90, close=108 → pos = (108-90)/(110-90)*100 = 90%
        bs = _barras(5, high_=110, low_=90, close_=108)
        assert len(_senales(bs, [_filtro("POSITION_IN_RANGE", "MAYOR_QUE", 80)])) == 1

    def test_position_in_range_abajo(self):
        bs = _barras(5, high_=110, low_=90, close_=92)
        assert len(_senales(bs, [_filtro("POSITION_IN_RANGE", "MENOR_QUE", 20)])) == 1

    def test_position_in_range_entre_cumple(self):
        bs = _barras(5, high_=110, low_=90, close_=100)
        # pos = (100-90)/(110-90)*100 = 50%
        assert len(_senales(bs, [_filtro("POSITION_IN_RANGE", "ENTRE", 40, 60)])) == 1


class TestPercentageRange:
    def test_percentage_range_alto_cumple(self):
        # high=110, low=90, close=100 → range% = 20/100*100 = 20%
        bs = _barras(5, high_=110, low_=90, close_=100)
        assert len(_senales(bs, [_filtro("PERCENTAGE_RANGE", "MAYOR_QUE", 15)])) == 1

    def test_percentage_range_bajo_no_cumple(self):
        bs = _barras(5, high_=100.5, low_=99.5, close_=100)
        # range% = 1/100*100 = 1%
        assert len(_senales(bs, [_filtro("PERCENTAGE_RANGE", "MAYOR_QUE", 5)])) == 0


class TestRangeDollars:
    def test_range_dollars_cumple(self):
        # high=110, low=90 → range = $20
        bs = _barras(5, high_=110, low_=90, close_=100)
        assert len(_senales(bs, [_filtro("RANGE_DOLLARS", "MAYOR_QUE", 10)])) == 1

    def test_range_dollars_no_cumple(self):
        bs = _barras(5, high_=100.5, low_=99.5, close_=100)
        assert len(_senales(bs, [_filtro("RANGE_DOLLARS", "MAYOR_QUE", 5)])) == 0

    def test_range_dollars_exacto(self):
        bs = _barras(5, high_=105, low_=95, close_=100)
        # range = $10, MAYOR_QUE 10 → False (no es mayor, es igual)
        assert len(_senales(bs, [_filtro("RANGE_DOLLARS", "MAYOR_QUE", 10)])) == 0
        assert len(_senales(bs, [_filtro("RANGE_DOLLARS", "MENOR_QUE", 11)])) == 1


class TestCrossingAboveBelow:
    def test_cruce_del_open(self, mock_pandas_ta):
        # open=100, prev_close=98, curr_close=102 → cruzó el open hacia arriba
        barras = [
            {"timestamp": "2025-01-06T09:30:00Z", "open": 100, "high": 103, "low": 97, "close": 98, "volume": 1e6},
            {"timestamp": "2025-01-06T09:31:00Z", "open": 100, "high": 103, "low": 99, "close": 102, "volume": 1e6},
        ]
        f = _filtro("CROSSING_ABOVE_BELOW", **{"NIVEL_CRUCE_CROSSING_ABOVE_BELOW": "OPEN"})
        assert len(_senales(barras, [f])) == 1

    def test_sin_cruce_mismo_lado(self, mock_pandas_ta):
        barras = [
            {"timestamp": "2025-01-06T09:30:00Z", "open": 100, "high": 103, "low": 97, "close": 98, "volume": 1e6},
            {"timestamp": "2025-01-06T09:31:00Z", "open": 100, "high": 101, "low": 97, "close": 99, "volume": 1e6},
        ]
        f = _filtro("CROSSING_ABOVE_BELOW", **{"NIVEL_CRUCE_CROSSING_ABOVE_BELOW": "OPEN"})
        # Ambos cierres están por debajo del open → no hubo cruce
        assert len(_senales(barras, [f])) == 0

    def test_cruce_ema(self, mock_pandas_ta):
        mock_pandas_ta.ema.return_value = pd.Series([100.0])
        barras = [
            {"timestamp": "2025-01-06T09:30:00Z", "open": 99, "high": 101, "low": 98, "close": 99, "volume": 1e6},
            {"timestamp": "2025-01-06T09:31:00Z", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 1e6},
        ]
        f = _filtro("CROSSING_ABOVE_BELOW",
                    **{"NIVEL_CRUCE_CROSSING_ABOVE_BELOW": "EMA",
                       "PERIODO_EMA_CROSSING_ABOVE_BELOW": 20})
        assert len(_senales(barras, [f])) == 1

    def test_datos_insuficientes(self, mock_pandas_ta):
        bs = _barras(1)
        assert len(_senales(bs, [_filtro("CROSSING_ABOVE_BELOW")])) == 1


class TestHalt:
    def test_halt_siempre_pasa(self):
        bs = _barras(5, volume=0, close_=0)
        assert len(_senales(bs, [_filtro("HALT")])) == 1


# ═════════════════════════════════════════════════════════════════════════════
# VOLATILIDAD
# ═════════════════════════════════════════════════════════════════════════════

class TestATR:
    def test_atr_mayor_que_cero_genera_senal(self, mock_pandas_ta):
        mock_pandas_ta.atr.return_value = pd.Series([2.5])
        bs = _barras(30)
        assert len(_senales(bs, [_filtro("ATR", "MAYOR_QUE", 0)])) == 1

    def test_atr_mayor_que_no_cumple(self, mock_pandas_ta):
        mock_pandas_ta.atr.return_value = pd.Series([0.5])
        bs = _barras(30)
        assert len(_senales(bs, [_filtro("ATR", "MAYOR_QUE", 1.0)])) == 0

    def test_atr_lee_longitud_atr(self, mock_pandas_ta):
        mock_pandas_ta.atr.return_value = pd.Series([1.0])
        bs = _barras(30)
        _senales(bs, [_filtro("ATR", "MAYOR_QUE", 0, **{"LONGITUD_ATR": 20})])
        _, kw = mock_pandas_ta.atr.call_args
        assert kw.get("length") == 20

    def test_atr_datos_insuficientes(self, mock_pandas_ta):
        bs = _barras(5)
        assert len(_senales(bs, [_filtro("ATR", "MAYOR_QUE", 999)])) == 1
        mock_pandas_ta.atr.assert_not_called()


class TestATRP:
    def test_atrp_calcula_pct_del_precio(self, mock_pandas_ta):
        # ATR=2, close=100 → ATRP=2%
        mock_pandas_ta.atr.return_value = pd.Series([2.0])
        bs = _barras(30, close_=100.0)
        assert len(_senales(bs, [_filtro("ATRP", "MAYOR_QUE", 1.5)])) == 1

    def test_atrp_no_cumple(self, mock_pandas_ta):
        mock_pandas_ta.atr.return_value = pd.Series([0.5])
        bs = _barras(30, close_=100.0)
        # ATRP = 0.5%
        assert len(_senales(bs, [_filtro("ATRP", "MAYOR_QUE", 1.0)])) == 0

    def test_atrp_lee_periodo_atr_atrp(self, mock_pandas_ta):
        mock_pandas_ta.atr.return_value = pd.Series([1.0])
        bs = _barras(30)
        _senales(bs, [_filtro("ATRP", "MAYOR_QUE", 0, **{"PERIODO_ATR_ATRP": 7})])
        _, kw = mock_pandas_ta.atr.call_args
        assert kw.get("length") == 7


class TestRelativeRange:
    def test_relative_range_alto_cumple(self, mock_pandas_ta):
        # ATR=1, range última vela=3 → relRange=300%
        mock_pandas_ta.atr.return_value = pd.Series([1.0])
        bs = _barras(30, high_=103, low_=100, close_=101)
        assert len(_senales(bs, [_filtro("RELATIVE_RANGE", "MAYOR_QUE", 200)])) == 1

    def test_relative_range_bajo_no_cumple(self, mock_pandas_ta):
        mock_pandas_ta.atr.return_value = pd.Series([10.0])
        bs = _barras(30, high_=100.5, low_=99.5, close_=100)
        # range=1, ATR=10 → relRange=10%
        assert len(_senales(bs, [_filtro("RELATIVE_RANGE", "MAYOR_QUE", 50)])) == 0


# ═════════════════════════════════════════════════════════════════════════════
# MOMENTUM E INDICADORES TÉCNICOS
# ═════════════════════════════════════════════════════════════════════════════

class TestRSI:
    def test_rsi_sobrecomprado_genera_senal(self, mock_pandas_ta):
        mock_pandas_ta.rsi.return_value = pd.Series([80.0])
        bs = _barras(30)
        assert len(_senales(bs, [_filtro("RSI", "MAYOR_QUE", 70)])) == 1

    def test_rsi_sobreventa_genera_senal(self, mock_pandas_ta):
        mock_pandas_ta.rsi.return_value = pd.Series([25.0])
        bs = _barras(30)
        assert len(_senales(bs, [_filtro("RSI", "MENOR_QUE", 30)])) == 1

    def test_rsi_no_cumple(self, mock_pandas_ta):
        mock_pandas_ta.rsi.return_value = pd.Series([50.0])
        bs = _barras(30)
        assert len(_senales(bs, [_filtro("RSI", "MAYOR_QUE", 70)])) == 0

    def test_rsi_lee_periodo_rsi(self, mock_pandas_ta):
        mock_pandas_ta.rsi.return_value = pd.Series([50.0])
        bs = _barras(30)
        _senales(bs, [_filtro("RSI", "MAYOR_QUE", 0, **{"PERIODO_RSI": 7})])
        _, kw = mock_pandas_ta.rsi.call_args
        assert kw.get("length") == 7


class TestDistanceFromVwapEmaMa:
    def test_distance_ema_positiva_cumple(self, mock_pandas_ta):
        # close=110, EMA=100 → distancia=+10%
        mock_pandas_ta.ema.return_value = pd.Series([100.0])
        bs = _barras(30, close_=110)
        f = _filtro("DISTANCE_FROM_EMA", "MAYOR_QUE", 5,
                    **{"LINEA_REFERENCIA_DISTANCE_FROM_VWAP_EMA_MA": "EMA",
                       "PERIODO_LINEA_DISTANCE_FROM_VWAP_EMA_MA": 20})
        assert len(_senales(bs, [f])) == 1

    def test_distance_ema_negativa_cumple(self, mock_pandas_ta):
        # close=90, EMA=100 → distancia=-10%
        mock_pandas_ta.ema.return_value = pd.Series([100.0])
        bs = _barras(30, close_=90)
        f = _filtro("DISTANCE_FROM_EMA", "MENOR_QUE", -5,
                    **{"LINEA_REFERENCIA_DISTANCE_FROM_VWAP_EMA_MA": "EMA"})
        assert len(_senales(bs, [f])) == 1

    def test_distance_vwap_usa_vwap(self, mock_pandas_ta):
        mock_pandas_ta.vwap.return_value = pd.Series([100.0])
        bs = _barras(30, close_=110)
        f = _filtro("DISTANCE_FROM_VWAP", "MAYOR_QUE", 5,
                    **{"LINEA_REFERENCIA_DISTANCE_FROM_VWAP_EMA_MA": "VWAP"})
        assert len(_senales(bs, [f])) == 1
        mock_pandas_ta.vwap.assert_called()

    def test_distance_ma_usa_sma(self, mock_pandas_ta):
        mock_pandas_ta.sma.return_value = pd.Series([100.0])
        bs = _barras(30, close_=110)
        f = _filtro("DISTANCE_FROM_MA", "MAYOR_QUE", 5,
                    **{"LINEA_REFERENCIA_DISTANCE_FROM_VWAP_EMA_MA": "MA"})
        assert len(_senales(bs, [f])) == 1
        mock_pandas_ta.sma.assert_called()

    def test_distance_entre_cumple(self, mock_pandas_ta):
        mock_pandas_ta.ema.return_value = pd.Series([100.0])
        bs = _barras(30, close_=101)
        f = _filtro("DISTANCE_FROM_EMA", "ENTRE", -2, 2)
        assert len(_senales(bs, [f])) == 1


class TestBackToEmaAlert:
    def test_back_to_ema_toca_y_cierra_sobre_ella(self, mock_pandas_ta):
        # low=99, ema=100, close=101 → tocó EMA desde arriba y cerró sobre
        mock_pandas_ta.ema.return_value = pd.Series([100.0])
        bs = _barras(30, low_=99, close_=101)
        assert len(_senales(bs, [_filtro("BACK_TO_EMA_ALERT",
                                         **{"PERIODO_EMA_BACK_TO_EMA": 20})])) == 1

    def test_back_to_ema_no_toca(self, mock_pandas_ta):
        # low=102, ema=100, close=105 → no tocó la EMA
        mock_pandas_ta.ema.return_value = pd.Series([100.0])
        bs = _barras(30, low_=102, close_=105)
        assert len(_senales(bs, [_filtro("BACK_TO_EMA_ALERT")])) == 0

    def test_back_to_ema_cierra_bajo_ema(self, mock_pandas_ta):
        # low=98, ema=100, close=99 → tocó pero cerró bajo
        mock_pandas_ta.ema.return_value = pd.Series([100.0])
        bs = _barras(30, low_=98, close_=99)
        assert len(_senales(bs, [_filtro("BACK_TO_EMA_ALERT")])) == 0


class TestThroughEmaVwapAlert:
    def test_cruce_ema_arriba(self, mock_pandas_ta):
        # prev_close=99, ema=100, curr_close=101 → cruzó hacia arriba
        mock_pandas_ta.ema.return_value = pd.Series([100.0])
        barras = _barras(29, close_=99) + _barras(1, close_=101)
        f = _filtro("THROUGH_EMA_VWAP_ALERT",
                    **{"THROUGH_EMA_VWAP_LINEA_CRUCE": "EMA",
                       "THROUGH_EMA_VWAP_PERIODO_EMA": 20,
                       "THROUGH_EMA_VWAP_DIRECCION_ROMPIMIENTO": "ABOVE"})
        assert len(_senales(barras, [f])) == 1

    def test_cruce_ema_abajo(self, mock_pandas_ta):
        # prev_close=101, ema=100, curr_close=99 → cruzó hacia abajo
        mock_pandas_ta.ema.return_value = pd.Series([100.0])
        barras = _barras(29, close_=101) + _barras(1, close_=99)
        f = _filtro("THROUGH_EMA_VWAP_ALERT",
                    **{"THROUGH_EMA_VWAP_LINEA_CRUCE": "EMA",
                       "THROUGH_EMA_VWAP_DIRECCION_ROMPIMIENTO": "BELOW"})
        assert len(_senales(barras, [f])) == 1

    def test_sin_cruce_no_genera_senal(self, mock_pandas_ta):
        # Ambos cierres sobre la EMA → no hay cruce
        mock_pandas_ta.ema.return_value = pd.Series([100.0])
        barras = _barras(29, close_=101) + _barras(1, close_=102)
        f = _filtro("THROUGH_EMA_VWAP_ALERT",
                    **{"THROUGH_EMA_VWAP_DIRECCION_ROMPIMIENTO": "ABOVE"})
        assert len(_senales(barras, [f])) == 0


class TestEmaVwapSupportResistance:
    def test_soporte_ema_toca_y_rebota(self, mock_pandas_ta):
        # low=99, ema=100, close=102 → precio tocó EMA y rebotó
        mock_pandas_ta.ema.return_value = pd.Series([100.0])
        bs = _barras(30, low_=99, close_=102)
        f = _filtro("EMA_VWAP_SUPPORT_RESISTANCE",
                    **{"LINEA_REFERENCIA_EMA_VWAP_SUPPORT": "EMA",
                       "TIPO_ROL_EMA_VWAP_SUPPORT": "SOPORTE"})
        assert len(_senales(bs, [f])) == 1

    def test_soporte_no_cumple_cierra_bajo(self, mock_pandas_ta):
        # low=98, ema=100, close=99 → tocó pero no rebotó sobre EMA
        mock_pandas_ta.ema.return_value = pd.Series([100.0])
        bs = _barras(30, low_=98, close_=99)
        f = _filtro("EMA_VWAP_SUPPORT_RESISTANCE",
                    **{"TIPO_ROL_EMA_VWAP_SUPPORT": "SOPORTE"})
        assert len(_senales(bs, [f])) == 0

    def test_resistencia_ema_rechaza(self, mock_pandas_ta):
        # high=101, ema=100, close=99 → precio tocó EMA desde abajo y cayó
        mock_pandas_ta.ema.return_value = pd.Series([100.0])
        bs = _barras(30, high_=101, close_=99)
        f = _filtro("EMA_VWAP_SUPPORT_RESISTANCE",
                    **{"TIPO_ROL_EMA_VWAP_SUPPORT": "RESISTENCIA"})
        assert len(_senales(bs, [f])) == 1

    def test_resistencia_no_cumple_cierra_sobre(self, mock_pandas_ta):
        mock_pandas_ta.ema.return_value = pd.Series([100.0])
        bs = _barras(30, high_=105, close_=103)
        f = _filtro("EMA_VWAP_SUPPORT_RESISTANCE",
                    **{"TIPO_ROL_EMA_VWAP_SUPPORT": "RESISTENCIA"})
        assert len(_senales(bs, [f])) == 0


# ═════════════════════════════════════════════════════════════════════════════
# TIEMPO Y PATRONES DE PRECIO
# ═════════════════════════════════════════════════════════════════════════════

class TestBearishBullishEngulfing:
    def _dos_velas(self, prev_open, prev_close, curr_open, curr_close):
        return [
            {"timestamp": "2025-01-06T09:30:00Z",
             "open": prev_open, "high": max(prev_open, prev_close) + 0.1,
             "low": min(prev_open, prev_close) - 0.1, "close": prev_close, "volume": 1e6},
            {"timestamp": "2025-01-06T09:31:00Z",
             "open": curr_open, "high": max(curr_open, curr_close) + 0.1,
             "low": min(curr_open, curr_close) - 0.1, "close": curr_close, "volume": 1e6},
        ]

    def test_bullish_engulfing_correcto(self):
        # Prev: bajista (open=105, close=100), Curr: alcista (open=99, close=106)
        bs = self._dos_velas(105, 100, 99, 106)
        f = _filtro("BEARISH_BULLISH_ENGULFING",
                    **{"TIPO_PATRON_BEARISH_BULLISH_ENGULFING_CANDLE": "BULLISH"})
        assert len(_senales(bs, [f])) == 1

    def test_bullish_engulfing_no_detecta_alcista_previa(self):
        # Prev: alcista (open=100, close=105), Curr: alcista (open=99, close=106)
        bs = self._dos_velas(100, 105, 99, 106)
        f = _filtro("BEARISH_BULLISH_ENGULFING",
                    **{"TIPO_PATRON_BEARISH_BULLISH_ENGULFING_CANDLE": "BULLISH"})
        assert len(_senales(bs, [f])) == 0

    def test_bearish_engulfing_correcto(self):
        # Prev: alcista (open=100, close=105), Curr: bajista (open=106, close=99)
        bs = self._dos_velas(100, 105, 106, 99)
        f = _filtro("BEARISH_BULLISH_ENGULFING",
                    **{"TIPO_PATRON_BEARISH_BULLISH_ENGULFING_CANDLE": "BEARISH"})
        assert len(_senales(bs, [f])) == 1

    def test_una_sola_vela_retorna_true(self):
        bs = _barras(1)
        f = _filtro("BEARISH_BULLISH_ENGULFING",
                    **{"TIPO_PATRON_BEARISH_BULLISH_ENGULFING_CANDLE": "BULLISH"})
        assert len(_senales(bs, [f])) == 1


class TestFirstCandle:
    def test_primera_vela_alcista(self):
        bs = _barras(5, open_=100, close_=105)
        f = _filtro("FIRST_CANDLE", **{"TIPO_VELA_FIRTS_CANDLE": "ALCISTA"})
        assert len(_senales(bs, [f])) == 1

    def test_primera_vela_bajista(self):
        bs = _barras(5, open_=105, close_=100)
        f = _filtro("FIRST_CANDLE", **{"TIPO_VELA_FIRTS_CANDLE": "BAJISTA"})
        assert len(_senales(bs, [f])) == 1

    def test_primera_vela_alcista_pero_pide_bajista(self):
        bs = _barras(5, open_=100, close_=105)
        f = _filtro("FIRST_CANDLE", **{"TIPO_VELA_FIRTS_CANDLE": "BAJISTA"})
        assert len(_senales(bs, [f])) == 0

    def test_primera_vela_es_siempre_la_primera(self):
        # Otras velas bajistas, pero la primera es alcista
        barras = _barras(1, open_=100, close_=110) + _barras(4, open_=110, close_=90)
        f = _filtro("FIRST_CANDLE", **{"TIPO_VELA_FIRTS_CANDLE": "ALCISTA"})
        assert len(_senales(barras, [f])) == 1


class TestConsecutiveCandles:
    def _velas_alcistas(self, n):
        return _barras(n, open_=100, close_=101, delta_close=0.1)

    def _velas_bajistas(self, n):
        return _barras(n, open_=101, close_=100, delta_close=-0.1)

    def test_racha_alcista_detectada(self):
        bs = self._velas_alcistas(5)
        f = _filtro("CONSECUTIVE_CANDLES", "MAYOR_QUE", 3,
                    **{"NUMERO_VELAS_CONSECUTIVAS": 10})
        assert len(_senales(bs, [f])) == 1

    def test_racha_alcista_no_llega_al_umbral(self):
        bs = self._velas_alcistas(2)
        f = _filtro("CONSECUTIVE_CANDLES", "MAYOR_QUE", 3,
                    **{"NUMERO_VELAS_CONSECUTIVAS": 10})
        assert len(_senales(bs, [f])) == 0

    def test_racha_bajista_detectada_con_valor_negativo(self):
        bs = self._velas_bajistas(5)
        f = _filtro("CONSECUTIVE_CANDLES", "MENOR_QUE", -3,
                    **{"NUMERO_VELAS_CONSECUTIVAS": 10})
        assert len(_senales(bs, [f])) == 1

    def test_racha_mixta_rompe_la_cuenta(self):
        barras = self._velas_alcistas(3) + self._velas_bajistas(2)
        f = _filtro("CONSECUTIVE_CANDLES", "MAYOR_QUE", 3,
                    **{"NUMERO_VELAS_CONSECUTIVAS": 10})
        assert len(_senales(barras, [f])) == 0


class TestHighLowOfDay:
    def test_high_of_day_ultima_barra(self):
        # Todas las barras con high=105, pero última con high=110
        barras = _barras(4, high_=105, close_=103) + _barras(1, high_=110, close_=108)
        f = _filtro("HIGH_LOW_OF_DAY", **{"OPCION_EXTREMO_HIGH_LOW_DAY": "HIGH"})
        assert len(_senales(barras, [f])) == 1

    def test_high_of_day_no_es_ultima(self):
        barras = _barras(4, high_=110, close_=108) + _barras(1, high_=105, close_=103)
        f = _filtro("HIGH_LOW_OF_DAY", **{"OPCION_EXTREMO_HIGH_LOW_DAY": "HIGH"})
        assert len(_senales(barras, [f])) == 0

    def test_low_of_day_ultima_barra(self):
        barras = _barras(4, low_=95, close_=97) + _barras(1, low_=90, close_=92)
        f = _filtro("HIGH_LOW_OF_DAY", **{"OPCION_EXTREMO_HIGH_LOW_DAY": "LOW"})
        assert len(_senales(barras, [f])) == 1


class TestNewCandleHighLow:
    def test_nuevo_high_ultima_barra(self):
        barras = _barras(4, high_=105) + _barras(1, high_=110, close_=108)
        f = _filtro("NEW_CANDLE_HIGH_LOW", **{"OPCION_EXTREMO_NEW_CANDLE": "HIGH"})
        assert len(_senales(barras, [f])) == 1

    def test_no_nuevo_high(self):
        barras = _barras(4, high_=110) + _barras(1, high_=105, close_=103)
        f = _filtro("NEW_CANDLE_HIGH_LOW", **{"OPCION_EXTREMO_NEW_CANDLE": "HIGH"})
        assert len(_senales(barras, [f])) == 0

    def test_nuevo_low_ultima_barra(self):
        barras = _barras(4, low_=95) + _barras(1, low_=90, close_=91)
        f = _filtro("NEW_CANDLE_HIGH_LOW", **{"OPCION_EXTREMO_NEW_CANDLE": "LOW"})
        assert len(_senales(barras, [f])) == 1

    def test_datos_insuficientes(self):
        bs = _barras(1, high_=110)
        f = _filtro("NEW_CANDLE_HIGH_LOW", **{"OPCION_EXTREMO_NEW_CANDLE": "HIGH"})
        assert len(_senales(bs, [f])) == 1


class TestPercentagePullbackHighsLows:
    def test_pullback_desde_alto_cumple(self):
        # max_high=120, close=108 → pullback = (120-108)/120*100 = 10%
        barras = _barras(4, high_=120, close_=118) + _barras(1, high_=109, close_=108)
        f = _filtro("PERCENTAGE_PULLBACK_HIGHS_LOWS", "MAYOR_QUE", 8,
                    **{"PUNTO_REFERENCIA_PULLBACK": "ALTO"})
        assert len(_senales(barras, [f])) == 1

    def test_pullback_desde_alto_no_cumple(self):
        barras = _barras(4, high_=105, close_=104) + _barras(1, high_=103, close_=103)
        # pullback muy pequeño
        f = _filtro("PERCENTAGE_PULLBACK_HIGHS_LOWS", "MAYOR_QUE", 10,
                    **{"PUNTO_REFERENCIA_PULLBACK": "ALTO"})
        assert len(_senales(barras, [f])) == 0

    def test_pullback_desde_bajo(self):
        # min_low=90, close=99 → pullback = (99-90)/90*100 = 10%
        barras = _barras(4, low_=90, close_=91) + _barras(1, low_=96, close_=99)
        f = _filtro("PERCENTAGE_PULLBACK_HIGHS_LOWS", "MAYOR_QUE", 8,
                    **{"PUNTO_REFERENCIA_PULLBACK": "BAJO"})
        assert len(_senales(barras, [f])) == 1


class TestBreakOverRecentHighsLows:
    def test_rompe_maximo_reciente(self):
        barras = _barras(4, high_=105, close_=104) + _barras(1, high_=112, close_=108)
        f = _filtro("BREAK_OVER_RECENT_HIGHS_LOWS",
                    **{"OPCION_EXTREMO_BREAK_OVER": "HIGH"})
        assert len(_senales(barras, [f])) == 1

    def test_no_rompe_maximo(self):
        barras = _barras(4, high_=110, close_=109) + _barras(1, high_=107, close_=106)
        f = _filtro("BREAK_OVER_RECENT_HIGHS_LOWS",
                    **{"OPCION_EXTREMO_BREAK_OVER": "HIGH"})
        assert len(_senales(barras, [f])) == 0

    def test_rompe_minimo_reciente(self):
        barras = _barras(4, low_=95, close_=96) + _barras(1, low_=89, close_=90)
        f = _filtro("BREAK_OVER_RECENT_HIGHS_LOWS",
                    **{"OPCION_EXTREMO_BREAK_OVER": "LOW"})
        assert len(_senales(barras, [f])) == 1


class TestOpeningRange:
    def test_breakout_sobre_primera_vela(self):
        barras = [
            {"timestamp": "2025-01-06T09:30:00Z", "open": 100, "high": 105,
             "low": 99, "close": 102, "volume": 1e6},
            {"timestamp": "2025-01-06T09:31:00Z", "open": 103, "high": 108,
             "low": 102, "close": 107, "volume": 1e6},
        ]
        assert len(_senales(barras, [_filtro("OPENING_RANGE_BREAKOUT")])) == 1

    def test_breakout_no_cumple(self):
        barras = [
            {"timestamp": "2025-01-06T09:30:00Z", "open": 100, "high": 105,
             "low": 99, "close": 102, "volume": 1e6},
            {"timestamp": "2025-01-06T09:31:00Z", "open": 101, "high": 104,
             "low": 100, "close": 103, "volume": 1e6},
        ]
        # close[-1]=103 < high[0]=105 → no breakout
        assert len(_senales(barras, [_filtro("OPENING_RANGE_BREAKOUT")])) == 0

    def test_breakdown_bajo_primera_vela(self):
        barras = [
            {"timestamp": "2025-01-06T09:30:00Z", "open": 100, "high": 105,
             "low": 99, "close": 102, "volume": 1e6},
            {"timestamp": "2025-01-06T09:31:00Z", "open": 100, "high": 101,
             "low": 95, "close": 97, "volume": 1e6},
        ]
        assert len(_senales(barras, [_filtro("OPENING_RANGE_BREAKDOWN")])) == 1

    def test_una_sola_vela_retorna_true(self):
        bs = _barras(1)
        assert len(_senales(bs, [_filtro("OPENING_RANGE_BREAKOUT")])) == 1
        assert len(_senales(bs, [_filtro("OPENING_RANGE_BREAKDOWN")])) == 1


class TestMinutosInMarket:
    def test_minutos_correctos_despues_de_apertura(self):
        # 9:30 ET = 13:30 UTC (hora de verano ET = UTC-4)
        # 14:00 UTC = 10:00 ET → 30 minutos después de apertura
        barras = [{
            "timestamp": "2025-06-02T14:00:00Z",  # 10:00 ET
            "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1e6,
        }]
        f = _filtro("MINUTOS_IN_MARKET", "MAYOR_QUE", 25)
        assert len(_senales(barras, [f])) == 1

    def test_minutos_no_cumple_demasiado_poco(self):
        # 13:35 UTC = 9:35 ET → solo 5 min después de apertura
        barras = [{
            "timestamp": "2025-06-02T13:35:00Z",
            "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1e6,
        }]
        f = _filtro("MINUTOS_IN_MARKET", "MAYOR_QUE", 30)
        assert len(_senales(barras, [f])) == 0

    def test_minutos_antes_de_apertura_retorna_true(self):
        # 13:00 UTC = 9:00 ET → antes de apertura
        barras = [{
            "timestamp": "2025-06-02T13:00:00Z",
            "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1e6,
        }]
        f = _filtro("MINUTOS_IN_MARKET", "MAYOR_QUE", 1)
        assert len(_senales(barras, [f])) == 1


class TestPivots:
    def test_pivots_siempre_pasa(self):
        bs = _barras(5)
        assert len(_senales(bs, [_filtro("PIVOTS")])) == 1


# ═════════════════════════════════════════════════════════════════════════════
# FUNDAMENTALES
# ═════════════════════════════════════════════════════════════════════════════

class TestFundamentales:
    @pytest.mark.parametrize("filtro_name", [
        "FLOAT", "SHARES_OUTSTANDING", "MARKET_CAP",
        "SHORT_INTEREST", "SHORT_RATIO", "DAYS_UNTIL_EARNINGS",
    ])
    def test_sin_datos_en_cache_es_permisivo(self, filtro_name):
        """Sin datos en fundamentales → permisivo (True), no bloquea la señal."""
        bs = _barras(5)
        assert len(_senales(bs, [_filtro(filtro_name, "MAYOR_QUE", 999_999_999)])) == 1

    @pytest.mark.parametrize("filtro_name,clave,valor", [
        ("FLOAT",               "float_shares",        5_000_000),
        ("SHARES_OUTSTANDING",  "shares_outstanding",  10_000_000),
        ("MARKET_CAP",          "market_cap",          500_000_000),
        ("SHORT_INTEREST",      "short_interest",      15.0),
        ("SHORT_RATIO",         "short_ratio",         3.5),
        ("DAYS_UNTIL_EARNINGS", "days_until_earnings", 30),
    ])
    def test_con_datos_cumple_condicion(self, filtro_name, clave, valor):
        bs = _barras(5)
        fund = {clave: valor}
        f = _filtro(filtro_name, "MAYOR_QUE", valor - 1)
        assert len(_senales(bs, [f], fundamentales=fund)) == 1

    @pytest.mark.parametrize("filtro_name,clave,valor", [
        ("FLOAT",               "float_shares",        5_000_000),
        ("SHARES_OUTSTANDING",  "shares_outstanding",  10_000_000),
        ("MARKET_CAP",          "market_cap",          500_000_000),
        ("SHORT_INTEREST",      "short_interest",      15.0),
        ("SHORT_RATIO",         "short_ratio",         3.5),
        ("DAYS_UNTIL_EARNINGS", "days_until_earnings", 30),
    ])
    def test_con_datos_no_cumple_condicion(self, filtro_name, clave, valor):
        bs = _barras(5)
        fund = {clave: valor}
        f = _filtro(filtro_name, "MAYOR_QUE", valor + 1)
        assert len(_senales(bs, [f], fundamentales=fund)) == 0

    def test_float_entre_rango_cumple(self):
        bs = _barras(5)
        fund = {"float_shares": 5_000_000}
        f = _filtro("FLOAT", "ENTRE", 1_000_000, v2=10_000_000)
        assert len(_senales(bs, [f], fundamentales=fund)) == 1

    def test_float_fuera_rango_cumple(self):
        bs = _barras(5)
        fund = {"float_shares": 50_000_000}
        f = _filtro("FLOAT", "FUERA", 1_000_000, v2=10_000_000)
        assert len(_senales(bs, [f], fundamentales=fund)) == 1

    def test_market_cap_menor_que_cumple(self):
        bs = _barras(5)
        fund = {"market_cap": 100_000_000}
        f = _filtro("MARKET_CAP", "MENOR_QUE", 500_000_000)
        assert len(_senales(bs, [f], fundamentales=fund)) == 1

    def test_days_until_earnings_igual_a_cumple(self):
        bs = _barras(5)
        fund = {"days_until_earnings": 5}
        f = _filtro("DAYS_UNTIL_EARNINGS", "IGUAL_A", 5)
        assert len(_senales(bs, [f], fundamentales=fund)) == 1


# ═════════════════════════════════════════════════════════════════════════════
# LÓGICA AND MULTI-FILTRO
# ═════════════════════════════════════════════════════════════════════════════

class TestLogicaAnd:
    def test_precio_y_volumen_ambos_cumplen(self):
        bs = _barras(5, close_=150, volume=2_000_000)
        filtros = [
            _filtro("PRECIO", "MAYOR_QUE", 100),
            _filtro("VOLUME", "MAYOR_QUE", 1_000_000),
        ]
        assert len(_senales(bs, filtros)) == 1

    def test_precio_cumple_volumen_no(self):
        bs = _barras(5, close_=150, volume=500_000)
        filtros = [
            _filtro("PRECIO", "MAYOR_QUE", 100),
            _filtro("VOLUME", "MAYOR_QUE", 1_000_000),
        ]
        assert len(_senales(bs, filtros)) == 0

    def test_cortocircuito_primer_filtro_falla(self):
        bs = _barras(5, close_=5, volume=5_000_000)
        filtros = [
            _filtro("PRECIO", "MAYOR_QUE", 100),   # falla
            _filtro("VOLUME", "MAYOR_QUE", 1_000_000),  # no se evalúa
        ]
        assert len(_senales(bs, filtros)) == 0

    def test_tres_filtros_todos_cumplen(self):
        bs = _barras(5, close_=150, high_=160, low_=140, volume=2_000_000)
        filtros = [
            _filtro("PRECIO", "MAYOR_QUE", 100),
            _filtro("VOLUME", "MAYOR_QUE", 1_000_000),
            _filtro("RANGE_DOLLARS", "MAYOR_QUE", 5),
        ]
        assert len(_senales(bs, filtros)) == 1

    def test_filtros_aplicados_lista_todos_los_cumplidos(self):
        bs = _barras(5, close_=150, volume=2_000_000)
        filtros = [
            _filtro("PRECIO", "MAYOR_QUE", 100),
            _filtro("VOLUME", "MAYOR_QUE", 1_000_000),
        ]
        senales = _senales(bs, filtros)
        aplicados = senales[0]["filtrosAplicados"].split(",")
        assert "PRECIO" in aplicados
        assert "VOLUME" in aplicados


# ═════════════════════════════════════════════════════════════════════════════
# ESTANDARIZACIÓN DE VALORES
# ═════════════════════════════════════════════════════════════════════════════

class TestEstandarizacionValores:
    """Verifica que los valores se interpretan igual que en scanner-management:
    porcentajes como raw (1 % = 1.0), dólares como raw, shares como raw."""

    def test_rsi_valores_raw_0_a_100(self, mock_pandas_ta):
        mock_pandas_ta.rsi.return_value = pd.Series([30.0])
        bs = _barras(30)
        # RSI=30, umbral=30 → MAYOR_QUE 30 es False (no es mayor)
        assert len(_senales(bs, [_filtro("RSI", "MAYOR_QUE", 30)])) == 0
        # RSI=30, MENOR_QUE 31 → True
        assert len(_senales(bs, [_filtro("RSI", "MENOR_QUE", 31)])) == 1

    def test_porcentaje_change_es_raw_no_decimal(self):
        # open=100, close=110 → change=10% (stored as 10.0, not 0.10)
        bs = _barras(5, open_=100, close_=110)
        # Debe cumplir MAYOR_QUE 9 (raw 9 = 9%), NO MAYOR_QUE 0.09
        assert len(_senales(bs, [_filtro("PERCENTAGE_CHANGE", "MAYOR_QUE", 9)])) == 1
        assert len(_senales(bs, [_filtro("PERCENTAGE_CHANGE", "MAYOR_QUE", 11)])) == 0

    def test_atr_valores_en_dolares(self, mock_pandas_ta):
        mock_pandas_ta.atr.return_value = pd.Series([2.5])
        bs = _barras(30, close_=100)
        # ATR=$2.50 stored as 2.5, not 0.025
        assert len(_senales(bs, [_filtro("ATR", "MAYOR_QUE", 2.0)])) == 1
        assert len(_senales(bs, [_filtro("ATR", "MAYOR_QUE", 3.0)])) == 0

    def test_relative_volume_es_porcentaje_raw(self):
        # vol_actual=2M, promedio=1M → relVol=200% (stored as 200, not 2.0)
        barras = _barras(9, volume=1_000_000) + _barras(1, volume=2_000_000)
        assert len(_senales(barras, [_filtro("RELATIVE_VOLUME", "MAYOR_QUE", 150)])) == 1
        assert len(_senales(barras, [_filtro("RELATIVE_VOLUME", "MAYOR_QUE", 250)])) == 0

    def test_distance_ema_es_porcentaje_raw(self, mock_pandas_ta):
        # close=110, EMA=100 → distancia=+10% (stored as 10.0, not 0.10)
        mock_pandas_ta.ema.return_value = pd.Series([100.0])
        bs = _barras(30, close_=110)
        assert len(_senales(bs, [_filtro("DISTANCE_FROM_EMA", "MAYOR_QUE", 9)])) == 1
        assert len(_senales(bs, [_filtro("DISTANCE_FROM_EMA", "MAYOR_QUE", 11)])) == 0

    def test_atrp_es_porcentaje_raw(self, mock_pandas_ta):
        # ATR=2, close=100 → ATRP=2% (stored as 2.0, not 0.02)
        mock_pandas_ta.atr.return_value = pd.Series([2.0])
        bs = _barras(30, close_=100)
        assert len(_senales(bs, [_filtro("ATRP", "MAYOR_QUE", 1.5)])) == 1
        assert len(_senales(bs, [_filtro("ATRP", "MAYOR_QUE", 2.5)])) == 0
