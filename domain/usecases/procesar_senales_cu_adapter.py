"""Caso de uso: procesar senales de escaneres."""

import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from application.input.procesar_senales_cu_int_port import ProcesarSenalesCUIntPort
from application.output.comunicacion_externa_int_port import ComunicacionExternaIntPort
from application.output.kafka_producer_int_port import KafkaProducerIntPort
from domain.models.escaner import Escaner
from domain.models.senal import Senal
from domain.usecases.validador_barras import validar_barras
from config import (
    MAX_WORKERS_SIMBOLOS,
    SIGNAL_COOLDOWN_SECONDS,
    VALIDACION_MAX_REINTENTOS,
    VALIDACION_PAUSA_REINTENTO_SEGUNDOS,
)

logger = logging.getLogger(__name__)

MINUTOS_POR_VELA = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30,
    "H1": 60, "D1": 1440, "W1": 10080, "MO1": 43200,
}


class ProcesarSenalesCUAdapter(ProcesarSenalesCUIntPort):

    def __init__(
        self,
        obj_comunicacion_externa: ComunicacionExternaIntPort,
        obj_filtro_executor,
        obj_kafka_producer: KafkaProducerIntPort = None,
        obj_candle_cache=None,
    ):
        logger.info("Inicializando ProcesarSenalesCUAdapter...")
        self.obj_comunicacion_externa = obj_comunicacion_externa
        self.obj_filtro_executor = obj_filtro_executor
        self.obj_kafka_producer = obj_kafka_producer
        self.obj_candle_cache = obj_candle_cache
        self.obj_scheduler = None
        self.obj_event_loop = None
        self._senales_emitidas = {}
        self._feriado_notificado = {}  # {escaner_id: date} - evita spam de logs en feriados
        logger.info(f"  -> MAX_WORKERS_SIMBOLOS: {MAX_WORKERS_SIMBOLOS}")
        logger.info(f"  -> SIGNAL_COOLDOWN_SECONDS: {SIGNAL_COOLDOWN_SECONDS}")
        logger.info(f"  -> Kafka producer: {'SI' if obj_kafka_producer else 'NO'}")
        logger.info(f"  -> Candle cache: {'SI' if obj_candle_cache else 'NO'}")
        logger.info("ProcesarSenalesCUAdapter inicializado OK")
        sys.stdout.flush()

    def iniciar(self) -> list[Escaner]:
        """Obtiene escaneres activos y los retorna para que el scheduler los programe."""
        logger.info("=" * 60)
        logger.info("  INICIANDO PROCESAMIENTO DE SENALES")
        logger.info("=" * 60)
        logger.info("Obteniendo escaneres activos desde scanner-management-service...")
        sys.stdout.flush()

        escaneres = self.obj_comunicacion_externa.obtener_escaneres_activos()

        logger.info(f"Escaneres activos encontrados: {len(escaneres)}")
        for esc in escaneres:
            logger.info(
                f"  - {esc.nombre} (ID:{esc.id_escaner}) | "
                f"{esc.hora_inicio}-{esc.hora_fin} | "
                f"Mercados: {len(esc.mercados)} | Filtros: {len(esc.filtros)}"
            )
        sys.stdout.flush()
        return escaneres

    def detener(self) -> None:
        logger.info("Deteniendo procesamiento de senales...")
        if self.obj_event_loop:
            self.obj_event_loop.detener()
        logger.info("Procesamiento de senales detenido OK")
        sys.stdout.flush()

    def registrar_escaner(self, escaner_data: dict) -> None:
        """Registra (programa) un nuevo escaner recibido via webhook."""
        nombre = escaner_data.get('nombre', 'unknown')
        logger.info(f"Registrando nuevo escaner via webhook: {nombre}")
        escaner = self.obj_comunicacion_externa._mapear_escaner(escaner_data)

        if escaner.esta_activo():
            if hasattr(self, 'obj_scheduler') and self.obj_scheduler:
                self.obj_scheduler.agregar_tarea_escaner(escaner)
                logger.info(f"Escaner {nombre} agregado al scheduler")
            else:
                logger.warning("Scheduler no inyectado, no se puede programar dinamicamente.")
        else:
            logger.info(f"Escaner {nombre} no esta activo, no se programa")
        sys.stdout.flush()

    def detener_escaner(self, id_escaner: int) -> None:
        logger.info(f"Deteniendo escaner ID: {id_escaner}")
        if self.obj_scheduler:
            self.obj_scheduler.remover_tarea_escaner(id_escaner)
        if self.obj_event_loop:
            self.obj_event_loop.remover_de_watchlist(id_escaner)
        if self.obj_candle_cache:
            self.obj_candle_cache.limpiar_escaner(id_escaner)
        logger.info(f"Escaner {id_escaner} detenido OK")
        sys.stdout.flush()

    # =========================================================================
    # Ejecucion principal del escaner
    # =========================================================================

    def ejecutar_escaner(self, escaner: Escaner) -> None:
        """
        Ejecuta un escaner completo con evaluacion en dos fases:
        - Fase 1: filtros de estado (cada 60s, velas cerradas)
        - Fase 2: filtros de evento (cada 0.1s, barra en formacion) via event loop

        IMPORTANTE: Valida que el mercado esté abierto (lun-vie, sin feriados) antes de ejecutar.
        """
        logger.info("=" * 60)
        logger.info(f"EJECUTANDO ESCANER: {escaner.nombre} (ID:{escaner.id_escaner})")
        logger.info("=" * 60)
        sys.stdout.flush()

        # Validar que el mercado esté abierto
        if not self._es_dia_de_mercado():
            fecha_hoy = datetime.now(timezone.utc).date()

            # Solo notificar UNA vez por escaner+dia (evita spam en feriados/fines de semana)
            if self._feriado_notificado.get(escaner.id_escaner) == fecha_hoy:
                return

            self._feriado_notificado[escaner.id_escaner] = fecha_hoy
            razon = self._obtener_razon_mercado_cerrado()
            logger.info(f"Escaner {escaner.nombre} OMITIDO: {razon}")

            # Publicar log informativo (no es error, es comportamiento esperado)
            if self.obj_kafka_producer:
                now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
                self.obj_kafka_producer.publicar_log({
                    "servicioOrigen": "signal-processing-service",
                    "nivel": "INFO",
                    "mensaje": f"Escaner '{escaner.nombre}' omitido: {razon}",
                    "idEscaner": escaner.id_escaner,
                    "symbol": None,
                    "categoria": "SCHEDULER",
                    "timestamp": now,
                    "metadatos": json.dumps({"razon": razon}),
                })

            sys.stdout.flush()
            return

        simbolos = self._obtener_simbolos(escaner)
        if not simbolos:
            logger.warning(f"Escaner {escaner.nombre}: no se obtuvieron simbolos.")
            # Si es tipo UNA_VEZ, notificar que termino (aunque sin simbolos)
            if escaner.obj_tipo_ejecucion.enum_tipo_ejecucion == "UNA_VEZ":
                self._notificar_escaner_completado(escaner, "SIN_SIMBOLOS")
            return

        logger.info(f"Escaner {escaner.nombre}: {len(simbolos)} simbolos a evaluar")
        logger.debug(f"Simbolos: {simbolos[:10]}{'...' if len(simbolos) > 10 else ''}")
        sys.stdout.flush()

        registry = self.obj_filtro_executor.obj_filtro_registry
        state_filters, event_filters = registry.clasificar_filtros(escaner.filtros)

        if not event_filters:
            logger.info(f"Escaner {escaner.nombre}: ejecutando en modo clasico (sin filtros de evento)")
            self._ejecutar_escaner_clasico(escaner, simbolos)
            return

        logger.info(
            f"Escaner {escaner.nombre}: {len(state_filters)} filtros de estado, "
            f"{len(event_filters)} filtros de evento"
        )
        sys.stdout.flush()

        # Batch fetch TODOS los simbolos para TODOS los timeframes (state + event filters)
        todos_filtros = state_filters + event_filters
        timeframes_necesarios = self.obj_filtro_executor.obtener_timeframes_necesarios(todos_filtros)
        logger.info(f"Batch fetching para fase 1: timeframes={timeframes_necesarios}, {len(simbolos)} symbols")

        cache_candles = self._fetch_con_cache(escaner, simbolos, timeframes_necesarios)

        logger.info(f"Batch fetch fase1 completado: {len(cache_candles)} (symbol,tf) pairs en cache")

        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS_SIMBOLOS, len(simbolos))) as executor:
            futures = {
                executor.submit(
                    self._evaluar_fase1, escaner, simbolo, state_filters, event_filters, cache_candles
                ): simbolo
                for simbolo in simbolos
            }
            for future in as_completed(futures):
                simbolo = futures[future]
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Error en fase 1 para {simbolo}: {e}", exc_info=True)

        logger.info(f"Escaner {escaner.nombre}: ejecucion completada")

        # Si es tipo UNA_VEZ, notificar que termino
        if escaner.obj_tipo_ejecucion.enum_tipo_ejecucion == "UNA_VEZ":
            self._notificar_escaner_completado(escaner, "COMPLETADO")

        sys.stdout.flush()

    # =========================================================================
    # Flujo clasico (sin filtros de evento) — backward compatible
    # =========================================================================

    def _ejecutar_escaner_clasico(self, escaner: Escaner, simbolos: list[str]) -> None:
        """Evaluacion clasica con batch fetching y cache incremental.

        Primera ejecucion: fetch completo de todas las barras necesarias.
        Ejecuciones posteriores: solo pide barras nuevas y las anade al cache.
        Valida las barras antes de evaluar. Cancela si no son confiables.
        """
        logger.info(f"Ejecutando escaner clasico BATCH: {escaner.nombre} con {len(simbolos)} simbolos")

        # Publicar log de inicio con detalles
        self._publicar_log_inicio_escaner(escaner, simbolos)

        # 1. Determinar timeframes necesarios
        timeframes_necesarios = self.obj_filtro_executor.obtener_timeframes_necesarios(escaner.filtros)
        logger.info(f"Timeframes necesarios: {timeframes_necesarios}")

        # 2. Fetch con cache incremental
        cache_candles = self._fetch_con_cache(escaner, simbolos, timeframes_necesarios)

        logger.info(f"Fetch completado: {len(cache_candles)} (symbol,tf) pairs disponibles")

        # 3. Evaluar cada simbolo localmente desde el cache
        senales_generadas = 0
        errores = 0
        sin_datos = 0

        for simbolo in simbolos:
            try:
                resultado = self._evaluar_simbolo_con_cache(escaner, simbolo, cache_candles)
                if resultado == "SIGNAL":
                    senales_generadas += 1
                elif resultado == "NO_DATA":
                    sin_datos += 1
            except Exception as e:
                logger.error(f"Error evaluando {simbolo} desde cache: {e}")
                errores += 1

        logger.info(f"Escaner clasico {escaner.nombre} completado: {senales_generadas} senales generadas")

        # Publicar log de finalizacion con estadisticas
        self._publicar_log_finalizacion_escaner(escaner, simbolos, senales_generadas, sin_datos, errores)

        # Si es tipo UNA_VEZ, notificar que termino
        if escaner.obj_tipo_ejecucion.enum_tipo_ejecucion == "UNA_VEZ":
            self._notificar_escaner_completado(escaner, "COMPLETADO")

        sys.stdout.flush()

    # =========================================================================
    # Fetch con cache incremental
    # =========================================================================

    def _fetch_con_cache(
        self, escaner: Escaner, simbolos: list[str], timeframes_necesarios: dict
    ) -> dict:
        """Fetch de barras con cache incremental.

        Primera ejecucion: fetch completo. Siguientes: solo barras nuevas.
        Retorna dict {(symbol, tf): [Candle, ...]}.
        """
        cache_candles = {}
        BATCH_SIZE = 200

        if not self.obj_candle_cache:
            # Sin cache: fetch completo siempre (comportamiento original)
            return self._fetch_completo(simbolos, timeframes_necesarios)

        for tf, cantidad_velas in timeframes_necesarios.items():
            # Clasificar simbolos: cuales necesitan fetch completo vs incremental
            simbolos_completo = []
            simbolos_incremental = []

            for simbolo in simbolos:
                if self.obj_candle_cache.necesita_fetch_completo(
                    escaner.id_escaner, simbolo, tf
                ):
                    simbolos_completo.append(simbolo)
                else:
                    simbolos_incremental.append(simbolo)

            logger.info(
                f"Cache tf={tf}: {len(simbolos_completo)} fetch completo, "
                f"{len(simbolos_incremental)} incremental"
            )

            # Fetch completo para simbolos sin cache
            if simbolos_completo:
                resultado = self._fetch_batch_con_reintentos(
                    simbolos_completo, tf, cantidad_velas
                )
                for symbol, candles in resultado.items():
                    self.obj_candle_cache.actualizar(
                        escaner.id_escaner, symbol, tf, candles
                    )
                    cache_candles[(symbol, tf)] = self.obj_candle_cache.obtener(
                        escaner.id_escaner, symbol, tf
                    ) or candles

            # Fetch incremental para simbolos con cache
            if simbolos_incremental:
                # Calcular cuantas barras nuevas necesitamos (usar el primer simbolo como referencia)
                barras_nuevas = self.obj_candle_cache.barras_faltantes(
                    escaner.id_escaner, simbolos_incremental[0], tf
                )
                if barras_nuevas <= 0:
                    barras_nuevas = 2  # Minimo 2 barras de margen

                logger.info(
                    f"Fetch incremental tf={tf}: {barras_nuevas} barras nuevas "
                    f"para {len(simbolos_incremental)} simbolos"
                )

                resultado = self._fetch_batch_con_reintentos(
                    simbolos_incremental, tf, barras_nuevas
                )
                for symbol, candles in resultado.items():
                    anadidas = self.obj_candle_cache.actualizar(
                        escaner.id_escaner, symbol, tf, candles
                    )
                    self.obj_candle_cache.recortar(
                        escaner.id_escaner, symbol, tf, cantidad_velas + 50
                    )
                    if anadidas > 0:
                        logger.debug(f"Cache {symbol} tf={tf}: +{anadidas} barras nuevas")

                # Usar datos del cache para todos los incrementales
                for symbol in simbolos_incremental:
                    cached = self.obj_candle_cache.obtener(
                        escaner.id_escaner, symbol, tf
                    )
                    if cached:
                        cache_candles[(symbol, tf)] = cached

        return cache_candles

    def _fetch_completo(
        self, simbolos: list[str], timeframes_necesarios: dict
    ) -> dict:
        """Fetch completo sin cache (comportamiento original)."""
        cache_candles = {}
        BATCH_SIZE = 200

        for tf, cantidad_velas in timeframes_necesarios.items():
            for i in range(0, len(simbolos), BATCH_SIZE):
                batch_symbols = simbolos[i:i + BATCH_SIZE]
                try:
                    resultado_batch = self.obj_comunicacion_externa.obtener_candles_historicos_batch(
                        symbols=batch_symbols, timeframe=tf, bars=cantidad_velas
                    )
                    for symbol, candles in resultado_batch.items():
                        cache_candles[(symbol, tf)] = candles
                except Exception as e:
                    logger.error(f"Error en batch fetch tf={tf}: {e}")

        return cache_candles

    def _fetch_batch_con_reintentos(
        self, simbolos: list[str], timeframe: str, bars: int
    ) -> dict:
        """Fetch batch con reintentos y validacion de barras."""
        BATCH_SIZE = 200
        resultado_total = {}

        for i in range(0, len(simbolos), BATCH_SIZE):
            batch_symbols = simbolos[i:i + BATCH_SIZE]

            for intento in range(VALIDACION_MAX_REINTENTOS):
                try:
                    resultado_batch = self.obj_comunicacion_externa.obtener_candles_historicos_batch(
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
                            self._publicar_log_validacion_fallida_batch(
                                timeframe, len(batch_symbols)
                            )
                        break

                    logger.info(
                        f"Reintentando fetch en {VALIDACION_PAUSA_REINTENTO_SEGUNDOS}s..."
                    )
                    time.sleep(VALIDACION_PAUSA_REINTENTO_SEGUNDOS)

                except Exception as e:
                    logger.error(f"Error en batch fetch tf={timeframe} intento {intento + 1}: {e}")
                    if intento < VALIDACION_MAX_REINTENTOS - 1:
                        time.sleep(VALIDACION_PAUSA_REINTENTO_SEGUNDOS)

        return resultado_total

    def _publicar_log_validacion_fallida_batch(self, timeframe: str, num_simbolos: int) -> None:
        """Publica log de validacion fallida a Kafka."""
        if not self.obj_kafka_producer:
            return

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        self.obj_kafka_producer.publicar_log({
            "servicioOrigen": "signal-processing-service",
            "nivel": "ERROR",
            "mensaje": (
                f"Validacion de barras fallida despues de {VALIDACION_MAX_REINTENTOS} "
                f"reintentos para tf={timeframe}, {num_simbolos} simbolos"
            ),
            "idEscaner": None,
            "symbol": None,
            "categoria": "DATA",
            "timestamp": now,
            "metadatos": json.dumps({
                "timeframe": timeframe,
                "numSimbolos": num_simbolos,
                "reintentos": VALIDACION_MAX_REINTENTOS,
            }),
        })

    # =========================================================================
    # Evaluacion de simbolos
    # =========================================================================

    def _evaluar_simbolo(self, escaner: Escaner, simbolo: str) -> str:
        """Evaluacion clasica de todos los filtros para un simbolo.

        Returns:
            "SIGNAL" - Se genero una senal
            "NO_DATA" - No se pudo obtener datos
            "NO_MATCH" - No cumplio con los filtros
        """
        logger.debug(f"Evaluando {simbolo} para escaner {escaner.nombre}")

        timeframes_necesarios = self.obj_filtro_executor.obtener_timeframes_necesarios(
            escaner.filtros
        )

        candles_por_timeframe = {}
        for tf, cantidad_velas in timeframes_necesarios.items():
            candles = self._obtener_candles(simbolo, tf, cantidad_velas)
            if candles:
                candles_por_timeframe[tf] = candles

        if not candles_por_timeframe:
            logger.warning(f"No se obtuvo data de candles para {simbolo}")
            return "NO_DATA"

        datos_fundamentales = self.obj_comunicacion_externa.obtener_datos_fundamentales(simbolo)

        resultado = self.obj_filtro_executor.ejecutar_filtros(
            filtros=escaner.filtros,
            candles_por_timeframe=candles_por_timeframe,
            simbolo=simbolo,
            datos_fundamentales=datos_fundamentales,
        )

        if resultado:
            logger.info(f"SENAL DETECTADA: {simbolo} en escaner {escaner.nombre}")
            self._emitir_senal(escaner, simbolo)
            return "SIGNAL"

        return "NO_MATCH"

    def _evaluar_simbolo_con_cache(self, escaner: Escaner, simbolo: str, cache_candles: dict) -> str:
        """Evaluacion de un simbolo usando candles pre-fetched del cache.

        Valida las barras antes de evaluar. Si la validacion falla, retorna NO_DATA.

        Args:
            cache_candles: dict {(symbol, timeframe): [Candle, ...]}

        Returns:
            "SIGNAL" - Se genero una senal
            "NO_DATA" - No se pudo obtener datos o datos no confiables
            "NO_MATCH" - No cumplio con los filtros
        """
        logger.debug(f"Evaluando {simbolo} desde cache para escaner {escaner.nombre}")

        timeframes_necesarios = self.obj_filtro_executor.obtener_timeframes_necesarios(escaner.filtros)

        candles_por_timeframe = {}
        for tf, _ in timeframes_necesarios.items():
            candles = cache_candles.get((simbolo, tf), [])
            if not candles:
                continue

            # Validar barras para este simbolo/timeframe
            resultado_val = validar_barras(candles, tf)
            if not resultado_val.valido:
                logger.warning(
                    f"Barras no validas para {simbolo} tf={tf}: {resultado_val.razon}"
                )
                continue

            candles_por_timeframe[tf] = candles

        if not candles_por_timeframe:
            logger.warning(f"No hay data valida en cache para {simbolo}")
            return "NO_DATA"

        datos_fundamentales = self.obj_comunicacion_externa.obtener_datos_fundamentales(simbolo)

        resultado = self.obj_filtro_executor.ejecutar_filtros(
            filtros=escaner.filtros,
            candles_por_timeframe=candles_por_timeframe,
            simbolo=simbolo,
            datos_fundamentales=datos_fundamentales,
        )

        if resultado:
            logger.info(f"SENAL DETECTADA: {simbolo} en escaner {escaner.nombre}")
            self._emitir_senal(escaner, simbolo)
            return "SIGNAL"

        return "NO_MATCH"

    # =========================================================================
    # Fase 1: filtros de estado (cada 60s)
    # =========================================================================

    def _evaluar_fase1(self, escaner, simbolo, state_filters, event_filters, cache_candles):
        """Evalua filtros de estado desde cache. Si pasan, registra simbolo en watchlist del event loop."""
        logger.debug(f"Fase 1: evaluando {simbolo} desde cache para escaner {escaner.nombre}")

        todos_filtros = state_filters + event_filters
        timeframes_necesarios = self.obj_filtro_executor.obtener_timeframes_necesarios(todos_filtros)

        candles_por_timeframe = {}
        for tf, _ in timeframes_necesarios.items():
            candles = cache_candles.get((simbolo, tf), [])
            if candles:
                candles_por_timeframe[tf] = candles

        if not candles_por_timeframe:
            logger.warning(f"No se obtuvo data de candles para {simbolo}")
            if self.obj_event_loop:
                self.obj_event_loop.remover_de_watchlist(escaner.id_escaner, simbolo)
            return

        datos_fundamentales = self.obj_comunicacion_externa.obtener_datos_fundamentales(simbolo)

        if state_filters:
            state_pass = self.obj_filtro_executor.ejecutar_filtros(
                filtros=state_filters,
                candles_por_timeframe=candles_por_timeframe,
                simbolo=simbolo,
                datos_fundamentales=datos_fundamentales,
            )
            if not state_pass:
                logger.debug(f"Fase 1: {simbolo} no paso filtros de estado")
                if self.obj_event_loop:
                    self.obj_event_loop.remover_de_watchlist(escaner.id_escaner, simbolo)
                return

        logger.debug(f"Fase 1: {simbolo} paso filtros de estado, registrando en watchlist")

        if self.obj_event_loop:
            self.obj_event_loop.actualizar_watchlist(
                escaner_id=escaner.id_escaner,
                symbol=simbolo,
                escaner=escaner,
                event_filters=event_filters,
                candles_cache=candles_por_timeframe,
                datos_fundamentales=datos_fundamentales,
            )

    # =========================================================================
    # Fase 2: evaluacion de evento (llamado por EventLoopScheduler cada 0.1s)
    # =========================================================================

    def evaluar_evento(self, escaner, symbol, event_filters, candles_cache,
                       datos_fundamentales, barras_en_formacion):
        """Evalua filtros de evento usando la barra en formacion del market-data-service."""
        candles_con_barra = {}
        for tf, candles in candles_cache.items():
            if not candles:
                continue
            barra = barras_en_formacion.get((symbol, tf))
            if barra:
                ultima_cache = candles[-1]
                if (barra.timestamp == ultima_cache.timestamp
                        and barra.open == ultima_cache.open
                        and barra.high == ultima_cache.high
                        and barra.low == ultima_cache.low
                        and barra.close == ultima_cache.close
                        and barra.volume == ultima_cache.volume):
                    logger.debug(
                        f"Barra en formacion identica al cache para {symbol} tf={tf}, "
                        f"saltando evaluacion"
                    )
                    candles_con_barra[tf] = candles
                    continue
                modified = list(candles)
                modified[-1] = barra
                candles_con_barra[tf] = modified
            else:
                candles_con_barra[tf] = candles

        resultado = self.obj_filtro_executor.ejecutar_filtros(
            filtros=event_filters,
            candles_por_timeframe=candles_con_barra,
            simbolo=symbol,
            datos_fundamentales=datos_fundamentales,
        )

        if resultado:
            if not self._ya_emitida(escaner.id_escaner, symbol):
                logger.info(f"SENAL EVENTO DETECTADA: {symbol} en escaner {escaner.nombre}")
                self._emitir_senal(escaner, symbol)
                if self.obj_event_loop:
                    self.obj_event_loop.remover_de_watchlist(escaner.id_escaner, symbol)

    # =========================================================================
    # Utilidades
    # =========================================================================

    def _obtener_simbolos(self, escaner: Escaner) -> list[str]:
        logger.debug(f"Obteniendo simbolos para escaner {escaner.nombre}...")
        simbolos = []
        for mercado in escaner.mercados:
            if mercado.enum_mercado:
                logger.debug(f"  -> Mercado: {mercado.enum_mercado}")
                syms = self.obj_comunicacion_externa.obtener_simbolos_por_mercado(
                    mercado.enum_mercado
                )
                simbolos.extend(syms)
                logger.debug(f"  -> {len(syms)} simbolos obtenidos de {mercado.enum_mercado}")
        logger.info(f"Total simbolos para escaner {escaner.nombre}: {len(simbolos)}")
        return simbolos

    def _obtener_candles(self, simbolo: str, timeframe: str, cantidad_velas: int) -> list:
        now = datetime.now(timezone.utc)
        minutos = MINUTOS_POR_VELA.get(timeframe, 5) * cantidad_velas
        from_date = now - timedelta(minutes=minutos)

        from_str = from_date.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        to_str = now.strftime("%Y-%m-%dT%H:%M:%S+00:00")

        return self.obj_comunicacion_externa.obtener_candles_historicos(
            symbol=simbolo,
            timeframe=timeframe,
            from_date=from_str,
            to_date=to_str,
        )

    def _emitir_senal(self, escaner, symbol):
        senal = Senal(
            escaner_id=escaner.id_escaner,
            escaner_nombre=escaner.nombre,
            symbol=symbol,
            filtros_evaluados=[f.enum_filtro for f in escaner.filtros],
        )

        logger.info("=" * 80)
        logger.info(f"SENAL GENERADA: {symbol}")
        logger.info(f"  Escaner: {escaner.nombre} (ID: {escaner.id_escaner})")
        logger.info(f"  Filtros: {[f.enum_filtro for f in escaner.filtros]}")
        logger.info("=" * 80)
        print(senal)
        sys.stdout.flush()

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        if self.obj_kafka_producer:
            logger.info(f"Publicando senal a Kafka para {symbol}...")

            # Publicar senal
            self.obj_kafka_producer.publicar_senal({
                "idEscaner": escaner.id_escaner,
                "nombreEscaner": escaner.nombre,
                "symbol": symbol,
                "tipoSenal": "ENTRADA",
                "filtrosAplicados": json.dumps([f.enum_filtro for f in escaner.filtros]),
                "precioDeteccion": None,
                "volumenDeteccion": None,
                "timestamp": now,
            })
            logger.info(f"  -> Topic 'signals': OK")

            # Publicar estado activo
            self.obj_kafka_producer.publicar_estado_activo({
                "idEscaner": escaner.id_escaner,
                "nombreEscaner": escaner.nombre,
                "symbol": symbol,
                "estado": "ACTIVO",
                "metadatos": json.dumps({"filtros": [f.enum_filtro for f in escaner.filtros]}),
                "timestamp": now,
            })
            logger.info(f"  -> Topic 'asset-state': OK")

            # Publicar log
            self.obj_kafka_producer.publicar_log({
                "servicioOrigen": "signal-processing-service",
                "nivel": "INFO",
                "mensaje": f"Senal generada para {symbol} en escaner {escaner.nombre}",
                "idEscaner": escaner.id_escaner,
                "symbol": symbol,
                "categoria": "SIGNAL",
                "timestamp": now,
                "metadatos": json.dumps({"filtros": [f.enum_filtro for f in escaner.filtros]}),
            })
            logger.info(f"  -> Topic 'logs': OK")

            logger.info(f"Senal publicada a Kafka exitosamente para {symbol}")
        else:
            logger.warning("Kafka producer no disponible, senal no publicada a Kafka")

        sys.stdout.flush()

    def _ya_emitida(self, escaner_id, symbol):
        key = (escaner_id, symbol)
        now = time.time()
        if key in self._senales_emitidas:
            if (now - self._senales_emitidas[key]) < SIGNAL_COOLDOWN_SECONDS:
                logger.debug(f"Senal ya emitida recientemente para {symbol}, cooldown activo")
                return True
        self._senales_emitidas[key] = now
        return False

    def _es_dia_de_mercado(self) -> bool:
        """
        Verifica si hoy es un día de mercado (lun-vie, sin feriados NYSE).
        Retorna True si el mercado está abierto, False si está cerrado.
        """
        now = datetime.now(timezone.utc)

        # 1. Verificar fin de semana (sábado=5, domingo=6)
        if now.weekday() >= 5:
            return False

        # 2. Verificar feriados NYSE 2026 (top 9 feriados que cierran el mercado completo)
        # Nota: En producción, considera usar pandas_market_calendars o market-calendar-service
        feriados_2026_utc = [
            datetime(2026, 1, 1, tzinfo=timezone.utc),   # New Year's Day
            datetime(2026, 1, 19, tzinfo=timezone.utc),  # Martin Luther King Jr. Day
            datetime(2026, 2, 16, tzinfo=timezone.utc),  # Presidents' Day
            datetime(2026, 4, 3, tzinfo=timezone.utc),   # Good Friday
            datetime(2026, 5, 25, tzinfo=timezone.utc),  # Memorial Day
            datetime(2026, 7, 3, tzinfo=timezone.utc),   # Independence Day (observed)
            datetime(2026, 9, 7, tzinfo=timezone.utc),   # Labor Day
            datetime(2026, 11, 26, tzinfo=timezone.utc), # Thanksgiving
            datetime(2026, 12, 25, tzinfo=timezone.utc), # Christmas
        ]

        fecha_hoy = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if fecha_hoy in feriados_2026_utc:
            return False

        return True

    def _obtener_razon_mercado_cerrado(self) -> str:
        """Retorna una descripción legible de por qué el mercado está cerrado."""
        now = datetime.now(timezone.utc)

        # Verificar fin de semana
        if now.weekday() == 5:
            return "Mercado cerrado (Sábado)"
        if now.weekday() == 6:
            return "Mercado cerrado (Domingo)"

        # Verificar feriados (simplificado, solo nombres comunes)
        fecha_hoy = now.replace(hour=0, minute=0, second=0, microsecond=0)
        feriados_nombres = {
            datetime(2026, 1, 1, tzinfo=timezone.utc): "New Year's Day",
            datetime(2026, 1, 19, tzinfo=timezone.utc): "MLK Day",
            datetime(2026, 2, 16, tzinfo=timezone.utc): "Presidents' Day",
            datetime(2026, 4, 3, tzinfo=timezone.utc): "Good Friday",
            datetime(2026, 5, 25, tzinfo=timezone.utc): "Memorial Day",
            datetime(2026, 7, 3, tzinfo=timezone.utc): "Independence Day",
            datetime(2026, 9, 7, tzinfo=timezone.utc): "Labor Day",
            datetime(2026, 11, 26, tzinfo=timezone.utc): "Thanksgiving",
            datetime(2026, 12, 25, tzinfo=timezone.utc): "Christmas",
        }

        if fecha_hoy in feriados_nombres:
            return f"Mercado cerrado (Feriado: {feriados_nombres[fecha_hoy]})"

        return "Mercado cerrado (razón desconocida)"

    def _publicar_log_inicio_escaner(self, escaner: Escaner, simbolos: list[str]) -> None:
        """Publica log detallado al iniciar la ejecucion de un escaner."""
        if not self.obj_kafka_producer:
            return

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        filtros_str = ", ".join([f.enum_filtro for f in escaner.filtros])
        mercados_str = ", ".join([m.enum_mercado for m in escaner.mercados])

        mensaje = (
            f"Escaner '{escaner.nombre}' iniciado\n"
            f"- Filtros: [{filtros_str}]\n"
            f"- Mercados: [{mercados_str}]\n"
            f"- Símbolos a evaluar: {len(simbolos)}\n"
            f"- Horario: {escaner.hora_inicio}-{escaner.hora_fin} UTC\n"
            f"- Tipo: {escaner.obj_tipo_ejecucion.enum_tipo_ejecucion}"
        )

        self.obj_kafka_producer.publicar_log({
            "servicioOrigen": "signal-processing-service",
            "nivel": "INFO",
            "mensaje": mensaje,
            "idEscaner": escaner.id_escaner,
            "symbol": None,
            "categoria": "SCANNER",
            "timestamp": now,
            "metadatos": json.dumps({
                "filtros": [f.enum_filtro for f in escaner.filtros],
                "mercados": [m.enum_mercado for m in escaner.mercados],
                "totalSimbolos": len(simbolos)
            }),
        })
        logger.info(f"Log de inicio publicado para escaner {escaner.nombre}")

    def _publicar_log_finalizacion_escaner(self, escaner: Escaner, simbolos: list[str],
                                            senales_generadas: int, sin_datos: int, errores: int) -> None:
        """Publica log detallado con estadisticas al finalizar la ejecucion de un escaner."""
        if not self.obj_kafka_producer:
            return

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        total_evaluados = len(simbolos)
        no_match = total_evaluados - senales_generadas - sin_datos - errores

        mensaje = (
            f"Escaner '{escaner.nombre}' finalizado\n"
            f"- Símbolos evaluados: {total_evaluados}\n"
            f"- Señales generadas: {senales_generadas}\n"
            f"- Breakdown:\n"
            f"  * Sin datos (timeout/error): {sin_datos}\n"
            f"  * No cumplieron filtros: {no_match}\n"
            f"  * Errores de evaluación: {errores}"
        )

        if total_evaluados > 0:
            porcentaje_exito = (senales_generadas / total_evaluados) * 100
            mensaje += f"\n- Tasa de éxito: {porcentaje_exito:.1f}%"

        self.obj_kafka_producer.publicar_log({
            "servicioOrigen": "signal-processing-service",
            "nivel": "INFO",
            "mensaje": mensaje,
            "idEscaner": escaner.id_escaner,
            "symbol": None,
            "categoria": "SCANNER",
            "timestamp": now,
            "metadatos": json.dumps({
                "totalSimbolos": total_evaluados,
                "senalesGeneradas": senales_generadas,
                "sinDatos": sin_datos,
                "noMatch": no_match,
                "errores": errores,
                "tasaExito": round((senales_generadas / total_evaluados) * 100, 1) if total_evaluados > 0 else 0
            }),
        })
        logger.info(f"Log de finalizacion publicado para escaner {escaner.nombre}")

    def _notificar_escaner_completado(self, escaner: Escaner, razon: str) -> None:
        """Notifica que un escaner UNA_VEZ ha completado su ejecucion."""
        if not self.obj_kafka_producer:
            logger.warning("Kafka producer no disponible, no se puede notificar escaner completado")
            return

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        logger.info(f"Notificando escaner completado: {escaner.nombre} (razon: {razon})")

        # Publicar evento de escaner completado al topic scanner.state
        self.obj_kafka_producer.publicar_escaner_completado({
            "idEscaner": escaner.id_escaner,
            "nombreEscaner": escaner.nombre,
            "estadoAnterior": "INICIADO",
            "estadoNuevo": "DETENIDO",
            "razon": f"ESCANER_UNA_VEZ_{razon}",
            "timestamp": now,
        })

        # Tambien publicar log
        self.obj_kafka_producer.publicar_log({
            "servicioOrigen": "signal-processing-service",
            "nivel": "INFO",
            "mensaje": f"Escaner '{escaner.nombre}' (UNA_VEZ) completado. Razon: {razon}",
            "idEscaner": escaner.id_escaner,
            "symbol": None,
            "categoria": "SCANNER",
            "timestamp": now,
            "metadatos": json.dumps({"razon": razon, "tipoEjecucion": "UNA_VEZ"}),
        })

        logger.info(f"Evento escaner completado publicado exitosamente: {escaner.nombre}")
        sys.stdout.flush()
