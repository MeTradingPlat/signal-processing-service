import asyncio
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Esperas en segundos entre reintentos: 5s, 15s, 30s
_BACKOFF_SEG = [5, 15, 30]


class MarketdataRestAdapter:
    """Cliente REST para marketdata-service."""

    def __init__(self, base_url: str):
        self._base_url = base_url
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=180.0,  # marketdata procesa 12k símbolos en oleadas de 10 canales → puede tardar ~150s
            headers={"X-Gateway-Passed": "true"},
        )

    async def _post_con_reintento(self, url: str, json_body: dict, descripcion: str) -> dict:
        """POST con reintentos en errores 5xx. Retorna el JSON de respuesta o {} si falla."""
        max_reintentos = settings.reintentos_rest
        for intento in range(max_reintentos + 1):
            try:
                respuesta = await self._client.post(url, json=json_body)
                respuesta.raise_for_status()
                return respuesta.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 and intento < max_reintentos:
                    espera = _BACKOFF_SEG[min(intento, len(_BACKOFF_SEG) - 1)]
                    logger.warning(
                        "%s: HTTP %d, reintentando en %ds (intento %d/%d)",
                        descripcion, e.response.status_code, espera,
                        intento + 1, max_reintentos,
                    )
                    await asyncio.sleep(espera)
                else:
                    logger.error("%s: %s", descripcion, e)
                    return {}
            except httpx.HTTPError as e:
                logger.error("%s: %s", descripcion, e)
                return {}
        return {}

    async def obtener_simbolos_por_mercados(self, mercados: list[str]) -> list[str]:
        """GET /api/marketdata/symbols?markets=us_equities,crypto,...
        Retorna lista de símbolos (strings).
        """
        try:
            respuesta = await self._client.get(
                "/api/marketdata/symbols",
                params={"markets": mercados},
            )
            respuesta.raise_for_status()
            datos = respuesta.json()
            return [item["symbol"] for item in datos if "symbol" in item]
        except httpx.HTTPError as e:
            logger.error("Error obteniendo simbolos para mercados %s: %s", mercados, e)
            return []

    async def obtener_barras_batch(
        self, simbolos: list[str], timeframe: str, bars: int = 200
    ) -> dict[str, list[dict]]:
        """POST /api/marketdata/historical/batch
        Manda todos los simbolos en un solo request.
        marketdata-service divide internamente en chunks de 200 (≤60KB por canal DxLink)
        y abre un canal paralelo por chunk — soporta 12 000+ simbolos.
        Retorna: {symbol: [velas...]}
        """
        datos = await self._post_con_reintento(
            "/api/marketdata/historical/batch",
            {"symbols": simbolos, "timeframe": timeframe, "bars": bars},
            f"barras batch ({len(simbolos)} simbolos)",
        )
        return datos.get("candlesPorSimbolo", {})

    async def obtener_ultima_vela_batch(
        self, simbolos: list[str], timeframe: str
    ) -> dict[str, dict]:
        """POST /api/marketdata/historical/batch/last
        Manda todos los simbolos en un solo request.
        Retorna: {symbol: vela}
        """
        datos = await self._post_con_reintento(
            "/api/marketdata/historical/batch/last",
            {"symbols": simbolos, "timeframe": timeframe},
            f"ultima vela batch ({len(simbolos)} simbolos)",
        )
        return datos.get("candlePorSimbolo", {})

    async def cerrar(self):
        await self._client.aclose()
