import logging
from typing import Dict, List, Optional

from app.models.enums import EnumCategoriaFiltro
from app.models.escaner import Escaner
from app.models.filtro import Filtro
from app.scanner.marketdata_client import MarketdataClient
from app.scanner.marketdata_models import CandleResponse, FundamentalResponse, QuoteResponse
from app.strategies.base import FilterStrategy, MarketData

logger = logging.getLogger(__name__)


def _make_marketdata(
    symbol: str,
    fund: Optional[FundamentalResponse] = None,
    candles: Optional[List[CandleResponse]] = None,
    quote: Optional[QuoteResponse] = None,
) -> MarketData:
    return MarketData(symbol=symbol, fundamental=fund, candles=candles, quote=quote)


def _get_strategy(filtro: Filtro) -> FilterStrategy:
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
    mapping = {
        "VOLUME": VolumeStrategy,
        "AVERAGE_VOLUME": AverageVolumeStrategy,
        "VOLUMEN_POST_PRE": VolumenPostPreStrategy,
        "RELATIVE_VOLUME": RelativeVolumeStrategy,
        "RELATIVE_VOLUME_SAME_TIME": RelativeVolumeStrategy,
        "VOLUME_SPIKE": VolumeSpikeStrategy,
        "CHANGE": ChangeStrategy,
        "PERCENTAGE_CHANGE": PercentageChangeStrategy,
        "PRECIO": PrecioStrategy,
        "GAP_FROM_CLOSE": GapFromCloseStrategy,
        "POSITION_IN_RANGE": PositionInRangeStrategy,
        "PERCENTAGE_RANGE": PercentageRangeStrategy,
        "RANGE_DOLLARS": RangeDollarsStrategy,
        "CROSSING_ABOVE_BELOW": CrossingAboveBelowStrategy,
        "HALT": HaltStrategy,
        "ATR": ATRStrategy,
        "ATRP": ATRPStrategy,
        "RELATIVE_RANGE": RelativeRangeStrategy,
        "RSI": RSIStrategy,
        "DISTANCE_FROM_VWAP": DistanceFromVWAPStrategy,
        "DISTANCE_FROM_EMA": DistanceFromEMAStrategy,
        "DISTANCE_FROM_MA": DistanceFromMAStrategy,
        "BACK_TO_EMA_ALERT": BackToEMAAlertStrategy,
        "THROUGH_EMA_VWAP_ALERT": ThroughEMAVWAPAlertStrategy,
        "EMA_VWAP_SUPPORT_RESISTANCE": EMAVWAPSupportResistanceStrategy,
        "BEARISH_BULLISH_ENGULFING": BearishBullishEngulfingStrategy,
        "CONSECUTIVE_CANDLES": ConsecutiveCandlesStrategy,
        "FIRST_CANDLE": FirstCandleStrategy,
        "HIGH_LOW_OF_DAY": HighLowOfDayStrategy,
        "NEW_CANDLE_HIGH_LOW": NewCandleHighLowStrategy,
        "PERCENTAGE_PULLBACK_HIGHS_LOWS": PercentagePullbackHighsLowsStrategy,
        "BREAK_OVER_RECENT_HIGHS_LOWS": BreakOverRecentHighsLowsStrategy,
        "OPENING_RANGE_BREAKDOWN": OpeningRangeBreakdownStrategy,
        "OPENING_RANGE_BREAKOUT": OpeningRangeBreakoutStrategy,
        "PIVOTS": PivotsStrategy,
        "MINUTOS_IN_MARKET": MinutosInMarketStrategy,
        "FLOAT": FloatStrategy,
        "SHARES_OUTSTANDING": SharesOutstandingStrategy,
        "MARKET_CAP": MarketCapStrategy,
        "SHORT_INTEREST": ShortInterestStrategy,
        "SHORT_RATIO": ShortRatioStrategy,
        "DAYS_UNTIL_EARNINGS": DaysUntilEarningsStrategy,
    }
    name = filtro.enumFiltro.name if filtro.enumFiltro else ""
    cls = mapping.get(name, _PassthroughStrategy)
    return cls(filtro)


class _PassthroughStrategy(FilterStrategy):
    def compute_value(self, data: MarketData) -> float:
        return 1.0

_STATIC_PRE: set[EnumCategoriaFiltro] = {
    EnumCategoriaFiltro.CARACTERISTICAS_FUNDAMENTALES,
}

_DYNAMIC_PRE: set[EnumCategoriaFiltro] = {
    EnumCategoriaFiltro.PRECIO_Y_MOVIMIENTO,
    EnumCategoriaFiltro.VOLUMEN,
}

_ALL_PRE = _STATIC_PRE | _DYNAMIC_PRE


def categorizar_filtros(filtros: List[Filtro]) -> tuple[List[Filtro], List[Filtro], List[Filtro]]:
    estaticos = []
    dinamicos = []
    tecnicos = []
    for f in filtros:
        cat = f.objCategoria.enumCategoriaFiltro if f.objCategoria else None
        if cat in _STATIC_PRE:
            estaticos.append(f)
        elif cat in _DYNAMIC_PRE:
            dinamicos.append(f)
        else:
            tecnicos.append(f)
    return estaticos, dinamicos, tecnicos


