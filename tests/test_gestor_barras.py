"""Tests unitarios para GestorBarras.

Verifica:
  - crear_dataframe_desde_velas: lista vacía, lista normal, columnas faltantes, tipos numéricos
  - agregar_vela: agrega fila, datos correctos, recorte a max_barras, mantiene las más recientes

Ejecutar:
    pytest tests/test_gestor_barras.py -v
"""

from unittest.mock import patch

import pandas as pd
import pytest

from app.core.gestor_barras import GestorBarras
from app.domain.models.vela import Vela


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vela_dict(timestamp: str, close: float, volumen: float = 100_000.0) -> dict:
    return {
        "timestamp": timestamp,
        "open":   close - 0.1,
        "high":   close + 0.2,
        "low":    close - 0.2,
        "close":  close,
        "volume": volumen,
    }


def _vela_obj(timestamp: str, close: float, volumen: float = 100_000.0) -> Vela:
    return Vela(
        symbol="TEST",
        timestamp=timestamp,
        open=close - 0.1,
        high=close + 0.2,
        low=close - 0.2,
        close=close,
        volume=volumen,
    )


# ---------------------------------------------------------------------------
# Tests: crear_dataframe_desde_velas
# ---------------------------------------------------------------------------

class TestCrearDataframe:
    def test_lista_vacia_retorna_df_con_columnas_correctas(self):
        df = GestorBarras.crear_dataframe_desde_velas([])
        assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
        assert len(df) == 0

    def test_una_vela_genera_una_fila(self):
        velas = [_vela_dict("2025-01-02T09:30:00Z", 100.0)]
        df = GestorBarras.crear_dataframe_desde_velas(velas)
        assert len(df) == 1

    def test_n_velas_genera_n_filas(self):
        velas = [_vela_dict(f"2025-01-{i+1:02d}T09:30:00Z", float(100 + i)) for i in range(20)]
        df = GestorBarras.crear_dataframe_desde_velas(velas)
        assert len(df) == 20

    def test_valores_close_son_correctos(self):
        velas = [
            _vela_dict("2025-01-02T09:30:00Z", 150.25),
            _vela_dict("2025-01-02T09:31:00Z", 151.00),
        ]
        df = GestorBarras.crear_dataframe_desde_velas(velas)
        assert df["close"].iloc[0] == pytest.approx(150.25)
        assert df["close"].iloc[1] == pytest.approx(151.00)

    def test_columnas_faltantes_se_rellenan_con_cero(self):
        # Vela sin 'volume' ni 'high'
        velas = [{"timestamp": "2025-01-02T09:30:00Z", "open": 100.0, "low": 99.0, "close": 100.5}]
        df = GestorBarras.crear_dataframe_desde_velas(velas)
        assert "volume" in df.columns
        assert "high" in df.columns
        assert df["volume"].iloc[0] == pytest.approx(0.0)
        assert df["high"].iloc[0] == pytest.approx(0.0)

    def test_columnas_numericas_son_float(self):
        velas = [_vela_dict("2025-01-02T09:30:00Z", 100.0)]
        df = GestorBarras.crear_dataframe_desde_velas(velas)
        for col in ["open", "high", "low", "close", "volume"]:
            assert pd.api.types.is_numeric_dtype(df[col]), f"Columna {col} no es numérica"

    def test_valores_string_se_convierten_a_numero(self):
        velas = [{"timestamp": "2025-01-02T09:30:00Z",
                  "open": "100.0", "high": "101.0", "low": "99.0",
                  "close": "100.5", "volume": "500000"}]
        df = GestorBarras.crear_dataframe_desde_velas(velas)
        assert df["close"].iloc[0] == pytest.approx(100.5)
        assert df["volume"].iloc[0] == pytest.approx(500_000.0)

    def test_indice_reset_empieza_en_cero(self):
        velas = [_vela_dict(f"2025-01-{i+1:02d}T09:30:00Z", float(100 + i)) for i in range(5)]
        df = GestorBarras.crear_dataframe_desde_velas(velas)
        assert list(df.index) == list(range(5))

    def test_solo_incluye_columnas_requeridas(self):
        velas = [{"timestamp": "T1", "open": 1.0, "high": 2.0, "low": 0.5,
                  "close": 1.5, "volume": 1000.0, "campo_extra": "ignorar"}]
        df = GestorBarras.crear_dataframe_desde_velas(velas)
        assert "campo_extra" not in df.columns
        assert set(df.columns) == {"timestamp", "open", "high", "low", "close", "volume"}


