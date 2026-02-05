"""Loop de tiempo real para filtros de evento (0.1s)."""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from config import EVENT_POLLING_INTERVAL_SECONDS, MAX_SYMBOLS_REALTIME

logger = logging.getLogger(__name__)


class EventLoopScheduler(threading.Thread):
    """Thread daemon que evalua filtros de evento cada 0.1s usando la barra en formacion."""

    def __init__(self, obj_procesar_senales, interval=None):
        super().__init__(daemon=True, name="EventLoopScheduler")
        self.obj_procesar_senales = obj_procesar_senales
        self.interval = interval or EVENT_POLLING_INTERVAL_SECONDS
        self._running = False
        self._watchlist = {}
        self._lock = threading.Lock()
        self._last_bar_timestamps = {}

    def actualizar_watchlist(
        self, escaner_id, symbol, escaner, event_filters, candles_cache, datos_fundamentales=None
    ):
        """Registra un simbolo para monitoreo en tiempo real."""
        with self._lock:
            if len(self._watchlist) >= MAX_SYMBOLS_REALTIME:
                logger.warning(
                    f"Watchlist llena ({MAX_SYMBOLS_REALTIME}), "
                    f"no se puede agregar {symbol} para escaner {escaner_id}"
                )
                return
            self._watchlist[(escaner_id, symbol)] = {
                "escaner": escaner,
                "event_filters": event_filters,
                "candles_cache": candles_cache,
                "datos_fundamentales": datos_fundamentales,
            }

    def remover_de_watchlist(self, escaner_id, symbol=None):
        """Remueve un simbolo o todos los simbolos de un escaner del watchlist."""
        with self._lock:
            if symbol:
                self._watchlist.pop((escaner_id, symbol), None)
            else:
                keys = [k for k in self._watchlist if k[0] == escaner_id]
                for k in keys:
                    del self._watchlist[k]

    def run(self):
        self._running = True
        logger.info(
            f"EventLoopScheduler iniciado (intervalo={self.interval}s, "
            f"max_simbolos={MAX_SYMBOLS_REALTIME})"
        )
        while self._running:
            start = time.monotonic()
            try:
                self._tick()
            except Exception as e:
                logger.error(f"Error en event loop tick: {e}")
            elapsed = time.monotonic() - start
            sleep_time = max(0, self.interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _tick(self):
        with self._lock:
            items = list(self._watchlist.items())

        if not items:
            return

        symbols_timeframes = {}
        for (esc_id, symbol), entry in items:
            for filtro in entry["event_filters"]:
                impl = self.obj_procesar_senales.obj_filtro_executor.obj_filtro_registry.obtener_filtro(
                    filtro.enum_filtro
                )
                if impl:
                    tf = impl.get_timeframe_requerido(filtro)
                    key = (symbol, tf)
                    if key not in symbols_timeframes:
                        symbols_timeframes[key] = None

        barras = self._fetch_barras_batch(list(symbols_timeframes.keys()))

        # Validar barras: detectar si hubo cambio de barra (nueva vela cerrada)
        # y descartar barras duplicadas/viejas
        barras_validadas = {}
        cambio_de_barra = set()
        for key, barra in barras.items():
            if barra is None:
                continue
            prev_ts = self._last_bar_timestamps.get(key)
            curr_ts = barra.timestamp
            if prev_ts and curr_ts != prev_ts:
                # El timestamp cambio: nueva barra, la anterior se cerro
                cambio_de_barra.add(key)
                logger.info(f"Cambio de barra detectado para {key}: {prev_ts} -> {curr_ts}")
            self._last_bar_timestamps[key] = curr_ts
            barras_validadas[key] = barra

        # Si hubo cambio de barra, actualizar candles_cache con la barra cerrada
        if cambio_de_barra:
            self._manejar_cambio_de_barra(cambio_de_barra)

        for (esc_id, symbol), entry in items:
            self.obj_procesar_senales.evaluar_evento(
                escaner=entry["escaner"],
                symbol=symbol,
                event_filters=entry["event_filters"],
                candles_cache=entry["candles_cache"],
                datos_fundamentales=entry["datos_fundamentales"],
                barras_en_formacion=barras_validadas,
            )

    def _manejar_cambio_de_barra(self, cambio_de_barra):
        """
        Cuando se detecta cambio de barra, solicita nuevas candles historicas
        para actualizar el cache, asegurando que los filtros de evento trabajen
        con datos frescos.
        """
        symbols_to_refresh = set()
        for (sym, tf) in cambio_de_barra:
            symbols_to_refresh.add(sym)

        with self._lock:
            for (esc_id, symbol), entry in self._watchlist.items():
                if symbol not in symbols_to_refresh:
                    continue
                # Recalcular candles desde el use case
                todos_filtros = entry["event_filters"]
                timeframes_necesarios = (
                    self.obj_procesar_senales.obj_filtro_executor
                    .obtener_timeframes_necesarios(todos_filtros)
                )
                for tf, cantidad in timeframes_necesarios.items():
                    nuevas_candles = self.obj_procesar_senales._obtener_candles(
                        symbol, tf, cantidad
                    )
                    if nuevas_candles:
                        entry["candles_cache"][tf] = nuevas_candles
                        logger.debug(
                            f"Cache actualizado para {symbol} tf={tf}: "
                            f"{len(nuevas_candles)} candles"
                        )

    def _fetch_barras_batch(self, symbols_timeframes):
        """Obtiene barras en formacion en paralelo. Retorna dict de (symbol, tf) -> Candle."""
        comunicacion = self.obj_procesar_senales.obj_comunicacion_externa
        results = {}
        max_workers = min(10, len(symbols_timeframes))
        if max_workers == 0:
            return results

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(comunicacion.obtener_barra_en_formacion, sym, tf): (sym, tf)
                for sym, tf in symbols_timeframes
            }
            for future in futures:
                key = futures[future]
                try:
                    result = future.result(timeout=2)
                    if result:
                        results[key] = result
                except Exception:
                    pass
        return results

    def detener(self):
        self._running = False
        logger.info("EventLoopScheduler detenido")
