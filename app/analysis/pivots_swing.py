from datetime import datetime

from app.scanner.marketdata_models import CandleResponse

PivotPoint = tuple[datetime, float]


def find_swings_in_range(
    candles: list[CandleResponse], current_price: float, price_range: float, longitud_velas: int,
) -> tuple[list[PivotPoint], list[PivotPoint]]:
    """Picos/valles (vela mas alta/baja que TODAS sus longitud_velas vecinas
    a cada lado) dentro de un rango de precio alrededor de current_price --
    version simplificada y simetrica del patron de 5 velas de PivotsAlpaca
    (ese hardcodeaba +/-2 y comparaba solo contra 3 de las 4 vecinas por una
    asimetria sin explicacion en el original)."""
    peaks: list[PivotPoint] = []
    valleys: list[PivotPoint] = []
    n = len(candles)

    for i in range(longitud_velas, n - longitud_velas):
        high = candles[i].high
        low = candles[i].low
        if high is None or low is None:
            continue
        vecinos = candles[i - longitud_velas:i] + candles[i + 1:i + longitud_velas + 1]
        vecinos_high = [c.high for c in vecinos if c.high is not None]
        vecinos_low = [c.low for c in vecinos if c.low is not None]

        if abs(high - current_price) < price_range and vecinos_high and high > max(vecinos_high):
            peaks.append((candles[i].timestamp, high))
        if abs(low - current_price) < price_range and vecinos_low and low < min(vecinos_low):
            valleys.append((candles[i].timestamp, low))

    return peaks, valleys
