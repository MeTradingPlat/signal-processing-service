"""Tests para fundamentals_adapter (marketdata-service via httpx)."""
from unittest.mock import AsyncMock, patch, MagicMock
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

    async def test_integra_datos_de_marketdata_service(self):
        """Verifica que el adaptador consume correctamente la respuesta del marketdata-service."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "AAPL": {
                "marketCap": 2e12,
                "floatShares": 15_000_000_000,
                "sharesOutstanding": 15_500_000_000,
                "shortInterest": 0.7,
                "shortRatio": 1.5,
                "daysUntilEarnings": 30,
                "preMarketVolume": 500_000,
                "postMarketVolume": 200_000,
            },
            "OTC": {
                "marketCap": 1e6,
                "floatShares": None,
                "sharesOutstanding": None,
                "shortInterest": None,
                "shortRatio": None,
                "daysUntilEarnings": None,
                "preMarketVolume": None,
                "postMarketVolume": None,
            },
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch("app.adapters.fundamentals_adapter._escribir_reporte_fundamentales"):
            res = await obtener_fundamentales_batch(["AAPL", "OTC"], "NYSE")

        assert "AAPL" in res
        assert "OTC" in res
        assert res["AAPL"]["market_cap"] == 2e12
        assert res["AAPL"]["pre_market_volume"] == 500_000
        assert res["AAPL"]["post_market_volume"] == 200_000
        assert res["AAPL"]["days_until_earnings"] == 30
        assert res["OTC"]["market_cap"] == 1e6

@pytest.mark.asyncio
class TestObtenerVolumenExtendido:
    async def test_skip_forex(self):
        res = await obtener_volumen_extendido_batch(["EUR"], "FOREX")
        assert res == {}

    async def test_retorna_vacio_siempre(self):
        """El volumen extendido ahora viene incluido en obtener_fundamentales_batch."""
        res = await obtener_volumen_extendido_batch(["AAPL", "MSFT"], "NYSE")
        assert res == {}
