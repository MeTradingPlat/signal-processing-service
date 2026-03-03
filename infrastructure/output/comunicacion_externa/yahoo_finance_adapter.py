"""
Adaptador para obtener datos fundamentales desde Yahoo Finance via yahooquery.

Cache en dos capas con TTL diferenciado por grupo de datos:
  - Shares (floatShares, sharesOutstanding, sharesShort, shortRatio):
      fuente key_stats, TTL 7 dias (YAHOO_TTL_SHARES_DIAS, default 7)
  - MarketCap:
      fuente summary_detail, TTL 4h (YAHOO_TTL_MCAP_HORAS, default 4)

Disco: /tmp/yahoo_cache.json (YAHOO_CACHE_PATH). Cada entrada guarda ts_shares y
ts_mcap por separado para renovar solo el grupo expirado.
"""

import json
import logging
import os
import time
from threading import Lock

from domain.models.datos_fundamentales import DatosFundamentales

logger = logging.getLogger(__name__)

_CACHE_PATH = os.getenv("YAHOO_CACHE_PATH", "/tmp/yahoo_cache.json")
_TTL_SHARES = float(os.getenv("YAHOO_TTL_SHARES_DIAS", "7")) * 86400
_TTL_MCAP = float(os.getenv("YAHOO_TTL_MCAP_HORAS", "4")) * 3600


