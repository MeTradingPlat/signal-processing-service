"""Tests for MarketdataRestAdapter."""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.output.marketdata_rest_adapter import MarketdataRestAdapter


def _mock_response(json_data, status_code=200):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


def _mock_http_error():
    resp = MagicMock(spec=httpx.Response)
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=resp
    )
    return resp


@pytest.fixture
def adapter():
    with patch("app.infrastructure.output.marketdata_rest_adapter.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        inst = MarketdataRestAdapter(base_url="http://marketdata-service:8082")
        inst._client = mock_client
        yield inst, mock_client


@pytest.mark.asyncio
class TestObtenerSimbolosPorMercados:
    async def test_retorna_lista_de_simbolos(self, adapter):
        inst, mock_client = adapter
        data = [{"symbol": "AAPL"}, {"symbol": "MSFT"}, {"symbol": "TSLA"}]
        mock_client.get = AsyncMock(return_value=_mock_response(data))

        result = await inst.obtener_simbolos_por_mercados(["NYSE", "NASDAQ"])
        assert result == ["AAPL", "MSFT", "TSLA"]

    async def test_pasa_mercados_como_params(self, adapter):
        inst, mock_client = adapter
        mock_client.get = AsyncMock(return_value=_mock_response([]))
        await inst.obtener_simbolos_por_mercados(["NYSE"])
        mock_client.get.assert_awaited_once_with(
            "/api/marketdata/symbols", params={"markets": ["NYSE"]}
        )

    async def test_retorna_lista_vacia_en_error_http(self, adapter):
        inst, mock_client = adapter
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        result = await inst.obtener_simbolos_por_mercados(["NYSE"])
        assert result == []

    async def test_ignora_items_sin_campo_symbol(self, adapter):
        inst, mock_client = adapter
        data = [{"symbol": "AAPL"}, {"nombre": "sin_symbol"}, {"symbol": "GOOG"}]
        mock_client.get = AsyncMock(return_value=_mock_response(data))
        result = await inst.obtener_simbolos_por_mercados(["NYSE"])
        assert result == ["AAPL", "GOOG"]

    async def test_retorna_lista_vacia_si_sin_items(self, adapter):
        inst, mock_client = adapter
        mock_client.get = AsyncMock(return_value=_mock_response([]))
        result = await inst.obtener_simbolos_por_mercados(["NYSE"])
        assert result == []


@pytest.mark.asyncio
class TestObtenerBarrasBatch:
    async def test_retorna_dict_candles_por_simbolo(self, adapter):
        inst, mock_client = adapter
        candles = {
            "AAPL": [{"close": 150.0}] * 5,
            "MSFT": [{"close": 300.0}] * 5,
        }
        mock_client.post = AsyncMock(return_value=_mock_response({"candlesPorSimbolo": candles}))

        result = await inst.obtener_barras_batch(["AAPL", "MSFT"], "1d", 200)
        assert "AAPL" in result
        assert "MSFT" in result
        assert len(result["AAPL"]) == 5

    async def test_envia_payload_correcto(self, adapter):
        inst, mock_client = adapter
        mock_client.post = AsyncMock(return_value=_mock_response({"candlesPorSimbolo": {}}))
        await inst.obtener_barras_batch(["AAPL"], "1h", 100)
        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["symbols"] == ["AAPL"]
        assert payload["timeframe"] == "1h"
        assert payload["bars"] == 100

    async def test_retorna_dict_vacio_en_error_http(self, adapter):
        inst, mock_client = adapter
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        result = await inst.obtener_barras_batch(["AAPL"], "1d")
        assert result == {}

    async def test_divide_en_lotes(self, adapter):
        """Con max_simbolos_por_lote=2 y 5 símbolos deben hacerse 3 llamadas."""
        inst, mock_client = adapter
        mock_client.post = AsyncMock(return_value=_mock_response({"candlesPorSimbolo": {}}))

        simbolos = ["A", "B", "C", "D", "E"]
        with patch("app.infrastructure.output.marketdata_rest_adapter.settings") as mock_settings:
            mock_settings.max_simbolos_por_lote = 2
            result = await inst.obtener_barras_batch(simbolos, "1d")

        assert mock_client.post.call_count == 3

    async def test_combina_resultados_de_multiples_lotes(self, adapter):
        inst, mock_client = adapter
        responses = [
            _mock_response({"candlesPorSimbolo": {"A": [{"close": 1.0}]}}),
            _mock_response({"candlesPorSimbolo": {"B": [{"close": 2.0}]}}),
        ]
        mock_client.post = AsyncMock(side_effect=responses)

        with patch("app.infrastructure.output.marketdata_rest_adapter.settings") as mock_settings:
            mock_settings.max_simbolos_por_lote = 1
            result = await inst.obtener_barras_batch(["A", "B"], "1d")

        assert "A" in result
        assert "B" in result


@pytest.mark.asyncio
class TestObtenerUltimaVelaBatch:
    async def test_retorna_dict_candle_por_simbolo(self, adapter):
        inst, mock_client = adapter
        data = {"candlePorSimbolo": {"AAPL": {"close": 155.0}, "TSLA": {"close": 210.0}}}
        mock_client.post = AsyncMock(return_value=_mock_response(data))

        result = await inst.obtener_ultima_vela_batch(["AAPL", "TSLA"], "1m")
        assert result["AAPL"]["close"] == 155.0
        assert result["TSLA"]["close"] == 210.0

    async def test_envia_payload_correcto(self, adapter):
        inst, mock_client = adapter
        mock_client.post = AsyncMock(return_value=_mock_response({"candlePorSimbolo": {}}))
        await inst.obtener_ultima_vela_batch(["AAPL"], "5m")
        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["symbols"] == ["AAPL"]
        assert payload["timeframe"] == "5m"

    async def test_retorna_dict_vacio_en_error_http(self, adapter):
        inst, mock_client = adapter
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        result = await inst.obtener_ultima_vela_batch(["AAPL"], "1m")
        assert result == {}

    async def test_divide_en_lotes(self, adapter):
        inst, mock_client = adapter
        mock_client.post = AsyncMock(return_value=_mock_response({"candlePorSimbolo": {}}))
        simbolos = ["A", "B", "C"]

        with patch("app.infrastructure.output.marketdata_rest_adapter.settings") as mock_settings:
            mock_settings.max_simbolos_por_lote = 1
            await inst.obtener_ultima_vela_batch(simbolos, "1m")

        assert mock_client.post.call_count == 3


@pytest.mark.asyncio
class TestCerrar:
    async def test_cierra_cliente(self, adapter):
        inst, mock_client = adapter
        await inst.cerrar()
        mock_client.aclose.assert_awaited_once()
