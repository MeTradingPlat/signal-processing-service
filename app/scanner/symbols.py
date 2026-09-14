import concurrent.futures
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from app.adapters.log_service_client import LogServiceClient
from app.models.enums import EnumFiltro
from app.models.escaner import Escaner
from app.models.filtro import Filtro
from app.models.signal_match import SignalMatch
from app.scanner.filter_categories import categorizar_filtros
from app.scanner.marketdata_client import MarketdataClient
from app.scanner.marketdata_models import CandleResponse, FundamentalResponse, PriceSnapshot
from app.scanner.timeframe import bars_necesarias_grupo, minutos_to_label
from app.strategies.base import MarketData
from app.strategies.registry import get_strategy

logger = logging.getLogger(__name__)

_FETCH_SYMBOLS_RETRIES = 3
_FETCH_SYMBOLS_RETRY_BACKOFF_SECONDS = 3.0

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

# RangeConfluenceStrategy es el unico filtro que necesita mas de una
# temporalidad a la vez (D1 propia del grupo + H4/H1 "extra") -- un lookback
# fijo y chico basta para su swing_range, no el piso de bars_necesarias_grupo
# (pensado para la temporalidad propia del grupo, que en D1 pide miles de
# barras por el margen minutos*2).
_TIMEFRAMES_CONFLUENCIA_EXTRA = ("H4", "H1")
_BARS_CONFLUENCIA_EXTRA = 50


def _todos_los_requeridos_pasan(filtros: List[Filtro], resultados: List[bool]) -> bool:
    """AND estricto sobre los filtros SIN grupoAlternativo (comportamiento
    de siempre); para los que comparten un mismo grupoAlternativo, basta
    con que UNO de ellos haya pasado -- son variantes alternativas del
    mismo paso, no requisitos simultaneos (ej. Liquidity Grab Candle o
    Aceleracion-Desaceleracion, no las dos a la vez). `resultados[i]`
    corresponde a `filtros[i]`, ya evaluado por el llamador."""
    alternativos: dict[int, list[int]] = {}
    for i, f in enumerate(filtros):
        if f.grupoAlternativo is None:
            if not resultados[i]:
                return False
        else:
            alternativos.setdefault(f.grupoAlternativo, []).append(i)
    return all(any(resultados[i] for i in indices) for indices in alternativos.values())


def _make_marketdata(
    symbol: str,
    fund: Optional[FundamentalResponse] = None,
    candles: Optional[List[CandleResponse]] = None,
    snapshot: Optional[PriceSnapshot] = None,
    zona: Optional[tuple] = None,
    velas_extra: Optional[Dict[str, List[CandleResponse]]] = None,
) -> MarketData:
    return MarketData(symbol=symbol, fundamental=fund, candles=candles, snapshot=snapshot, zona=zona,
                       velas_extra=velas_extra)


