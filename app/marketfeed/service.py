import logging
import threading
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


def _bootstrap(client: MarketdataClient, fundamentals_cache, snapshot_cache, symbols: list[str]) -> None:
    """Carga inicial por REST (una sola vez, no por ciclo) -- suscribirse a
    /ws/fundamentals y /ws/snapshot NO trae un snapshot al momento: ambos
    solo empujan cuando algo cambia de verdad (confirmado en vivo el
    2026-09-30: recien desplegado, la cache quedaba en 0/8889 simbolos
    hasta el primer refresco real de marketdata-service, hasta 15+ min de
    escaneres con filtros estaticos/dinamicos ciegos). Corre en un hilo
    aparte para no demorar la conexion WS -- las dos fuentes escriben la
    MISMA cache, un push en vivo mas reciente simplemente pisa el valor de
    arranque sin ningun problema de orden."""
    try:
        fetched = client.fetch_fundamentals(symbols)
        for symbol, resp in fetched.items():
            fundamentals_cache[symbol] = resp.model_dump()
        logger.info("MarketFeed: bootstrapped fundamentals for %d/%d symbols", len(fetched), len(symbols))
    except Exception as e:
        logger.error("MarketFeed: fundamentals bootstrap failed: %s", e)

    try:
        prices = client.fetch_current_prices(symbols)
        for symbol, price in prices.items():
            snapshot_cache[symbol] = {"currentPrice": price}
        logger.info("MarketFeed: bootstrapped snapshot for %d/%d symbols", len(prices), len(symbols))
    except Exception as e:
        logger.error("MarketFeed: snapshot bootstrap failed: %s", e)


def run_market_feed(fundamentals_cache, snapshot_cache) -> None:
    """Unico proceso (no uno por escaner) que mantiene fundamentales y
    snapshot de TODO el universo en memoria compartida -- reemplaza que
    cada escaner pida por REST lo mismo cada ciclo (Fase 2 del rediseño por
    eventos). No abre ninguna conexion a DxLink: ambos WS son un fan-out
    interno de datos que marketdata-service ya tiene en su propia cache."""
    client = MarketdataClient()
    symbols = client.fetch_symbols(_ALL_MARKETS)
    logger.info("MarketFeed: loaded %d symbols, starting feeds", len(symbols))

    threading.Thread(target=_bootstrap, args=(client, fundamentals_cache, snapshot_cache, symbols),
                     daemon=True, name="market-feed-bootstrap").start()

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
