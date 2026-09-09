from typing import List

from app.models.enums import EnumCategoriaFiltro, EnumFiltro
from app.models.filtro import Filtro

_STATIC_PRE: set[EnumCategoriaFiltro] = {
    EnumCategoriaFiltro.CARACTERISTICAS_FUNDAMENTALES,
}

_DYNAMIC_PRE: set[EnumCategoriaFiltro] = {
    EnumCategoriaFiltro.PRECIO_Y_MOVIMIENTO,
    EnumCategoriaFiltro.VOLUMEN,
}

_FILTRO_CATEGORY_FALLBACK: dict[EnumFiltro, EnumCategoriaFiltro] = {
    EnumFiltro.FLOAT: EnumCategoriaFiltro.CARACTERISTICAS_FUNDAMENTALES,
    EnumFiltro.SHARES_OUTSTANDING: EnumCategoriaFiltro.CARACTERISTICAS_FUNDAMENTALES,
    EnumFiltro.MARKET_CAP: EnumCategoriaFiltro.CARACTERISTICAS_FUNDAMENTALES,
    EnumFiltro.SHORT_INTEREST: EnumCategoriaFiltro.CARACTERISTICAS_FUNDAMENTALES,
    EnumFiltro.SHORT_RATIO: EnumCategoriaFiltro.CARACTERISTICAS_FUNDAMENTALES,
    EnumFiltro.DAYS_UNTIL_EARNINGS: EnumCategoriaFiltro.CARACTERISTICAS_FUNDAMENTALES,
    EnumFiltro.VOLUME: EnumCategoriaFiltro.VOLUMEN,
    EnumFiltro.VOLUMEN_POST_PRE: EnumCategoriaFiltro.VOLUMEN,
    EnumFiltro.CHANGE: EnumCategoriaFiltro.PRECIO_Y_MOVIMIENTO,
    EnumFiltro.PRECIO: EnumCategoriaFiltro.PRECIO_Y_MOVIMIENTO,
    EnumFiltro.GAP_FROM_CLOSE: EnumCategoriaFiltro.PRECIO_Y_MOVIMIENTO,
    EnumFiltro.POSITION_IN_RANGE: EnumCategoriaFiltro.PRECIO_Y_MOVIMIENTO,
    EnumFiltro.PERCENTAGE_RANGE: EnumCategoriaFiltro.PRECIO_Y_MOVIMIENTO,
    EnumFiltro.RANGE_DOLLARS: EnumCategoriaFiltro.PRECIO_Y_MOVIMIENTO,
    EnumFiltro.HALT: EnumCategoriaFiltro.PRECIO_Y_MOVIMIENTO,
    # DISTANCE_FROM_VWAP/EMA/MA, PERCENTAGE_CHANGE, AVERAGE_VOLUME,
    # RELATIVE_VOLUME(_SAME_TIME), VOLUME_SPIKE, CROSSING_ABOVE_BELOW NO van
    # aca: sus estrategias necesitan velas reales (promedios/comparacion
    # historica de volumen, EMA/VWAP, cambio sobre N barras) -- la etapa
    # dinamica solo construye MarketData con quote (candles=None siempre), asi
    # que listarlos aca hacia que compute_value devolviera None SIEMPRE, y
    # como se exige que todos los dinamicos pasen a la vez, ningun simbolo
    # podia pasar nunca (confirmado en vivo: "6149 -> 0" en cada ciclo para un
    # escaner con DISTANCE_FROM_VWAP). Sin entrada aca caen por defecto en
    # tecnicos, donde si se les pasan velas reales.
    #
    # VOLUME/POSITION_IN_RANGE/PERCENTAGE_RANGE/RANGE_DOLLARS/CHANGE si se
    # quedan aca porque son datos puntuales (no series historicas) que ya
    # vienen en el fundamental REST que _aplicar_dinamicos ya tiene en
    # memoria -- ver el enriquecimiento del quote mas abajo.
}


# Filtros cuya estrategia SIEMPRE necesita velas reales -- si la API manda
# una categoria de "precio y movimiento" o "volumen" para estos (bug
# confirmado en scanner-management-service: varias FiltroFactory*.java
# tenian la categoria de Java desalineada con lo que su propia estrategia
# Python necesita), no se puede confiar en esa categoria: la etapa dinamica
# construye MarketData con candles=None siempre, asi que compute_value
# devolveria None SIEMPRE y ningun simbolo pasaria nunca (confirmado en
# vivo: "2114 -> 0" en cada ciclo con PERCENTAGE_CHANGE). Esta lista manda
# por encima de lo que diga la API, no solo cuando la categoria viene vacia.
_REQUIERE_VELAS: set[EnumFiltro] = {
    EnumFiltro.PERCENTAGE_CHANGE,
    EnumFiltro.CROSSING_ABOVE_BELOW,
    EnumFiltro.VOLUME_SPIKE,
    EnumFiltro.RELATIVE_VOLUME,
    EnumFiltro.RELATIVE_VOLUME_SAME_TIME,
    EnumFiltro.AVERAGE_VOLUME,
    EnumFiltro.DISTANCE_FROM_VWAP,
    EnumFiltro.DISTANCE_FROM_EMA,
    EnumFiltro.DISTANCE_FROM_MA,
    EnumFiltro.BACK_TO_EMA_ALERT,
    EnumFiltro.THROUGH_EMA_VWAP_ALERT,
    EnumFiltro.EMA_VWAP_SUPPORT_RESISTANCE,
    # Mismo caso que PERCENTAGE_CHANGE: las FiltroFactory*.java de estos las
    # declaran PRECIO_Y_MOVIMIENTO (etapa dinamica, candles=None siempre)
    # pero sus estrategias leen data.candles (maximo/minimo del dia, ultimas
    # N velas, rango reciente) -- en la etapa dinamica devuelven None SIEMPRE
    # y ningun simbolo pasa (confirmado en vivo el 2026-08-24: el escaner
    # 'PRUEBA 23344' con BREAK_OVER_RECENT_HIGHS_LOWS + HIGH_LOW_OF_DAY daba
    # "dynamic filters 11532 -> 0" en cada ciclo).
    EnumFiltro.BREAK_OVER_RECENT_HIGHS_LOWS,
    EnumFiltro.HIGH_LOW_OF_DAY,
    EnumFiltro.PERCENTAGE_PULLBACK_HIGHS_LOWS,
}


def categorizar_filtros(filtros: List[Filtro]) -> tuple[List[Filtro], List[Filtro], List[Filtro]]:
    estaticos = []
    dinamicos = []
    tecnicos = []
    for f in filtros:
        if f.enumFiltro in _REQUIERE_VELAS:
            tecnicos.append(f)
            continue
        cat = f.objCategoria.enumCategoriaFiltro if f.objCategoria else None
        if cat is None and f.enumFiltro:
            cat = _FILTRO_CATEGORY_FALLBACK.get(f.enumFiltro)
        if cat in _STATIC_PRE:
            estaticos.append(f)
        elif cat in _DYNAMIC_PRE:
            dinamicos.append(f)
        else:
            tecnicos.append(f)
    return estaticos, dinamicos, tecnicos
