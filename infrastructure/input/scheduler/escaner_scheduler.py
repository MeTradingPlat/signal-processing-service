"""Adaptador de entrada: programa la ejecucion de escaneres segun su horario."""

import logging
import sys
import time as time_mod
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from domain.models.escaner import Escaner
from config import (
    POLLING_INTERVAL_SECONDS,
    PRE_DESPERTAR_UMBRAL_SEGUNDOS,
    PRE_DESPERTAR_MINUTOS,
    PRE_DESPERTAR_MARGEN_SEGUNDOS,
)

logger = logging.getLogger(__name__)

INTERVALO_POR_TIMEFRAME = {
    "M1": 60, "M5": 300, "M15": 900, "M30": 1800,
    "H1": 3600, "D1": 86400, "W1": 604800, "MO1": 2592000,
}

NYSE_TZ = ZoneInfo("America/New_York")
HORA_CIERRE_NYSE = 16  # 4:00 PM ET


class EscanerScheduler:

    def __init__(self, obj_procesar_senales_cu, obj_filtro_executor=None):
        logger.info("Inicializando EscanerScheduler...")
        self.obj_procesar_senales_cu = obj_procesar_senales_cu
        self.obj_filtro_executor = obj_filtro_executor
        self.scheduler = BlockingScheduler(
            executors={'default': ThreadPoolExecutor(20)}
        )
        logger.info(f"  -> POLLING_INTERVAL_SECONDS: {POLLING_INTERVAL_SECONDS}")
        logger.info(f"  -> PRE_DESPERTAR: umbral={PRE_DESPERTAR_UMBRAL_SEGUNDOS}s, "
                     f"minutos={PRE_DESPERTAR_MINUTOS}, margen={PRE_DESPERTAR_MARGEN_SEGUNDOS}s")
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
        """Programa un escaner individual con ejecucion recurrente diaria (lun-vie).

        Para escaneres PERIODICO con intervalo >= PRE_DESPERTAR_UMBRAL_SEGUNDOS,
        se adelanta el trigger N minutos y se usa pre-despertar para recalcular
        el sleep exacto hasta el cierre de barra.
        """
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
                logger.debug(f"  -> CronTrigger UTC: {hora_inicio.hour}:{hora_inicio.minute:02d} (una vez)")

                self.scheduler.add_job(
                    func=self.obj_procesar_senales_cu.ejecutar_escaner,
                    trigger=trigger,
                    args=[escaner],
                    id=f"escaner_{escaner.id_escaner}",
                    name=f"Escaner: {escaner.nombre}",
                    replace_existing=True,
                )
            else:
                # PERIODICO: CronTrigger recurrente lun-vie para re-ejecucion diaria
                intervalo = self._calcular_intervalo_escaner(escaner)
                interval_minutes = intervalo // 60

                # Ajustar hora_fin para rango inclusivo (21:00 -> ejecutar hasta 20:59)
                hora_fin_int = hora_fin.hour if hora_fin.minute == 0 else hora_fin.hour

                # Determinar si aplica pre-despertar
                usar_pre_despertar = intervalo >= PRE_DESPERTAR_UMBRAL_SEGUNDOS

                if interval_minutes < 1:
                    # Intervalos < 60s: usar IntervalTrigger continuo + validacion manual de horario
                    logger.warning(
                        f"Intervalo {intervalo}s < 60s: usando IntervalTrigger continuo. "
                        f"Horario {escaner.hora_inicio}-{escaner.hora_fin} se valida en ejecutar_escaner()."
                    )
                    trigger = IntervalTrigger(
                        seconds=intervalo,
                        timezone='UTC'
                    )
                elif usar_pre_despertar:
                    # Pre-despertar: adelantar el CronTrigger N minutos
                    minuto_adelantado = interval_minutes - PRE_DESPERTAR_MINUTOS
                    if minuto_adelantado < 0:
                        minuto_adelantado = 0

                    # Ajustar hora de inicio (restar PRE_DESPERTAR_MINUTOS)
                    hora_inicio_adelantada = hora_inicio.hour
                    minuto_inicio_adelantado = hora_inicio.minute
                    if hora_inicio.minute < PRE_DESPERTAR_MINUTOS:
                        hora_inicio_adelantada = max(0, hora_inicio.hour - 1)
                        minuto_inicio_adelantado = 60 - (PRE_DESPERTAR_MINUTOS - hora_inicio.minute)
                    else:
                        minuto_inicio_adelantado = hora_inicio.minute - PRE_DESPERTAR_MINUTOS

                    if interval_minutes > 1:
                        minute_expr = f'{minuto_adelantado}/{interval_minutes}'
                    else:
                        minute_expr = '*'

                    trigger = CronTrigger(
                        day_of_week='mon-fri',
                        hour=f'{hora_inicio_adelantada}-{hora_fin_int}',
                        minute=minute_expr,
                        timezone='UTC'
                    )
                    logger.info(
                        f"  -> CronTrigger UTC con PRE-DESPERTAR: lun-vie "
                        f"{hora_inicio_adelantada}:00-{hora_fin_int}:59, "
                        f"cada {interval_minutes}min (adelantado {PRE_DESPERTAR_MINUTOS}min)"
                    )
                else:
                    # Intervalos >= 60s sin pre-despertar: CronTrigger normal
                    trigger = CronTrigger(
                        day_of_week='mon-fri',
                        hour=f'{hora_inicio.hour}-{hora_fin_int}',
                        minute=f'*/{interval_minutes}' if interval_minutes > 1 else '*',
                        timezone='UTC'
                    )
                    logger.info(
                        f"  -> CronTrigger UTC: lun-vie {hora_inicio.hour}:00-{hora_fin_int}:59, "
                        f"cada {interval_minutes}min (recurrente diario)"
                    )

                if usar_pre_despertar:
                    self.scheduler.add_job(
                        func=self._ejecutar_con_pre_despertar,
                        trigger=trigger,
                        args=[escaner, intervalo],
                        id=f"escaner_{escaner.id_escaner}",
                        name=f"Escaner: {escaner.nombre} (pre-despertar)",
                        replace_existing=True,
                    )
                else:
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
                f"{' | Pre-despertar: SI' if escaner.obj_tipo_ejecucion.enum_tipo_ejecucion == 'PERIODICO' and self._calcular_intervalo_escaner(escaner) >= PRE_DESPERTAR_UMBRAL_SEGUNDOS else ''}"
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
    # Pre-despertar
    # =========================================================================

    def _ejecutar_con_pre_despertar(self, escaner: Escaner, intervalo_segundos: int) -> None:
        """Pre-despertar: despierta antes de la ejecucion real, recalcula el
        tiempo exacto hasta el cierre de la barra, duerme hasta ese momento,
        y ejecuta el escaner.
        """
        ahora = datetime.now(timezone.utc)

        ts_cierre = self._calcular_proximo_cierre_barra(ahora, intervalo_segundos)

        if ts_cierre is None:
            logger.info(
                f"Pre-despertar {escaner.nombre}: no se pudo calcular cierre, "
                f"ejecutando directamente"
            )
            self.obj_procesar_senales_cu.ejecutar_escaner(escaner)
            return

        segundos_restantes = (ts_cierre - ahora).total_seconds()

        if segundos_restantes <= 0:
            logger.info(
                f"Pre-despertar {escaner.nombre}: barra ya cerrada "
                f"(diferencia={segundos_restantes:.1f}s), ejecutando"
            )
            self.obj_procesar_senales_cu.ejecutar_escaner(escaner)
            return

        # Agregar margen para que DXLink tenga la barra lista
        segundos_restantes += PRE_DESPERTAR_MARGEN_SEGUNDOS

        logger.info(
            f"Pre-despertar {escaner.nombre}: esperando {segundos_restantes:.1f}s "
            f"hasta cierre de barra ({ts_cierre.isoformat()})"
        )
        sys.stdout.flush()

        time_mod.sleep(segundos_restantes)

        logger.info(f"Pre-despertar {escaner.nombre}: sleep completado, ejecutando escaner")
        sys.stdout.flush()

        self.obj_procesar_senales_cu.ejecutar_escaner(escaner)

    @staticmethod
    def _calcular_proximo_cierre_barra(
        ahora: datetime, intervalo_segundos: int
    ) -> datetime | None:
        """Calcula el timestamp UTC del proximo cierre de barra.

        Para intraday: alinea al epoch (ej: H1 cierra en :00 de cada hora).
        Para D1: cierre NYSE a las 16:00 ET (maneja DST).
        """
        if intervalo_segundos >= 86400:
            # D1: calcular cierre NYSE dinamicamente
            ahora_ny = ahora.astimezone(NYSE_TZ)
            cierre_hoy_ny = ahora_ny.replace(
                hour=HORA_CIERRE_NYSE, minute=0, second=0, microsecond=0
            )
            if ahora_ny < cierre_hoy_ny:
                return cierre_hoy_ny.astimezone(timezone.utc)
            else:
                return None  # Ya paso el cierre de hoy

        # Intraday: alinear al epoch
        epoch_seg = int(ahora.timestamp())
        seg_en_barra = epoch_seg % intervalo_segundos
        seg_hasta_cierre = intervalo_segundos - seg_en_barra

        return ahora + timedelta(seconds=seg_hasta_cierre)

    # =========================================================================
    # Calculo de intervalo
    # =========================================================================

    def _calcular_intervalo_escaner(self, escaner: Escaner) -> int:
        """Calcula el intervalo optimo basado en el menor timeframe de los filtros."""
        if not self.obj_filtro_executor:
            return POLLING_INTERVAL_SECONDS

        try:
            timeframes = self.obj_filtro_executor.obtener_timeframes_necesarios(escaner.filtros)
            if not timeframes:
                return POLLING_INTERVAL_SECONDS

            min_intervalo = POLLING_INTERVAL_SECONDS
            for tf in timeframes:
                intervalo = INTERVALO_POR_TIMEFRAME.get(tf, POLLING_INTERVAL_SECONDS)
                min_intervalo = min(min_intervalo, intervalo)

            return max(60, min_intervalo)
        except Exception as e:
            logger.error(f"Error calculando intervalo para escaner {escaner.nombre}: {e}")
            return POLLING_INTERVAL_SECONDS

    @staticmethod
    def _parse_time(time_str: str) -> time:
        """Parsea un string de hora (HH:MM o HH:MM:SS) a time."""
        parts = time_str.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        second = int(parts[2]) if len(parts) > 2 else 0
        return time(hour, minute, second)
