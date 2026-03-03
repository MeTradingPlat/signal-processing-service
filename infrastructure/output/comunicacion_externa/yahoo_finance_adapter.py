"""
Adaptador para obtener datos fundamentales desde Yahoo Finance via yahooquery.

Provee datos que TastyTrade API no ofrece:
- floatShares, sharesOutstanding, sharesShort, shortRatio

Cache en dos capas:
- Memoria: lookup O(1) durante la sesion activa
- Disco (JSON): persiste entre reinicios del contenedor; TTL configurable via
  YAHOO_CACHE_TTL_HORAS (default 24h). Ruta: YAHOO_CACHE_PATH (default /tmp/yahoo_cache.json)
"""

import json
import logging
import os
import time
from threading import Lock

from domain.models.datos_fundamentales import DatosFundamentales

logger = logging.getLogger(__name__)

_CACHE_PATH = os.getenv("YAHOO_CACHE_PATH", "/tmp/yahoo_cache.json")
_CACHE_TTL_SEGUNDOS = float(os.getenv("YAHOO_CACHE_TTL_HORAS", "24")) * 3600


class YahooFinanceAdapter:

    def __init__(self):
        self._cache: dict[str, DatosFundamentales] = {}
        self._lock = Lock()
        self._cargar_cache_disco()

    # -------------------------------------------------------------------------
    # Cache en disco
    # -------------------------------------------------------------------------

    def _cargar_cache_disco(self) -> None:
        """Carga el cache JSON del disco al iniciar. Ignora entradas expiradas."""
        try:
            if not os.path.exists(_CACHE_PATH):
                return
            with open(_CACHE_PATH, "r", encoding="utf-8") as f:
                raw: dict = json.load(f)
            ahora = time.time()
            cargados = 0
            for symbol, entry in raw.items():
                if ahora - entry.get("ts", 0) < _CACHE_TTL_SEGUNDOS:
                    self._cache[symbol] = DatosFundamentales(
                        symbol=symbol,
                        market_cap=entry.get("market_cap", 0.0),
                        float_shares=entry.get("float_shares", 0.0),
                        shares_outstanding=entry.get("shares_outstanding", 0.0),
                        short_interest=entry.get("short_interest", 0.0),
                        short_ratio=entry.get("short_ratio", 0.0),
                    )
                    cargados += 1
            logger.info(f"Yahoo cache disco: {cargados}/{len(raw)} entradas cargadas (TTL {_CACHE_TTL_SEGUNDOS/3600:.0f}h)")
        except Exception as e:
            logger.warning(f"No se pudo cargar cache disco Yahoo: {e}")

    def _guardar_en_disco(self, symbol: str, datos: DatosFundamentales) -> None:
        """Escribe/actualiza la entrada del simbolo en el archivo JSON."""
        try:
            raw: dict = {}
            if os.path.exists(_CACHE_PATH):
                try:
                    with open(_CACHE_PATH, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                except Exception:
                    raw = {}

            raw[symbol] = {
                "ts": time.time(),
                "market_cap": datos.market_cap,
                "float_shares": datos.float_shares,
                "shares_outstanding": datos.shares_outstanding,
                "short_interest": datos.short_interest,
                "short_ratio": datos.short_ratio,
            }

            with open(_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(raw, f)
        except Exception as e:
            logger.warning(f"No se pudo guardar cache disco Yahoo para {symbol}: {e}")

    # -------------------------------------------------------------------------
    # API publica
    # -------------------------------------------------------------------------

    def obtener_datos_fundamentales(self, symbol: str) -> DatosFundamentales:
        """
        Obtiene datos fundamentales de Yahoo Finance.
        Busca primero en memoria, luego en disco (con TTL), y solo llama a Yahoo si
        no hay datos validos en ninguna capa.
        """
        with self._lock:
            if symbol in self._cache:
                return self._cache[symbol]

        try:
            from yahooquery import Ticker
            ticker = Ticker(symbol)
            stats = ticker.key_stats

            if isinstance(stats, str) or symbol not in stats:
                logger.warning(f"Yahoo Finance: no data for {symbol}")
                datos = DatosFundamentales(symbol=symbol)
            else:
                data = stats[symbol]
                if isinstance(data, str):
                    logger.warning(f"Yahoo Finance: error for {symbol}: {data}")
                    datos = DatosFundamentales(symbol=symbol)
                else:
                    summary_detail = ticker.summary_detail.get(symbol, {})
                    market_cap = float(summary_detail.get("marketCap", 0) or 0)

                    datos = DatosFundamentales(
                        symbol=symbol,
                        float_shares=float(data.get("floatShares", 0) or 0),
                        shares_outstanding=float(data.get("sharesOutstanding", 0) or 0),
                        short_interest=float(data.get("sharesShort", 0) or 0),
                        short_ratio=float(data.get("shortRatio", 0) or 0),
                        market_cap=market_cap,
                    )

            with self._lock:
                self._cache[symbol] = datos

            self._guardar_en_disco(symbol, datos)

            logger.debug(
                f"Yahoo Finance {symbol}: float={datos.float_shares}, "
                f"outstanding={datos.shares_outstanding}, short={datos.short_interest}, "
                f"ratio={datos.short_ratio}, mcap={datos.market_cap}"
            )
            return datos

        except Exception as e:
            logger.error(f"Yahoo Finance error for {symbol}: {e}")
            datos = DatosFundamentales(symbol=symbol)
            with self._lock:
                self._cache[symbol] = datos
            return datos

    def limpiar_cache(self) -> None:
        with self._lock:
            self._cache.clear()
        try:
            if os.path.exists(_CACHE_PATH):
                os.remove(_CACHE_PATH)
                logger.info(f"Cache disco Yahoo eliminado: {_CACHE_PATH}")
        except Exception as e:
            logger.warning(f"No se pudo eliminar cache disco Yahoo: {e}")
