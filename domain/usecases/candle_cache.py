"""Cache persistente de barras historicas entre ejecuciones de escaneres."""

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from domain.models.candle import Candle

logger = logging.getLogger(__name__)

INTERVALO_POR_TIMEFRAME = {
    "M1": 60, "M5": 300, "M15": 900, "M30": 1800,
    "H1": 3600, "D1": 86400, "W1": 604800, "MO1": 2592000,
}


class CandleCache:
    """Cache de barras historicas por escaner/simbolo/timeframe.

    Primera ejecucion: se hace fetch completo de N barras.
    Ejecuciones posteriores: solo se piden las barras nuevas y se anaden al cache.
    """

    def __init__(self):
        self._cache: dict[tuple, list[Candle]] = {}
        self._lock = threading.Lock()

    def obtener(self, escaner_id: int, symbol: str, timeframe: str) -> Optional[list[Candle]]:
        """Retorna las barras cacheadas o None si no hay cache."""
        key = (escaner_id, symbol, timeframe)
        with self._lock:
            candles = self._cache.get(key)
            if candles is not None:
                return list(candles)
            return None

    def actualizar(
        self,
        escaner_id: int,
        symbol: str,
        timeframe: str,
        nuevas_barras: list[Candle],
    ) -> int:
        """Anade barras nuevas al cache, evitando duplicados por timestamp.

        Returns:
            Cantidad de barras nuevas anadidas.
        """
        if not nuevas_barras:
            return 0

        key = (escaner_id, symbol, timeframe)
        with self._lock:
            existentes = self._cache.get(key, [])

            # Obtener timestamps existentes para deduplicar
            timestamps_existentes = {c.timestamp for c in existentes}

            barras_nuevas = [
                b for b in nuevas_barras
                if b.timestamp not in timestamps_existentes
            ]

            if barras_nuevas:
                combinadas = existentes + barras_nuevas
                # Ordenar por timestamp ascendente
                combinadas.sort(key=lambda c: c.timestamp)
                self._cache[key] = combinadas

            return len(barras_nuevas)

    def necesita_fetch_completo(self, escaner_id: int, symbol: str, timeframe: str) -> bool:
        """True si no hay cache (primera ejecucion)."""
        key = (escaner_id, symbol, timeframe)
        with self._lock:
            return key not in self._cache or not self._cache[key]

    def barras_faltantes(
        self,
        escaner_id: int,
        symbol: str,
        timeframe: str,
        ahora: Optional[datetime] = None,
    ) -> int:
        """Calcula cuantas barras faltan desde el ultimo timestamp hasta ahora.

        Retorna 0 si el cache esta al dia, o el numero de barras que faltan.
        Si no hay cache, retorna -1 (necesita fetch completo).
        """
        key = (escaner_id, symbol, timeframe)
        ahora = ahora or datetime.now(timezone.utc)

        with self._lock:
            candles = self._cache.get(key)
            if not candles:
                return -1

            ultima = candles[-1]
            ts_ultima = ultima.get_datetime()
            if ts_ultima is None:
                return -1

            intervalo = INTERVALO_POR_TIMEFRAME.get(timeframe)
            if intervalo is None:
                return -1

            diferencia_seg = (ahora - ts_ultima).total_seconds()
            barras = int(diferencia_seg / intervalo)

            # Agregar margen de seguridad
            return max(0, barras + 2)

    def limpiar_escaner(self, escaner_id: int) -> int:
        """Limpia todo el cache de un escaner (cuando se detiene).

        Returns:
            Cantidad de entradas eliminadas.
        """
        with self._lock:
            keys_a_eliminar = [k for k in self._cache if k[0] == escaner_id]
            for key in keys_a_eliminar:
                del self._cache[key]
            if keys_a_eliminar:
                logger.info(
                    f"Cache limpiado para escaner {escaner_id}: "
                    f"{len(keys_a_eliminar)} entradas eliminadas"
                )
            return len(keys_a_eliminar)

    def recortar(self, escaner_id: int, symbol: str, timeframe: str, max_barras: int) -> None:
        """Mantiene solo las ultimas max_barras para evitar crecimiento infinito."""
        key = (escaner_id, symbol, timeframe)
        with self._lock:
            candles = self._cache.get(key)
            if candles and len(candles) > max_barras:
                self._cache[key] = candles[-max_barras:]

    def obtener_estadisticas(self) -> dict:
        """Retorna estadisticas del cache para monitoreo."""
        with self._lock:
            total_entradas = len(self._cache)
            total_barras = sum(len(v) for v in self._cache.values())
            escaneres = set(k[0] for k in self._cache)
            return {
                "total_entradas": total_entradas,
                "total_barras": total_barras,
                "escaneres_activos": len(escaneres),
            }
