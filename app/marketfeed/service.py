import logging
import time
from functools import partial

from app.config import settings
from app.marketfeed.relay_feed_client import RelayFeedClient
from app.scanner.marketdata_client import MarketdataClient

logger = logging.getLogger(__name__)

# Todos los mercados que un escaner puede seleccionar (ver mappings.py) --
# el feed cubre el universo COMPLETO una sola vez, sin importar que
# mercados use cada escaner individual (ver el comentario de SymbolPipeline
# sobre por que un cache por mercado no vale la pena: cualquier escaner
# puede necesitar cualquier simbolo).
_ALL_MARKETS = ["NASDAQ", "NYSE", "AMEX", "ETF", "BATS", "OTC"]

_IDLE_POLL_SECONDS = 3600.0


def _store(cache, symbol: str, data: dict) -> None:
    cache[symbol] = data


def run_market_feed(fundamentals_cache, snapshot_cache) -> None:
    """Unico proceso (no uno por escaner) que mantiene fundamentales y
    snapshot de TODO el universo en memoria compartida -- reemplaza que
    cada escaner pida por REST lo mismo cada ciclo (Fase 2 del rediseño por
    eventos). No abre ninguna conexion a DxLink: ambos WS son un fan-out
    interno de datos que marketdata-service ya tiene en su propia cache."""
    symbols = MarketdataClient().fetch_symbols(_ALL_MARKETS)
    logger.info("MarketFeed: loaded %d symbols, starting feeds", len(symbols))

    ws_base = settings.marketdata_url.replace("http://", "ws://").replace("https://", "wss://")

    fundamentals_client = RelayFeedClient(
        f"{ws_base}/ws/fundamentals", "fundamentals", symbols, partial(_store, fundamentals_cache),
    )
    snapshot_client = RelayFeedClient(
        f"{ws_base}/ws/snapshot", "snapshot", symbols, partial(_store, snapshot_cache),
    )

    try:
        while True:
            time.sleep(_IDLE_POLL_SECONDS)
    except KeyboardInterrupt:
        pass
    finally:
        fundamentals_client.stop()
        snapshot_client.stop()
