"""Adaptador de entrada: programa la ejecucion de escaneres segun su horario."""

import json
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
from domain.services.market_calendar_service import MarketCalendarService
from domain.services.time_sync_service import TimeSyncService
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


class EscanerScheduler:

    def __init__(self, obj_procesar_senales_cu, obj_filtro_executor=None):
        logger.info("Inicializando EscanerScheduler...")
        self.obj_procesar_senales_cu = obj_procesar_senales_cu
        self.obj_filtro_executor = obj_filtro_executor
        self.scheduler = BlockingScheduler(
            executors={'default': ThreadPoolExecutor(20)}
        )
        # {escaner_id: date} - evita ejecuciones repetidas en dias sin mercado
        self._mercado_cerrado_notificado = {}
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
                    func=self._ejecutar_con_validacion_mercado,
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

                # Ajustar hora_fin para el CronTrigger
                # Si termina a las 21:00 en punto, el Cron debe disparar solo hasta las 20:59 (hora 20)
                # Si termina a las 21:30, debe disparar en la hora 21.
                if hora_fin.minute == 0 and hora_fin.hour > hora_inicio.hour:
                    hora_fin_int = hora_fin.hour - 1
                else:
                    hora_fin_int = hora_fin.hour

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
                        func=self._ejecutar_con_validacion_mercado,
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
    # Validacion de mercado
    # =========================================================================

    def _ejecutar_con_validacion_mercado(self, escaner: Escaner) -> None:
        """Wrapper: verifica que el mercado este abierto y que la hora actual
        este dentro de la ventana hora_inicio-hora_fin antes de ejecutar.
        Si el mercado esta cerrado, publica 1 solo log por escaner+dia.
        """
        if not MarketCalendarService.es_dia_de_mercado():
            fecha_hoy = datetime.now(timezone.utc).date()
            if self._mercado_cerrado_notificado.get(escaner.id_escaner) == fecha_hoy:
                return  # Ya notificado hoy, no hacer nada

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

        # Validar ventana horaria (el CronTrigger incluye la hora completa,
        # p.ej. hour='14-21' dispara a las 21:43 aunque hora_fin=21:00)
        # Hacer la comparacion sin info de zona horaria (UTC implicito) para evitar TypeErrors
        ahora_time = datetime.now(timezone.utc).time().replace(tzinfo=None)
        hora_inicio_t = self._parse_time(escaner.hora_inicio)
        hora_fin_t = self._parse_time(escaner.hora_fin)

        # Si son exactamente las 21:00:00 (hora fin), permitimos la ejecucion si queremos capturar el cierre.
        # Pero si pasaron ya unos segundos/minutos (ej 21:05), cortamos.
        # Definimos una tolerancia de latencia (ej. 30 seg) para aceptar la ejecucion "en punto".
        # En general: Si ahora >= hora_fin + tolerancia -> RECHAZAR.
        
        # Logica estricta corregida:
        # Se ejecuta si: inicio <= ahora < fin
        # Excepcion: si ahora es apenas pasadito de fin (latencia del scheduler desencadenando a las 21:00:00.05)
        
        if ahora_time < hora_inicio_t:
             logger.info(
                f"Escaner '{escaner.nombre}' antes de hora inicio "
                f"(ahora={ahora_time.strftime('%H:%M:%S')}, inicio={escaner.hora_inicio}) — omitido"
            )
             sys.stdout.flush()
             return

        # Tolerancia de 59 segundos para la hora de cierre exacta
        # Ej: Fin 21:00:00. Ahora 21:00:58 -> OK (es el run de las 21:00). Ahora 21:01:00 -> OMITIR.
        tolerancia_cierre = timedelta(seconds=59)
        # Convertir a datetime dummy para poder sumar timedelta
        dummy_date = datetime(2000, 1, 1)
        dt_fin = dummy_date.replace(hour=hora_fin_t.hour, minute=hora_fin_t.minute, second=hora_fin_t.second)
        dt_ahora = dummy_date.replace(hour=ahora_time.hour, minute=ahora_time.minute, second=ahora_time.second)
        
        if dt_ahora > (dt_fin + tolerancia_cierre):
            logger.info(
                f"Escaner '{escaner.nombre}' despues de hora fin "
                f"(ahora={ahora_time.strftime('%H:%M:%S')}, fin={escaner.hora_fin}) — omitido"
            )
            sys.stdout.flush()
            return

        self.obj_procesar_senales_cu.ejecutar_escaner(escaner)

    # =========================================================================
    # Pre-despertar
    # =========================================================================

    def _ejecutar_con_pre_despertar(self, escaner: Escaner, intervalo_segundos: int) -> None:
        """Pre-despertar: despierta antes de la ejecucion real, recalcula el
        tiempo exacto hasta el cierre de la barra usando TimeSyncService,
        duerme hasta ese momento, y ejecuta el escaner.
        """
        # Validar mercado antes del pre-despertar
        if not MarketCalendarService.es_dia_de_mercado():
            fecha_hoy = datetime.now(timezone.utc).date()
            if self._mercado_cerrado_notificado.get(escaner.id_escaner) == fecha_hoy:
                return
            self._mercado_cerrado_notificado[escaner.id_escaner] = fecha_hoy
            razon = MarketCalendarService.obtener_razon_mercado_cerrado()
            logger.info(f"Pre-despertar {escaner.nombre} OMITIDO: {razon}")

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

        # Validar ventana horaria también en pre-despertar
        # Comparacion tz-naive (UTC implicito)
        ahora = datetime.now(timezone.utc)
        ahora_time = ahora.time().replace(tzinfo=None)
        hora_inicio_t = self._parse_time(escaner.hora_inicio)
        hora_fin_t = self._parse_time(escaner.hora_fin)

        if ahora_time < hora_inicio_t:
             logger.info(
                f"Pre-despertar '{escaner.nombre}' antes de hora inicio "
                f"(ahora={ahora_time.strftime('%H:%M:%S')}, inicio={escaner.hora_inicio}) — omitido"
            )
             sys.stdout.flush()
             return

        # Tolerancia de 59 segundos para la hora de cierre exacta
        tolerancia_cierre = timedelta(seconds=59)
        dummy_date = datetime(2000, 1, 1)
        dt_fin = dummy_date.replace(hour=hora_fin_t.hour, minute=hora_fin_t.minute, second=hora_fin_t.second)
        dt_ahora = dummy_date.replace(hour=ahora_time.hour, minute=ahora_time.minute, second=ahora_time.second)
        
        if dt_ahora > (dt_fin + tolerancia_cierre):
            logger.info(
                f"Pre-despertar '{escaner.nombre}' despues de hora fin "
                f"(ahora={ahora_time.strftime('%H:%M:%S')}, fin={escaner.hora_fin}) — omitido"
            )
            sys.stdout.flush()
            return

        # Sincroniza y duerme hasta el cierre exacto de la barra
        executed = TimeSyncService.sleep_hasta_proximo_cierre(intervalo_segundos, PRE_DESPERTAR_MARGEN_SEGUNDOS)
        
        if executed:
            self.obj_procesar_senales_cu.ejecutar_escaner(escaner)

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
