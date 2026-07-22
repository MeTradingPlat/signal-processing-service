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
        "VOLUME_SPIKE": VolumeSpikeStrategy,
    }
    cls = mapping.get(filtro.enumFiltro.name if filtro.enumFiltro else "", _PassthroughStrategy)
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
