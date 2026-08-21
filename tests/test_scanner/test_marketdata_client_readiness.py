from unittest.mock import patch

from app.scanner.marketdata_client import MarketdataClient


def test_not_common_stock_regex_excludes_warrants_and_preferreds():
    excluded = ["BWIV/WS", "PCGpA", "SNUSpI", "WHRpA"]
    kept = ["AAPL", "BWXT", "TCAI", "SPY"]
    for symbol in excluded:
        assert MarketdataClient._NOT_COMMON_STOCK_RE.search(symbol), symbol
    for symbol in kept:
        assert not MarketdataClient._NOT_COMMON_STOCK_RE.search(symbol), symbol


def test_fundamentals_ready_ignores_structurally_sparse_symbols():
    # Regression: los primeros N simbolos de cada mercado (orden fijo) caian
    # seguido por debajo del umbral solo porque incluian warrants/preferentes
    # sin marketCap/prevClose de forma estructural -- confirmado en vivo:
    # fundamentals_ready() nunca daba True, 5 minutos perdidos en cada
    # arranque del servicio.
    client = MarketdataClient()

    _POR_MERCADO = {
        "NASDAQ": ["BWIV/WS", "PCGpA", "AAPL", "MSFT", "NVDA"],
        "NYSE": ["JPM", "XOM", "KO", "WMT", "DIS"],
        "AMEX": ["SNUSpI", "IWM", "GLD", "SLV", "USO"],
        "ETF": ["SPY", "QQQ", "VTI", "VOO", "DIA"],
    }

    def fake_fetch_symbols(mercados):
        return _POR_MERCADO[mercados[0]]

    class Fund:
        def __init__(self, market_cap, prev_close):
            self.marketCap = market_cap
            self.prevClose = prev_close

    def fake_fetch_fundamentals(symbols):
        return {s: Fund(100.0, 10.0) for s in symbols}

    with patch.object(client, "fetch_symbols", side_effect=fake_fetch_symbols), \
         patch.object(client, "fetch_fundamentals", side_effect=fake_fetch_fundamentals):
        assert client.fundamentals_ready(per_mercado_sample=3) is True
