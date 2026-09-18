from typing import Literal

from fastapi import APIRouter, HTTPException

from app.analysis.pivots_atr import calculate_atr
from app.analysis.pivots_finder import PRICE_RANGE_SCALING, find_strong_pivots, find_weak_pivots
from app.scanner.marketdata_client import MarketdataClient

router = APIRouter(prefix="/signal-processing/pivots", tags=["pivots"])
_client = MarketdataClient()

# Solo D1 por ahora, igual que el catalogo de configuracion del indicador de
# salida en scanner-management-service.
_TIMEFRAME = "_1D"
_TRADING_DAYS_PER_YEAR = 252

PriceReference = Literal["live", "open", "prev_close", "signal"]


def _bars_for_years(years: int) -> int:
    return years * _TRADING_DAYS_PER_YEAR + 30


def _fetch_clean_candles(symbol: str, years: int):
    candles_crudas = _client.fetch_candles([symbol], _TIMEFRAME, _bars_for_years(years)).get(symbol, [])
    # La vela D1 del dia en curso suele venir con high/low/close en None hasta
    # que cierra -- sin filtrarla, calculate_atr revienta con un 500 al restar
    # None (confirmado en vivo: fallaba para CUALQUIER simbolo, no solo uno
    # con historial corto).
    return [c for c in candles_crudas if c.high is not None and c.low is not None and c.close is not None]


# El precio ancla desde el cual se buscan pivots arriba/abajo -- "live" es el
# de siempre (ultimo trade real). "open" y "prev_close" son relativos a la
# ULTIMA vela D1 que exista, sea de hoy o no (fin de semana, feriado, mercado
# recien cerrado): "open" es la apertura de esa ultima vela (crudo, sin el
# filtro de _fetch_clean_candles -- si sigue en formacion ya tiene open
# seteado aunque high/low/close todavia esten en None), "prev_close" es el
# cierre de la vela INMEDIATA ANTERIOR a esa, este cerrada o no la ultima.
# "signal" no resuelve nada del mercado -- usa el precio EXACTO al que
# disparo una senal del escaner (viene del frontend, ver
# PivotsConfigDialog/symbol-chart.component.ts), asi que exige
# explicit_price y no tiene sentido si la senal no trae precio.
def _resolve_current_price(symbol: str, reference: PriceReference, explicit_price: float | None) -> float | None:
    if reference == "signal":
        return explicit_price
    if reference == "live":
        return _client.fetch_current_prices([symbol]).get(symbol)
    crudas = _client.fetch_candles([symbol], _TIMEFRAME, 2).get(symbol, [])
    if reference == "open":
        return crudas[-1].open if crudas else None
    if reference == "prev_close":
        return crudas[-2].close if len(crudas) >= 2 else None
    return None


@router.get("/{symbol}")
def get_pivots(
    symbol: str, atr_length: int = 14, slip_ratio_pct: float = 0.1,
    longitud_velas: int = 2, anios_historico: int = 4, numero_pivotes: int = 5,
    price_reference: PriceReference = "live", explicit_price: float | None = None,
):
    """Picos/valles de precio cercanos al precio actual de symbol en D1 --
    endpoint de exploracion para dibujar en el chart de Activos, todavia sin
    ligar a ningun escaner/orden.

    Expansion progresiva de historial (1..anios_historico años), igual que
    PivotsAlpaca: si el primer año ya encuentra suficientes pivotes fuertes,
    no se pide mas historial -- para la mayoria de los simbolos esto basta,
    y evita tocar chunks viejos comprimidos de TimescaleDB (mas lentos de
    leer) que solo hacen falta para el caso raro que necesita años de
    historial. El ATR se calcula una sola vez, con el primer año que
    alcance para calcularlo, y se reusa en las expansiones siguientes
    (igual que el original: no se recalcula al crecer el historial). Los
    pivotes debiles solo se buscan en el ultimo intento (el de historial
    mas profundo), como relleno final si aun faltan fuertes.
    """
    current_price = _resolve_current_price(symbol, price_reference, explicit_price)
    if current_price is None:
        if price_reference == "live":
            detail = "No se pudo obtener el precio actual del símbolo"
        elif price_reference == "signal":
            detail = "La señal no trae un precio para calcular pivots"
        else:
            detail = "No hay suficiente historial D1 para este símbolo"
        raise HTTPException(status_code=404, detail=detail)

    atr = None
    resistencias_fuertes: list = []
    soportes_fuertes: list = []
    peaks: list = []
    valleys: list = []

    for year in range(1, anios_historico + 1):
        candles = _fetch_clean_candles(symbol, year)
        if len(candles) < atr_length + 1:
            continue

        if atr is None:
            atr = calculate_atr(candles, atr_length)
        price_range = PRICE_RANGE_SCALING * atr
        slip_ratio = slip_ratio_pct * atr

        resistencias_fuertes, soportes_fuertes, peaks, valleys = find_strong_pivots(
            candles, current_price, price_range, slip_ratio, longitud_velas, numero_pivotes)

        if len(resistencias_fuertes) >= numero_pivotes and len(soportes_fuertes) >= numero_pivotes:
            break

    if atr is None:
        raise HTTPException(status_code=404, detail="No hay suficiente historial D1 para este símbolo")

    resistencias, soportes = find_weak_pivots(
        peaks, valleys, current_price, slip_ratio, resistencias_fuertes, soportes_fuertes, numero_pivotes)

    return {
        "symbol": symbol,
        "currentPrice": current_price,
        "timeframe": "D1",
        "resistances": [
            {"timestamp": ts.isoformat(), "price": price, "strength": strength}
            for ts, price, strength in resistencias
        ],
        "supports": [
            {"timestamp": ts.isoformat(), "price": price, "strength": strength}
            for ts, price, strength in soportes
        ],
    }
