import functools
import logging
import threading
from typing import Callable

from app.models.escaner import Escaner
from app.models.filtro import Filtro
from app.models.signal_match import SignalMatch
from app.scanner.buffered_candle import BufferedCandle, candle_from_bar
from app.scanner.candle_columns import CandleColumns
from app.scanner.realtime_candle_client import RealtimeCandleClient
from app.scanner.session_state import ProfileLoader, SessionState
from app.scanner.timeframe import bars_buffer_grupo, bars_historial_grupo, minutos_to_label
from app.strategies.base import MarketData
from app.strategies.registry import get_strategy

logger = logging.getLogger(__name__)

_FALLBACK_BARS = 200
_MAX_REQUESTED_BARS = 2000


def _locked(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


def _todos_los_requeridos_pasan(filtros: list[Filtro], resultados: list[bool]) -> bool:
    """Copia de app.scanner.symbols._todos_los_requeridos_pasan -- mismo
    criterio de grupoAlternativo, pero este modulo no puede importar symbols
    (dependencia circular: symbols ya no conoce este archivo, y no hace
    falta que lo haga)."""
    alternativos: dict[int, list[int]] = {}
    for i, f in enumerate(filtros):
        if f.grupoAlternativo is None:
            if not resultados[i]:
                return False
        else:
            alternativos.setdefault(f.grupoAlternativo, []).append(i)
    return all(any(resultados[i] for i in indices) for indices in alternativos.values())


class RealtimeFilterWatcher:
    """Motor unico de evaluacion de filtros tecnicos -- reemplaza el ciclo
    batch (que pedia velas por REST cada ~60-90s) para CUALQUIER escaner con
    al menos un filtro tecnico, ya no solo los marcados revisionTiempoReal
    (retirado, ver frontend/scanner-management-service). Encadena grupos de
    mayor a menor temporalidad (D1 -> H1 -> M1) igual que
    SymbolPipeline.evaluar_tecnicos, pero por eventos: cada simbolo avanza de
    grupo en grupo a medida que van cerrando sus propias velas, en vez de
    recalcularse todo junto en una pasada sincronica.

    Estado por simbolo (todo se resetea via actualizar_universo cuando los
    pre-filtros lo excluyen):
    - `_stage[symbol]`: indice (en `_grupos`, ordenado grueso->fino) del
      PROXIMO grupo que este simbolo necesita pasar. Un simbolo sigue
      suscripto a su propio timeframe Y a los de todos los grupos mas
      gruesos que ya paso (ver _resuscribir) -- asi una vela mas gruesa que
      vuelve a cerrar (ej. D1 al dia siguiente) puede re-validarlo o
      degradarlo, igual que el batch recalculaba candidatos_previos_a_grupo
      desde cero en cada ciclo.
    - `_group_matches[symbol][i]`: matches que produjo el grupo `i` la
      ULTIMA vez que el simbolo lo paso -- se descartan los indices >= al
      grupo que acaba de fallar (ver _on_bar) para no arrastrar matches
      viejos de un grupo mas fino que ya no es valido.
    - `_zonas[symbol]`: misma idea que SymbolPipeline.zonas, pero mantenida
      por este watcher en vez de por una pasada batch.
    - `_signaling`: simbolos que YA completaron la cadena entera y siguen
      calificando sin interrupcion -- evita republicar en cada vela fina que
      sigue pasando (mismo espiritu que nuevos_symbols/_previously_matched
      del camino batch, pero por simbolo en vez de por set completo).
    """

    def __init__(self, escaner: Escaner, ws_url: str,
                 publish_signal: Callable[[Escaner, str, list[SignalMatch]], None],
                 client_factory=RealtimeCandleClient, profile_loader: ProfileLoader | None = None):
        self._escaner = escaner
        self._publish_signal = publish_signal
        self._grupos: list[tuple[int, str, list[Filtro]]] = []
        self._candles: dict[tuple[str, str], CandleColumns] = {}
        self._zonas: dict[str, tuple[float, float]] = {}
        self._group_matches: dict[str, dict[int, list[SignalMatch]]] = {}
        self._stage: dict[str, int] = {}
        self._signaling: set[str] = set()
        self._capped_timeframes: set[str] = set()
        self._keys_por_symbol: dict[str, set[tuple[str, str]]] = {}
        self._pares_por_grupo: dict[int, list] = {}
        self._lock = threading.RLock()
        self._state = SessionState(profile_loader)
        self._client = client_factory(ws_url, self._on_history, self._on_bar, self._bars_for)

    def configurar_grupos(self, grupos: dict[int, list[Filtro]]) -> None:
        """Se llama una sola vez al arrancar el escaner -- los filtros
        tecnicos de un escaner no cambian en caliente (editar filtros exige
        parar/reiniciar el escaner, ver scanner-management-service)."""
        self._grupos = [
            (minutos, minutos_to_label(minutos), filtros)
            for minutos, filtros in sorted(grupos.items(), key=lambda kv: -kv[0])
        ]
        self._state.configurar(self._grupos)
        self._pares_por_grupo = {}

    @_locked
    def actualizar_universo(self, filtrados: set[str]) -> None:
        """Se llama tras cada refresco de pre-filtros (aplicar_pre_filtros):
        agrega simbolos nuevos al primer grupo (el mas grueso), y resetea
        por completo cualquier simbolo que los pre-filtros ya no admiten --
        no tiene sentido seguir gastando una suscripcion en un simbolo que
        ni siquiera paso el precio/volumen/fundamentales."""
        actuales = set(self._stage)
        for symbol in actuales - filtrados:
            self._resetear_symbol(symbol)
        for symbol in filtrados - actuales:
            self._stage[symbol] = 0
        self._resuscribir()
        self._state.cargar_perfiles(filtrados)

    def stop(self) -> None:
        self._client.stop()

    def _resetear_symbol(self, symbol: str) -> None:
        self._stage.pop(symbol, None)
        self._group_matches.pop(symbol, None)
        self._zonas.pop(symbol, None)
        self._signaling.discard(symbol)

    def _keys_de(self, symbol: str) -> set[tuple[str, str]]:
        # Suscripto a su propio grupo (stage) Y a todos los mas gruesos que
        # ya paso (0..stage-1) -- estos ultimos siguen vigilados para poder
        # degradar al simbolo si una vela gruesa que vuelve a cerrar deja de
        # calificar.
        stage = self._stage.get(symbol)
        if stage is None:
            return set()
        return {(symbol, self._grupos[i][1]) for i in range(min(stage, len(self._grupos) - 1) + 1)}

    def _resuscribir(self) -> None:
        self._keys_por_symbol = {symbol: self._keys_de(symbol) for symbol in self._stage}
        keys: set[tuple[str, str]] = set().union(*self._keys_por_symbol.values())
        self._client.update_subscriptions(keys)
        for key in [k for k in self._candles if k not in keys]:
            del self._candles[key]
        self._state.podar(keys)

    def _resuscribir_symbol(self, symbol: str) -> None:
        nuevas = self._keys_de(symbol)
        actuales = self._keys_por_symbol.get(symbol, set())
        agregar, quitar = nuevas - actuales, actuales - nuevas
        self._keys_por_symbol[symbol] = nuevas
        if not agregar and not quitar:
            return
        self._client.change_subscriptions(agregar, quitar)
        for key in quitar:
            self._candles.pop(key, None)
        self._state.olvidar(quitar)

    def _bars_for(self, timeframe: str) -> int:
        j = self._indice_grupo(timeframe)
        if j is None:
            return _FALLBACK_BARS
        minutos, label, filtros = self._grupos[j]
        needed = bars_historial_grupo(filtros, minutos) + 1
        if needed > _MAX_REQUESTED_BARS and label not in self._capped_timeframes:
            self._capped_timeframes.add(label)
            logger.warning("RealtimeFilterWatcher: escaner=%d %s necesita %d barras, se acota a %d",
                           self._escaner.idEscaner, label, needed, _MAX_REQUESTED_BARS)
        return min(needed, _MAX_REQUESTED_BARS)

    def _buffer_for(self, timeframe: str) -> int:
        j = self._indice_grupo(timeframe)
        if j is None:
            return _FALLBACK_BARS
        minutos, _, filtros = self._grupos[j]
        return min(bars_buffer_grupo(filtros, minutos) + 1, _MAX_REQUESTED_BARS)

    def buffer_stats(self) -> tuple[int, int]:
        buffers = list(self._candles.values())
        return len(buffers), sum(len(b) for b in buffers)

    @_locked
    def _on_history(self, symbol: str, timeframe: str, bars: list[dict]) -> None:
        closed = [b for b in bars if b.get("closed")][-self._bars_for(timeframe):]
        candles = [candle_from_bar(symbol, b) for b in closed]
        self._state.sembrar(symbol, timeframe, candles)
        self._candles[(symbol, timeframe)] = CandleColumns(symbol, candles[-self._buffer_for(timeframe):])

    def _indice_grupo(self, tf_label: str) -> int | None:
        for i, (_, label, _) in enumerate(self._grupos):
            if label == tf_label:
                return i
        return None

    @_locked
    def _on_bar(self, symbol: str, timeframe: str, bar: dict) -> None:
        # /ws/candles manda un mensaje por CADA tick de la vela en formacion
        # (closed=false) y recien uno solo, al cerrar el periodo real,
        # closed=true (ver forwardLive en candle_ws_session.go). Sin este
        # filtro se evaluaba (y se podia promover/degradar/publicar) en cada
        # tick parcial en vez de una sola vez por vela realmente cerrada --
        # mismo criterio que _on_history ya aplicaba al sembrar el historial
        # inicial (filtra por "closed" ahi tambien).
        if not bar.get("closed"):
            return
        if bar.get("corrected"):
            self._aplicar_correccion(symbol, timeframe, bar)
            return

        key = (symbol, timeframe)
        candles = self._candles.setdefault(key, CandleColumns(symbol))
        candle = candle_from_bar(symbol, bar)
        self._state.actualizar(symbol, timeframe, candle)
        candles.append(candle)
        candles.trim(self._buffer_for(timeframe))
        self._evaluar(symbol, timeframe, candles.materialize())

    def _pares_de(self, j: int, filtros: list[Filtro]) -> list:
        pares = self._pares_por_grupo.get(j)
        if pares is None:
            pares = self._pares_por_grupo[j] = [(f, get_strategy(f)) for f in filtros]
        return pares

    def _evaluar(self, symbol: str, timeframe: str, candles: list[BufferedCandle]) -> None:
        j = self._indice_grupo(timeframe)
        if j is None:
            return
        stage = self._stage.get(symbol)
        # stage=None: los pre-filtros ya no admiten este simbolo (o nunca lo
        # admitieron) -- pudo quedar un evento en vuelo justo cuando se
        # desuscribio, se descarta. j > stage: todavia no le toca (no paso
        # los grupos mas gruesos), _resuscribir no deberia haberlo
        # suscripto a esto, pero se descarta por las dudas.
        if stage is None or j > stage:
            return

        _, _, filtros = self._grupos[j]
        data = MarketData(symbol=symbol, candles=candles, zona=self._zonas.get(symbol),
                          day=self._state.day(symbol, timeframe),
                          volume_profile=self._state.profile(symbol, timeframe))
        pares = self._pares_de(j, filtros)
        for _f, estrategia in pares:
            if hasattr(estrategia, "ultima_zona"):
                estrategia.ultima_zona = None
        resultados = [estrategia.evaluate(data) for _f, estrategia in pares]
        paso = _todos_los_requeridos_pasan(filtros, resultados)

        if not paso:
            self._degradar(symbol, j)
            return

        matches = [
            SignalMatch(filtro=f, vela_timestamp=candles[-1].timestamp, precio=candles[-1].close)
            for (f, _e), r in zip(pares, resultados) if r
        ]
        self._group_matches.setdefault(symbol, {})[j] = matches
        for _f, estrategia in pares:
            zona = getattr(estrategia, "ultima_zona", None)
            if zona is not None:
                self._zonas[symbol] = zona

        if j == len(self._grupos) - 1:
            self._completar_cadena(symbol)
            return
        if j == stage:
            self._stage[symbol] = j + 1
            self._resuscribir_symbol(symbol)

    def _aplicar_correccion(self, symbol: str, timeframe: str, bar: dict) -> None:
        """marketdata reenvia una vela ya cerrada con datos corregidos (un tick
        tardio de dxFeed): se reemplaza la que ya estaba en el buffer, con el
        mismo timestamp, y se ajusta el resumen del dia. Solo si es la ULTIMA
        vela del buffer se reevalua el grupo, igual que con una vela nueva
        (puede promover al simbolo, o publicar una señal que la vela sin
        corregir no alcanzo): una señal ya publicada nunca se retira ni se
        revierte, es un hecho del historial, y _completar_cadena no repite la
        de un simbolo que ya estaba calificando."""
        candles = self._candles.get((symbol, timeframe))
        if not candles:
            return
        corregida = candle_from_bar(symbol, bar)
        i = candles.index_of(corregida.timestamp)
        if i is None:
            return
        anterior = candles.replace(i, corregida)
        self._state.corregir(symbol, timeframe, anterior, corregida)
        if i == len(candles) - 1:
            self._evaluar(symbol, timeframe, candles.materialize())

    def _degradar(self, symbol: str, grupo_index: int) -> None:
        """El simbolo dejo de calificar en el grupo `grupo_index` -- vuelve
        a quedar a la espera de que ESE grupo cierre otra vela y lo
        re-evalue (no se lo saca del universo, eso solo lo decide
        actualizar_universo segun los pre-filtros). Se descartan los
        matches/zona de este grupo en adelante: son de una cadena que ya no
        es valida."""
        self._stage[symbol] = grupo_index
        matches_por_grupo = self._group_matches.get(symbol)
        if matches_por_grupo:
            for i in [i for i in matches_por_grupo if i >= grupo_index]:
                del matches_por_grupo[i]
        self._zonas.pop(symbol, None)
        self._signaling.discard(symbol)
        self._resuscribir_symbol(symbol)

    def _completar_cadena(self, symbol: str) -> None:
        """El simbolo paso TODOS los grupos, del mas grueso al mas fino --
        misma señal completa que evaluar_tecnicos arma en una sola pasada,
        aca ensamblada a partir de lo que cada grupo fue confirmando por su
        cuenta. Solo se publica en la transicion de "no calificaba" a
        "califica" -- si ya estaba calificando sin interrupcion, no se
        repite la señal cada vez que la vela mas fina vuelve a cerrar
        (mismo espiritu que nuevos_symbols del camino batch)."""
        if symbol in self._signaling:
            return
        self._signaling.add(symbol)
        matches_por_grupo = self._group_matches.get(symbol, {})
        matches = [m for i in sorted(matches_por_grupo) for m in matches_por_grupo[i]]
        logger.info("RealtimeFilterWatcher: cadena completa symbol=%s escaner=%d filtros=%s",
                    symbol, self._escaner.idEscaner, [m.filtro.enumFiltro.name for m in matches])
        self._publish_signal(self._escaner, symbol, matches)
