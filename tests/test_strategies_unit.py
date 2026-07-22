"""Unit tests: verify ALL strategies compute correct values with known test data."""
import math
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.enums import EnumCondicional, EnumParametro
from app.models.filtro import Filtro
from app.models.parametro import Parametro
from app.models.valor import ValorCondicional, ValorFloat, ValorInteger, ValorString
from app.scanner.marketdata_models import CandleResponse, FundamentalResponse, QuoteResponse
from app.strategies.base import MarketData
from app.strategies.condition import evaluate_condition

# ─── helpers ─────────────────────────────────────────────

def _make_fund(**kw) -> FundamentalResponse:
    return FundamentalResponse(symbol="TEST", **kw)


def _make_quote(**kw) -> QuoteResponse:
    return QuoteResponse(symbol="TEST", **kw)


def _make_candle(**kw) -> CandleResponse:
    return CandleResponse(symbol="TEST", **kw)


def _make_marketdata(fund=None, quote=None, candles=None) -> MarketData:
    return MarketData(symbol="TEST", fundamental=fund, quote=quote, candles=candles)


def _strategy(cls, **params):
    from app.models.enums import EnumFiltro
    f = Filtro(enumFiltro=EnumFiltro.UNKNOWN)
    f.parametros = []
    for key, val in params.items():
        if isinstance(val, float):
            v = ValorFloat(valor=val)
        elif isinstance(val, int):
            v = ValorInteger(valor=val)
        elif isinstance(val, str):
            v = ValorString(valor=val)
        else:
            v = val
        f.parametros.append(Parametro(enumParametro=key, objValorSeleccionado=v))
    return cls(f)


def assert_approx(actual, expected, name, tolerance=0.01):
    if actual is None or expected is None:
        ok = actual == expected
    else:
        ok = abs(actual - expected) < tolerance
    status = "✅" if ok else f"❌ expected {expected}, got {actual}"
    print(f"  {name:30s} {status}")
    return ok


# ─── TEST DATA ──────────────────────────────────────────

AAPL_FUND = _make_fund(
    marketCap=4.9e12, sharesOutstanding=15_000_000_000,
    floatShares=13_500_000_000, shortInterest=1.04, shortRatio=1.73,
    open=323.13, prevClose=326.59, daysUntilEarnings=8,
    eps=8.23, beta=1.09, tradingStatus="ACTIVE",
)


AAPL_QUOTE = _make_quote(
    last=327.74, bid=327.37, ask=327.40, open=323.13,
    high=329.60, low=322.22, prevClose=326.59, volume=41_349_908,
    tradingHalted=False,
)


def _make_candles(prices: list[tuple[float, float, float, float, float]]):
    """(open, high, low, close, volume) tuples"""
    candles = []
    for i, (o, h, l, c, v) in enumerate(prices):
        ts = f"2026-07-21T{10 + i // 12:02d}:{(i % 12) * 5:02d}:00Z"
        candles.append(_make_candle(open=o, high=h, low=l, close=c, volume=v, timestamp=ts))
    return candles


# 14 candles with uptrend, clear OHLC
BULLISH_CANDLES = _make_candles([
    (100, 102, 99, 101, 1000), (101, 103, 100, 102, 1200),
    (102, 105, 101, 104, 1500), (104, 106, 103, 105, 1300),
    (105, 108, 104, 107, 1600), (107, 109, 106, 108, 1400),
    (108, 110, 107, 109, 1700), (109, 112, 108, 111, 1800),
    (111, 113, 110, 112, 1500), (112, 115, 111, 114, 1900),
    (114, 116, 113, 115, 2000), (115, 118, 114, 117, 2100),
    (117, 120, 116, 119, 2200), (119, 122, 118, 121, 2300),
])

ENGULFING_CANDLES = _make_candles([
    (100, 105, 95, 97, 1000),   # bearish (close < open)
    (97, 103, 96, 102.5, 1500),  # BULLISH engulfing (open<prev_close, close>prev_open)
])

PIVOT_CANDLES = _make_candles([
    (100, 102, 99, 101, 1000),
    (101, 105, 100, 104, 1200),  # pivot high
    (104, 103, 99, 100, 1100),
])


