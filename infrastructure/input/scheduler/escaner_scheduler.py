"""Adaptador de entrada: programa la ejecucion de escaneres segun su horario."""

import json
import logging
import sys
import time as time_lib
from datetime import datetime, time, timedelta, timezone

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from domain.models.escaner import Escaner
from domain.services.market_calendar_service import MarketCalendarService
from config import (
    PRE_DESPERTAR_MINUTOS,
)

logger = logging.getLogger(__name__)


class EscanerScheduler:

    def __init__(self, obj_procesar_senales_cu, obj_filtro_executor=None):
        logger.info("Inicializando EscanerScheduler...")
        self.obj_procesar_senales_cu = obj_procesar_senales_cu
        self.obj_filtro_executor = obj_filtro_executor
        self.scheduler = BlockingScheduler(
            executors={'default': ThreadPoolExecutor(2)},
            job_defaults={
                'misfire_grace_time': 300,
                'coalesce': True,
                'max_instances': 1,
            }
        )
        # {escaner_id: date} - evita notificaciones repetidas de mercado cerrado
        self._mercado_cerrado_notificado = {}
        logger.info(f"  -> PRE_DESPERTAR_MINUTOS: {PRE_DESPERTAR_MINUTOS}")
        logger.info("EscanerScheduler inicializado OK")
        sys.stdout.flush()

    def programar_escaneres(self, escaneres: list[Escaner]) -> None:
        """Programa cada escaner segun su horaInicio."""
        logger.info(f"Programando {len(escaneres)} escaneres...")
        sys.stdout.flush()

        for escaner in escaneres:
            self._programar_escaner(escaner)

        total_jobs = len(self.scheduler.get_jobs())
        logger.info(f"Total jobs programados: {total_jobs}")

        if total_jobs > 0:
            logger.info("Jobs programados:")
            for job in self.scheduler.get_jobs():
                logger.info(f"  - {job.name} (ID: {job.id}) | Trigger: {job.trigger}")
        sys.stdout.flush()

    def _programar_escaner(self, escaner: Escaner) -> None:
        """Programa un escaner individual.

        UNA_VEZ: CronTrigger exactamente a hora_inicio. Ejecuta una pasada y muere.
        DIARIA:  CronTrigger PRE_DESPERTAR_MINUTOS antes de hora_inicio. Duerme hasta
                 hora_inicio exacta y lanza la sesion completa (loop hasta hora_fin).
                 APScheduler lo reprograma automaticamente para el siguiente dia habil.
        """
        logger.info(f"Programando escaner: {escaner.nombre} (ID: {escaner.id_escaner})")
        try:
            hora_inicio = self._parse_time(escaner.hora_inicio)
            hora_fin = self._parse_time(escaner.hora_fin)
            tipo = escaner.obj_tipo_ejecucion.enum_tipo_ejecucion

            logger.debug(f"  -> Hora inicio UTC: {hora_inicio}, Hora fin UTC: {hora_fin}")
            logger.debug(f"  -> Tipo ejecucion: {tipo}")

            if tipo == "UNA_VEZ":
                trigger = CronTrigger(
                    day_of_week='mon-fri',
                    hour=hora_inicio.hour,
                    minute=hora_inicio.minute,
                    timezone='UTC'
                )
                self.scheduler.add_job(
                    func=self._ejecutar_con_validacion_mercado,
                    trigger=trigger,
                    args=[escaner],
                    id=f"escaner_{escaner.id_escaner}",
                    name=f"Escaner: {escaner.nombre}",
                    replace_existing=True,
                )
                logger.info(
                    f"  -> CronTrigger UTC: {hora_inicio.hour}:{hora_inicio.minute:02d} "
                    f"(una vez, lun-vie)"
                )

            elif tipo == "DIARIA":
                # Despertar PRE_DESPERTAR_MINUTOS antes de hora_inicio
                dummy = datetime(2000, 1, 1, hora_inicio.hour, hora_inicio.minute)
                hora_pre = (dummy - timedelta(minutes=PRE_DESPERTAR_MINUTOS)).time()

                trigger = CronTrigger(
                    day_of_week='mon-fri',
                    hour=hora_pre.hour,
                    minute=hora_pre.minute,
                    timezone='UTC'
                )
                self.scheduler.add_job(
                    func=self._ejecutar_con_pre_despertar,
                    trigger=trigger,
                    args=[escaner],
                    id=f"escaner_{escaner.id_escaner}",
                    name=f"Escaner: {escaner.nombre}",
                    replace_existing=True,
                )
                logger.info(
                    f"  -> CronTrigger UTC: {hora_pre.hour}:{hora_pre.minute:02d} "
                    f"(pre-despertar {PRE_DESPERTAR_MINUTOS}min antes de {escaner.hora_inicio} UTC, lun-vie)"
                )

            else:
                logger.error(
                    f"Tipo de ejecucion desconocido '{tipo}' "
                    f"para escaner '{escaner.nombre}' — omitido."
                )
                sys.stdout.flush()
                return

            logger.info(
                f"Escaner programado OK (UTC): '{escaner.nombre}' | "
                f"{escaner.hora_inicio}-{escaner.hora_fin} UTC | Tipo: {tipo}"
            )
        except Exception as e:
            logger.error(f"Error programando escaner {escaner.nombre}: {e}", exc_info=True)
        sys.stdout.flush()

    def agregar_tarea_escaner(self, escaner: Escaner) -> None:
        """Agrega un escaner dinamicamente."""
        logger.info(f"Agregando escaner dinamicamente: {escaner.nombre}")
        self._programar_escaner(escaner)

    def remover_tarea_escaner(self, id_escaner: int) -> None:
        """Remueve la tarea de un escaner."""
        job_id = f"escaner_{id_escaner}"
        logger.info(f"Removiendo tarea: {job_id}")
        job = self.scheduler.get_job(job_id)
        if job:
            job.remove()
            logger.info(f"Tarea removida exitosamente: {job_id}")
        else:
            logger.warning(f"No se encontro tarea para remover: {job_id}")
        sys.stdout.flush()

    def iniciar(self) -> None:
        """Inicia el scheduler (bloqueante)."""
        logger.info("=" * 60)
        logger.info("  INICIANDO SCHEDULER (BlockingScheduler)")
        logger.info("=" * 60)
        logger.info(f"Jobs activos: {len(self.scheduler.get_jobs())}")
        sys.stdout.flush()
        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler detenido por interrupcion.")
        except Exception as e:
            logger.error(f"Error en scheduler: {e}", exc_info=True)
        sys.stdout.flush()

    def detener(self) -> None:
        """Detiene el scheduler."""
        logger.info("Deteniendo scheduler...")
        self.scheduler.shutdown()
        logger.info("Scheduler detenido OK")
        sys.stdout.flush()

    # =========================================================================
    # Ejecucion con validacion de mercado (UNA_VEZ)
    # =========================================================================

    def _ejecutar_con_validacion_mercado(self, escaner: Escaner) -> None:
        """Verifica mercado abierto y ventana horaria antes de ejecutar (UNA_VEZ)."""
        if not MarketCalendarService.es_dia_de_mercado():
            fecha_hoy = datetime.now(timezone.utc).date()
            if self._mercado_cerrado_notificado.get(escaner.id_escaner) == fecha_hoy:
                return

            self._mercado_cerrado_notificado[escaner.id_escaner] = fecha_hoy
            razon = MarketCalendarService.obtener_razon_mercado_cerrado()
            logger.info(f"Escaner {escaner.nombre} OMITIDO: {razon}")

            kafka_producer = getattr(self.obj_procesar_senales_cu, 'obj_kafka_producer', None)
            if kafka_producer:
                now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
                kafka_producer.publicar_log({
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

        # Validar ventana horaria (tolerancia de 59s para latencia del scheduler)
        ahora_time = datetime.now(timezone.utc).time()
        hora_inicio_t = self._parse_time(escaner.hora_inicio)
        hora_fin_t = self._parse_time(escaner.hora_fin)

        if ahora_time < hora_inicio_t:
            logger.info(
                f"Escaner '{escaner.nombre}' antes de hora inicio "
                f"(ahora={ahora_time.strftime('%H:%M:%S')}, inicio={escaner.hora_inicio}) — omitido"
            )
            sys.stdout.flush()
            return

        dummy_date = datetime(2000, 1, 1)
        dt_fin = dummy_date.replace(hour=hora_fin_t.hour, minute=hora_fin_t.minute, second=hora_fin_t.second)
        dt_ahora = dummy_date.replace(hour=ahora_time.hour, minute=ahora_time.minute, second=ahora_time.second)

        if dt_ahora > (dt_fin + timedelta(seconds=59)):
            logger.info(
                f"Escaner '{escaner.nombre}' despues de hora fin "
                f"(ahora={ahora_time.strftime('%H:%M:%S')}, fin={escaner.hora_fin}) — omitido"
            )
            sys.stdout.flush()
            return

        self.obj_procesar_senales_cu.ejecutar_sesion(escaner)

        # UNA_VEZ: eliminar job tras finalizar la sesion completa (hora_inicio -> hora_fin)
        if escaner.obj_tipo_ejecucion.enum_tipo_ejecucion == "UNA_VEZ":
            logger.info(f"Escaner UNA_VEZ '{escaner.nombre}' completado, removiendo job del scheduler.")
            self.remover_tarea_escaner(escaner.id_escaner)

    # =========================================================================
    # Pre-despertar (DIARIA)
    # =========================================================================

    def _ejecutar_con_pre_despertar(self, escaner: Escaner) -> None:
        """Pre-despertar: despierta PRE_DESPERTAR_MINUTOS antes de hora_inicio,
        duerme hasta hora_inicio exacta y lanza la sesion completa del dia.
        """
        if not MarketCalendarService.es_dia_de_mercado():
            fecha_hoy = datetime.now(timezone.utc).date()
            if self._mercado_cerrado_notificado.get(escaner.id_escaner) == fecha_hoy:
                return
            self._mercado_cerrado_notificado[escaner.id_escaner] = fecha_hoy
            razon = MarketCalendarService.obtener_razon_mercado_cerrado()
            logger.info(f"Pre-despertar '{escaner.nombre}' OMITIDO: {razon}")

            kafka_producer = getattr(self.obj_procesar_senales_cu, 'obj_kafka_producer', None)
            if kafka_producer:
                now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
                kafka_producer.publicar_log({
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

        # Calcular segundos exactos hasta hora_inicio
        ahora = datetime.now(timezone.utc)
        hora_inicio_t = self._parse_time(escaner.hora_inicio)
        dt_inicio = ahora.replace(
            hour=hora_inicio_t.hour, minute=hora_inicio_t.minute,
            second=hora_inicio_t.second, microsecond=0
        )
        segundos_espera = (dt_inicio - ahora).total_seconds()

        if segundos_espera > 0:
            logger.info(
                f"Pre-despertar '{escaner.nombre}': esperando {segundos_espera:.1f}s "
                f"hasta {escaner.hora_inicio} UTC"
            )
            time_lib.sleep(segundos_espera)
        elif segundos_espera < -(PRE_DESPERTAR_MINUTOS * 60 * 2):
            # Despertamos demasiado tarde (mas del doble del margen), algo fallo
            logger.warning(
                f"Pre-despertar '{escaner.nombre}': hora_inicio paso hace "
                f"{-segundos_espera:.0f}s, omitiendo"
            )
            sys.stdout.flush()
            return

        logger.info(f"Pre-despertar '{escaner.nombre}': lanzando sesion del dia.")
        self.obj_procesar_senales_cu.ejecutar_sesion(escaner)

    # =========================================================================
    # Utilidades
    # =========================================================================

    @staticmethod
    def _parse_time(time_str: str) -> time:
        """Parsea un string de hora (HH:MM o HH:MM:SS) a time."""
        parts = time_str.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        second = int(parts[2]) if len(parts) > 2 else 0
        return time(hour, minute, second)
