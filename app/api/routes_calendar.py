from datetime import datetime, timezone

from fastapi import APIRouter

from app.scanner.calendar import is_trading_day, next_trading_day

router = APIRouter(prefix="/signal-processing/calendar", tags=["calendar"])


@router.get("/estado")
def calendar_status():
    """hoyEsDiaHabil: si hoy se puede escanear. proximoDiaHabil: el
    siguiente dia habil DESPUES de hoy (fines de semana/feriados saltados),
    sin importar si hoy mismo lo es -- el frontend decide cual de los dos
    usar segun si la ventana de hoy ya paso o no."""
    today = datetime.now(timezone.utc).date()
    return {
        "hoyEsDiaHabil": is_trading_day(today),
        "proximoDiaHabil": next_trading_day(today).isoformat(),
    }