class SymbolPipeline:
    def __init__(self, escaner: Escaner):
        self.mercados = [m.enumMercado.value for m in escaner.mercados]
        self.pre_estaticos, self.pre_dinamicos, self.tecnicos = categorizar_filtros(escaner.filtros)
        self._todos: List[str] = []
        self._filtrados: List[str] = []
        self._estaticos_aplicados = False
        self._client = MarketdataClient()
        self._fundamentals: Dict[str, FundamentalResponse] = {}
        self._candles: Dict[str, List[CandleResponse]] = {}
        logger.info(
            "SymbolPipeline: id=%d mercados=%s estaticos=%d dinamicos=%d tecnicos=%d",
            escaner.idEscaner, self.mercados,
            len(self.pre_estaticos), len(self.pre_dinamicos), len(self.tecnicos),
        )

    def cargar_todos(self):
        logger.info("SymbolPipeline: fetching symbols for markets=%s", self.mercados)
        try:
            self._todos = self._client.fetch_symbols(self.mercados)
            self._filtrados = list(self._todos)
            logger.info("SymbolPipeline: loaded %d symbols", len(self._todos))
        except Exception as e:
            logger.error("SymbolPipeline: failed to fetch symbols: %s", e)
            self._todos = []
            self._filtrados = []

    def _fetch_fundamentals(self):
        if not self._todos:
            return
        try:
            batch = self._todos[:200]
            self._fundamentals = self._client.fetch_fundamentals(batch)
            logger.info("SymbolPipeline: loaded fundamentals for %d symbols", len(self._fundamentals))
        except Exception as e:
            logger.error("SymbolPipeline: fundamentals fetch failed: %s", e)

    def aplicar_pre_filtros(self, first_cycle_of_day: bool = False):
        if first_cycle_of_day or not self._estaticos_aplicados:
            self._fetch_fundamentals()
            self._aplicar_estaticos()
            self._estaticos_aplicados = True
        self._aplicar_dinamicos()

    def _aplicar_estaticos(self):
        if not self.pre_estaticos:
            return
        remaining = []
        for sym in self._todos:
            fund = self._fundamentals.get(sym)
            if fund is None:
                remaining.append(sym)
                continue
            ok = True
            for f in self.pre_estaticos:
                strategy = _get_strategy(f)
                data = _make_marketdata(sym, fund, None, None)
                if not strategy.evaluate(data):
                    ok = False
                    break
            if ok:
                remaining.append(sym)
        self._filtrados = remaining
        logger.info("SymbolPipeline: static filters %d -> %d symbols", len(self._todos), len(self._filtrados))

    def _aplicar_dinamicos(self):
        if not self.pre_dinamicos:
            return
        try:
            quotes = self._client.fetch_quotes(self._filtrados)
        except Exception as e:
            logger.error("Failed to fetch quotes: %s", e)
            return
        remaining = []
        for sym in self._filtrados:
            fund = self._fundamentals.get(sym)
            price = quotes.get(sym)
            quote = QuoteResponse(symbol=sym, last=price) if price else None
            data = _make_marketdata(sym, fund, None, quote)
            if all(_get_strategy(f).evaluate(data) for f in self.pre_dinamicos):
                remaining.append(sym)
        self._filtrados = remaining
        logger.info("SymbolPipeline: dynamic filters %d -> %d symbols",
                    len(quotes), len(self._filtrados))

    def evaluar_tecnicos(self, grupos: dict[int, list[Filtro]]) -> dict[str, list[Filtro]]:
        from app.scanner.mappings import timeframe_to_marketdata

        candidates = set(self._filtrados)
        for minutos, filtros in grupos.items():
            if not candidates:
                break
            tf_label = _minutos_to_label(minutos)
            tf_marketdata = timeframe_to_marketdata(tf_label)
            try:
                batch = list(candidates)[:200]
                candles_map = self._client.fetch_candles(batch, tf_label, bars=max(50, minutos))
            except Exception as e:
                logger.error("Failed to fetch candles for %s: %s", tf_label, e)
                continue

            passing = set()
            for sym in candidates:
                candles = candles_map.get(sym, [])
                if not candles:
                    continue
                fund = self._fundamentals.get(sym)
                data = _make_marketdata(sym, fund, candles, None)
                if all(_get_strategy(f).evaluate(data) for f in filtros):
                    passing.add(sym)
            candidates = passing

        result = {}
        for sym in candidates:
            result[sym] = [f for f in self.tecnicos
                          if _get_strategy(f).evaluate(_make_marketdata(sym, self._fundamentals.get(sym), self._candles.get(sym, []), None))]
        return result

    def renovar_si_nuevo_dia(self):
        logger.info("SymbolPipeline: daily refresh, reloading symbols and static filters")
        self.cargar_todos()
        self._estaticos_aplicados = False

    @property
    def todos(self) -> List[str]:
        return self._todos

    @property
    def filtrados(self) -> List[str]:
        return self._filtrados

    @property
    def pre_filtros(self) -> List[Filtro]:
        return self.pre_estaticos + self.pre_dinamicos


def _minutos_to_label(minutos: int) -> str:
    if minutos < 60:
        return f"{minutos}M"
    elif minutos < 1440:
        return f"{minutos // 60}H"
    elif minutos < 10080:
        return f"{minutos // 1440}D"
    else:
        return f"{minutos // 10080}W"
