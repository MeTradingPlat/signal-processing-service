"""Configuración compartida de pytest para todos los tests.

Incluye el fixture `mock_pandas_ta` que reemplaza pandas_ta con un mock
controlable, evitando la dependencia de numba (incompatible con Python 3.14).

Los tests de worker_filtros usan este fixture explícitamente para controlar
el valor exacto que retorna cada indicador técnico.
"""

import importlib.machinery
import sys
import types

import pandas as pd
import pytest
from unittest.mock import MagicMock


# ──────────────────────────────────────────────────────────────────────────────
# Mocks de librerías externas (inyectados a nivel de módulo)
# Permite que @patch funcione incluso sin las librerías instaladas localmente.
# En Docker (con requirements.txt completo) sys.modules ya tiene los reales.
# ──────────────────────────────────────────────────────────────────────────────

if "yfinance" not in sys.modules:
    # Usar types.ModuleType en vez de MagicMock: pandas_ta.maps llama a
    # importlib.util.find_spec("yfinance") que requiere __spec__ != None.
    # MagicMock pone __spec__ = None internamente → ValueError en find_spec.
    _mock_yf = types.ModuleType("yfinance")
    _mock_yf.__spec__ = importlib.machinery.ModuleSpec("yfinance", None)
    _mock_yf.Ticker = MagicMock()
    _mock_yf.download = MagicMock(return_value=pd.DataFrame())
    sys.modules["yfinance"] = _mock_yf


@pytest.fixture
def mock_pandas_ta(monkeypatch):
    """Mock de pandas_ta inyectado en sys.modules.

    Cada test que lo usa puede configurar el valor que retorna cada indicador:
        mock_pandas_ta.rsi.return_value = pd.Series([80.0])
        mock_pandas_ta.atr.return_value = pd.Series([2.5])

    Los valores por defecto son neutros (RSI=50, ATR=1.0, EMA=close, VWAP=100).
    """
    mock_ta = MagicMock()
    mock_ta.rsi.return_value  = pd.Series([50.0])
    mock_ta.atr.return_value  = pd.Series([1.0])
    mock_ta.ema.return_value  = pd.Series([100.0])
    mock_ta.vwap.return_value = pd.Series([100.0])
    monkeypatch.setitem(sys.modules, "pandas_ta", mock_ta)
    return mock_ta
