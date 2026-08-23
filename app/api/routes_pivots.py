from fastapi import APIRouter, HTTPException

from app.analysis.pivots_finder import find_pivots
from app.scanner.marketdata_client import MarketdataClient

router = APIRouter(prefix="/signal-processing/pivots", tags=["pivots"])
_client = MarketdataClient()

# Solo D1 por ahora, igual que el catalogo de configuracion del indicador de
# salida en scanner-management-service.
_TIMEFRAME = "_1D"
_TRADING_DAYS_PER_YEAR = 252


@router.get("/{symbol}")
def get_pivots(
    symbol: str, atr_length: int = 14, slip_ratio_pct: float = 0.1,
    longitud_velas: int = 2, anios_historico: int = 5, numero_pivotes: int = 5,
):
    """Picos/valles de precio cercanos al precio actual de symbol en D1 --
    endpoint de exploracion para dibujar en el chart de Activos, todavia sin
    ligar a ningun escaner/orden."""
    bars = anios_historico * _TRADING_DAYS_PER_YEAR + 30
    candles_crudas = _client.fetch_candles([symbol], _TIMEFRAME, bars).get(symbol, [])
    # La vela D1 del dia en curso suele venir con high/low/close en None hasta
    # que cierra -- sin filtrarla, calculate_atr revienta con un 500 al restar
    # None (confirmado en vivo: fallaba para CUALQUIER simbolo, no solo uno
    # con historial corto).
    candles = [c for c in candles_crudas if c.high is not None and c.low is not None and c.close is not None]
    if len(candles) < atr_length + 1:
        raise HTTPException(status_code=404, detail="No hay suficiente historial D1 para este símbolo")

    current_price = _client.fetch_current_prices([symbol]).get(symbol)
    if current_price is None:
        raise HTTPException(status_code=404, detail="No se pudo obtener el precio actual del símbolo")

    resistencias, soportes = find_pivots(
        candles, current_price, atr_length=atr_length, slip_ratio_pct=slip_ratio_pct,
        longitud_velas=longitud_velas, number_pivots=numero_pivotes,
    )

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
