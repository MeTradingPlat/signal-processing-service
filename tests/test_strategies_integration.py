"""Integration test: run ALL strategies against real marketdata."""
import json
import urllib.request
import sys
import os

import pytest

pytestmark = pytest.mark.integration

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.strategies.fundamentales import (
    DaysUntilEarningsStrategy, FloatStrategy, MarketCapStrategy,
    SharesOutstandingStrategy, ShortInterestStrategy, ShortRatioStrategy)
from app.strategies.momentum import (
    BackToEMAAlertStrategy, DistanceFromEMAStrategy, DistanceFromMAStrategy,
    DistanceFromVWAPStrategy, EMAVWAPSupportResistanceStrategy,
    RSIStrategy, ThroughEMAVWAPAlertStrategy)
from app.strategies.patrones import (
    BearishBullishEngulfingStrategy, BreakOverRecentHighsLowsStrategy,
    ConsecutiveCandlesStrategy, FirstCandleStrategy, HighLowOfDayStrategy,
    MinutosInMarketStrategy, NewCandleHighLowStrategy,
    OpeningRangeBreakdownStrategy, OpeningRangeBreakoutStrategy,
    PercentagePullbackHighsLowsStrategy, PivotsStrategy)
from app.strategies.precio_movimiento import (
    ChangeStrategy, CrossingAboveBelowStrategy, GapFromCloseStrategy,
    HaltStrategy, PercentageChangeStrategy, PercentageRangeStrategy,
    PositionInRangeStrategy, PrecioStrategy, RangeDollarsStrategy)
from app.strategies.volatilidad import ATRPStrategy, ATRStrategy, RelativeRangeStrategy
from app.strategies.volumen.average_volume import AverageVolumeStrategy
from app.strategies.volumen.relative_volume import RelativeVolumeStrategy
from app.strategies.volumen.volume import VolumeStrategy
from app.strategies.volumen.volume_spike import VolumeSpikeStrategy
from app.strategies.volumen.volumen_post_pre import VolumenPostPreStrategy
from app.scanner.marketdata_models import CandleResponse, FundamentalResponse, QuoteResponse
from app.strategies.base import MarketData

BASE = "https://api.metradingplat.net"

def auth():
    data = json.dumps({"username": "admin", "password": "Coltes2025!"}).encode()
    req = urllib.request.Request(f"{BASE}/auth/login", data=data,
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["token"]

def request(token, method, path, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f"{BASE}{path}", data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

@pytest.mark.integration
def test_symbol(sym, token):
    print(f"\n{'='*60}")
    print(f"Testing: {sym}")
    print(f"{'='*60}")

    fundamentals = request(token, "POST", "/marketdata/fundamentals/realtime", body=[sym]).get(sym, {})
    fund = FundamentalResponse(**fundamentals) if fundamentals else None

    quotes_raw = request(token, "POST", "/marketdata/quotes/cached", body=[sym])
    quote_val = quotes_raw.get(sym)
    quote = QuoteResponse(symbol=sym, last=quote_val) if quote_val else None

    candles_raw = request(token, "POST", "/marketdata/historical/batch",
        body={"symbols": [sym], "timeframe": "M5", "bars": 20})
    candles_list = candles_raw.get("candlesPorSimbolo", {}).get(sym, [])
    candles = [CandleResponse(**c) for c in candles_list] if candles_list else []

    data = MarketData(symbol=sym, fundamental=fund, quote=quote, candles=candles)

    strategies = [
        ("FLOTA", FloatStrategy),
        ("SHARES_OUT", SharesOutstandingStrategy),
        ("MARKET_CAP", MarketCapStrategy),
        ("SHORT_INT", ShortInterestStrategy),
        ("SHORT_RATIO", ShortRatioStrategy),
        ("EARN_DAYS", DaysUntilEarningsStrategy),
        ("PRECIO", PrecioStrategy),
        ("CHANGE", ChangeStrategy),
        ("PCT_CHANGE", PercentageChangeStrategy),
        ("GAP", GapFromCloseStrategy),
        ("POS_RANGE", PositionInRangeStrategy),
        ("PCT_RANGE", PercentageRangeStrategy),
        ("RANGE_$", RangeDollarsStrategy),
        ("CROSS_EMA", CrossingAboveBelowStrategy),
        ("HALT", HaltStrategy),
        ("ATR", ATRStrategy),
        ("ATRP", ATRPStrategy),
        ("REL_RANGE", RelativeRangeStrategy),
        ("RSI", RSIStrategy),
        ("DIST_VWAP", DistanceFromVWAPStrategy),
        ("DIST_EMA", DistanceFromEMAStrategy),
        ("DIST_MA", DistanceFromMAStrategy),
        ("BACK_EMA", BackToEMAAlertStrategy),
        ("THRU_EMA", ThroughEMAVWAPAlertStrategy),
        ("EMA_VWAP_SR", EMAVWAPSupportResistanceStrategy),
        ("ENGULFING", BearishBullishEngulfingStrategy),
        ("CONSEC_CNDL", ConsecutiveCandlesStrategy),
        ("FIRST_CNDL", FirstCandleStrategy),
        ("HI_LO_DAY", HighLowOfDayStrategy),
        ("NEW_HI_LO", NewCandleHighLowStrategy),
        ("PULLBACK", PercentagePullbackHighsLowsStrategy),
        ("BREAK_HI_LO", BreakOverRecentHighsLowsStrategy),
        ("OR_BREAKDN", OpeningRangeBreakdownStrategy),
        ("OR_BREAKOUT", OpeningRangeBreakoutStrategy),
        ("PIVOTS", PivotsStrategy),
        ("MIN_MKT", MinutosInMarketStrategy),
        ("VOLUME", VolumeStrategy),
        ("AVG_VOL", AverageVolumeStrategy),
        ("VOL_POST_PRE", VolumenPostPreStrategy),
        ("REL_VOL", RelativeVolumeStrategy),
        ("VOL_SPIKE", VolumeSpikeStrategy),
    ]

    results = {}
    errors = []
    nulls = []
    for name, factory in strategies:
        try:
            s = factory(None)
            val = s.compute_value(data)
            results[name] = val
            if val == 0.0 or val is None:
                nulls.append(name)
        except Exception as e:
            errors.append(f"{name}: {e}")

    for name, val in sorted(results.items(), key=lambda x: abs(x[1]) if x[1] else 0, reverse=True):
        marker = " ⚠️" if name in nulls else ""
        print(f"  {name:20s} = {val:>15.6f}{marker}")

    if errors:
        print(f"\n  ERRORES: {errors}")
    print(f"\n  Con datos: {len(results) - len(nulls)}/{len(results)} | Errores: {len(errors)}")
    return results


if __name__ == "__main__":
    token = auth()
    print("Auth OK")
    for sym in ["AAPL", "GME"]:
        test_symbol(sym, token)
