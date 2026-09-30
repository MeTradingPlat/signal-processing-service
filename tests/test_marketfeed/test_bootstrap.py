from app.marketfeed.service import _bootstrap
from app.scanner.marketdata_models import FundamentalResponse


class _FakeClient:
    def __init__(self, fundamentals=None, prices=None, fail_fundamentals=False, fail_prices=False):
        self._fundamentals = fundamentals or {}
        self._prices = prices or {}
        self._fail_fundamentals = fail_fundamentals
        self._fail_prices = fail_prices

    def fetch_fundamentals(self, symbols):
        if self._fail_fundamentals:
            raise RuntimeError("marketdata-service caido")
        return self._fundamentals

    def fetch_current_prices(self, symbols):
        if self._fail_prices:
            raise RuntimeError("marketdata-service caido")
        return self._prices


def test_bootstrap_carga_fundamentales_como_dict_plano_en_la_cache():
    client = _FakeClient(fundamentals={"AAPL": FundamentalResponse(symbol="AAPL", marketCap=3_000_000_000)})
    fundamentals_cache, snapshot_cache = {}, {}

    _bootstrap(client, fundamentals_cache, snapshot_cache, ["AAPL"])

    assert fundamentals_cache["AAPL"]["marketCap"] == 3_000_000_000


def test_bootstrap_carga_el_precio_actual_en_el_snapshot():
    client = _FakeClient(prices={"AAPL": 150.0})
    fundamentals_cache, snapshot_cache = {}, {}

    _bootstrap(client, fundamentals_cache, snapshot_cache, ["AAPL"])

    assert snapshot_cache["AAPL"] == {"currentPrice": 150.0}


def test_bootstrap_no_lanza_si_fundamentals_falla_y_aun_asi_carga_precios():
    client = _FakeClient(prices={"AAPL": 150.0}, fail_fundamentals=True)
    fundamentals_cache, snapshot_cache = {}, {}

    _bootstrap(client, fundamentals_cache, snapshot_cache, ["AAPL"])

    assert fundamentals_cache == {}
    assert snapshot_cache["AAPL"] == {"currentPrice": 150.0}


def test_bootstrap_no_lanza_si_precios_falla_y_aun_asi_carga_fundamentales():
    client = _FakeClient(fundamentals={"AAPL": FundamentalResponse(symbol="AAPL", marketCap=1)}, fail_prices=True)
    fundamentals_cache, snapshot_cache = {}, {}

    _bootstrap(client, fundamentals_cache, snapshot_cache, ["AAPL"])

    assert fundamentals_cache["AAPL"]["marketCap"] == 1
    assert snapshot_cache == {}
