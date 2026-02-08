"""Adaptador de entrada: programa la ejecucion de escaneres segun su horario."""

import logging
import sys
from datetime import datetime, time, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from domain.models.escaner import Escaner
from config import POLLING_INTERVAL_SECONDS

logger = logging.getLogger(__name__)


class EscanerScheduler:

    def __init__(self, obj_procesar_senales_cu):
        logger.info("Inicializando EscanerScheduler...")
        self.obj_procesar_senales_cu = obj_procesar_senales_cu
        self.scheduler = BlockingScheduler()
        logger.info(f"  -> POLLING_INTERVAL_SECONDS: {POLLING_INTERVAL_SECONDS}")
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
        """Programa un escaner individual."""
        logger.info(f"Programando escaner: {escaner.nombre} (ID: {escaner.id_escaner})")
        try:
            hora_inicio = self._parse_time(escaner.hora_inicio)
            hora_fin = self._parse_time(escaner.hora_fin)

            logger.debug(f"  -> Hora inicio UTC: {hora_inicio}, Hora fin UTC: {hora_fin}")
            logger.debug(f"  -> Tipo ejecucion: {escaner.obj_tipo_ejecucion.enum_tipo_ejecucion}")

            if escaner.obj_tipo_ejecucion.enum_tipo_ejecucion == "UNA_VEZ":
                trigger = CronTrigger(
                    hour=hora_inicio.hour,
                    minute=hora_inicio.minute,
                    timezone='UTC'
                )
                logger.debug(f"  -> CronTrigger UTC: {hora_inicio.hour}:{hora_inicio.minute}")
            else:
                # Usar datetime.now(timezone.utc) en vez de datetime.now()
                trigger = IntervalTrigger(
                    seconds=POLLING_INTERVAL_SECONDS,
                    start_date=datetime.now(timezone.utc).replace(
                        hour=hora_inicio.hour, minute=hora_inicio.minute, second=0
                    ),
                    end_date=datetime.now(timezone.utc).replace(
                        hour=hora_fin.hour, minute=hora_fin.minute, second=0
                    ),
                    timezone='UTC'
                )
                logger.debug(f"  -> IntervalTrigger UTC: cada {POLLING_INTERVAL_SECONDS}s")

            self.scheduler.add_job(
                func=self.obj_procesar_senales_cu.ejecutar_escaner,
                trigger=trigger,
                args=[escaner],
                id=f"escaner_{escaner.id_escaner}",
                name=f"Escaner: {escaner.nombre}",
                replace_existing=True,
            )
            logger.info(
                f"Escaner programado OK (UTC): '{escaner.nombre}' | "
                f"{escaner.hora_inicio}-{escaner.hora_fin} UTC | "
                f"Tipo: {escaner.obj_tipo_ejecucion.enum_tipo_ejecucion}"
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

    @staticmethod
    def _parse_time(time_str: str) -> time:
        """Parsea un string de hora (HH:MM o HH:MM:SS) a time."""
        parts = time_str.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        second = int(parts[2]) if len(parts) > 2 else 0
        return time(hour, minute, second)
