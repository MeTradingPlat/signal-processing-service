"""Tests for EscanerRestAdapter."""
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

from app.infrastructure.output.escaner_rest_adapter import EscanerRestAdapter


@pytest.fixture
def adapter():
    with patch("app.infrastructure.output.escaner_rest_adapter.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        inst = EscanerRestAdapter(base_url="http://scanner-management-service:8081")
        inst._client = mock_client
        yield inst, mock_client


def _mock_response(json_data, status_code=200):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


def _mock_http_error():
    resp = MagicMock(spec=httpx.Response)
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404", request=MagicMock(), response=resp
    )
    return resp


@pytest.mark.asyncio
class TestObtenerEscaneresIniciados:
    async def test_retorna_lista_de_escaneres(self, adapter):
        inst, mock_client = adapter
        data = [{"id": 1, "nombre": "Scanner A"}, {"id": 2, "nombre": "Scanner B"}]
        mock_client.get = AsyncMock(return_value=_mock_response(data))

        result = await inst.obtener_escaneres_iniciados()
        assert result == data
        mock_client.get.assert_awaited_once_with("/escaner/iniciados")

    async def test_retorna_lista_vacia_en_error_http(self, adapter):
        inst, mock_client = adapter
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        result = await inst.obtener_escaneres_iniciados()
        assert result == []

    async def test_retorna_lista_vacia_si_status_error(self, adapter):
        inst, mock_client = adapter
        resp = _mock_http_error()
        mock_client.get = AsyncMock(return_value=resp)
        result = await inst.obtener_escaneres_iniciados()
        assert result == []


@pytest.mark.asyncio
class TestObtenerEscanerPorId:
    async def test_retorna_dict_del_escaner(self, adapter):
        inst, mock_client = adapter
        data = {"id": 5, "nombre": "Mi Escaner", "estado": "INICIADO"}
        mock_client.get = AsyncMock(return_value=_mock_response(data))

        result = await inst.obtener_escaner_por_id(5)
        assert result == data
        mock_client.get.assert_awaited_once_with("/escaner/5")

    async def test_retorna_none_en_error_http(self, adapter):
        inst, mock_client = adapter
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        result = await inst.obtener_escaner_por_id(99)
        assert result is None

    async def test_retorna_none_si_status_error(self, adapter):
        inst, mock_client = adapter
        resp = _mock_http_error()
        mock_client.get = AsyncMock(return_value=resp)
        result = await inst.obtener_escaner_por_id(1)
        assert result is None

    async def test_url_incluye_id_correcto(self, adapter):
        inst, mock_client = adapter
        mock_client.get = AsyncMock(return_value=_mock_response({"id": 42}))
        await inst.obtener_escaner_por_id(42)
        mock_client.get.assert_awaited_once_with("/escaner/42")


@pytest.mark.asyncio
class TestObtenerFiltrosEscaner:
    async def test_retorna_lista_de_filtros(self, adapter):
        inst, mock_client = adapter
        filtros = [
            {"tipo": "RSI", "parametros": {"periodo": 14, "umbral": 30}},
            {"tipo": "ATR", "parametros": {"periodo": 14, "umbral": 1.5}},
        ]
        mock_client.get = AsyncMock(return_value=_mock_response(filtros))

        result = await inst.obtener_filtros_escaner(3)
        assert result == filtros
        mock_client.get.assert_awaited_once_with("/escaner/filtro/escaner/3")

    async def test_retorna_lista_vacia_en_error_http(self, adapter):
        inst, mock_client = adapter
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        result = await inst.obtener_filtros_escaner(1)
        assert result == []

    async def test_url_incluye_id_correcto(self, adapter):
        inst, mock_client = adapter
        mock_client.get = AsyncMock(return_value=_mock_response([]))
        await inst.obtener_filtros_escaner(10)
        mock_client.get.assert_awaited_once_with("/escaner/filtro/escaner/10")

    async def test_lista_vacia_si_no_hay_filtros(self, adapter):
        inst, mock_client = adapter
        mock_client.get = AsyncMock(return_value=_mock_response([]))
        result = await inst.obtener_filtros_escaner(1)
        assert result == []


@pytest.mark.asyncio
class TestCerrar:
    async def test_cierra_el_cliente(self, adapter):
        inst, mock_client = adapter
        await inst.cerrar()
        mock_client.aclose.assert_awaited_once()
