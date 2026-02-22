"""Servicio de dominio para manejar el calendario de mercado y feriados."""

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

NYSE_TZ = ZoneInfo("America/New_York")
HORA_CIERRE_NYSE = 16  # 4:00 PM ET

# Feriados NYSE 2026 (dias completos sin mercado)
FERIADOS_NYSE_2026 = {
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

class MarketCalendarService:
    """Clase encapsulando la logica del calendario del mercado."""

    @staticmethod
    def es_dia_de_mercado() -> bool:
        """Verifica si hoy es un dia de mercado (lun-vie, sin feriados NYSE)."""
        now = datetime.now(timezone.utc)
        if now.weekday() >= 5:
            return False
        fecha_hoy = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return fecha_hoy not in FERIADOS_NYSE_2026

    @staticmethod
    def obtener_razon_mercado_cerrado() -> str:
        """Retorna una descripcion legible de por que el mercado esta cerrado."""
        now = datetime.now(timezone.utc)
        if now.weekday() == 5:
            return "Mercado cerrado (Sabado)"
        if now.weekday() == 6:
            return "Mercado cerrado (Domingo)"
        fecha_hoy = now.replace(hour=0, minute=0, second=0, microsecond=0)
        nombre = FERIADOS_NYSE_2026.get(fecha_hoy)
        if nombre:
            return f"Mercado cerrado (Feriado: {nombre})"
        return "Mercado cerrado (razon desconocida)"