# ─── TESTS ──────────────────────────────────────────────

def test_condition_evaluation():
    print("\n=== CONDICIONES ===")
    cond_mayor = ValorCondicional(enumCondicional=EnumCondicional.MAYOR_QUE, valor1=5.0)
    cond_menor = ValorCondicional(enumCondicional=EnumCondicional.MENOR_QUE, valor1=5.0)
    cond_entre = ValorCondicional(enumCondicional=EnumCondicional.ENTRE, valor1=3.0, valor2=7.0)
    cond_fuera = ValorCondicional(enumCondicional=EnumCondicional.FUERA, valor1=3.0, valor2=7.0)
    cond_igual = ValorCondicional(enumCondicional=EnumCondicional.IGUAL_A, valor1=5.0)

    assert evaluate_condition(cond_mayor, 6.0)   # 6 > 5 = True
    assert not evaluate_condition(cond_mayor, 4.0)  # 4 > 5 = False
    assert evaluate_condition(cond_menor, 4.0)   # 4 < 5 = True
    assert evaluate_condition(cond_entre, 5.0)   # 3 <= 5 <= 7 = True
    assert not evaluate_condition(cond_entre, 2.0)  # 2 outside
    assert evaluate_condition(cond_fuera, 2.0)   # 2 < 3 = True
    assert evaluate_condition(cond_igual, 5.0)   # 5 == 5 = True
    assert evaluate_condition(None, 999.0)       # null condition = always True
    print("  Condiciones: ✅ 9/9")


def test_fundamentals():
    print("\n=== FUNDAMENTALES ===")
    from app.strategies.fundamentales import (
        FloatStrategy, MarketCapStrategy, ShortInterestStrategy,
        ShortRatioStrategy, DaysUntilEarningsStrategy, SharesOutstandingStrategy,
    )
    data = _make_marketdata(fund=AAPL_FUND)

    ok = True
    ok &= assert_approx(_strategy(FloatStrategy).compute_value(data), 13_500_000_000, "Float")
    ok &= assert_approx(_strategy(MarketCapStrategy).compute_value(data), 4.9e12, "MarketCap")
    ok &= assert_approx(_strategy(ShortInterestStrategy).compute_value(data), 1.04, "ShortInterest")
    ok &= assert_approx(_strategy(ShortRatioStrategy).compute_value(data), 1.73, "ShortRatio")
    ok &= assert_approx(_strategy(DaysUntilEarningsStrategy).compute_value(data), 8.0, "DaysUntilEarnings")
    ok &= assert_approx(_strategy(SharesOutstandingStrategy).compute_value(data), 15_000_000_000, "SharesOut")
    print(f"  Fundamentales: {'✅' if ok else '❌'}")


def test_precio_movimiento():
    print("\n=== PRECIO Y MOVIMIENTO ===")
    from app.strategies.precio_movimiento import (
        PrecioStrategy, ChangeStrategy, GapFromCloseStrategy,
        PositionInRangeStrategy, PercentageRangeStrategy, RangeDollarsStrategy,
        HaltStrategy,
    )
    data = _make_marketdata(quote=AAPL_QUOTE, fund=AAPL_FUND)

    ok = True
    # Precio: last price
    ok &= assert_approx(_strategy(PrecioStrategy).compute_value(data), 327.74, "Precio", 0.5)
    # Gap: open - prev_close, in %: (323.13-326.59)/326.59*100 = -1.06%
    expected_gap = (323.13 - 326.59) / 326.59 * 100
    ok &= assert_approx(
        _strategy(GapFromCloseStrategy, **{EnumParametro.FORMATO_GAP_FROM_CLOSE: "PORCENTAJE"})
        .compute_value(data), expected_gap, "GapFromClose%", 0.1)
    # Position in range: (last-low)/(high-low)*100
    pos = (327.74 - 322.22) / (329.60 - 322.22) * 100
    ok &= assert_approx(_strategy(PositionInRangeStrategy).compute_value(data), pos, "PositionInRange", 1)
    # Range %: (high-low)/((high+low)/2)*100
    rng_pct = (329.60 - 322.22) / ((329.60 + 322.22) / 2) * 100
    ok &= assert_approx(_strategy(PercentageRangeStrategy).compute_value(data), rng_pct, "PercentageRange", 0.5)
    # Range $: high - low
    ok &= assert_approx(_strategy(RangeDollarsStrategy).compute_value(data), 7.38, "RangeDollars", 0.1)
    # Halt: not halted
    ok &= assert_approx(_strategy(HaltStrategy).compute_value(data), 0.0, "Halt (active)")
    # Change: default ref=CLOSE, medida=PRECIO → last - prevClose
    ch = 327.74 - 326.59
    ok &= assert_approx(
        _strategy(ChangeStrategy, **{EnumParametro.PUNTO_REFERENCIA_CHANGE: "CLOSE",
                                      EnumParametro.TIPO_MEDIDA_CHANGE: "PRECIO"})
        .compute_value(data), ch, "Change", 0.5)
    print(f"  Precio/Movimiento: {'✅' if ok else '❌'}")


