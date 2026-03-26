"""Tests para fundamentals_adapter (Estrategia Bulk y No-Hilos)."""
from unittest.mock import AsyncMock, patch
import pytest

from app.adapters.fundamentals_adapter import (
    obtener_fundamentales_batch,
    obtener_volumen_extendido_batch,
    _parse_finviz_numero,
    _parse_finviz_porcentaje,
    _normalizar_simbolo_yahoo,
)

class TestParseFinvizNumero:
    def test_parsea_billones(self):
        assert _parse_finviz_numero("15.44B") == pytest.approx(15_440_000_000.0)
    def test_parsea_trillones(self):
        assert _parse_finviz_numero("3.42T") == pytest.approx(3_420_000_000_000.0)
    def test_parsea_millones(self):
        assert _parse_finviz_numero("500M") == pytest.approx(500_000_000.0)
    def test_sin_sufijo(self):
        assert _parse_finviz_numero("3.2") == pytest.approx(3.2)
    def test_invalido(self):
        assert _parse_finviz_numero("-") is None

class TestParseFinvizPorcentaje:
    def test_porcentaje(self):
        assert _parse_finviz_porcentaje("2.35%") == pytest.approx(2.35)
    def test_nulo(self):
        assert _parse_finviz_porcentaje("-") is None

class TestNormalizarSimboloYahoo:
    def test_barra_a_guion(self):
        assert _normalizar_simbolo_yahoo("AKO/A") == "AKO-A"
        assert _normalizar_simbolo_yahoo("UHAL/B") == "UHAL-B"

@pytest.mark.asyncio
class TestObtenerFundamentalesBatch:
    async def test_skip_crypto(self):
        res = await obtener_fundamentales_batch(["BTC"], "CRYPTO")
        assert res == {}

    async def test_integra_finviz_y_yahoo(self):
        finviz_dict = {"AAPL": {"market_cap": 2e12}}
        yahoo_dict = {"OTC": {"market_cap": 1e6}}
        
        with patch("app.adapters.fundamentals_adapter._bulk_scrape_finviz_screener", new_callable=AsyncMock, return_value=finviz_dict), \
             patch("app.adapters.fundamentals_adapter._bulk_yahoo_async_fallback", new_callable=AsyncMock, return_value=yahoo_dict), \
             patch("app.adapters.fundamentals_adapter._escribir_reporte_fundamentales"):
            res = await obtener_fundamentales_batch(["AAPL", "OTC"], "NYSE")
            assert "AAPL" in res
            assert "OTC" in res
            assert res["AAPL"]["market_cap"] == 2e12
            assert res["OTC"]["market_cap"] == 1e6

@pytest.mark.asyncio
class TestObtenerVolumenExtendido:
    async def test_skip_forex(self):
        res = await obtener_volumen_extendido_batch(["EUR"], "FOREX")
        assert res == {}
