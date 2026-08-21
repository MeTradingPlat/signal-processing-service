import concurrent.futures
import logging
import time
from typing import Dict, List, Optional

from app.models.enums import EnumCategoriaFiltro, EnumFiltro
from app.models.escaner import Escaner
from app.models.filtro import Filtro
from app.models.signal_match import SignalMatch
from app.scanner.marketdata_client import MarketdataClient
from app.scanner.marketdata_models import CandleResponse, FundamentalResponse, PriceSnapshot
from app.scanner.timeframe import bars_necesarias_grupo
from app.strategies.base import FilterStrategy, MarketData

logger = logging.getLogger(__name__)

_FETCH_SYMBOLS_RETRIES = 3
_FETCH_SYMBOLS_RETRY_BACKOFF_SECONDS = 3.0


def _make_marketdata(
    symbol: str,
    fund: Optional[FundamentalResponse] = None,
    candles: Optional[List[CandleResponse]] = None,
    snapshot: Optional[PriceSnapshot] = None,
) -> MarketData:
    return MarketData(symbol=symbol, fundamental=fund, candles=candles, snapshot=snapshot)


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
    from app.strategies.volumen.relative_volume_same_time import RelativeVolumeSameTimeStrategy
    from app.strategies.volumen.volume import VolumeStrategy
    from app.strategies.volumen.volume_spike import VolumeSpikeStrategy
    from app.strategies.volumen.volumen_post_pre import VolumenPostPreStrategy
    mapping = {
        "VOLUME": VolumeStrategy,
        "AVERAGE_VOLUME": AverageVolumeStrategy,
        "VOLUMEN_POST_PRE": VolumenPostPreStrategy,
        "RELATIVE_VOLUME": RelativeVolumeStrategy,
        "RELATIVE_VOLUME_SAME_TIME": RelativeVolumeSameTimeStrategy,
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

# Tamano de lote y concurrencia para evaluar_tecnicos -- ver
# _evaluar_grupo_tecnico para el porque (acotar memoria sin perder el
# paralelismo que marketdata-service ya hace internamente por conexion).
# Bajado de 4 a 2 workers: un escaner sin pre-filtros configurados evalua el
# universo completo (~8800 simbolos) en cada temporalidad tecnica, en cada
# ciclo (~70s) -- confirmado en vivo que eso, con 4 lotes de 700 en vuelo a
# la vez, tumbaba el contenedor por OOM cada vez (SIGKILL, sin traceback,
# el proceso simplemente desaparecia a mitad de ciclo).
_CANDLE_CHUNK_SIZE = 700
_CANDLE_CHUNK_WORKERS = 2

_STATIC_PRE: set[EnumCategoriaFiltro] = {
    EnumCategoriaFiltro.CARACTERISTICAS_FUNDAMENTALES,
}

_DYNAMIC_PRE: set[EnumCategoriaFiltro] = {
    EnumCategoriaFiltro.PRECIO_Y_MOVIMIENTO,
    EnumCategoriaFiltro.VOLUMEN,
}

_ALL_PRE = _STATIC_PRE | _DYNAMIC_PRE

_FILTRO_CATEGORY_FALLBACK: dict[EnumFiltro, EnumCategoriaFiltro] = {
    EnumFiltro.FLOAT: EnumCategoriaFiltro.CARACTERISTICAS_FUNDAMENTALES,
    EnumFiltro.SHARES_OUTSTANDING: EnumCategoriaFiltro.CARACTERISTICAS_FUNDAMENTALES,
    EnumFiltro.MARKET_CAP: EnumCategoriaFiltro.CARACTERISTICAS_FUNDAMENTALES,
    EnumFiltro.SHORT_INTEREST: EnumCategoriaFiltro.CARACTERISTICAS_FUNDAMENTALES,
    EnumFiltro.SHORT_RATIO: EnumCategoriaFiltro.CARACTERISTICAS_FUNDAMENTALES,
    EnumFiltro.DAYS_UNTIL_EARNINGS: EnumCategoriaFiltro.CARACTERISTICAS_FUNDAMENTALES,
    EnumFiltro.VOLUME: EnumCategoriaFiltro.VOLUMEN,
    EnumFiltro.VOLUMEN_POST_PRE: EnumCategoriaFiltro.VOLUMEN,
    EnumFiltro.CHANGE: EnumCategoriaFiltro.PRECIO_Y_MOVIMIENTO,
    EnumFiltro.PRECIO: EnumCategoriaFiltro.PRECIO_Y_MOVIMIENTO,
    EnumFiltro.GAP_FROM_CLOSE: EnumCategoriaFiltro.PRECIO_Y_MOVIMIENTO,
    EnumFiltro.POSITION_IN_RANGE: EnumCategoriaFiltro.PRECIO_Y_MOVIMIENTO,
    EnumFiltro.PERCENTAGE_RANGE: EnumCategoriaFiltro.PRECIO_Y_MOVIMIENTO,
    EnumFiltro.RANGE_DOLLARS: EnumCategoriaFiltro.PRECIO_Y_MOVIMIENTO,
    EnumFiltro.HALT: EnumCategoriaFiltro.PRECIO_Y_MOVIMIENTO,
    # DISTANCE_FROM_VWAP/EMA/MA, PERCENTAGE_CHANGE, AVERAGE_VOLUME,
    # RELATIVE_VOLUME(_SAME_TIME), VOLUME_SPIKE, CROSSING_ABOVE_BELOW NO van
    # aca: sus estrategias necesitan velas reales (promedios/comparacion
    # historica de volumen, EMA/VWAP, cambio sobre N barras) -- la etapa
    # dinamica solo construye MarketData con quote (candles=None siempre), asi
    # que listarlos aca hacia que compute_value devolviera None SIEMPRE, y
    # como se exige que todos los dinamicos pasen a la vez, ningun simbolo
    # podia pasar nunca (confirmado en vivo: "6149 -> 0" en cada ciclo para un
    # escaner con DISTANCE_FROM_VWAP). Sin entrada aca caen por defecto en
    # tecnicos, donde si se les pasan velas reales.
    #
    # VOLUME/POSITION_IN_RANGE/PERCENTAGE_RANGE/RANGE_DOLLARS/CHANGE si se
    # quedan aca porque son datos puntuales (no series historicas) que ya
    # vienen en el fundamental REST que _aplicar_dinamicos ya tiene en
    # memoria -- ver el enriquecimiento del quote mas abajo.
}


# Filtros cuya estrategia SIEMPRE necesita velas reales -- si la API manda
# una categoria de "precio y movimiento" o "volumen" para estos (bug
# confirmado en scanner-management-service: varias FiltroFactory*.java
# tenian la categoria de Java desalineada con lo que su propia estrategia
# Python necesita), no se puede confiar en esa categoria: la etapa dinamica
# construye MarketData con candles=None siempre, asi que compute_value
# devolveria None SIEMPRE y ningun simbolo pasaria nunca (confirmado en
# vivo: "2114 -> 0" en cada ciclo con PERCENTAGE_CHANGE). Esta lista manda
# por encima de lo que diga la API, no solo cuando la categoria viene vacia.
_REQUIERE_VELAS: set[EnumFiltro] = {
    EnumFiltro.PERCENTAGE_CHANGE,
    EnumFiltro.CROSSING_ABOVE_BELOW,
    EnumFiltro.VOLUME_SPIKE,
    EnumFiltro.RELATIVE_VOLUME,
    EnumFiltro.RELATIVE_VOLUME_SAME_TIME,
    EnumFiltro.AVERAGE_VOLUME,
    EnumFiltro.DISTANCE_FROM_VWAP,
    EnumFiltro.DISTANCE_FROM_EMA,
    EnumFiltro.DISTANCE_FROM_MA,
    EnumFiltro.BACK_TO_EMA_ALERT,
    EnumFiltro.THROUGH_EMA_VWAP_ALERT,
    EnumFiltro.EMA_VWAP_SUPPORT_RESISTANCE,
}


def categorizar_filtros(filtros: List[Filtro]) -> tuple[List[Filtro], List[Filtro], List[Filtro]]:
    estaticos = []
    dinamicos = []
    tecnicos = []
    for f in filtros:
        if f.enumFiltro in _REQUIERE_VELAS:
            tecnicos.append(f)
            continue
        cat = f.objCategoria.enumCategoriaFiltro if f.objCategoria else None
        if cat is None and f.enumFiltro:
            cat = _FILTRO_CATEGORY_FALLBACK.get(f.enumFiltro)
        if cat in _STATIC_PRE:
            estaticos.append(f)
        elif cat in _DYNAMIC_PRE:
            dinamicos.append(f)
        else:
            tecnicos.append(f)
    return estaticos, dinamicos, tecnicos


class SymbolPipeline:
    def __init__(self, escaner: Escaner):
        self.scanner_id = escaner.idEscaner
        self.mercados = [m.enumMercado.value for m in escaner.mercados]
        self.pre_estaticos, self.pre_dinamicos, self.tecnicos = categorizar_filtros(escaner.filtros)
        self._todos: List[str] = []
        self._filtrados: List[str] = []
        self._client = MarketdataClient()
        self._fundamentals: Dict[str, FundamentalResponse] = {}
        self._signaled_today: set = set()
        self._previously_matched: set = set()
        logger.info(
            "SymbolPipeline: id=%d mercados=%s estaticos=%d dinamicos=%d tecnicos=%d",
            escaner.idEscaner, self.mercados,
            len(self.pre_estaticos), len(self.pre_dinamicos), len(self.tecnicos),
        )

    def cargar_todos(self):
        """Reintenta con backoff corto antes de rendirse -- confirmado en
        vivo: un simple restart de marketdata-service (segundos de
        "Connection refused") tumbaba esta llamada UNA vez al arrancar el
        escaner, y como nada mas la volvia a intentar, el escaner se quedaba
        evaluando una lista de simbolos vacia por horas, sin ningun error
        visible salvo un log suelto. El reintento por ciclo (ver runner.py,
        _run_daily/_run_loop_until_end) cubre caidas mas largas que este
        backoff corto."""
        logger.info("SymbolPipeline: fetching symbols for markets=%s", self.mercados)
        for intento in range(1, _FETCH_SYMBOLS_RETRIES + 1):
            try:
                self._todos = self._client.fetch_symbols(self.mercados)
                self._filtrados = list(self._todos)
                logger.info("SymbolPipeline: loaded %d symbols", len(self._todos))
                return
            except Exception as e:
                logger.error("SymbolPipeline: failed to fetch symbols (intento %d/%d): %s",
                             intento, _FETCH_SYMBOLS_RETRIES, e)
                if intento < _FETCH_SYMBOLS_RETRIES:
                    time.sleep(_FETCH_SYMBOLS_RETRY_BACKOFF_SECONDS * intento)
        self._todos = []
        self._filtrados = []

    def _fetch_fundamentals(self):
        if not self._todos:
            return
        try:
            self._fundamentals = self._client.fetch_fundamentals(self._todos)
            no_data = sum(
                1 for f in self._fundamentals.values()
                if f.marketCap is None and f.prevClose is None and f.shortInterest is None
            )
            logger.info(
                "SymbolPipeline: loaded fundamentals for %d symbols (%d with no usable data from marketdata)",
                len(self._fundamentals), no_data,
            )
        except Exception as e:
            logger.error("SymbolPipeline: fundamentals fetch failed: %s", e)

    def aplicar_pre_filtros(self):
        self._fetch_fundamentals()
        self._aplicar_estaticos()
        self._aplicar_dinamicos()
        self._excluir_ya_senializados_hoy()

    def _aplicar_estaticos(self):
        if not self.pre_estaticos:
            return
        remaining = []
        rejected_no_data = 0
        for sym in self._todos:
            fund = self._fundamentals.get(sym)
            if fund is None:
                rejected_no_data += 1
                continue
            if all(_get_strategy(f).evaluate(_make_marketdata(sym, fund, None, None))
                   for f in self.pre_estaticos):
                remaining.append(sym)
        self._filtrados = remaining
        logger.info("SymbolPipeline: static %d->%d (no_data=%d)", len(self._todos), len(self._filtrados), rejected_no_data)

    def _aplicar_dinamicos(self):
        if not self.pre_dinamicos:
            return
        try:
            prices = self._client.fetch_current_prices(self._filtrados)
        except Exception as e:
            logger.error("Failed to fetch current prices, keeping previous filtered set: %s", e)
            return
        if not prices:
            logger.warning("Dynamic filters: no price data, keeping previous filtered set")
            return
        remaining = []
        for sym in self._filtrados:
            price = prices.get(sym)
            if price is None:
                continue
            fund = self._fundamentals.get(sym)
            snapshot = PriceSnapshot(
                symbol=sym,
                last=price,
                # VOLUME/POSITION_IN_RANGE/PERCENTAGE_RANGE/RANGE_DOLLARS/CHANGE
                # necesitan volumen y rango del dia, que el snapshot ligero no
                # trae por si solo -- pero ya estan en fund (REST, ya en
                # memoria de _fetch_fundamentals), asi que se copian aca en
                # vez de pedir nada nuevo.
                volume=fund.dayVolume if fund else None,
                open=fund.open if fund else None,
                high=fund.high if fund else None,
                low=fund.low if fund else None,
                prevClose=fund.prevClose if fund else None,
            )
            data = _make_marketdata(sym, fund, None, snapshot)
            if all(_get_strategy(f).evaluate(data) for f in self.pre_dinamicos):
                remaining.append(sym)
        self._filtrados = remaining
        logger.info("SymbolPipeline: dynamic filters %d -> %d symbols", len(prices), len(self._filtrados))

    def _excluir_ya_senializados_hoy(self):
        """Consulta al log-service los simbolos que ya tuvieron senal hoy para
        este escaner y los saca de _filtrados. Sin esto, el mismo simbolo
        genera senal en cada ciclo del dia -- el usuario quiere una sola senal
        por simbolo por dia por escaner. La lista se refresca en cada ciclo
        para cubrir simbolos que se senializaron en ciclos anteriores de hoy."""
        if not self._filtrados:
            return
        try:
            import urllib.request, json
            from app.config import settings
            url = f"{settings.log_service_url}/logs/escaner/{self.scanner_id}/signaled-today"
            req = urllib.request.Request(url, headers={"X-Gateway-Passed": "true"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                self._signaled_today = set(json.loads(resp.read()))
            antes = len(self._filtrados)
            self._filtrados = [s for s in self._filtrados if s not in self._signaled_today]
            excluidos = antes - len(self._filtrados)
            if excluidos:
                logger.info("SymbolPipeline: excluded %d already-signaled-today symbols, %d remain",
                            excluidos, len(self._filtrados))
        except Exception as e:
            logger.warning("SymbolPipeline: signaled-today check failed, proceeding without exclusion: %s", e)

    def evaluar_tecnicos(self, grupos: dict[int, list[Filtro]]) -> dict[str, list[SignalMatch]]:
        candidates = set(self._filtrados)
        matched: dict[str, list[SignalMatch]] = {sym: [] for sym in candidates}

        for minutos, filtros in grupos.items():
            if not candidates:
                break
            tf_label = _minutos_to_label(minutos)
            bars_needed = bars_necesarias_grupo(filtros, minutos)
            passing, stats = self._evaluar_grupo_tecnico(candidates, filtros, tf_label, bars_needed, matched)
            logger.info(
                "evaluar_tecnicos %s: %d symbols, %d/%d bars with a null OHLC field",
                tf_label, stats[0], stats[1], stats[2],
            )
            candidates = passing

        return {sym: matched[sym] for sym in candidates}

    def _evaluar_grupo_tecnico(
        self, candidates: set[str], filtros: list[Filtro], tf_label: str, bars_needed: int,
        matched: dict[str, list[SignalMatch]],
    ) -> tuple[set[str], tuple[int, int, int]]:
        """Pide y evalua velas por lotes acotados y concurrentes (no todo el
        universo candidato de una sola llamada) -- con miles de simbolos, una
        sola peticion gigante mantiene todas sus velas en memoria a la vez
        hasta terminar de evaluar el filtro completo, lo que ya provoco un
        OutOfMemory real en produccion el mismo dia que el fix de filtros
        dinamicos empezo a dejar pasar el volumen real de simbolos por
        primera vez. Los lotes en vuelo se limitan a _CANDLE_CHUNK_WORKERS a
        la vez (concurrentes, no secuenciales, para no perder el paralelismo
        que marketdata-service ya hace internamente por conexion) y cada uno
        se evalua y se descarta apenas llega, en vez de acumular todos antes
        de evaluar nada."""
        batch = list(candidates)
        chunks = [batch[i:i + _CANDLE_CHUNK_SIZE] for i in range(0, len(batch), _CANDLE_CHUNK_SIZE)]

        def fetch_chunk(chunk: list[str]) -> dict[str, list[CandleResponse]]:
            try:
                return self._client.fetch_candles(chunk, tf_label, bars=bars_needed)
            except Exception as e:
                logger.error("Failed to fetch candles for %s (chunk of %d): %s", tf_label, len(chunk), e)
                return {}

        passing: set[str] = set()
        symbols_with_data = 0
        total_bars = 0
        null_bars = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=_CANDLE_CHUNK_WORKERS) as executor:
            pending = {executor.submit(fetch_chunk, chunk) for chunk in chunks}
            # as_completed(futures) NO suelta cada Future al procesarlo -- el
            # objeto (con las velas ya parseadas adentro) se queda vivo en la
            # lista `futures` hasta que la funcion entera termina, aunque ya
            # se haya leido su .result(). Con wait()+reasignar `pending` en
            # cada vuelta, los lotes ya procesados si quedan sin referencias y
            # se pueden liberar de a uno, que era la intencion original.
            while pending:
                done, pending = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
                for future in done:
                    candles_map = future.result()
                    symbols_with_data += len(candles_map)
                    for sym, candles in candles_map.items():
                        if sym not in matched:
                            # marketdata-service a veces devuelve un simbolo que
                            # no estaba en el lote pedido (ej. una serie de
                            # preferentes emparentada, visto en vivo con
                            # COF -> COFPN) -- confiar en esa clave tumbaba el
                            # escaner entero con un KeyError. No es un
                            # candidato que pedimos evaluar, se descarta.
                            logger.warning(
                                "evaluar_tecnicos %s: marketdata devolvio simbolo no pedido '%s', descartado",
                                tf_label, sym,
                            )
                            continue
                        total_bars += len(candles)
                        null_bars += sum(
                            1 for c in candles
                            if c.open is None or c.high is None or c.low is None or c.close is None
                        )
                        if not candles:
                            continue
                        fund = self._fundamentals.get(sym)
                        data = _make_marketdata(sym, fund, candles, None)
                        sym_matches = [f for f in filtros if _get_strategy(f).evaluate(data)]
                        if len(sym_matches) == len(filtros):
                            vela_timestamp = candles[-1].timestamp
                            precio = candles[-1].close
                            matched[sym].extend(
                                SignalMatch(filtro=f, vela_timestamp=vela_timestamp, precio=precio)
                                for f in sym_matches
                            )
                            passing.add(sym)

        return passing, (symbols_with_data, null_bars, total_bars)

    def renovar_si_nuevo_dia(self):
        logger.info("SymbolPipeline: daily refresh, reloading symbols and static filters")
        self.cargar_todos()
        self._previously_matched = set()

    def nuevos_symbols(self, signals: dict) -> set:
        """Simbolos que empiezan a calificar en este ciclo (no calificaban en
        el anterior). Reemplaza el estado, no lo une, para que un simbolo que
        deja de calificar y vuelve a calificar despues cuente como nuevo otra
        vez."""
        nuevos = set(signals) - self._previously_matched
        self._previously_matched = set(signals)
        return nuevos

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
    # Nunca manejaba meses/anios -- cualquier cosa >= 1 semana (10080 min)
    # caia en el "else" y se etiquetaba como "W<n>" sin importar que tan
    # grande fuera, asi que 1MO/3MO/6MO/1Y (43200/129600/259200/525600 min)
    # se mandaban a marketdata-service como "W4"/"W12"/"W25"/"W52" -- ninguno
    # de esos existe en EnumTimeframe, asi que esos 4 timeframes fallaban en
    # silencio igual que los que ya se arreglaron en marketdata-service.
    if minutos < 60:
        return f"M{minutos}"
    if minutos < 1440:
        return f"H{minutos // 60}"
    if minutos < 10080:
        return f"D{minutos // 1440}"
    if minutos < 43200:
        return f"W{minutos // 10080}"
    if minutos < 525600:
        return f"MO{minutos // 43200}"
    return "Y1"
