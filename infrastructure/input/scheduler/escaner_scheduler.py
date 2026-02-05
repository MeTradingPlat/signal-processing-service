"""Adaptador de entrada: programa la ejecucion de escaneres segun su horario."""

import logging
from datetime import datetime, time

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from domain.models.escaner import Escaner
from config import POLLING_INTERVAL_SECONDS

logger = logging.getLogger(__name__)


class EscanerScheduler:

    def __init__(self, obj_procesar_senales_cu):
        self.obj_procesar_senales_cu = obj_procesar_senales_cu
        self.scheduler = BlockingScheduler()

    def programar_escaneres(self, escaneres: list[Escaner]) -> None:
        """Programa cada escaner segun su horaInicio."""
        for escaner in escaneres:
            self._programar_escaner(escaner)

        logger.info(f"Total jobs programados: {len(self.scheduler.get_jobs())}")

    def _programar_escaner(self, escaner: Escaner) -> None:
        """Programa un escaner individual."""
        try:
            hora_inicio = self._parse_time(escaner.hora_inicio)
            hora_fin = self._parse_time(escaner.hora_fin)

            if escaner.obj_tipo_ejecucion.enum_tipo_ejecucion == "UNA_VEZ":
                trigger = CronTrigger(
                    hour=hora_inicio.hour,
                    minute=hora_inicio.minute,
                )
            else:
                trigger = IntervalTrigger(
                    seconds=POLLING_INTERVAL_SECONDS,
                    start_date=datetime.now().replace(
                        hour=hora_inicio.hour, minute=hora_inicio.minute, second=0
                    ),
                    end_date=datetime.now().replace(
                        hour=hora_fin.hour, minute=hora_fin.minute, second=0
                    ),
                )

            self.scheduler.add_job(
                func=self.obj_procesar_senales_cu.ejecutar_escaner,
                trigger=trigger,
                args=[escaner],
                id=f"escaner_{escaner.id_escaner}",
                name=f"Escaner: {escaner.nombre}",
                replace_existing=True,
            )
            logger.info(
                f"Programado escaner '{escaner.nombre}' | "
                f"{escaner.hora_inicio}-{escaner.hora_fin} | "
                f"Tipo: {escaner.obj_tipo_ejecucion.enum_tipo_ejecucion}"
            )
        except Exception as e:
            logger.error(f"Error programando escaner {escaner.nombre}: {e}")

    def agregar_tarea_escaner(self, escaner: Escaner) -> None:
        """Agrega un escaner dinamicamente."""
        self._programar_escaner(escaner)

    def remover_tarea_escaner(self, id_escaner: int) -> None:
        """Remueve la tarea de un escaner."""
        job_id = f"escaner_{id_escaner}"
        job = self.scheduler.get_job(job_id)
        if job:
            job.remove()
            logger.info(f"Tarea removida: {job_id}")
        else:
            logger.warning(f"No se encontro tarea para remover: {job_id}")

    def iniciar(self) -> None:
        """Inicia el scheduler (bloqueante)."""
        logger.info("Iniciando scheduler...")
        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler detenido.")

    def detener(self) -> None:
        """Detiene el scheduler."""
        self.scheduler.shutdown()

    @staticmethod
    def _parse_time(time_str: str) -> time:
        """Parsea un string de hora (HH:MM o HH:MM:SS) a time."""
        parts = time_str.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        second = int(parts[2]) if len(parts) > 2 else 0
        return time(hour, minute, second)
