"""Tests for MarketdataRestAdapter."""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch, call

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

    async def test_manda_todos_los_simbolos_en_un_request(self, adapter):
        """Todos los simbolos se mandan en un solo POST — marketdata divide internamente."""
        inst, mock_client = adapter
        mock_client.post = AsyncMock(return_value=_mock_response({"candlesPorSimbolo": {}}))

        simbolos = ["A", "B", "C", "D", "E"]
        result = await inst.obtener_barras_batch(simbolos, "1d")

        assert mock_client.post.call_count == 1
        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["symbols"] == simbolos

    async def test_retorna_todos_los_simbolos_de_la_respuesta(self, adapter):
        inst, mock_client = adapter
        mock_client.post = AsyncMock(return_value=_mock_response(
            {"candlesPorSimbolo": {"A": [{"close": 1.0}], "B": [{"close": 2.0}]}}
        ))

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

    async def test_manda_todos_los_simbolos_en_un_request(self, adapter):
        """Todos los simbolos se mandan en un solo POST."""
        inst, mock_client = adapter
        mock_client.post = AsyncMock(return_value=_mock_response({"candlePorSimbolo": {}}))
        simbolos = ["A", "B", "C"]

        await inst.obtener_ultima_vela_batch(simbolos, "1m")

        assert mock_client.post.call_count == 1
        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["symbols"] == simbolos


@pytest.mark.asyncio
class TestCerrar:
    async def test_cierra_cliente(self, adapter):
        inst, mock_client = adapter
        await inst.cerrar()
        mock_client.aclose.assert_awaited_once()


# ──────────────────────────────────────────────────────────────────────────────
# Tests de reintentos en errores 5xx (nueva lógica _post_con_reintento)
# ──────────────────────────────────────────────────────────────────────────────

def _mock_503():
    """Respuesta mock que simula HTTP 503."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 503
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "503 Service Unavailable", request=MagicMock(), response=resp
    )
    return resp


def _mock_ok(json_data: dict):
    """Respuesta mock HTTP 200 con JSON."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
class TestReintentosEn5xx:
    """Verifica que _post_con_reintento reintenta en 5xx y tiene backoff."""

    async def test_reintenta_en_503_y_exito_en_segundo_intento(self, adapter):
        """Primer intento 503 → reintento → éxito → retorna datos."""
        inst, mock_client = adapter
        mock_client.post = AsyncMock(side_effect=[
            _mock_503(),
            _mock_ok({"candlesPorSimbolo": {"AAPL": [{"close": 150.0}]}}),
        ])

        with patch("app.infrastructure.output.marketdata_rest_adapter.settings") as ms, \
             patch("app.infrastructure.output.marketdata_rest_adapter.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            ms.max_simbolos_por_lote = 100
            ms.reintentos_rest = 3
            result = await inst.obtener_barras_batch(["AAPL"], "M1", 50)

        assert "AAPL" in result
        assert mock_client.post.call_count == 2
        mock_sleep.assert_awaited_once()

    async def test_devuelve_vacio_si_todos_los_reintentos_fallan(self, adapter):
        """4 intentos (1 inicial + 3 reintentos) todos 503 → dict vacío."""
        inst, mock_client = adapter
        mock_client.post = AsyncMock(return_value=_mock_503())

        with patch("app.infrastructure.output.marketdata_rest_adapter.settings") as ms, \
             patch("app.infrastructure.output.marketdata_rest_adapter.asyncio.sleep", new_callable=AsyncMock):
            ms.max_simbolos_por_lote = 100
            ms.reintentos_rest = 3
            result = await inst.obtener_barras_batch(["AAPL"], "M1", 50)

        assert result == {}
        assert mock_client.post.call_count == 4  # 1 inicial + 3 reintentos

    async def test_no_reintenta_en_404(self, adapter):
        """Error 404 (no es 5xx) → NO reintenta → devuelve vacío en un solo intento."""
        inst, mock_client = adapter
        resp_404 = MagicMock(spec=httpx.Response)
        resp_404.status_code = 404
        resp_404.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found", request=MagicMock(), response=resp_404
        )
        mock_client.post = AsyncMock(return_value=resp_404)

        with patch("app.infrastructure.output.marketdata_rest_adapter.settings") as ms, \
             patch("app.infrastructure.output.marketdata_rest_adapter.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            ms.max_simbolos_por_lote = 100
            ms.reintentos_rest = 3
            result = await inst.obtener_barras_batch(["AAPL"], "M1", 50)

        assert result == {}
        assert mock_client.post.call_count == 1   # Sin reintentos
        mock_sleep.assert_not_awaited()

    async def test_ultima_vela_reintenta_en_503(self, adapter):
        """obtener_ultima_vela_batch también reintenta en 503."""
        inst, mock_client = adapter
        mock_client.post = AsyncMock(side_effect=[
            _mock_503(),
            _mock_ok({"candlePorSimbolo": {"AAPL": {"close": 200.0}}}),
        ])

        with patch("app.infrastructure.output.marketdata_rest_adapter.settings") as ms, \
             patch("app.infrastructure.output.marketdata_rest_adapter.asyncio.sleep", new_callable=AsyncMock):
            ms.max_simbolos_por_lote = 100
            ms.reintentos_rest = 3
            result = await inst.obtener_ultima_vela_batch(["AAPL"], "M1")

        assert result == {"AAPL": {"close": 200.0}}
        assert mock_client.post.call_count == 2

    async def test_backoff_aumenta_entre_reintentos(self, adapter):
        """Las esperas entre reintentos deben ser crecientes (5s, 15s, 30s)."""
        inst, mock_client = adapter
        mock_client.post = AsyncMock(side_effect=[
            _mock_503(), _mock_503(), _mock_503(),
            _mock_ok({"candlesPorSimbolo": {}}),
        ])

        sleep_calls = []
        async def capture_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("app.infrastructure.output.marketdata_rest_adapter.settings") as ms, \
             patch("app.infrastructure.output.marketdata_rest_adapter.asyncio.sleep", side_effect=capture_sleep):
            ms.max_simbolos_por_lote = 100
            ms.reintentos_rest = 3
            await inst.obtener_barras_batch(["AAPL"], "M1", 50)

        assert sleep_calls == [5, 15, 30]  # Backoff: 5s → 15s → 30s
