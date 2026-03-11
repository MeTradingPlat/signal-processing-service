import logging

import httpx

logger = logging.getLogger(__name__)


class EscanerRestAdapter:
    """Cliente REST para scanner-management-service."""

    def __init__(self, base_url: str):
        self._base_url = base_url
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=10.0,
            headers={"X-Gateway-Passed": "true"},
        )

    async def obtener_escaneres_iniciados(self) -> list[dict]:
        """GET /api/escaner/iniciados"""
        try:
            respuesta = await self._client.get("/api/escaner/iniciados")
            respuesta.raise_for_status()
            return respuesta.json()
        except httpx.HTTPError as e:
            logger.error("Error obteniendo escaneres iniciados: %s", e)
            return []

    async def obtener_escaner_por_id(self, id_escaner: int) -> dict | None:
        """GET /api/escaner/{id}"""
        try:
            respuesta = await self._client.get(f"/api/escaner/{id_escaner}")
            respuesta.raise_for_status()
            return respuesta.json()
        except httpx.HTTPError as e:
            logger.error("Error obteniendo escaner %d: %s", id_escaner, e)
            return None

    async def obtener_filtros_escaner(self, id_escaner: int) -> list[dict]:
        """GET /api/escaner/filtro/escaner/{id}"""
        try:
            respuesta = await self._client.get(f"/api/escaner/filtro/escaner/{id_escaner}")
            respuesta.raise_for_status()
            return respuesta.json()
        except httpx.HTTPError as e:
            logger.error("Error obteniendo filtros del escaner %d: %s", id_escaner, e)
            return []

    async def cerrar(self):
        await self._client.aclose()