class YahooFinanceAdapter:

    def __init__(self):
        # {symbol: (DatosFundamentales, ts_shares, ts_mcap)}
        self._cache: dict[str, tuple] = {}
        self._lock = Lock()
        self._cargar_cache_disco()

    # -------------------------------------------------------------------------
    # Cache en disco
    # -------------------------------------------------------------------------

    def _cargar_cache_disco(self) -> None:
        try:
            if not os.path.exists(_CACHE_PATH):
                return
            with open(_CACHE_PATH, "r", encoding="utf-8") as f:
                raw: dict = json.load(f)
            ahora = time.time()
            cargados = 0
            for symbol, entry in raw.items():
                ts_shares = entry.get("ts_shares", 0)
                ts_mcap = entry.get("ts_mcap", 0)
                # Solo cargar en memoria si al menos shares sigue vigente
                if ahora - ts_shares < _TTL_SHARES:
                    datos = DatosFundamentales(
                        symbol=symbol,
                        market_cap=entry.get("market_cap", 0.0) if ahora - ts_mcap < _TTL_MCAP else 0.0,
                        float_shares=entry.get("float_shares", 0.0),
                        shares_outstanding=entry.get("shares_outstanding", 0.0),
                        short_interest=entry.get("short_interest", 0.0),
                        short_ratio=entry.get("short_ratio", 0.0),
                    )
                    # Si mcap expiró al cargar, marcamos ts_mcap = 0 para que se refresque
                    ts_mcap_efectivo = ts_mcap if ahora - ts_mcap < _TTL_MCAP else 0.0
                    self._cache[symbol] = (datos, ts_shares, ts_mcap_efectivo)
                    cargados += 1
            logger.info(
                f"Yahoo cache disco: {cargados}/{len(raw)} entradas cargadas "
                f"(TTL shares {_TTL_SHARES/86400:.0f}d, mcap {_TTL_MCAP/3600:.0f}h)"
            )
        except Exception as e:
            logger.warning(f"No se pudo cargar cache disco Yahoo: {e}")

    def _guardar_en_disco(self, symbol: str, datos: DatosFundamentales,
                          ts_shares: float, ts_mcap: float) -> None:
        try:
            raw: dict = {}
            if os.path.exists(_CACHE_PATH):
                try:
                    with open(_CACHE_PATH, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                except Exception:
                    raw = {}

            raw[symbol] = {
                "ts_shares": ts_shares,
                "ts_mcap": ts_mcap,
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
    # Fetch parcial de Yahoo
    # -------------------------------------------------------------------------

    def _fetch_shares(self, symbol: str) -> tuple[float, float, float, float]:
        """Llama key_stats. Retorna (float_shares, shares_outstanding, short_interest, short_ratio)."""
        from yahooquery import Ticker
        ticker = Ticker(symbol)
        stats = ticker.key_stats
        if isinstance(stats, str) or symbol not in stats:
            return 0.0, 0.0, 0.0, 0.0
        data = stats[symbol]
        if isinstance(data, str):
            return 0.0, 0.0, 0.0, 0.0
        return (
            float(data.get("floatShares", 0) or 0),
            float(data.get("sharesOutstanding", 0) or 0),
            float(data.get("sharesShort", 0) or 0),
            float(data.get("shortRatio", 0) or 0),
        )

    def _fetch_mcap(self, symbol: str) -> float:
        """Llama summary_detail. Retorna marketCap."""
        from yahooquery import Ticker
        ticker = Ticker(symbol)
        summary = ticker.summary_detail
        if isinstance(summary, str) or symbol not in summary:
            return 0.0
        return float(summary[symbol].get("marketCap", 0) or 0)

    # -------------------------------------------------------------------------
    # API publica
    # -------------------------------------------------------------------------

    def obtener_datos_fundamentales(self, symbol: str) -> DatosFundamentales:
        """
        Retorna DatosFundamentales con TTL diferenciado:
        - Shares (float/outstanding/short): TTL 7 dias
        - MarketCap: TTL 4h

        Solo llama a Yahoo para los grupos expirados, minimizando llamadas HTTP.
        """
        ahora = time.time()

        with self._lock:
            entrada = self._cache.get(symbol)

        shares_stale = True
        mcap_stale = True
        datos_actuales = DatosFundamentales(symbol=symbol)

        if entrada:
            datos_actuales, ts_shares, ts_mcap = entrada
            shares_stale = (ahora - ts_shares) >= _TTL_SHARES
            mcap_stale = (ahora - ts_mcap) >= _TTL_MCAP

        if not shares_stale and not mcap_stale:
            return datos_actuales

        ts_shares_nuevo = ahora if not shares_stale else 0.0
        ts_mcap_nuevo = ahora if not mcap_stale else 0.0

        try:
            if shares_stale:
                float_shares, shares_outstanding, short_interest, short_ratio = self._fetch_shares(symbol)
                datos_actuales = DatosFundamentales(
                    symbol=symbol,
                    market_cap=datos_actuales.market_cap,
                    float_shares=float_shares,
                    shares_outstanding=shares_outstanding,
                    short_interest=short_interest,
                    short_ratio=short_ratio,
                )
                ts_shares_nuevo = ahora
                logger.debug(f"Yahoo shares actualizados para {symbol}")

            if mcap_stale:
                mcap = self._fetch_mcap(symbol)
                datos_actuales = DatosFundamentales(
                    symbol=symbol,
                    market_cap=mcap,
                    float_shares=datos_actuales.float_shares,
                    shares_outstanding=datos_actuales.shares_outstanding,
                    short_interest=datos_actuales.short_interest,
                    short_ratio=datos_actuales.short_ratio,
                )
                ts_mcap_nuevo = ahora
                logger.debug(f"Yahoo mcap actualizado para {symbol}: {mcap}")

        except Exception as e:
            logger.error(f"Yahoo Finance error for {symbol}: {e}")
            if not entrada:
                datos_actuales = DatosFundamentales(symbol=symbol)
            ts_shares_nuevo = ts_shares_nuevo or ahora
            ts_mcap_nuevo = ts_mcap_nuevo or ahora

        with self._lock:
            self._cache[symbol] = (datos_actuales, ts_shares_nuevo, ts_mcap_nuevo)

        self._guardar_en_disco(symbol, datos_actuales, ts_shares_nuevo, ts_mcap_nuevo)
        return datos_actuales

    def limpiar_cache(self) -> None:
        with self._lock:
            self._cache.clear()
        try:
            if os.path.exists(_CACHE_PATH):
                os.remove(_CACHE_PATH)
                logger.info(f"Cache disco Yahoo eliminado: {_CACHE_PATH}")
        except Exception as e:
            logger.warning(f"No se pudo eliminar cache disco Yahoo: {e}")
