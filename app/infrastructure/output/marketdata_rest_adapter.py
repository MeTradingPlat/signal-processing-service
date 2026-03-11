import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class MarketdataRestAdapter:
    """Cliente REST para marketdata-service."""

    def __init__(self, base_url: str):
        self._base_url = base_url
        self._client = httpx.AsyncClient(base_url=base_url, timeout=30.0)

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
        Envía lotes de max_simbolos_por_lote símbolos.
        Retorna: {symbol: [velas...]}
        """
        resultado: dict[str, list[dict]] = {}
        lote_size = settings.max_simbolos_por_lote

        for i in range(0, len(simbolos), lote_size):
            lote = simbolos[i : i + lote_size]
            try:
                respuesta = await self._client.post(
                    "/api/marketdata/historical/batch",
                    json={
                        "symbols": lote,
                        "timeframe": timeframe,
                        "bars": bars,
                    },
                )
                respuesta.raise_for_status()
                datos = respuesta.json()
                candles_por_simbolo = datos.get("candlesPorSimbolo", {})
                resultado.update(candles_por_simbolo)
            except httpx.HTTPError as e:
                logger.error(
                    "Error obteniendo barras batch (lote %d-%d): %s",
                    i, i + lote_size, e,
                )

        return resultado

    async def obtener_ultima_vela_batch(
        self, simbolos: list[str], timeframe: str
    ) -> dict[str, dict]:
        """POST /api/marketdata/historical/batch/last
        Retorna: {symbol: vela}
        """
        resultado: dict[str, dict] = {}
        lote_size = settings.max_simbolos_por_lote

        for i in range(0, len(simbolos), lote_size):
            lote = simbolos[i : i + lote_size]
            try:
                respuesta = await self._client.post(
                    "/api/marketdata/historical/batch/last",
                    json={
                        "symbols": lote,
                        "timeframe": timeframe,
                    },
                )
                respuesta.raise_for_status()
                datos = respuesta.json()
                candle_por_simbolo = datos.get("candlePorSimbolo", {})
                resultado.update(candle_por_simbolo)
            except httpx.HTTPError as e:
                logger.error(
                    "Error obteniendo ultima vela batch (lote %d-%d): %s",
                    i, i + lote_size, e,
                )

        return resultado

    async def cerrar(self):
        await self._client.aclose()
