"""Servicio para optimizar la obtencion de datos y el manejo de reintentos."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from domain.usecases.validador_barras import validar_barras, INTERVALO_POR_TIMEFRAME
from domain.models.escaner import Escaner
from application.output.comunicacion_externa_int_port import ComunicacionExternaIntPort
from config import VALIDACION_MAX_REINTENTOS

logger = logging.getLogger(__name__)

class DataFetchService:
    """Clase para abstraer el fetch con/sin cache de datos historicos y reintentos."""

    def __init__(self, obj_comunicacion_externa: ComunicacionExternaIntPort, obj_candle_cache=None, notification_service=None):
        self.comunicacion = obj_comunicacion_externa
        self.cache = obj_candle_cache
        self.notification_service = notification_service

    def fetch_con_cache(self, escaner: Escaner, simbolos: list[str], timeframes_necesarios: dict) -> dict:
        """Fetch de barras con cache incremental. Retorna dict {(symbol, tf): [Candle, ...]}. """
        cache_candles = {}

        if not self.cache:
            # Sin cache: fetch completo siempre
            return self._fetch_completo(simbolos, timeframes_necesarios)

        def _fetch_timeframe(tf, cantidad_velas):
            resultado_tf = {}
            simbolos_completo = []
            simbolos_incremental = []

            for simbolo in simbolos:
                if self.cache.necesita_fetch_completo(escaner.id_escaner, simbolo, tf):
                    simbolos_completo.append(simbolo)
                else:
                    simbolos_incremental.append(simbolo)

            logger.info(f"Cache tf={tf}: {len(simbolos_completo)} fetch completo, {len(simbolos_incremental)} incremental")

            if simbolos_completo:
                resultado = self._fetch_batch_con_reintentos(simbolos_completo, tf, cantidad_velas)
                for symbol, candles in resultado.items():
                    self.cache.actualizar(escaner.id_escaner, symbol, tf, candles)
                    resultado_tf[(symbol, tf)] = self.cache.obtener(escaner.id_escaner, symbol, tf) or candles

            if simbolos_incremental:
                barras_nuevas = self.cache.barras_faltantes(escaner.id_escaner, simbolos_incremental[0], tf)
                if barras_nuevas <= 0:
                    barras_nuevas = 2

                logger.info(f"Fetch incremental tf={tf}: {barras_nuevas} barras nuevas para {len(simbolos_incremental)} simbolos")

                resultado = self._fetch_batch_con_reintentos(simbolos_incremental, tf, barras_nuevas)
                for symbol, candles in resultado.items():
                    anadidas = self.cache.actualizar(escaner.id_escaner, symbol, tf, candles)
                    self.cache.recortar(escaner.id_escaner, symbol, tf, cantidad_velas + 50)
                    if anadidas > 0:
                        logger.debug(f"Cache {symbol} tf={tf}: +{anadidas} barras nuevas")

                for symbol in simbolos_incremental:
                    cached = self.cache.obtener(escaner.id_escaner, symbol, tf)
                    if cached:
                        resultado_tf[(symbol, tf)] = cached

            return resultado_tf

        n_workers = min(len(timeframes_necesarios), 4)
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            futures = {
                executor.submit(_fetch_timeframe, tf, qty): tf
                for tf, qty in timeframes_necesarios.items()
            }
            for future in as_completed(futures):
                tf = futures[future]
                try:
                    cache_candles.update(future.result())
                except Exception as e:
                    logger.error(f"Error en fetch paralelo tf={tf}: {e}")

        return cache_candles

    def _fetch_completo(self, simbolos: list[str], timeframes_necesarios: dict) -> dict:
        """Fetch completo sin cache (comportamiento original)."""
        cache_candles = {}
        BATCH_SIZE = 200

        for tf, cantidad_velas in timeframes_necesarios.items():
            for i in range(0, len(simbolos), BATCH_SIZE):
                batch_symbols = simbolos[i:i + BATCH_SIZE]
                try:
                    resultado_batch = self.comunicacion.obtener_candles_historicos_batch(
                        symbols=batch_symbols, timeframe=tf, bars=cantidad_velas
                    )
                    for symbol, candles in resultado_batch.items():
                        cache_candles[(symbol, tf)] = candles
                except Exception as e:
                    logger.error(f"Error en batch fetch tf={tf}: {e}")

        return cache_candles

    def _fetch_batch_con_reintentos(self, simbolos: list[str], timeframe: str, bars: int) -> dict:
        """Fetch batch con reintentos y validacion de barras."""
        BATCH_SIZE = 200
        resultado_total = {}

        for i in range(0, len(simbolos), BATCH_SIZE):
            batch_symbols = simbolos[i:i + BATCH_SIZE]

            for intento in range(VALIDACION_MAX_REINTENTOS):
                try:
                    resultado_batch = self.comunicacion.obtener_candles_historicos_batch(
                        symbols=batch_symbols, timeframe=timeframe, bars=bars
                    )

                    # Validar una muestra
                    muestra_valida = True
                    for sym, candles in resultado_batch.items():
                        resultado_val = validar_barras(candles, timeframe)
                        if not resultado_val.valido:
                            logger.warning(
                                f"Validacion fallida intento {intento + 1}/{VALIDACION_MAX_REINTENTOS} "
                                f"para {sym} tf={timeframe}: {resultado_val.razon}"
                            )
                            muestra_valida = False
                            break

                    if muestra_valida or intento == VALIDACION_MAX_REINTENTOS - 1:
                        resultado_total.update(resultado_batch)
                        if not muestra_valida:
                            logger.error(
                                f"Barras no confiables despues de {VALIDACION_MAX_REINTENTOS} "
                                f"reintentos para tf={timeframe}. Usando datos disponibles."
                            )
                            if self.notification_service:
                                self.notification_service.publicar_log_validacion_fallida_batch(
                                    timeframe, len(batch_symbols), VALIDACION_MAX_REINTENTOS
                                )
                        break

                    espera = self._calcular_espera_reintento(timeframe)
                    logger.info(f"Reintentando fetch en {espera:.1f}s...")
                    time.sleep(espera)

                except Exception as e:
                    logger.error(f"Error en batch fetch tf={timeframe} intento {intento + 1}: {e}")
                    if intento < VALIDACION_MAX_REINTENTOS - 1:
                        espera = self._calcular_espera_reintento(timeframe)
                        time.sleep(espera)

        return resultado_total

    def _calcular_espera_reintento(self, timeframe: str) -> float:
        """Calcula cuantos segundos esperar antes de reintentar la obtencion de barras.

        Logica:
        - Calcula cuando cierra la barra que se espera (cierre = inicio_barra_actual).
        - Si ya paso el cierre (falta <= 0): el proveedor aun no publico la barra -> esperar 1 seg.
        - Si falta tiempo para el cierre (falta > 0): esperar hasta el cierre + 1 seg.
        """
        if timeframe in ("D1", "W1", "MO1"):
            return 1.0

        intervalo = INTERVALO_POR_TIMEFRAME.get(timeframe)
        if intervalo is None:
            return 1.0

        ahora = datetime.now(timezone.utc)
        epoch_seg = ahora.timestamp()
        seg_en_barra = epoch_seg % intervalo
        # El cierre de la ultima barra = inicio de la barra actual
        ts_cierre_ultima = ahora - timedelta(seconds=seg_en_barra)
        falta = (ts_cierre_ultima - ahora).total_seconds()  # siempre <= 0 si ya paso

        if falta <= 0:
            # Cierre ya paso, el proveedor deberia tener la barra — esperar 1 seg
            return 1.0
        else:
            # Barra aun no ha cerrado — esperar hasta el cierre + 1 seg
            return falta + 1.0