# ---------------------------------------------------------------------------
# Tests: agregar_vela
# ---------------------------------------------------------------------------

class TestAgregarVela:
    def _df_inicial(self, n: int = 5) -> pd.DataFrame:
        velas = [_vela_dict(f"2025-01-{i+1:02d}T09:30:00Z", float(100 + i)) for i in range(n)]
        return GestorBarras.crear_dataframe_desde_velas(velas)

    def test_agrega_una_fila(self):
        df = self._df_inicial(5)
        nueva = _vela_obj("2025-01-06T09:30:00Z", 105.0)
        df2 = GestorBarras.agregar_vela(df, nueva)
        assert len(df2) == 6

    def test_ultima_fila_tiene_los_datos_de_la_vela(self):
        df = self._df_inicial(3)
        nueva = _vela_obj("2025-03-10T14:00:00Z", 250.75, volumen=999_999.0)
        df2 = GestorBarras.agregar_vela(df, nueva)
        ultima = df2.iloc[-1]
        assert ultima["timestamp"] == "2025-03-10T14:00:00Z"
        assert ultima["close"] == pytest.approx(250.75)
        assert ultima["volume"] == pytest.approx(999_999.0)

    def test_no_modifica_df_original(self):
        df = self._df_inicial(3)
        filas_originales = len(df)
        nueva = _vela_obj("2025-03-10T14:00:00Z", 200.0)
        GestorBarras.agregar_vela(df, nueva)
        assert len(df) == filas_originales  # df original intacto

    def test_recorta_cuando_supera_max_barras(self):
        max_barras = 10
        with patch("app.core.gestor_barras.settings") as mock_settings:
            mock_settings.max_barras_por_simbolo = max_barras
            df = self._df_inicial(max_barras)  # exactamente en el límite
            nueva = _vela_obj("2025-03-10T14:00:00Z", 999.0)
            df2 = GestorBarras.agregar_vela(df, nueva)
        assert len(df2) == max_barras

    def test_recorte_mantiene_barras_mas_recientes(self):
        max_barras = 5
        with patch("app.core.gestor_barras.settings") as mock_settings:
            mock_settings.max_barras_por_simbolo = max_barras
            df = self._df_inicial(max_barras)  # barras con close 100,101,102,103,104
            nueva = _vela_obj("2025-03-10T14:00:00Z", 999.0)
            df2 = GestorBarras.agregar_vela(df, nueva)
        # La primera barra (100.0) debe haber sido eliminada
        assert 999.0 in df2["close"].values
        assert 100.0 not in df2["close"].values

    def test_sin_recorte_si_no_supera_max(self):
        max_barras = 500
        with patch("app.core.gestor_barras.settings") as mock_settings:
            mock_settings.max_barras_por_simbolo = max_barras
            df = self._df_inicial(10)
            nueva = _vela_obj("2025-03-10T14:00:00Z", 200.0)
            df2 = GestorBarras.agregar_vela(df, nueva)
        assert len(df2) == 11

    def test_indice_continuo_tras_agregar(self):
        df = self._df_inicial(3)
        nueva = _vela_obj("2025-03-10T14:00:00Z", 200.0)
        df2 = GestorBarras.agregar_vela(df, nueva)
        assert list(df2.index) == list(range(4))
