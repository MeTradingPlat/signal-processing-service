from datetime import datetime

from app.analysis.pivots_cluster import merge_and_limit
from app.analysis.pivots_swing import PivotPoint, find_swings_in_range
from app.scanner.marketdata_models import CandleResponse

# (timestamp, precio, "strong" | "weak") -- la referencia (PivotsAlpaca)
# dibujaba las 4 categorias por separado (Pico/Valle Fuerte/Debil), no las
# fusionaba en un solo "resistencia"/"soporte" generico.
PivotLevel = tuple[datetime, float, str]

# Mismo multiplicador que PivotsAlpaca: 3x ATR define el rango de precio
# donde se buscan pivotes, no es un parametro configurable por ahora.
PRICE_RANGE_SCALING = 3


def find_strong_pivots(
    candles: list[CandleResponse], current_price: float, price_range: float,
    slip_ratio: float, longitud_velas: int, number_pivots: int,
) -> tuple[list[PivotPoint], list[PivotPoint], list[PivotPoint], list[PivotPoint]]:
    """Pivotes fuertes (del lado correcto del precio actual) dentro del
    historial dado. Devuelve tambien los peaks/valleys crudos (para que el
    llamador pueda buscar debiles despues sin recalcular el swing detection)."""
    peaks, valleys = find_swings_in_range(candles, current_price, price_range, longitud_velas)
    resistencias = merge_and_limit(
        [p for p in peaks if p[1] > current_price], current_price, slip_ratio, number_pivots)
    soportes = merge_and_limit(
        [v for v in valleys if v[1] < current_price], current_price, slip_ratio, number_pivots)
    return resistencias, soportes, peaks, valleys


def find_weak_pivots(
    peaks: list[PivotPoint], valleys: list[PivotPoint], current_price: float, slip_ratio: float,
    resistencias_fuertes: list[PivotPoint], soportes_fuertes: list[PivotPoint], number_pivots: int,
) -> tuple[list[PivotLevel], list[PivotLevel]]:
    """Completa con debiles (relleno automatico, ver find_pivots) lo que
    falte hasta number_pivots por lado. Si ya hay suficientes fuertes, no
    agrega nada -- igual que PivotsAlpaca solo busca debiles cuando faltan."""
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


def find_pivots(
    candles: list[CandleResponse], current_price: float, *,
    atr_length: int = 14, slip_ratio_pct: float = 0.1, longitud_velas: int = 2, number_pivots: int = 5,
) -> tuple[list[PivotLevel], list[PivotLevel]]:
    """Version de una sola pasada (sin la expansion progresiva de historial
    que hace el endpoint) -- usada por los tests unitarios, donde el
    historial completo ya esta disponible de entrada."""
    from app.analysis.pivots_atr import calculate_atr

    atr = calculate_atr(candles, atr_length)
    price_range = PRICE_RANGE_SCALING * atr
    slip_ratio = slip_ratio_pct * atr

    resistencias_fuertes, soportes_fuertes, peaks, valleys = find_strong_pivots(
        candles, current_price, price_range, slip_ratio, longitud_velas, number_pivots)

    return find_weak_pivots(
        peaks, valleys, current_price, slip_ratio, resistencias_fuertes, soportes_fuertes, number_pivots)