class SymbolPipeline:
    def __init__(
        self,
        escaner: Escaner,
        marketdata_client: Optional[MarketdataClient] = None,
        log_service_client: Optional[LogServiceClient] = None,
    ):
        self.scanner_id = escaner.idEscaner
        self.permitir_multiples_senales = escaner.permitirMultiplesSenales
        self.mercados = [m.enumMercado.value for m in escaner.mercados]
        self.pre_estaticos, self.pre_dinamicos, self.tecnicos = categorizar_filtros(escaner.filtros)
        self._todos: List[str] = []
        self._filtrados: List[str] = []
        # Ultimo set que paso los filtros dinamicos con exito -- ante un fallo
        # de fetch_current_prices (marketdata-service caido/reiniciando) el
        # fallback usa ESTE set, no el universo: sin filtros estaticos
        # configurados, _aplicar_estaticos ya reseteo _filtrados al universo
        # completo antes, asi que el fallback ciego evaluaba tecnicos sobre
        # TODO el universo con el filtro de volumen (o precio) simplemente
        # sin aplicar (confirmado en vivo 2026-08-24: 35 min de fallos del
        # fetch de precios y warrants de 2 velas al dia senialados).
        self._ultimo_filtrado: List[str] = []
        self._client = marketdata_client or MarketdataClient()
        self._log_client = log_service_client or LogServiceClient()
        self._fundamentals: Dict[str, FundamentalResponse] = {}
        self._signaled_today: set = set()
        # Candidatos que sobrevivieron a todos los grupos evaluados ANTES de
        # cada temporalidad, poblado en cada evaluar_tecnicos -- lo usa
        # RealtimeFilterWatcher (runner.py) para saber a que simbolos
        # suscribirse en /ws/candles para los filtros con
        # revisionTiempoReal=true de esa temporalidad.
        self.candidatos_previos_a_grupo: dict[int, set] = {}
        # Zona de precio (low, high) descubierta para cada simbolo por el
        # ultimo filtro "productor de zona" (Order Block, Range Extreme
        # Proximity) que paso su grupo -- ver evaluar_tecnicos. Publica (sin
        # guion bajo) para que RealtimeFilterWatcher/runner.py la lea igual
        # que candidatos_previos_a_grupo.
        self.zonas: dict[str, tuple[float, float]] = {}
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
            # Sin filtros estaticos que reinicien el pool desde _todos cada
            # ciclo, _aplicar_dinamicos venia filtrando sobre su propio
            # resultado del ciclo anterior (nunca sobre el universo completo)
            # -- un simbolo que un dia dejaba de cumplir el filtro dinamico
            # quedaba excluido para siempre, hasta converger a lista vacia y
            # quedarse ahi (confirmado en vivo: 'TEST POST MARKET', solo
            # CHANGE + GAP_FROM_CLOSE dinamicos, 3+ horas seguidas en 0).
            self._filtrados = list(self._todos)
            return
        remaining = []
        rejected_no_data = 0
        for sym in self._todos:
            fund = self._fundamentals.get(sym)
            if fund is None:
                rejected_no_data += 1
                continue
            resultados = [get_strategy(f).evaluate(_make_marketdata(sym, fund, None, None))
                          for f in self.pre_estaticos]
            if _todos_los_requeridos_pasan(self.pre_estaticos, resultados):
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
            self._filtrados = list(self._ultimo_filtrado)
            return
        if not prices:
            logger.warning("Dynamic filters: no price data, keeping previous filtered set")
            self._filtrados = list(self._ultimo_filtrado)
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
            resultados = [get_strategy(f).evaluate(data) for f in self.pre_dinamicos]
            if _todos_los_requeridos_pasan(self.pre_dinamicos, resultados):
                remaining.append(sym)
        self._filtrados = remaining
        self._ultimo_filtrado = list(remaining)
        logger.info("SymbolPipeline: dynamic filters %d -> %d symbols", len(prices), len(self._filtrados))

    def _excluir_ya_senializados_hoy(self):
        """Consulta al log-service los simbolos que ya tuvieron senal hoy para
        este escaner y los saca de _filtrados. Sin esto, el mismo simbolo
        genera senal en cada ciclo del dia -- el usuario quiere una sola senal
        por simbolo por dia por escaner. La lista se refresca en cada ciclo
        para cubrir simbolos que se senializaron en ciclos anteriores de hoy.

        Si el escaner tiene permitirMultiplesSenales=true, esta exclusion se
        salta por completo -- kafka_producer.publish_signals ya solo publica
        `nuevos` (ver runner.py/_publish_signals), asi que un simbolo que
        sigue calificando sin interrupcion no se re-publica cada ciclo; lo
        que si vuelve a pasar es que si deja de calificar y despues vuelve a
        calificar el mismo dia, esa segunda vez cuenta como nueva senal
        (via nuevos_symbols/_previously_matched)."""
        if not self._filtrados or self.permitir_multiples_senales:
            return
        try:
            self._signaled_today = self._log_client.get_signaled_today(self.scanner_id)
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
        self.candidatos_previos_a_grupo = {}
        # Resetear en cada ciclo, no solo en __init__: sin esto, la zona de
        # un simbolo que ya no tiene un Order Block vigente este ciclo
        # arrastraria la del ciclo anterior y se colaria como restriccion en
        # el primer grupo (que deberia evaluar sin ninguna zona todavia).
        self.zonas = {}

        # Ordenado de mayor a menor temporalidad: el encadenamiento de zona
        # exige que un grupo mas amplio (H4/H1) se evalue ANTES que uno mas
        # fino (M15, M1/M3) para que la zona le llegue -- el orden de
        # insercion de `grupos` (agrupar_por_timeframe) solo refleja como el
        # usuario agrego los filtros al escaner, no el tamano real de cada
        # temporalidad.
        for minutos, filtros in sorted(grupos.items(), key=lambda kv: -kv[0]):
            self.candidatos_previos_a_grupo[minutos] = set(candidates)
            if not candidates:
                break
            tf_label = minutos_to_label(minutos)
            # +1: la vela mas reciente que devuelve marketdata-service puede
            # seguir en formacion (candles_m5/m15 agregan en vivo sobre M1 sin
            # cerrar todavia) -- se pide una vela extra para poder descartarla
            # y evaluar siempre sobre velas ya cerradas, sin quedar corto de
            # historia real para el filtro mas exigente del grupo.
            bars_needed = bars_necesarias_grupo(filtros, minutos) + 1
            passing, stats = self._evaluar_grupo_tecnico(candidates, filtros, tf_label, bars_needed, matched, minutos)
            logger.info(
                "evaluar_tecnicos %s: %d symbols, %d/%d bars with a null OHLC field",
                tf_label, stats[0], stats[1], stats[2],
            )
            candidates = passing

        return {sym: matched[sym] for sym in candidates}

    def _evaluar_grupo_tecnico(
        self, candidates: set[str], filtros: list[Filtro], tf_label: str, bars_needed: int,
        matched: dict[str, list[SignalMatch]], minutos: int,
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

        # RangeConfluenceStrategy necesita H4/H1 ademas de la temporalidad
        # propia del grupo -- costo adicional que solo paga un escaner que
        # use ese filtro explicitamente (ver _fetch_velas_extra).
        velas_extra_por_simbolo: Dict[str, Dict[str, List[CandleResponse]]] = {}
        if any(f.enumFiltro == EnumFiltro.RANGE_CONFLUENCE_D1_H4_H1 for f in filtros):
            velas_extra_por_simbolo = self._fetch_velas_extra(batch)

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
        stale_symbols = 0

        # self.zonas se muta mas abajo sin lock a proposito: los workers de
        # este ThreadPoolExecutor solo hacen fetch_chunk (I/O puro, no tocan
        # self.zonas), toda la evaluacion de estrategias y la escritura de
        # zonas ocurre despues, secuencialmente, en este mismo hilo principal
        # dentro del `for future in done` de abajo -- no hay carrera real.
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
                        # marketdata-service agrega M5/M15 en vivo sobre M1
                        # sin cerrar todavia -- la ultima vela devuelta puede
                        # seguir formandose. Evaluar sobre eso produce señales
                        # que "repintan": el precio/hora que se registra deja
                        # de coincidir con la vela una vez que termina de
                        # cerrar (confirmado en vivo con SUGP: precio de una
                        # vela M5 a medio formar, que ya no calzaba con
                        # ninguna vela real del grafico media hora despues).
                        # Se descarta si su cierre (timestamp + minutos) es
                        # posterior a ahora -- bars_needed ya pidio una vela
                        # de mas para compensar.
                        #
                        # marketdata-service ahora tambien confirma, antes de
                        # entregar la ultima vela como "cerrada", que ya llego
                        # data mas nueva que su cierre (no le falta el ultimo
                        # minuto llegando tarde a la BD) -- el caso NMAX
                        # (precio de una vela a medio completar) se corrige
                        # ahi, en la fuente, en vez de adivinar un margen de
                        # tiempo fijo aca.
                        now_utc = datetime.now(timezone.utc)
                        if candles and candles[-1].timestamp + timedelta(minutes=minutos) > now_utc:
                            candles = candles[:-1]
                        total_bars += len(candles)
                        null_bars += sum(
                            1 for c in candles
                            if c.open is None or c.high is None or c.low is None or c.close is None
                        )
                        if not candles:
                            continue
                        candle_close_time = candles[-1].timestamp + timedelta(minutes=minutos)
                        if minutos >= 1440:
                            # D1+: el mercado no genera velas sabado/domingo
                            # (ni feriados), asi que "ahora - cierre de la
                            # ultima vela" supera 2x la temporalidad todos los
                            # lunes solo por el fin de semana -- confirmado en
                            # vivo: rechazaba el 100% de los candidatos de
                            # 'prueba daniel' (RANGE_EXTREME_PROXIMITY en D1)
                            # cada lunes, sin ningun dato realmente atrasado.
                            # Margen fijo que cubre un fin de semana largo mas
                            # un feriado adicional, en vez de la formula
                            # generica (pensada para temporalidades intradia
                            # que si deben refrescar dentro del mismo dia
                            # habil).
                            staleness_limit = timedelta(days=4)
                        else:
                            staleness_limit = timedelta(minutes=max(20, minutos * 2))
                        if now_utc - candle_close_time > staleness_limit:
                            stale_symbols += 1
                            continue
                        fund = self._fundamentals.get(sym)
                        data = _make_marketdata(sym, fund, candles, None, self.zonas.get(sym),
                                                 velas_extra_por_simbolo.get(sym))
                        # Instancias construidas una sola vez por simbolo (no
                        # un dict keyed por Filtro -- el modelo pydantic no es
                        # hashable): se reusan tanto para evaluar como para
                        # leer la zona despues, evitando reconstruir y
                        # re-escanear el Order Block por segunda vez.
                        pares = [(f, get_strategy(f)) for f in filtros]
                        resultados = [estrategia.evaluate(data) for _f, estrategia in pares]
                        sym_matches = [f for (f, _e), r in zip(pares, resultados) if r]
                        if _todos_los_requeridos_pasan(filtros, resultados):
                            vela_timestamp = candles[-1].timestamp
                            precio = candles[-1].close
                            matched[sym].extend(
                                SignalMatch(filtro=f, vela_timestamp=vela_timestamp, precio=precio)
                                for f in sym_matches
                            )
                            passing.add(sym)
                            # Si algun filtro de este grupo produjo una zona
                            # (Order Block, Range Extreme Proximity), queda
                            # disponible para los grupos siguientes (mas
                            # finos) via self.zonas -- ver evaluar_tecnicos.
                            for _f, estrategia in pares:
                                zona = getattr(estrategia, "ultima_zona", None)
                                if zona is not None:
                                    self.zonas[sym] = zona

        if stale_symbols > 0:
            logger.warning(
                "evaluar_tecnicos %s: %d/%d symbols descartados por vela stale (limite %s)",
                tf_label, stale_symbols, symbols_with_data, staleness_limit,
            )

        return passing, (symbols_with_data, null_bars, total_bars)

    def _fetch_velas_extra(self, symbols: list[str]) -> Dict[str, Dict[str, List[CandleResponse]]]:
        """Velas de H4 y H1 para RangeConfluenceStrategy, ademas de la
        temporalidad propia del grupo (D1) -- el unico filtro de la
        plataforma que necesita mas de una temporalidad a la vez. Secuencial
        y con un `bars` chico a proposito: no vale la pena la maquinaria de
        streaming/concurrencia de _evaluar_grupo_tecnico (pensada para
        cientos de barras sobre miles de simbolos) para un puñado de barras
        que solo paga el escaner que use este filtro."""
        resultado: Dict[str, Dict[str, List[CandleResponse]]] = {}
        chunks = [symbols[i:i + _CANDLE_CHUNK_SIZE] for i in range(0, len(symbols), _CANDLE_CHUNK_SIZE)]
        for tf_label in _TIMEFRAMES_CONFLUENCIA_EXTRA:
            for chunk in chunks:
                try:
                    candles_map = self._client.fetch_candles(chunk, tf_label, bars=_BARS_CONFLUENCIA_EXTRA)
                except Exception as e:
                    logger.error("Failed to fetch extra timeframe %s for confluence: %s", tf_label, e)
                    continue
                for sym, candles in candles_map.items():
                    resultado.setdefault(sym, {})[tf_label] = candles
        return resultado

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
