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
            # Si el watchlist esta vacio, dormir mas tiempo para ahorrar CPU
            with self._lock:
                empty = len(self._watchlist) == 0

            if empty:
                time.sleep(5)
                continue

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
            # Obtener TODOS los timeframes requeridos (Event + State)
            # Para asegurar que detectamos cierre de velas en timeframes de estado
            esc = entry["escaner"]
            timeframes_necesarios = self.obj_procesar_senales.obj_filtro_executor.obtener_timeframes_necesarios(esc.filtros)
            
            for tf in timeframes_necesarios.keys():
                key = (symbol, tf)
                if key not in symbols_timeframes:
                    symbols_timeframes[key] = None

        # Fetch batch de baras en formacion para TODOS los timeframes monitoreados
        barras = self._fetch_barras_batch(list(symbols_timeframes.keys()))

        # Validar barras y detectar cambios (cierres)
        barras_validadas = {}
        cambio_de_barra = set()
        for key, barra in barras.items():
            if barra is None:
                continue
            prev_ts = self._last_bar_timestamps.get(key)
            curr_ts = barra.timestamp
            if prev_ts and curr_ts != prev_ts:
                cambio_de_barra.add(key)
                logger.info(f"Cambio de barra detectado para {key}: {prev_ts} -> {curr_ts}")
            self._last_bar_timestamps[key] = curr_ts
            barras_validadas[key] = barra

        # Actualizar cache y re-evaluar estado si hubo cierre
        if cambio_de_barra:
            self._manejar_cambio_de_barra(cambio_de_barra)

        # Evaluar eventos con la informacion mas reciente
        with self._lock:
            # Re-leer items porque _manejar_cambio_de_barra pudo haber removido entradas
            current_items = list(self._watchlist.items())

        for (esc_id, symbol), entry in current_items:
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
        Solicita ULTIMA barra cerrada y actualiza cache.
        Ademas, RE-EVALUA filtros de estado. Si fallan, remueve del watchlist.
        """
        tf_to_symbols = {}
        for (sym, tf) in cambio_de_barra:
            if tf not in tf_to_symbols:
                tf_to_symbols[tf] = set()
            tf_to_symbols[tf].add(sym)

        to_remove = set()

        with self._lock:
            for tf, symbols in tf_to_symbols.items():
                list_symbols = list(symbols)
                logger.debug(f"Refresh batch LAST tf={tf}: {len(list_symbols)} symbols")
                try:
                    nuevas_data = self.obj_procesar_senales.obj_comunicacion_externa.obtener_ultima_barra_completa_batch(
                        symbols=list_symbols,
                        timeframe=tf
                    )
                    
                    for (esc_id, symbol), entry in self._watchlist.items():
                        # Actualizar cache si corresponde
                        if symbol in nuevas_data and tf in entry["candles_cache"]:
                            nueva_vela = nuevas_data[symbol]
                            cache = entry["candles_cache"][tf]
                            
                            updated = False
                            if not cache or nueva_vela.timestamp != cache[-1].timestamp:
                                cache.append(nueva_vela)
                                if len(cache) > 500:
                                    entry["candles_cache"][tf] = cache[-500:]
                                updated = True
                                logger.debug(f"Cache actualizado para {symbol} tf={tf}")

                            # Si se actualizo el cache de un timeframe usado por filtros de estado, re-evaluar
                            if updated:
                                sigue_valido = self.obj_procesar_senales.re_evaluar_fase1(
                                    escaner=entry["escaner"],
                                    simbolo=symbol,
                                    candles_cache=entry["candles_cache"],
                                    datos_fundamentales=entry["datos_fundamentales"]
                                )
                                if not sigue_valido:
                                    logger.info(f"Removiendo {symbol} de watchlist por fallo en re-evaluacion estado")
                                    to_remove.add((esc_id, symbol))

                except Exception as e:
                    logger.error(f"Error refreshing batch last candles for tf={tf}: {e}")

            # Remover los que fallaron la re-evaluacion
            if to_remove:
                for key_rem in to_remove:
                    self._watchlist.pop(key_rem, None)
                    logger.info(f"Removido de watchlist: {key_rem}")

    def _fetch_barras_batch(self, symbols_timeframes):
        """Obtiene barras en formacion usando los nuevos endpoints de BATCH, agrupando por timeframe."""
        comunicacion = self.obj_procesar_senales.obj_comunicacion_externa
        results = {}
        
        # Agrupar simbolos por timeframe
        tf_groups = {}
        for (sym, tf) in symbols_timeframes:
            if tf not in tf_groups:
                tf_groups[tf] = []
            tf_groups[tf].append(sym)

        # Consultar cada grupo en batch
        for tf, symbols in tf_groups.items():
            try:
                # Cada llamada a obtener_barra_en_formacion_batch ya es un POST batch
                batch_res = comunicacion.obtener_barra_en_formacion_batch(symbols, tf)
                for sym, candle in batch_res.items():
                    results[(sym, tf)] = candle
            except Exception as e:
                logger.error(f"Error en _fetch_barras_batch para tf={tf}: {e}")
        
        return results

    def detener(self):
        self._running = False
        logger.info("EventLoopScheduler detenido")