def test_volatilidad():
    print("\n=== VOLATILIDAD ===")
    from app.strategies.volatilidad import ATRStrategy, ATRPStrategy
    data = _make_marketdata(candles=BULLISH_CANDLES)

    ok = True
    # ATR for BULLISH_CANDLES: ~3.0 (range 2-4 per candle)
    atr = _strategy(ATRStrategy, **{EnumParametro.LONGITUD_ATR: 14}).compute_value(data)
    ok &= assert_approx(atr, 3.0, "ATR", 0.5)
    # ATRP: atr/price*100 = 3.0/121*100 = ~2.5%
    atrp = _strategy(ATRPStrategy, **{EnumParametro.PERIODO_ATR_ATRP: 14}).compute_value(data)
    ok &= assert_approx(atrp, 2.5, "ATRP", 1.0)
    print(f"  Volatilidad: {'✅' if ok else '❌'}")


def test_momentum():
    print("\n=== MOMENTUM ===")
    from app.strategies.momentum import RSIStrategy, DistanceFromEMAStrategy, DistanceFromMAStrategy
    data = _make_marketdata(candles=BULLISH_CANDLES)

    ok = True
    # RSI in uptrend should be > 50
    rsi = _strategy(RSIStrategy, **{EnumParametro.PERIODO_RSI: 14}).compute_value(data)
    ok &= rsi > 50
    print(f"  RSI={rsi:.2f} {'✅ > 50 (uptrend)' if rsi > 50 else '❌ should be > 50'}")

    # Distance from EMA should be small positive (price slightly above EMA in uptrend)
    dist_ema = _strategy(DistanceFromEMAStrategy, **{EnumParametro.PERIODO_LINEA_DISTANCE_FROM_VWAP_EMA_MA: 9}).compute_value(data)
    print(f"  DistEMA={dist_ema:.4f}% {'✅' if abs(dist_ema) < 10 else '❌ too far'}")

    # Distance from MA
    dist_ma = _strategy(DistanceFromMAStrategy, **{EnumParametro.PERIODO_LINEA_DISTANCE_FROM_VWAP_EMA_MA: 20}).compute_value(data)
    print(f"  DistMA={dist_ma:.4f}% {'✅' if abs(dist_ma) < 10 else '❌ too far'}")


