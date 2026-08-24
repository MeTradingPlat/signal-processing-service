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


def _fetch_clean_candles(symbol: str, years: int):
    bars = years * _TRADING_DAYS_PER_YEAR + 30
    candles_crudas = _client.fetch_candles([symbol], _TIMEFRAME, bars).get(symbol, [])
    # La vela D1 del dia en curso suele venir con high/low/close en None hasta
    # que cierra -- sin filtrarla, calculate_atr revienta con un 500 al restar
    # None (confirmado en vivo: fallaba para CUALQUIER simbolo, no solo uno
    # con historial corto).
    return [c for c in candles_crudas if c.high is not None and c.low is not None and c.close is not None]


@router.get("/{symbol}")
def get_pivots(
    symbol: str, atr_length: int = 14, slip_ratio_pct: float = 0.1,
    longitud_velas: int = 2, anios_historico: int = 4, numero_pivotes: int = 5,
):
    """Picos/valles de precio cercanos al precio actual de symbol en D1 --
    endpoint de exploracion para dibujar en el chart de Activos, todavia sin
    ligar a ningun escaner/orden.

    Expansion progresiva de historial (1..anios_historico años), igual que
    PivotsAlpaca: si el primer año ya encuentra suficientes pivotes fuertes,
    no se pide mas historial. El ATR se calcula una sola vez, con el primer
    año que alcance para calcularlo, y se reusa en las expansiones
    siguientes (igual que el original: no se recalcula al crecer el
    historial). Los pivotes debiles solo se buscan en el ultimo intento (el
    de historial mas profundo), como relleno final si aun faltan fuertes.
    """
    current_price = _client.fetch_current_prices([symbol]).get(symbol)
    if current_price is None:
        raise HTTPException(status_code=404, detail="No se pudo obtener el precio actual del símbolo")

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
