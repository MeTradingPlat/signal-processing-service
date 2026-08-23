from datetime import datetime

from app.analysis.pivots_atr import calculate_atr
from app.analysis.pivots_cluster import merge_and_limit
from app.analysis.pivots_swing import find_swings_in_range
from app.scanner.marketdata_models import CandleResponse

# (timestamp, precio, "strong" | "weak") -- la referencia (PivotsAlpaca)
# dibujaba las 4 categorias por separado (Pico/Valle Fuerte/Debil), no las
# fusionaba en un solo "resistencia"/"soporte" generico.
PivotLevel = tuple[datetime, float, str]

# Mismos multiplicadores de ATR que PivotsAlpaca: 3x define el rango de
# precio donde se buscan pivotes, no es un parametro configurable por ahora.
_PRICE_RANGE_SCALING = 3


def find_pivots(
    candles: list[CandleResponse], current_price: float, *,
    atr_length: int = 14, slip_ratio_pct: float = 0.1, longitud_velas: int = 2, number_pivots: int = 5,
) -> tuple[list[PivotLevel], list[PivotLevel]]:
    """Devuelve (resistencias, soportes) cercanos a current_price, cada una
    con su fuerza. Un pivote "fuerte" es uno que ya cae del lado correcto del
    precio (pico arriba = resistencia, valle abajo = soporte); si no hay
    suficientes fuertes, se completa con "debiles" -- el pivote del tipo
    opuesto que igual quedo del lado correcto (un valle que quedo arriba
    actua como techo, un pico que quedo abajo actua como piso)."""
    atr = calculate_atr(candles, atr_length)
    price_range = _PRICE_RANGE_SCALING * atr
    slip_ratio = slip_ratio_pct * atr

    peaks, valleys = find_swings_in_range(candles, current_price, price_range, longitud_velas)

    resistencias_fuertes = merge_and_limit(
        [p for p in peaks if p[1] > current_price], current_price, slip_ratio, number_pivots)
    soportes_fuertes = merge_and_limit(
        [v for v in valleys if v[1] < current_price], current_price, slip_ratio, number_pivots)

    resistencias: list[PivotLevel] = [(ts, price, "strong") for ts, price in resistencias_fuertes]
    soportes: list[PivotLevel] = [(ts, price, "strong") for ts, price in soportes_fuertes]

    if len(resistencias) < number_pivots:
        debiles = [v for v in valleys if v[1] > current_price]
        elegidos = merge_and_limit(debiles, current_price, slip_ratio, number_pivots - len(resistencias))
        resistencias += [(ts, price, "weak") for ts, price in elegidos]
    if len(soportes) < number_pivots:
        debiles = [p for p in peaks if p[1] < current_price]
        elegidos = merge_and_limit(debiles, current_price, slip_ratio, number_pivots - len(soportes))
        soportes += [(ts, price, "weak") for ts, price in elegidos]

    return resistencias, soportes
