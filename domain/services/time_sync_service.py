"""Servicio de dominio para sincronizacion de tiempo y sleep exacto inspirado en mt5_bot."""

import logging
import time as time_mod
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

NYSE_TZ = ZoneInfo("America/New_York")
HORA_CIERRE_NYSE = 16  # 4:00 PM ET

class TimeSyncService:
    """Clase encapsulando la logica de medicion de tiempo y pre-despertar."""

    @staticmethod
    def sleep_hasta_proximo_cierre(intervalo_segundos: int, margen_segundos: int = 0) -> bool:
        """
        Calcula el timestamp UTC del proximo cierre de barra basado en el intervalo.
        Duerme hasta ese momento exacto + margen_segundos.
        Retorna True si durmio exitosamente, False si ya cerro o no calculable (ej: D1 ya paso).
        """
        ahora = datetime.now(timezone.utc)
        ts_cierre = TimeSyncService.calcular_proximo_cierre_barra(ahora, intervalo_segundos)

        if ts_cierre is None:
            # El cierre de la barra del dia ya ocurrio (p.ej. D1 cierra a las 16:00 ET)
            logger.info(f"TimeSync: El mercado (NYSE/D1) ya ha cerrado por hoy ({HORA_CIERRE_NYSE}:00 ET). No se esperan nuevas barras hasta el proximo periodo.")
            return False

        segundos_restantes = (ts_cierre - ahora).total_seconds()

        if segundos_restantes <= 0:
            logger.info(f"TimeSync: Barra ya cerrada (diff={segundos_restantes:.1f}s), ejecutando.")
            return True

        # Agregar margen para dar tiempo a que los datos esten disponibles
        segundos_restantes += margen_segundos

        logger.info(f"TimeSync: Esperando {segundos_restantes:.1f}s hasta cierre de barra ({ts_cierre.isoformat()}).")
        time_mod.sleep(segundos_restantes)
        logger.info("TimeSync: Sleep completado.")
        
        return True

    @staticmethod
    def calcular_proximo_cierre_barra(ahora: datetime, intervalo_segundos: int) -> datetime | None:
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
