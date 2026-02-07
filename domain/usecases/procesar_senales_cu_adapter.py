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
from config import MAX_WORKERS_SIMBOLOS, SIGNAL_COOLDOWN_SECONDS

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
    ):
        logger.info("Inicializando ProcesarSenalesCUAdapter...")
        self.obj_comunicacion_externa = obj_comunicacion_externa
        self.obj_filtro_executor = obj_filtro_executor
        self.obj_kafka_producer = obj_kafka_producer
        self.obj_scheduler = None
        self.obj_event_loop = None
        self._senales_emitidas = {}
        logger.info(f"  -> MAX_WORKERS_SIMBOLOS: {MAX_WORKERS_SIMBOLOS}")
        logger.info(f"  -> SIGNAL_COOLDOWN_SECONDS: {SIGNAL_COOLDOWN_SECONDS}")
        logger.info(f"  -> Kafka producer: {'SI' if obj_kafka_producer else 'NO'}")
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
        """
        logger.info("=" * 60)
        logger.info(f"EJECUTANDO ESCANER: {escaner.nombre} (ID:{escaner.id_escaner})")
        logger.info("=" * 60)
        sys.stdout.flush()

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

        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS_SIMBOLOS, len(simbolos))) as executor:
            futures = {
                executor.submit(
                    self._evaluar_fase1, escaner, simbolo, state_filters, event_filters
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
        """Evaluacion clasica: todos los filtros con velas cerradas cada 60s."""
        logger.info(f"Ejecutando escaner clasico: {escaner.nombre} con {len(simbolos)} simbolos")
        senales_generadas = 0

        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS_SIMBOLOS, len(simbolos))) as executor:
            futures = {
                executor.submit(self._evaluar_simbolo, escaner, simbolo): simbolo
                for simbolo in simbolos
            }
            for future in as_completed(futures):
                simbolo = futures[future]
                try:
                    resultado = future.result()
                    if resultado:
                        senales_generadas += 1
                except Exception as e:
                    logger.error(f"Error evaluando {simbolo} en escaner {escaner.nombre}: {e}")

        logger.info(f"Escaner clasico {escaner.nombre} completado: {senales_generadas} senales generadas")

        # Si es tipo UNA_VEZ, notificar que termino
        if escaner.obj_tipo_ejecucion.enum_tipo_ejecucion == "UNA_VEZ":
            self._notificar_escaner_completado(escaner, "COMPLETADO")

        sys.stdout.flush()

    def _evaluar_simbolo(self, escaner: Escaner, simbolo: str) -> bool:
        """Evaluacion clasica de todos los filtros para un simbolo."""
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
            return False

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
            return True

        return False

    # =========================================================================
    # Fase 1: filtros de estado (cada 60s)
    # =========================================================================

    def _evaluar_fase1(self, escaner, simbolo, state_filters, event_filters):
        """Evalua filtros de estado. Si pasan, registra simbolo en watchlist del event loop."""
        logger.debug(f"Fase 1: evaluando {simbolo} para escaner {escaner.nombre}")

        todos_filtros = state_filters + event_filters
        timeframes_necesarios = self.obj_filtro_executor.obtener_timeframes_necesarios(todos_filtros)

        candles_por_timeframe = {}
        for tf, cantidad_velas in timeframes_necesarios.items():
            candles = self._obtener_candles(simbolo, tf, cantidad_velas)
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
