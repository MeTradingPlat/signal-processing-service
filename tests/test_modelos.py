"""Tests for domain models: Vela, ContextoSimbolo, Senal."""
import pytest
import pandas as pd
from datetime import datetime, timezone

from app.domain.models.vela import Vela
from app.domain.models.contexto_simbolo import ContextoSimbolo
from app.domain.models.senal import Senal


# ──────────────────────────────────────────────────────────────────────────────
# Vela
# ──────────────────────────────────────────────────────────────────────────────

class TestVelaDesdeDict:
    def test_campos_completos(self):
        data = {
            "symbol": "AAPL",
            "timestamp": "2025-01-01T10:00:00Z",
            "open": "150.0",
            "high": "155.5",
            "low": "149.0",
            "close": "153.0",
            "volume": "1000000",
        }
        v = Vela.desde_dict(data)
        assert v.symbol == "AAPL"
        assert v.timestamp == "2025-01-01T10:00:00Z"
        assert v.open == 150.0
        assert v.high == 155.5
        assert v.low == 149.0
        assert v.close == 153.0
        assert v.volume == 1_000_000.0

    def test_symbol_desde_parametro_si_no_en_dict(self):
        data = {"timestamp": "t", "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 100}
        v = Vela.desde_dict(data, symbol="TSLA")
        assert v.symbol == "TSLA"

    def test_symbol_en_dict_tiene_prioridad(self):
        data = {"symbol": "MSFT", "timestamp": "t", "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 100}
        v = Vela.desde_dict(data, symbol="IGNORED")
        assert v.symbol == "MSFT"

    def test_valores_ausentes_usan_cero(self):
        v = Vela.desde_dict({})
        assert v.open == 0.0
        assert v.high == 0.0
        assert v.low == 0.0
        assert v.close == 0.0
        assert v.volume == 0.0
        assert v.timestamp == ""
        assert v.symbol == ""

    def test_convierte_strings_a_float(self):
        data = {"open": "10", "high": "20", "low": "5", "close": "15", "volume": "500"}
        v = Vela.desde_dict(data)
        assert isinstance(v.open, float)
        assert isinstance(v.close, float)

    def test_dataclass_equality(self):
        data = {"symbol": "X", "timestamp": "t", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 100.0}
        v1 = Vela.desde_dict(data)
        v2 = Vela.desde_dict(data)
        assert v1 == v2


# ──────────────────────────────────────────────────────────────────────────────
# ContextoSimbolo
# ──────────────────────────────────────────────────────────────────────────────

class TestContextoSimbolo:
    def _make_df(self, n_barras=3):
        return pd.DataFrame({
            "timestamp": [f"2025-01-01T{i:02d}:00:00Z" for i in range(n_barras)],
            "open":   [float(100 + i) for i in range(n_barras)],
            "high":   [float(105 + i) for i in range(n_barras)],
            "low":    [float(99 + i)  for i in range(n_barras)],
            "close":  [float(102 + i) for i in range(n_barras)],
            "volume": [float(1000 * (i + 1)) for i in range(n_barras)],
        })

    def _make_ctx(self, symbol="AAPL", n_barras=3, tf="M5"):
        df = self._make_df(n_barras)
        return ContextoSimbolo(
            symbol=symbol,
            barras_por_tf={tf: df},
            ultima_vela_por_tf={tf: "2025-01-01T02:00:00Z"},
        )

    def test_barras_por_tf_inicial_vacio(self):
        ctx = ContextoSimbolo(symbol="TEST")
        assert ctx.barras_por_tf == {}
        assert ctx.ultima_vela_por_tf == {}

    def test_tiene_barras_con_datos(self):
        ctx = self._make_ctx(n_barras=3)
        assert ctx.tiene_barras() is True

    def test_tiene_barras_sin_datos(self):
        ctx = ContextoSimbolo(symbol="TEST")
        assert ctx.tiene_barras() is False

    def test_a_dict_serializable_contiene_campos(self):
        ctx = self._make_ctx()
        d = ctx.a_dict_serializable()
        assert d["symbol"] == "AAPL"
        assert "barras_por_tf" in d
        assert "M5" in d["barras_por_tf"]

    def test_a_dict_serializable_barras_como_dict_de_listas(self):
        ctx = self._make_ctx(n_barras=3)
        d = ctx.a_dict_serializable()
        barras_m5 = d["barras_por_tf"]["M5"]
        assert "close" in barras_m5
        assert len(barras_m5["close"]) == 3

    def test_a_dict_serializable_multiples_tf(self):
        df5 = self._make_df(3)
        df15 = self._make_df(5)
        ctx = ContextoSimbolo(symbol="AAPL", barras_por_tf={"M5": df5, "M15": df15})
        d = ctx.a_dict_serializable()
        assert set(d["barras_por_tf"].keys()) == {"M5", "M15"}
        assert len(d["barras_por_tf"]["M15"]["close"]) == 5

    def test_a_dict_serializable_sin_barras(self):
        ctx = ContextoSimbolo(symbol="X")
        d = ctx.a_dict_serializable()
        assert d["barras_por_tf"] == {}

    def test_a_dict_serializable_valores_numericos(self):
        ctx = self._make_ctx(n_barras=2)
        d = ctx.a_dict_serializable()
        closes = d["barras_por_tf"]["M5"]["close"]
        assert pytest.approx(closes) == [102.0, 103.0]


# ──────────────────────────────────────────────────────────────────────────────
# Senal
# ──────────────────────────────────────────────────────────────────────────────

class TestSenal:
    def _make_senal(self, timestamp=""):
        return Senal(
            id_escaner=1,
            nombre_escaner="TestScanner",
            symbol="AAPL",
            tipo_senal="COMPRA",
            filtros_aplicados="RSI,ATR",
            precio_deteccion=150.5,
            volumen_deteccion=50000.0,
            timestamp=timestamp,
        )

    def test_timestamp_autogenerado_si_vacio(self):
        senal = self._make_senal(timestamp="")
        assert senal.timestamp != ""
        # Should be a valid ISO format timestamp
        dt = datetime.fromisoformat(senal.timestamp.replace("Z", "+00:00"))
        assert dt.tzinfo is not None

    def test_timestamp_respeta_si_provisto(self):
        senal = self._make_senal(timestamp="2025-06-01T12:00:00+00:00")
        assert senal.timestamp == "2025-06-01T12:00:00+00:00"

    def test_a_dict_contiene_todos_los_campos(self):
        senal = self._make_senal()
        d = senal.a_dict()
        assert d["idEscaner"] == 1
        assert d["nombreEscaner"] == "TestScanner"
        assert d["symbol"] == "AAPL"
        assert d["tipoSenal"] == "COMPRA"
        assert d["filtrosAplicados"] == "RSI,ATR"
        assert d["precioDeteccion"] == 150.5
        assert d["volumenDeteccion"] == 50000.0
        assert d["servicioOrigen"] == "signal-processing-service"
        assert "timestamp" in d

    def test_a_dict_servicio_origen_fijo(self):
        senal = self._make_senal()
        assert senal.a_dict()["servicioOrigen"] == "signal-processing-service"

    def test_multiples_senales_timestamps_distintos(self):
        s1 = Senal(1, "sc", "SYM", "COMPRA", "RSI", 100.0, 1000.0)
        s2 = Senal(2, "sc", "SYM", "VENTA", "ATR", 101.0, 2000.0)
        # Both should have timestamps (may be equal if fast enough, but both non-empty)
        assert s1.timestamp != ""
        assert s2.timestamp != ""
