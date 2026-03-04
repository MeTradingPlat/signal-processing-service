"""Proceso OS independiente para un escaner activo.

Cada escaner activo corre en su propio ScannerProcess con su propio ciclo
de sleep, completamente aislado de los demas escaners. Esto resuelve el
problema de timing donde el pool de threads del scheduler serializaba los
escaners y los hacia correr tarde.

Ciclo de vida:
  DIARIA:  esperar hora_inicio → validar mercado → ejecutar_sesion() → repetir manana
  UNA_VEZ: esperar hora_inicio → validar mercado → ejecutar_sesion() → terminar
"""

import logging
import multiprocessing
import sys
from datetime import datetime, timezone, timedelta
from datetime import time as dt_time

from domain.models.escaner import Escaner
from infrastructure.input.process.kafka_publisher_process import QueueKafkaProxy

logger = logging.getLogger(__name__)

# Intervalo maximo de sleep interruptible (para que stop_event pueda interrumpir)
_CHECK_STOP_SEGUNDOS = 30


class ScannerProcess(multiprocessing.Process):
    """Un proceso OS por escaner activo.

    Gestiona su propio ciclo completo:
      - Espera hasta hora_inicio UTC
      - Valida que el mercado este abierto (lun-vie, sin feriados NYSE)
      - Ejecuta ejecutar_sesion() (loop interno hasta hora_fin)
      - Para DIARIA: repite al dia siguiente
      - Para UNA_VEZ: termina tras la primera sesion
    """

    def __init__(self, escaner: Escaner, signal_queue: multiprocessing.Queue):
        super().__init__(
            daemon=True,
            name=f"Scanner-{escaner.id_escaner}",
        )
        self._escaner = escaner
        self._queue = signal_queue
        self._stop_event = multiprocessing.Event()

    def run(self):
        import os
        os.environ['TZ'] = 'UTC'

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(processName)s %(name)s - %(message)s",
            stream=sys.stdout,
        )
        log = logging.getLogger(f"Scanner-{self._escaner.id_escaner}")
        log.info(
            f"Iniciado: '{self._escaner.nombre}' | "
            f"{self._escaner.hora_inicio}-{self._escaner.hora_fin} UTC | "
            f"{self._escaner.obj_tipo_ejecucion.enum_tipo_ejecucion}"
        )
        sys.stdout.flush()

        # Crear dependencias DENTRO del proceso para evitar problemas con fork
        # (requests.Session, confluent_kafka.Producer, etc. no son seguros cross-fork)
        from infrastructure.output.comunicacion_externa.yahoo_finance_adapter import YahooFinanceAdapter
        from infrastructure.output.comunicacion_externa.comunicacion_externa_adapter import ComunicacionExternaAdapter
        from infrastructure.business.strategies.filtro_registry import FiltroRegistry
        from infrastructure.business.strategies.filtro_executor import FiltroExecutor
        from domain.usecases.candle_cache import CandleCache
        from domain.usecases.procesar_senales_cu_adapter import ProcesarSenalesCUAdapter
        from domain.services.market_calendar_service import MarketCalendarService
        from infrastructure.input.scheduler.event_loop_scheduler import EventLoopScheduler

        yahoo = YahooFinanceAdapter()
        comunicacion = ComunicacionExternaAdapter(yahoo_adapter=yahoo)
        filtro_registry = FiltroRegistry()
        filtro_executor = FiltroExecutor(filtro_registry)
        candle_cache = CandleCache()
        kafka_proxy = QueueKafkaProxy(self._queue)

        obj_procesar = ProcesarSenalesCUAdapter(
            obj_comunicacion_externa=comunicacion,
            obj_filtro_executor=filtro_executor,
            obj_kafka_producer=kafka_proxy,
            obj_candle_cache=candle_cache,
        )

        # EventLoopScheduler corre como thread dentro de este proceso
        event_loop = EventLoopScheduler(obj_procesar)
        obj_procesar.obj_event_loop = event_loop
        event_loop.start()

        tipo = self._escaner.obj_tipo_ejecucion.enum_tipo_ejecucion

        try:
            while not self._stop_event.is_set():
                # 1. Esperar hasta hora_inicio UTC de hoy
                if not self._esperar_hora_inicio(log):
                    break

                if self._stop_event.is_set():
                    break

                # 2. Validar que el mercado este abierto
                if not MarketCalendarService.es_dia_de_mercado():
                    razon = MarketCalendarService.obtener_razon_mercado_cerrado()
                    log.info(f"Mercado cerrado: {razon}. Esperando al dia siguiente...")
                    kafka_proxy.publicar_log({
                        "servicioOrigen": "signal-processing-service",
                        "nivel": "INFO",
                        "mensaje": f"Escaner '{self._escaner.nombre}' omitido: {razon}",
                        "idEscaner": self._escaner.id_escaner,
                        "symbol": None,
                        "categoria": "SCHEDULER",
                        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                        "metadatos": "{}",
                    })
                    # Saltar al inicio del dia siguiente para reintentar
                    self._esperar_inicio_siguiente_dia(log)
                    continue

                # 3. Ejecutar sesion (loop hasta hora_fin)
                log.info("Iniciando sesion del dia")
                obj_procesar.ejecutar_sesion(self._escaner)

                if self._stop_event.is_set():
                    break

                # 4. Post-sesion
                if tipo == "UNA_VEZ":
                    log.info("Tipo UNA_VEZ: sesion completada, proceso terminando")
                    break

                # DIARIA: esperar hasta el inicio del dia siguiente
                self._esperar_inicio_siguiente_dia(log)

        except Exception as e:
            log.error(f"Error fatal en ScannerProcess: {e}", exc_info=True)
        finally:
            event_loop.detener()
            log.info("ScannerProcess terminado")
            sys.stdout.flush()

    # =========================================================================
    # Gestion de tiempo
    # =========================================================================

    def _esperar_hora_inicio(self, log) -> bool:
        """Espera hasta hora_inicio UTC de hoy. Retorna False si stop_event fue activado."""
        partes = self._escaner.hora_inicio.split(":")
        hora_inicio_t = dt_time(int(partes[0]), int(partes[1]))

        ahora = datetime.now(timezone.utc)
        hoy_inicio = ahora.replace(
            hour=hora_inicio_t.hour, minute=hora_inicio_t.minute,
            second=0, microsecond=0
        )

        if ahora >= hoy_inicio:
            # La hora de hoy ya llego o paso, ejecutar directamente
            return True

        segundos = (hoy_inicio - ahora).total_seconds()
        log.info(
            f"Esperando hora_inicio {self._escaner.hora_inicio} UTC "
            f"({segundos:.0f}s)"
        )

        # Usar Event.wait() para que stop_event pueda interrumpir el sleep
        self._stop_event.wait(timeout=segundos)
        return not self._stop_event.is_set()

    def _esperar_inicio_siguiente_dia(self, log) -> None:
        """Para DIARIA: espera hasta hora_inicio del dia siguiente (UTC).

        Usa multiples waits cortos para que stop_event pueda interrumpir.
        """
        partes = self._escaner.hora_inicio.split(":")
        hora_inicio_t = dt_time(int(partes[0]), int(partes[1]))

        ahora = datetime.now(timezone.utc)
        manana_inicio = (ahora + timedelta(days=1)).replace(
            hour=hora_inicio_t.hour, minute=hora_inicio_t.minute,
            second=0, microsecond=0
        )
        segundos = (manana_inicio - ahora).total_seconds()

        log.info(
            f"Sesion completada. Esperando {segundos:.0f}s "
            f"hasta {self._escaner.hora_inicio} UTC manana"
        )

        self._stop_event.wait(timeout=max(0.0, segundos))

    # =========================================================================
    # Control externo
    # =========================================================================

    def detener(self):
        """Senaliza al proceso para que termine y espera hasta 30s."""
        self._stop_event.set()
        self.join(timeout=30)
        if self.is_alive():
            logger.warning(
                f"ScannerProcess {self.name} no termino en 30s, "
                "terminando forzosamente"
            )
            self.terminate()
            self.join(timeout=5)
