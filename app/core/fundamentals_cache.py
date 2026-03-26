"""Caché thread-safe de datos fundamentales para todos los símbolos activos.

Diseño:
  - Singleton compartido entre todos los EjecutorEscaner del proceso.
  - Refresh una vez por día al inicio de la sesión de mercado.
  - Los workers del ProcessPoolExecutor NO acceden al caché directamente —
    el EjecutorEscaner inyecta los datos en el ctx_data antes de enviarlos
    al pool (los datos viajan como dicts serializados).
  - Múltiples escáneres con símbolos superpuestos comparten los mismos datos.
  - Thread-safe: usa threading.Lock para leer/escribir el dict interno.

Escalabilidad:
  - 500 símbolos → ~2-3 min de carga al arranque (paralelo, 10 threads)
  - 2000 símbolos → ~8-10 min (una sola vez por día)
  - Durante el día: acceso O(1) desde memoria, 0 llamadas HTTP

Unidades (ver fundamentals_adapter.py para detalle completo):
  float_shares / shares_outstanding : acciones raw
  market_cap                        : dólares raw
  short_interest                    : % (10.5 = 10.5%)
  short_ratio                       : días raw
  days_until_earnings               : días enteros
  pre_market_volume / post_market_volume : acciones raw
"""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import date

logger = logging.getLogger(__name__)

_MERCADOS_SIN_FUNDAMENTALES = {"CRYPTO", "FOREX"}


class FundamentalsCache:
    """Caché en memoria de fundamentales por símbolo, thread-safe."""

    def __init__(self) -> None:
        self._cache: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._ultima_fecha_refresh: date | None = None
        self._refresh_event = asyncio.Event()
        self._refresh_event.set()   # empieza "libre" (nadie refresheando)
        self._refresh_en_curso = False

    # ── Consulta ──────────────────────────────────────────────────────────────

    def obtener(self, symbol: str) -> dict:
        """Retorna dict de fundamentales del símbolo (copia). Vacío si no hay datos."""
        with self._lock:
            return dict(self._cache.get(symbol, {}))

    def necesita_refresh(self) -> bool:
        """True si no se ha refrescado hoy o nunca."""
        return self._ultima_fecha_refresh != date.today()

    def total_simbolos(self) -> int:
        with self._lock:
            return len(self._cache)

    # ── Refresh ───────────────────────────────────────────────────────────────

    async def refrescar(
        self,
        simbolos: list[str],
        mercado: str,
        forzar: bool = False,
    ) -> None:
        """Refresca fundamentales para la lista de símbolos.

        Solo ejecuta el fetch si hoy no se ha refrescado (o forzar=True).
        Corre los fetches en un thread pool para no bloquear el event loop.

        Args:
            simbolos: Lista de símbolos a refrescar.
            mercado:  Mercado principal (CRYPTO/FOREX se saltan).
            forzar:   Ignorar la condición de "ya refrescado hoy".
        """
        if mercado in _MERCADOS_SIN_FUNDAMENTALES:
            return

        if not simbolos:
            return

        if not forzar and not self.necesita_refresh():
            logger.debug("FundamentalsCache: datos del día disponibles, skip refresh")
            return

        # Si otro scanner ya está haciendo el refresh, esperar a que termine
        # en lugar de lanzar un segundo fetch paralelo (conflictos de crumb yfinance)
        if self._refresh_en_curso:
            logger.info("FundamentalsCache: refresh ya en curso, esperando que termine...")
            await self._refresh_event.wait()
            logger.info("FundamentalsCache: refresh anterior completado, usando datos del caché")
            return

        self._refresh_en_curso = True
        self._refresh_event.clear()

        from app.adapters.fundamentals_adapter import (
            obtener_fundamentales_batch,
            obtener_volumen_extendido_batch,
        )

        logger.info(
            "FundamentalsCache: iniciando refresh de %d símbolos (mercado=%s)",
            len(simbolos), mercado,
        )

        loop = asyncio.get_event_loop()

        try:
            # Fetch asíncrono nativo (sin delegar a ThreadPoolExecutor)
            fundamentales, volumenes = await asyncio.gather(
                obtener_fundamentales_batch(simbolos, mercado),
                obtener_volumen_extendido_batch(simbolos, mercado),
            )

            # Merge y actualizar caché
            with self._lock:
                for sym in simbolos:
                    merged = {
                        **fundamentales.get(sym, {}),
                        **volumenes.get(sym, {}),
                    }
                    if merged:
                        self._cache[sym] = merged
                self._ultima_fecha_refresh = date.today()

            con_datos = sum(1 for v in self._cache.values() if v)
            sin_datos_cache = [s for s in simbolos if not self._cache.get(s)]
            logger.info(
                "FundamentalsCache: refresh completado — %d/%d símbolos con datos en caché",
                con_datos, len(simbolos),
            )
            if sin_datos_cache:
                logger.warning(
                    "FundamentalsCache: %d símbolos quedaron SIN datos en caché: %s",
                    len(sin_datos_cache),
                    ", ".join(sorted(sin_datos_cache)[:50]) + (" ..." if len(sin_datos_cache) > 50 else ""),
                )
        finally:
            self._refresh_en_curso = False
            self._refresh_event.set()   # liberar scanners que estaban esperando

    async def actualizar_volumen_extendido(self, simbolos: list[str], mercado: str) -> None:
        """Actualización asíncrona de volúmenes pre/post."""
        if mercado in _MERCADOS_SIN_FUNDAMENTALES or not simbolos:
            return
        from app.adapters.fundamentals_adapter import obtener_volumen_extendido_batch
        volumenes = await obtener_volumen_extendido_batch(simbolos, mercado)
        with self._lock:
            for sym, vol_data in volumenes.items():
                if sym in self._cache:
                    self._cache[sym].update(vol_data)
                else:
                    self._cache[sym] = vol_data

    def limpiar(self) -> None:
        """Limpia el caché completamente (útil en tests)."""
        with self._lock:
            self._cache.clear()
            self._ultima_fecha_refresh = None
