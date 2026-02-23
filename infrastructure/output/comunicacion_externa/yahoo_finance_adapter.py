"""
Adaptador para obtener datos fundamentales desde Yahoo Finance via yahooquery.

Provee datos que TastyTrade API no ofrece:
- floatShares, sharesOutstanding, sharesShort, shortRatio
"""

import logging
from threading import Lock

# from yahooquery import Ticker  # Mover a lazy load en obtener_datos_fundamentales

from domain.models.datos_fundamentales import DatosFundamentales

logger = logging.getLogger(__name__)


class YahooFinanceAdapter:

    def __init__(self):
        self._cache: dict[str, DatosFundamentales] = {}
        self._lock = Lock()

    def obtener_datos_fundamentales(self, symbol: str) -> DatosFundamentales:
        """
        Obtiene datos fundamentales de Yahoo Finance.
        Cache en memoria por simbolo para evitar llamadas repetidas en la misma corrida.
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
                    # Intentar obtener marketCap desde 'summary_detail' o 'price' si no esta en key_stats
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