def test_patrones():
    print("\n=== PATRONES ===")
    from app.strategies.patrones import (
        BearishBullishEngulfingStrategy, PivotsStrategy,
        HighLowOfDayStrategy, NewCandleHighLowStrategy,
        ConsecutiveCandlesStrategy,
    )

    # Engulfing
    ok = True
    engulf = _strategy(BearishBullishEngulfingStrategy,
                       **{EnumParametro.TIPO_PATRON_BEARISH_BULLISH_ENGULFING_CANDLE: "BULLISH"})
    engulf_data = _make_marketdata(candles=ENGULFING_CANDLES)
    val = engulf.compute_value(engulf_data)
    ok &= assert_approx(val, 1.0, "BullishEngulfing")

    # Pivot
    pivot_data = _make_marketdata(candles=PIVOT_CANDLES)
    val = _strategy(PivotsStrategy).compute_value(pivot_data)
    ok &= assert_approx(val, 1.0, "PivotHigh")

    # HighLowOfDay
    hl_data = _make_marketdata(candles=BULLISH_CANDLES)
    val = _strategy(HighLowOfDayStrategy).compute_value(hl_data)
    ok &= val >= 0 and val <= 100
    print(f"  HighLowOfDay={val:.1f}% {'✅' if ok else '❌'}")

    # NewCandleHighLow (last candle has highest high)
    val = _strategy(NewCandleHighLowStrategy).compute_value(hl_data)
    ok &= assert_approx(val, 1.0, "NewHigh")

    # 3 consecutive bullish
    bull_3 = _make_candles([
        (100, 102, 99, 101, 1000),
        (101, 103, 100, 102.5, 1200),
        (102.5, 105, 101, 104, 1500),
    ])
    val = _strategy(ConsecutiveCandlesStrategy,
                    **{EnumParametro.NUMERO_VELAS_CONSECUTIVAS: 3}).compute_value(
        _make_marketdata(candles=bull_3))
    ok &= assert_approx(val, 1.0, "ConsecutiveBull3")
    print(f"  Patrones: {'✅' if ok else '❌'}")


def test_filter_evaluation():
    print("\n=== FILTER EVALUATION (end-to-end) ===")
    from app.strategies.base import FilterStrategy

    from app.models.enums import EnumFiltro
    # Test a filter with condition: PRECIO > 300
    data = _make_marketdata(quote=AAPL_QUOTE)
    f = Filtro(enumFiltro=EnumFiltro.PRECIO)
    f.parametros = [
        Parametro(
            enumParametro=EnumParametro.CONDICION,
            objValorSeleccionado=ValorCondicional(
                enumCondicional=EnumCondicional.MAYOR_QUE, valor1=300.0,
            ),
        ),
    ]

    class TestPrecioStrategy(FilterStrategy):
        def compute_value(self, data: MarketData) -> float:
            return data.quote.last or 0.0

    s = TestPrecioStrategy(f)
    assert s.evaluate(data)  # 327.74 > 300 = True
    print(f"  AAPL price > 300: {'✅ PASS' if s.evaluate(data) else '❌ FAIL'}")

    # Test: PRECIO > 500 (should fail)
    f2 = Filtro(enumFiltro=EnumFiltro.PRECIO)
    f2.parametros = [
        Parametro(
            enumParametro=EnumParametro.CONDICION,
            objValorSeleccionado=ValorCondicional(
                enumCondicional=EnumCondicional.MAYOR_QUE, valor1=500.0,
            ),
        ),
    ]
    s2 = TestPrecioStrategy(f2)
    assert not s2.evaluate(data)  # 327.74 > 500 = False
    print(f"  AAPL price > 500: {'✅ FAIL (correct)' if not s2.evaluate(data) else '❌ SHOULD FAIL'}")

    # Test: MarketCap ENTRE 1T y 10T (should pass)
    f3 = Filtro(enumFiltro=EnumFiltro.MARKET_CAP)
    f3.parametros = [
        Parametro(
            enumParametro=EnumParametro.CONDICION,
            objValorSeleccionado=ValorCondicional(
                enumCondicional=EnumCondicional.ENTRE, valor1=1e12, valor2=10e12,
            ),
        ),
    ]
    from app.strategies.fundamentales import MarketCapStrategy
    s3 = MarketCapStrategy(f3)
    fund_data = _make_marketdata(fund=AAPL_FUND)
    assert s3.evaluate(fund_data)  # 4.9T between 1T and 10T
    print(f"  MarketCap 1T-10T: {'✅ PASS' if s3.evaluate(fund_data) else '❌ FAIL'}")


if __name__ == "__main__":
    test_condition_evaluation()
    test_fundamentals()
    test_precio_movimiento()
    test_volatilidad()
    test_momentum()
    test_patrones()
    test_filter_evaluation()
    print("\n" + "=" * 50)
    print("ALL TESTS COMPLETE")
    print("=" * 50)
