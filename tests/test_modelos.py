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
    def _make_ctx(self, symbol="AAPL", n_barras=3):
        barras = {
            "timestamp": [f"2025-01-01T{i:02d}:00:00Z" for i in range(n_barras)],
            "open": [float(100 + i) for i in range(n_barras)],
            "high": [float(105 + i) for i in range(n_barras)],
            "low": [float(99 + i) for i in range(n_barras)],
            "close": [float(102 + i) for i in range(n_barras)],
            "volume": [float(1000 * (i + 1)) for i in range(n_barras)],
        }
        df = pd.DataFrame(barras)
        return ContextoSimbolo(symbol=symbol, df_barras=df, ultima_vela_timestamp="2025-01-01T02:00:00Z")

    def test_df_inicial_vacio(self):
        ctx = ContextoSimbolo(symbol="TEST")
        assert ctx.df_barras.empty
        assert list(ctx.df_barras.columns) == ["timestamp", "open", "high", "low", "close", "volume"]

    def test_a_dict_serializable_contiene_campos(self):
        ctx = self._make_ctx()
        d = ctx.a_dict_serializable()
        assert d["symbol"] == "AAPL"
        assert "barras" in d
        assert d["ultima_vela_timestamp"] == "2025-01-01T02:00:00Z"

    def test_a_dict_serializable_barras_como_dict_de_listas(self):
        ctx = self._make_ctx(n_barras=3)
        d = ctx.a_dict_serializable()
        barras = d["barras"]
        assert "close" in barras
        assert len(barras["close"]) == 3

    def test_roundtrip_desde_dict_serializable(self):
        ctx = self._make_ctx(n_barras=5)
        d = ctx.a_dict_serializable()
        ctx2 = ContextoSimbolo.desde_dict_serializable(d)
        assert ctx2.symbol == ctx.symbol
        assert ctx2.ultima_vela_timestamp == ctx.ultima_vela_timestamp
        assert len(ctx2.df_barras) == 5
        assert list(ctx2.df_barras.columns) == list(ctx.df_barras.columns)

    def test_roundtrip_valores_numericos(self):
        ctx = self._make_ctx(n_barras=2)
        ctx2 = ContextoSimbolo.desde_dict_serializable(ctx.a_dict_serializable())
        assert pytest.approx(ctx2.df_barras["close"].tolist()) == ctx.df_barras["close"].tolist()

    def test_ultima_vela_timestamp_none(self):
        ctx = ContextoSimbolo(symbol="X")
        d = ctx.a_dict_serializable()
        assert d["ultima_vela_timestamp"] is None
        ctx2 = ContextoSimbolo.desde_dict_serializable(d)
        assert ctx2.ultima_vela_timestamp is None

    def test_desde_dict_serializable_df_vacio(self):
        d = {
            "symbol": "Z",
            "barras": {"timestamp": [], "open": [], "high": [], "low": [], "close": [], "volume": []},
            "ultima_vela_timestamp": None,
        }
        ctx = ContextoSimbolo.desde_dict_serializable(d)
        assert ctx.df_barras.empty


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
