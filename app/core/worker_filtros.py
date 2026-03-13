"""Worker de filtros ejecutado en ProcessPoolExecutor.

Implementa todas las estrategias del scanner-management-service.

Estandarización de valores (igual que scanner-management y frontend):
  - Porcentajes   : valor raw (1 % → 1.0,  10 % → 10.0)
  - Dólares       : valor raw (1.5 → $1.50)
  - Volumen       : shares reales (100_000 → 100 000 acciones)
  - Volumen relat.: como % (150 → 150 % = 1.5× el promedio)
  - RSI           : índice 0–100
  - ATR           : en unidades de precio ($)
  - ATRP          : en % del precio (1 → 1 %)
  - Distancia EMA/VWAP/MA: en % (5 → 5 %)
"""

from __future__ import annotations

import pandas as pd

from app.domain.enums import EnumCondicional
from app.domain.models.escaner import ValorCondicional

# ══════════════════════════════════════════════════════════════════════════════
# Helpers para leer parámetros
# ══════════════════════════════════════════════════════════════════════════════

def _leer_condicional(parametros: list[dict]) -> ValorCondicional | None:
    """Extrae el primer parámetro de tipo CONDICIONAL."""
    for p in parametros:
        val = p.get("obj_valor_seleccionado")
        if val and val.get("enumTipoValor") == "CONDICIONAL":
            return ValorCondicional(
                enum_condicional=val.get("enumCondicional", ""),
                valor1=val.get("valor1"),
                valor2=val.get("valor2"),
                is_integer=val.get("isInteger", False),
            )
    return None


def _leer_int(parametros: list[dict], *claves: str, default: int = 0) -> int:
    """Lee el primer param INTEGER/FLOAT cuyo enum_parametro contenga alguna clave."""
    for p in parametros:
        enum_p = p.get("enum_parametro", "")
        if any(c in enum_p for c in claves):
            val = p.get("obj_valor_seleccionado")
            if val and val.get("enumTipoValor") in ("INTEGER", "FLOAT"):
                v = val.get("valor")
                if v is not None:
                    return int(v)
    return default


def _leer_float(parametros: list[dict], *claves: str, default: float = 0.0) -> float:
    for p in parametros:
        enum_p = p.get("enum_parametro", "")
        if any(c in enum_p for c in claves):
            val = p.get("obj_valor_seleccionado")
            if val and val.get("enumTipoValor") in ("FLOAT", "INTEGER"):
                v = val.get("valor")
                if v is not None:
                    return float(v)
    return default


def _leer_str(parametros: list[dict], *claves: str, default: str = "") -> str:
    for p in parametros:
        enum_p = p.get("enum_parametro", "")
        if any(c in enum_p for c in claves):
            val = p.get("obj_valor_seleccionado")
            if val:
                return str(val.get("valor") or val.get("etiqueta") or "")
    return default


# ══════════════════════════════════════════════════════════════════════════════
# evaluar_condicional — lógica de comparación
# ══════════════════════════════════════════════════════════════════════════════

def evaluar_condicional(valor_calculado: float, condicional: ValorCondicional) -> bool:
    """Evalúa si un valor calculado cumple la condición configurada."""
    if condicional.valor1 is None:
        return True

    cond = condicional.enum_condicional
    v1   = condicional.valor1
    v2   = condicional.valor2

    if cond == EnumCondicional.MAYOR_QUE:
        return valor_calculado > v1
    if cond == EnumCondicional.MENOR_QUE:
        return valor_calculado < v1
    if cond == EnumCondicional.ENTRE:
        return v1 <= valor_calculado <= v2 if v2 is not None else True
    if cond == EnumCondicional.FUERA:
        return (valor_calculado < v1 or valor_calculado > v2) if v2 is not None else True
    if cond == EnumCondicional.IGUAL_A:
        return valor_calculado == v1
    return True


# ══════════════════════════════════════════════════════════════════════════════
# VOLUMEN
# ══════════════════════════════════════════════════════════════════════════════

def _evaluar_volume(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """VOLUME — volumen de la última vela vs umbral (en shares)."""
    cond = _leer_condicional(parametros)
    if cond is None or df.empty:
        return True
    return evaluar_condicional(float(df["volume"].iloc[-1]), cond)


def _evaluar_average_volume(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """AVERAGE_VOLUME — volumen promedio de todas las velas vs umbral."""
    cond = _leer_condicional(parametros)
    if cond is None or df.empty:
        return True
    return evaluar_condicional(float(df["volume"].mean()), cond)


def _evaluar_relative_volume(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """RELATIVE_VOLUME — (vol_actual / vol_promedio) × 100 vs umbral (en %).
    Ej.: valor1=150 → volumen 1.5× el promedio."""
    cond = _leer_condicional(parametros)
    if cond is None or len(df) < 2:
        return True
    avg = float(df["volume"].iloc[:-1].mean())
    if avg == 0:
        return True
    rel = (float(df["volume"].iloc[-1]) / avg) * 100
    return evaluar_condicional(rel, cond)


def _evaluar_relative_volume_same_time(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """RELATIVE_VOLUME_SAME_TIME — igual que RELATIVE_VOLUME (sin datos de misma hora)."""
    return _evaluar_relative_volume(df, parametros)


def _evaluar_volume_spike(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """VOLUME_SPIKE — vol_actual / promedio_N_velas previas vs umbral (multiplicador).
    NUMERO_VELAS_VOLUME_SPIKE: cuántas velas comparar (default 10).
    CONDICION compara el ratio (ej. MAYOR_QUE 3 = más de 3× el promedio)."""
    cond = _leer_condicional(parametros)
    n    = _leer_int(parametros, "NUMERO_VELAS", default=10)
    if cond is None or len(df) < 2:
        return True
    n = max(1, min(n, len(df) - 1))
    avg = float(df["volume"].iloc[-n - 1:-1].mean())
    if avg == 0:
        return True
    ratio = float(df["volume"].iloc[-1]) / avg
    return evaluar_condicional(ratio, cond)


def _evaluar_volumen_post_pre(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """VOLUMEN_POST_PRE — volumen de la sesión pre/post-market.

    SESION_VOLUMEN_POST_PRE: PRE (4:00-9:30 ET), POST (16:00-20:00 ET), AMBOS.
    Valor en acciones raw (ej. 500_000 = 500K acciones).
    Datos provienen del FundamentalsCache (yfinance extended hours)."""
    sesion = _leer_str(parametros, "SESION_VOLUMEN_POST_PRE", "SESION", default="AMBOS")
    cond   = _leer_condicional(parametros)
    if cond is None:
        return True

    fund     = df.attrs.get("fundamentales", {})
    pre_vol  = fund.get("pre_market_volume")  or 0
    post_vol = fund.get("post_market_volume") or 0

    if sesion == "PRE":
        vol = pre_vol
    elif sesion == "POST":
        vol = post_vol
    else:  # AMBOS
        vol = pre_vol + post_vol

    if vol == 0 and pre_vol == 0 and post_vol == 0 and "pre_market_volume" not in fund:
        return False  # sin datos en caché → restrictivo (se descarta)

    return evaluar_condicional(float(vol), cond)


# ══════════════════════════════════════════════════════════════════════════════
# PRECIO Y MOVIMIENTO
# ══════════════════════════════════════════════════════════════════════════════

def _evaluar_precio(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """PRECIO — precio actual (close) vs umbral en dólares."""
    cond = _leer_condicional(parametros)
    if cond is None or df.empty:
        return True
    return evaluar_condicional(float(df["close"].iloc[-1]), cond)


def _evaluar_change(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """CHANGE — cambio desde punto de referencia.
    TIPO_MEDIDA_CHANGE: PRECIO ($) o PORCENTAJE (%).
    PUNTO_REFERENCIA_CHANGE: OPEN (open[0]) o CLOSE/otros (close[-2]).
    Valores en $ o % según tipo de medida."""
    cond      = _leer_condicional(parametros)
    referencia = _leer_str(parametros, "PUNTO_REFERENCIA", default="OPEN")
    medida     = _leer_str(parametros, "TIPO_MEDIDA", default="PORCENTAJE")
    if cond is None or df.empty:
        return True

    close_actual = float(df["close"].iloc[-1])

    if referencia == "OPEN":
        ref = float(df["open"].iloc[0])
    elif referencia == "CLOSE" and len(df) >= 2:
        ref = float(df["close"].iloc[-2])
    else:
        ref = float(df["open"].iloc[0])

    if ref == 0:
        return True

    if medida == "PRECIO":
        valor = close_actual - ref
    else:
        valor = ((close_actual - ref) / ref) * 100

    return evaluar_condicional(valor, cond)


def _evaluar_percentage_change(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """PERCENTAGE_CHANGE — cambio % desde la primera vela hasta la última.
    Valores en % (ej. valor1=-30 → bajó más de 30 %)."""
    cond = _leer_condicional(parametros)
    if cond is None or df.empty:
        return True
    ref = float(df["open"].iloc[0])
    if ref == 0:
        return True
    pct = ((float(df["close"].iloc[-1]) - ref) / ref) * 100
    return evaluar_condicional(pct, cond)


def _evaluar_gap_from_close(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """GAP_FROM_CLOSE — gap entre el open de la sesión y el close anterior.
    FORMATO_GAP_FROM_CLOSE: PRECIO ($) o PORCENTAJE (%).
    Requiere ≥2 velas."""
    cond    = _leer_condicional(parametros)
    formato = _leer_str(parametros, "FORMATO", default="PRECIO")
    if cond is None or len(df) < 2:
        return True
    open_actual  = float(df["open"].iloc[-1])
    prev_close   = float(df["close"].iloc[-2])
    if prev_close == 0:
        return True
    if formato == "PORCENTAJE":
        valor = ((open_actual - prev_close) / prev_close) * 100
    else:
        valor = open_actual - prev_close
    return evaluar_condicional(valor, cond)


def _evaluar_position_in_range(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """POSITION_IN_RANGE — posición del close dentro del rango high-low (%).
    0 % = mínimo del periodo, 100 % = máximo.
    Valores en % (ej. valor1=20, valor2=80)."""
    cond = _leer_condicional(parametros)
    if cond is None or df.empty:
        return True
    max_h = float(df["high"].max())
    min_l = float(df["low"].min())
    rango = max_h - min_l
    if rango == 0:
        return True
    pos = ((float(df["close"].iloc[-1]) - min_l) / rango) * 100
    return evaluar_condicional(pos, cond)


def _evaluar_percentage_range(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """PERCENTAGE_RANGE — (high - low) / close × 100 de la última vela (%).
    Valores en % (ej. valor1=2 → rango > 2 %)."""
    cond = _leer_condicional(parametros)
    if cond is None or df.empty:
        return True
    close = float(df["close"].iloc[-1])
    if close == 0:
        return True
    rango_pct = ((float(df["high"].iloc[-1]) - float(df["low"].iloc[-1])) / close) * 100
    return evaluar_condicional(rango_pct, cond)


def _evaluar_range_dollars(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """RANGE_DOLLARS — (high - low) de la última vela en dólares.
    Valores en $ (ej. valor1=0.10 → rango > $0.10)."""
    cond = _leer_condicional(parametros)
    if cond is None or df.empty:
        return True
    rango = float(df["high"].iloc[-1]) - float(df["low"].iloc[-1])
    return evaluar_condicional(rango, cond)


def _evaluar_crossing_above_below(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """CROSSING_ABOVE_BELOW — precio cruzó el nivel de referencia en la última vela.
    NIVEL_CRUCE: OPEN, CLOSE, VWAP, EMA.
    PERIODO_EMA_CROSSING_ABOVE_BELOW: periodo para EMA.
    Detecta cualquier cruce (sin importar dirección)."""
    import pandas_ta as ta

    nivel  = _leer_str(parametros, "NIVEL_CRUCE", default="OPEN")
    period = _leer_int(parametros, "PERIODO_EMA_CROSSING", default=20)

    if len(df) < 2:
        return True

    curr_close = float(df["close"].iloc[-1])
    prev_close = float(df["close"].iloc[-2])

    if nivel == "OPEN":
        ref = float(df["open"].iloc[-1])
    elif nivel == "CLOSE":
        ref = float(df["close"].iloc[-2]) if len(df) >= 3 else float(df["open"].iloc[0])
    elif nivel == "EMA":
        ema = ta.ema(df["close"], length=period)
        if ema is None or ema.dropna().empty:
            return True
        ref = float(ema.iloc[-1])
    elif nivel == "VWAP":
        vwap = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
        if vwap is None or vwap.dropna().empty:
            return True
        ref = float(vwap.iloc[-1])
    else:
        ref = float(df["open"].iloc[-1])

    # Cruce: lados opuestos del nivel
    return (prev_close - ref) * (curr_close - ref) < 0


def _evaluar_halt(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """HALT — bloquea el símbolo si está actualmente halteado por NASDAQ.

    Retorna False (no pasa el filtro) si el símbolo está halteado.
    El estado de halt llega en df.attrs["halteado"] inyectado por EjecutorEscaner
    desde el HaltMonitor. Si no hay datos → permisivo (True)."""
    return not df.attrs.get("halteado", False)


# ══════════════════════════════════════════════════════════════════════════════
# VOLATILIDAD
# ══════════════════════════════════════════════════════════════════════════════

def _evaluar_atr(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """ATR — Average True Range vs umbral en dólares.
    LONGITUD_ATR: periodo (default 14).
    Valores en $ (ej. valor1=0.01 → ATR > $0.01)."""
    import pandas_ta as ta

    periodo = _leer_int(parametros, "LONGITUD_ATR", "PERIODO_ATR", default=14)
    cond    = _leer_condicional(parametros)
    if cond is None or len(df) < periodo + 1:
        return True
    atr = ta.atr(df["high"], df["low"], df["close"], length=periodo)
    if atr is None or atr.dropna().empty:
        return True
    return evaluar_condicional(float(atr.iloc[-1]), cond)


def _evaluar_atrp(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """ATRP — ATR como porcentaje del precio: (ATR / close) × 100.
    PERIODO_ATR_ATRP: periodo (default 14).
    Valores en % (ej. valor1=0.1 → ATRP > 0.1 %)."""
    import pandas_ta as ta

    periodo = _leer_int(parametros, "PERIODO_ATR_ATRP", "PERIODO_ATR", "LONGITUD", default=14)
    cond    = _leer_condicional(parametros)
    if cond is None or len(df) < periodo + 1:
        return True
    atr = ta.atr(df["high"], df["low"], df["close"], length=periodo)
    if atr is None or atr.dropna().empty:
        return True
    close = float(df["close"].iloc[-1])
    if close == 0:
        return True
    atrp = (float(atr.iloc[-1]) / close) * 100
    return evaluar_condicional(atrp, cond)


def _evaluar_relative_range(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """RELATIVE_RANGE — (high - low) / ATR × 100 de la última vela (%).
    Valores en % (ej. valor1=50 → rango > 50 % del ATR)."""
    import pandas_ta as ta

    periodo = 14
    cond    = _leer_condicional(parametros)
    if cond is None or len(df) < periodo + 1:
        return True
    atr = ta.atr(df["high"], df["low"], df["close"], length=periodo)
    if atr is None or atr.dropna().empty:
        return True
    atr_val = float(atr.iloc[-1])
    if atr_val == 0:
        return True
    rango     = float(df["high"].iloc[-1]) - float(df["low"].iloc[-1])
    rel_range = (rango / atr_val) * 100
    return evaluar_condicional(rel_range, cond)


# ══════════════════════════════════════════════════════════════════════════════
# MOMENTUM E INDICADORES TÉCNICOS
# ══════════════════════════════════════════════════════════════════════════════

def _evaluar_rsi(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """RSI — Relative Strength Index vs umbral (0–100).
    PERIODO_RSI: periodo (default 14)."""
    import pandas_ta as ta

    periodo = _leer_int(parametros, "PERIODO_RSI", "PERIODO", default=14)
    cond    = _leer_condicional(parametros)
    if cond is None or len(df) < periodo + 1:
        return True
    rsi = ta.rsi(df["close"], length=periodo)
    if rsi is None or rsi.dropna().empty:
        return True
    return evaluar_condicional(float(rsi.iloc[-1]), cond)


def _evaluar_distance_from_vwap_ema_ma(
    df: pd.DataFrame, parametros: list[dict], default_linea: str = "EMA"
) -> bool:
    """DISTANCE_FROM_VWAP / DISTANCE_FROM_EMA / DISTANCE_FROM_MA.
    LINEA_REFERENCIA_DISTANCE_FROM_VWAP_EMA_MA: VWAP, EMA, MA.
    PERIODO_LINEA_DISTANCE_FROM_VWAP_EMA_MA: periodo para EMA/MA.
    Distancia = (close - línea) / línea × 100  — valores en %."""
    import pandas_ta as ta

    linea   = _leer_str(parametros, "LINEA_REFERENCIA", default=default_linea)
    periodo = _leer_int(parametros, "PERIODO_LINEA", "PERIODO", default=20)
    cond    = _leer_condicional(parametros)
    if cond is None or df.empty:
        return True

    if linea == "VWAP":
        if len(df) < 2:
            return True
        serie = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
    elif linea == "MA":
        if len(df) < periodo + 1:
            return True
        serie = ta.sma(df["close"], length=periodo)
    else:  # EMA (default)
        if len(df) < periodo + 1:
            return True
        serie = ta.ema(df["close"], length=periodo)

    if serie is None or serie.dropna().empty:
        return True

    linea_val = float(serie.iloc[-1])
    close_val = float(df["close"].iloc[-1])
    if linea_val == 0:
        return True

    distancia_pct = ((close_val - linea_val) / linea_val) * 100
    return evaluar_condicional(distancia_pct, cond)


def _evaluar_distance_from_vwap(df: pd.DataFrame, parametros: list[dict]) -> bool:
    return _evaluar_distance_from_vwap_ema_ma(df, parametros, "VWAP")


def _evaluar_distance_from_ema(df: pd.DataFrame, parametros: list[dict]) -> bool:
    return _evaluar_distance_from_vwap_ema_ma(df, parametros, "EMA")


def _evaluar_distance_from_ma(df: pd.DataFrame, parametros: list[dict]) -> bool:
    return _evaluar_distance_from_vwap_ema_ma(df, parametros, "MA")


def _evaluar_back_to_ema_alert(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """BACK_TO_EMA_ALERT — precio tocó la EMA en la última vela (low ≤ EMA ≤ high)
    y cerró por encima (alcista). PERIODO_EMA_BACK_TO_EMA: periodo."""
    import pandas_ta as ta

    periodo = _leer_int(parametros, "PERIODO_EMA_BACK_TO_EMA", "PERIODO", default=20)
    if len(df) < periodo + 1:
        return True

    ema = ta.ema(df["close"], length=periodo)
    if ema is None or ema.dropna().empty:
        return True

    ema_val    = float(ema.iloc[-1])
    low_actual = float(df["low"].iloc[-1])
    close_act  = float(df["close"].iloc[-1])

    # Barra tocó la EMA desde arriba y cerró sobre ella
    return low_actual <= ema_val and close_act > ema_val


def _evaluar_through_ema_vwap_alert(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """THROUGH_EMA_VWAP_ALERT — precio cruzó la EMA o VWAP en la dirección indicada.
    THROUGH_EMA_VWAP_LINEA_CRUCE: VWAP o EMA.
    THROUGH_EMA_VWAP_PERIODO_EMA: periodo para EMA.
    THROUGH_EMA_VWAP_DIRECCION_ROMPIMIENTO: ABOVE (alcista) o BELOW (bajista)."""
    import pandas_ta as ta

    linea     = _leer_str(parametros, "THROUGH_EMA_VWAP_LINEA_CRUCE", "LINEA_CRUCE", default="EMA")
    periodo   = _leer_int(parametros, "THROUGH_EMA_VWAP_PERIODO_EMA", "PERIODO_EMA", default=20)
    direccion = _leer_str(parametros, "THROUGH_EMA_VWAP_DIRECCION", "DIRECCION_ROMPIMIENTO", default="ABOVE")

    if len(df) < 2:
        return True

    if linea == "VWAP":
        serie = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
    else:
        if len(df) < periodo + 1:
            return True
        serie = ta.ema(df["close"], length=periodo)

    if serie is None or serie.dropna().empty:
        return True

    linea_val  = float(serie.iloc[-1])
    curr_close = float(df["close"].iloc[-1])
    prev_close = float(df["close"].iloc[-2])

    if direccion == "ABOVE":
        return prev_close < linea_val <= curr_close  # cruzó hacia arriba
    else:
        return prev_close > linea_val >= curr_close  # cruzó hacia abajo


def _evaluar_ema_vwap_support_resistance(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """EMA_VWAP_SUPPORT_RESISTANCE — EMA/VWAP actúa como soporte o resistencia.
    LINEA_REFERENCIA_EMA_VWAP_SUPPORT: VWAP, EMA, MA.
    PERIODO_EMA_EMA_VWAP_SUPPORT: periodo.
    TIPO_ROL_EMA_VWAP_SUPPORT: SOPORTE o RESISTENCIA."""
    import pandas_ta as ta

    linea  = _leer_str(parametros, "LINEA_REFERENCIA_EMA_VWAP_SUPPORT", "LINEA_REFERENCIA", default="EMA")
    period = _leer_int(parametros, "PERIODO_EMA_EMA_VWAP_SUPPORT", "PERIODO_EMA", default=20)
    rol    = _leer_str(parametros, "TIPO_ROL_EMA_VWAP_SUPPORT", "TIPO_ROL", default="SOPORTE")

    if len(df) < 2:
        return True

    if linea == "VWAP":
        serie = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
    elif linea == "MA":
        serie = ta.sma(df["close"], length=period) if len(df) >= period + 1 else None
    else:
        serie = ta.ema(df["close"], length=period) if len(df) >= period + 1 else None

    if serie is None or serie.dropna().empty:
        return True

    linea_val = float(serie.iloc[-1])
    low_act   = float(df["low"].iloc[-1])
    high_act  = float(df["high"].iloc[-1])
    close_act = float(df["close"].iloc[-1])

    if rol == "SOPORTE":
        # Precio tocó la línea desde arriba y cerró sobre ella
        return low_act <= linea_val and close_act > linea_val
    else:  # RESISTENCIA
        # Precio tocó la línea desde abajo y cerró bajo ella
        return high_act >= linea_val and close_act < linea_val


# ══════════════════════════════════════════════════════════════════════════════
# TIEMPO Y PATRONES DE PRECIO
# ══════════════════════════════════════════════════════════════════════════════

def _evaluar_bearish_bullish_engulfing(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """BEARISH_BULLISH_ENGULFING — patrón de vela envolvente.
    TIPO_PATRON_BEARISH_BULLISH_ENGULFING_CANDLE: BULLISH o BEARISH."""
    tipo = _leer_str(parametros, "TIPO_PATRON", default="BULLISH")
    if len(df) < 2:
        return True

    prev_open  = float(df["open"].iloc[-2])
    prev_close = float(df["close"].iloc[-2])
    curr_open  = float(df["open"].iloc[-1])
    curr_close = float(df["close"].iloc[-1])

    if tipo == "BULLISH":
        prev_bearish = prev_close < prev_open
        curr_bullish = curr_close > curr_open
        engulfs      = curr_open <= prev_close and curr_close >= prev_open
        return prev_bearish and curr_bullish and engulfs
    else:  # BEARISH
        prev_bullish = prev_close > prev_open
        curr_bearish = curr_close < curr_open
        engulfs      = curr_open >= prev_close and curr_close <= prev_open
        return prev_bullish and curr_bearish and engulfs


def _evaluar_first_candle(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """FIRST_CANDLE — primera vela de la sesión es alcista o bajista.
    TIPO_VELA_FIRTS_CANDLE: ALCISTA o BAJISTA."""
    tipo = _leer_str(parametros, "TIPO_VELA_FIRTS_CANDLE", "TIPO_VELA", default="ALCISTA")
    if df.empty:
        return True
    open0  = float(df["open"].iloc[0])
    close0 = float(df["close"].iloc[0])
    if tipo == "ALCISTA":
        return close0 > open0
    else:
        return close0 < open0


def _evaluar_consecutive_candles(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """CONSECUTIVE_CANDLES — racha de velas consecutivas en la misma dirección.
    Cuenta = +N (N alcistas) o −N (N bajistas). CONDICION compara esa cuenta.
    Ej.: MAYOR_QUE 3 → más de 3 velas alcistas consecutivas al final.
    NUMERO_VELAS_CONSECUTIVAS: máximo de velas a revisar hacia atrás."""
    cond = _leer_condicional(parametros)
    n    = _leer_int(parametros, "NUMERO_VELAS_CONSECUTIVAS", "NUMERO_VELAS", default=10)
    if cond is None or df.empty:
        return True

    opens  = df["open"].values
    closes = df["close"].values
    n = min(n, len(df))

    # Contar racha al final
    if closes[-1] > opens[-1]:
        direction = 1   # alcista
    elif closes[-1] < opens[-1]:
        direction = -1  # bajista
    else:
        return evaluar_condicional(0, cond)

    count = 1
    for i in range(len(df) - 2, max(len(df) - 1 - n, -1), -1):
        candle_dir = 1 if closes[i] > opens[i] else (-1 if closes[i] < opens[i] else 0)
        if candle_dir == direction:
            count += 1
        else:
            break

    return evaluar_condicional(float(direction * count), cond)


def _evaluar_high_low_of_day(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """HIGH_LOW_OF_DAY — la última barra tiene el máximo o mínimo del periodo.
    OPCION_EXTREMO_HIGH_LOW_DAY: HIGH o LOW."""
    opcion = _leer_str(parametros, "OPCION_EXTREMO_HIGH_LOW_DAY", "OPCION_EXTREMO", default="HIGH")
    if df.empty:
        return True
    if opcion == "HIGH":
        return float(df["high"].iloc[-1]) >= float(df["high"].max())
    else:
        return float(df["low"].iloc[-1]) <= float(df["low"].min())


def _evaluar_new_candle_high_low(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """NEW_CANDLE_HIGH_LOW — la última barra hace un nuevo high o low respecto a las anteriores.
    OPCION_EXTREMO_NEW_CANDLE: HIGH o LOW."""
    opcion = _leer_str(parametros, "OPCION_EXTREMO_NEW_CANDLE", "OPCION_EXTREMO", default="HIGH")
    if len(df) < 2:
        return True
    if opcion == "HIGH":
        return float(df["high"].iloc[-1]) > float(df["high"].iloc[:-1].max())
    else:
        return float(df["low"].iloc[-1]) < float(df["low"].iloc[:-1].min())


def _evaluar_percentage_pullback_highs_lows(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """PERCENTAGE_PULLBACK_HIGHS_LOWS — retroceso porcentual desde el alto o bajo del periodo.
    PUNTO_REFERENCIA_PULLBACK: ALTO (desde el máximo) o BAJO (desde el mínimo).
    CONDICION compara el % de retroceso.
    Valores en % (ej. valor1=10 → retrocedió > 10 %)."""
    cond = _leer_condicional(parametros)
    ref  = _leer_str(parametros, "PUNTO_REFERENCIA_PULLBACK", "PUNTO_REFERENCIA", default="ALTO")
    if cond is None or df.empty:
        return True

    close = float(df["close"].iloc[-1])

    if ref == "ALTO":
        extremo = float(df["high"].max())
        if extremo == 0:
            return True
        pullback_pct = ((extremo - close) / extremo) * 100
    else:  # BAJO
        extremo = float(df["low"].min())
        if extremo == 0:
            return True
        pullback_pct = ((close - extremo) / extremo) * 100

    return evaluar_condicional(pullback_pct, cond)


def _evaluar_break_over_recent_highs_lows(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """BREAK_OVER_RECENT_HIGHS_LOWS — precio rompió el máximo o mínimo reciente.
    OPCION_EXTREMO_BREAK_OVER: HIGH (rompe por arriba) o LOW (rompe por abajo)."""
    opcion = _leer_str(parametros, "OPCION_EXTREMO_BREAK_OVER", "OPCION_EXTREMO", default="HIGH")
    if len(df) < 2:
        return True

    close = float(df["close"].iloc[-1])

    if opcion == "HIGH":
        recent_high = float(df["high"].iloc[:-1].max())
        return close > recent_high
    else:
        recent_low = float(df["low"].iloc[:-1].min())
        return close < recent_low


def _evaluar_opening_range_breakout(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """OPENING_RANGE_BREAKOUT — precio superó el high de la primera barra (opening range)."""
    if len(df) < 2:
        return True
    opening_high = float(df["high"].iloc[0])
    return float(df["close"].iloc[-1]) > opening_high


def _evaluar_opening_range_breakdown(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """OPENING_RANGE_BREAKDOWN — precio cayó bajo el low de la primera barra (opening range)."""
    if len(df) < 2:
        return True
    opening_low = float(df["low"].iloc[0])
    return float(df["close"].iloc[-1]) < opening_low


def _evaluar_minutos_in_market(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """MINUTOS_IN_MARKET — minutos transcurridos desde la apertura del mercado (9:30 ET).
    CONDICION compara los minutos (ej. MAYOR_QUE 30 → lleva más de 30 min en mercado).
    Valores en minutos enteros."""
    from datetime import datetime, time as dtime
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo  # type: ignore

    cond = _leer_condicional(parametros)
    if cond is None or df.empty:
        return True

    ts_str = str(df.index[-1]) if not isinstance(df.index, pd.RangeIndex) else ""
    if not ts_str:
        # Intentar desde columna timestamp
        if "timestamp" not in df.columns:
            return True
        ts_str = str(df["timestamp"].iloc[-1])

    try:
        dt_utc = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        dt_et  = dt_utc.astimezone(ZoneInfo("America/New_York"))
        apertura = dtime(9, 30)
        if dt_et.time() < apertura:
            return True  # antes de apertura
        mins = (dt_et.hour * 60 + dt_et.minute) - (9 * 60 + 30)
        return evaluar_condicional(float(mins), cond)
    except Exception:
        return True


def _evaluar_pivots(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """PIVOTS — análisis de pivots (requiere datos de sesión anterior). Stub permisivo."""
    return True


# ══════════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════
# CARACTERÍSTICAS FUNDAMENTALES
# Datos vienen del FundamentalsCache vía df.attrs["fundamentales"].
# Si el campo es None o falta → permisivo (True): sin datos no se bloquea.
# Unidades iguales a scanner-management (ver fundamentals_adapter.py).
# ══════════════════════════════════════════════════════════════════════════════

def _leer_fundamental(df: pd.DataFrame, clave: str):
    """Extrae un valor fundamental de df.attrs. Retorna None si no existe."""
    return df.attrs.get("fundamentales", {}).get(clave)


def _evaluar_fundamental_numerico(
    df: pd.DataFrame, parametros: list[dict], clave: str
) -> bool:
    """Patrón común: leer valor del caché, comparar con condicional."""
    cond  = _leer_condicional(parametros)
    if cond is None:
        return True
    valor = _leer_fundamental(df, clave)
    if valor is None:
        return False  # sin datos → restrictivo (se descarta)
    return evaluar_condicional(float(valor), cond)


def _evaluar_float(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """FLOAT — número de acciones en circulación (float shares).
    Valor en acciones raw (ej. 5_000_000 = 5M acciones)."""
    return _evaluar_fundamental_numerico(df, parametros, "float_shares")


def _evaluar_shares_outstanding(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """SHARES_OUTSTANDING — total de acciones emitidas.
    Valor en acciones raw."""
    return _evaluar_fundamental_numerico(df, parametros, "shares_outstanding")


def _evaluar_market_cap(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """MARKET_CAP — capitalización de mercado.
    Valor en dólares raw (ej. 1_000_000_000 = $1B)."""
    return _evaluar_fundamental_numerico(df, parametros, "market_cap")


def _evaluar_short_interest(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """SHORT_INTEREST — porcentaje del float vendido en corto.
    Valor en % raw (ej. 10.5 = 10.5% del float)."""
    return _evaluar_fundamental_numerico(df, parametros, "short_interest")


def _evaluar_short_ratio(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """SHORT_RATIO — días necesarios para cubrir el short (days-to-cover).
    Valor en días raw (ej. 3.2 = 3.2 días)."""
    return _evaluar_fundamental_numerico(df, parametros, "short_ratio")


def _evaluar_days_until_earnings(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """DAYS_UNTIL_EARNINGS — días hasta el próximo earnings report.
    Valor en días enteros (ej. 15 = faltan 15 días)."""
    return _evaluar_fundamental_numerico(df, parametros, "days_until_earnings")


def _stub_noticias(df: pd.DataFrame, parametros: list[dict]) -> bool:
    """NOTICIAS — pendiente de micro-servicio de noticias. Stub permisivo."""
    return True


# ══════════════════════════════════════════════════════════════════════════════
# Registro de evaluadores
# ══════════════════════════════════════════════════════════════════════════════

_EVALUADORES: dict[str, callable] = {
    # Volumen
    "VOLUME":                        _evaluar_volume,
    "AVERAGE_VOLUME":                _evaluar_average_volume,
    "RELATIVE_VOLUME":               _evaluar_relative_volume,
    "RELATIVE_VOLUME_SAME_TIME":     _evaluar_relative_volume_same_time,
    "VOLUME_SPIKE":                  _evaluar_volume_spike,
    "VOLUMEN_POST_PRE":              _evaluar_volumen_post_pre,

    # Precio y movimiento
    "PRECIO":                        _evaluar_precio,
    "CHANGE":                        _evaluar_change,
    "PERCENTAGE_CHANGE":             _evaluar_percentage_change,
    "GAP_FROM_CLOSE":                _evaluar_gap_from_close,
    "POSITION_IN_RANGE":             _evaluar_position_in_range,
    "PERCENTAGE_RANGE":              _evaluar_percentage_range,
    "RANGE_DOLLARS":                 _evaluar_range_dollars,
    "CROSSING_ABOVE_BELOW":          _evaluar_crossing_above_below,
    "HALT":                          _evaluar_halt,

    # Volatilidad
    "ATR":                           _evaluar_atr,
    "ATRP":                          _evaluar_atrp,
    "RELATIVE_RANGE":                _evaluar_relative_range,

    # Momentum e indicadores técnicos
    "RSI":                           _evaluar_rsi,
    "DISTANCE_FROM_VWAP":            _evaluar_distance_from_vwap,
    "DISTANCE_FROM_EMA":             _evaluar_distance_from_ema,
    "DISTANCE_FROM_MA":              _evaluar_distance_from_ma,
    "DISTANCE_FROM_VWAP_EMA_MA":     _evaluar_distance_from_vwap_ema_ma,
    "BACK_TO_EMA_ALERT":             _evaluar_back_to_ema_alert,
    "THROUGH_EMA_VWAP_ALERT":        _evaluar_through_ema_vwap_alert,
    "EMA_VWAP_SUPPORT_RESISTANCE":   _evaluar_ema_vwap_support_resistance,

    # Tiempo y patrones
    "BEARISH_BULLISH_ENGULFING":         _evaluar_bearish_bullish_engulfing,
    "FIRST_CANDLE":                      _evaluar_first_candle,
    "CONSECUTIVE_CANDLES":               _evaluar_consecutive_candles,
    "HIGH_LOW_OF_DAY":                   _evaluar_high_low_of_day,
    "NEW_CANDLE_HIGH_LOW":               _evaluar_new_candle_high_low,
    "PERCENTAGE_PULLBACK_HIGHS_LOWS":    _evaluar_percentage_pullback_highs_lows,
    "BREAK_OVER_RECENT_HIGHS_LOWS":      _evaluar_break_over_recent_highs_lows,
    "OPENING_RANGE_BREAKOUT":            _evaluar_opening_range_breakout,
    "OPENING_RANGE_BREAKDOWN":           _evaluar_opening_range_breakdown,
    "MINUTOS_IN_MARKET":                 _evaluar_minutos_in_market,
    "PIVOTS":                            _evaluar_pivots,

    # Fundamentales (datos de FundamentalsCache vía df.attrs)
    "FLOAT":               _evaluar_float,
    "SHARES_OUTSTANDING":  _evaluar_shares_outstanding,
    "MARKET_CAP":          _evaluar_market_cap,
    "SHORT_INTEREST":      _evaluar_short_interest,
    "SHORT_RATIO":         _evaluar_short_ratio,
    "DAYS_UNTIL_EARNINGS": _evaluar_days_until_earnings,
    "NOTICIAS":            _stub_noticias,
}


# ══════════════════════════════════════════════════════════════════════════════
# Función principal
# ══════════════════════════════════════════════════════════════════════════════

def evaluar_simbolos(
    contextos: dict[str, dict],
    filtros: list[dict],
    id_escaner: int,
    nombre_escaner: str,
) -> list[dict]:
    """Evalúa todos los filtros (lógica AND) para todos los símbolos.

    Ejecutado en ProcessPoolExecutor — recibe y retorna dicts puros.

    Args:
        contextos: {symbol: {barras: {col: [vals]}, symbol: str, ...}}
        filtros:   [{enum_filtro, parametros: [{enum_parametro, obj_valor_seleccionado}]}]
        id_escaner: ID del escáner
        nombre_escaner: Nombre del escáner

    Returns:
        Lista de señales (dicts) para símbolos que cumplieron todos los filtros.
    """
    senales: list[dict] = []

    for symbol, ctx_data in contextos.items():
        df = pd.DataFrame(ctx_data["barras"])
        if df.empty:
            continue

        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Adjuntar metadatos al DataFrame para que los evaluadores los lean
        df.attrs["symbol"]        = symbol
        df.attrs["fundamentales"] = ctx_data.get("fundamentales", {})
        df.attrs["halteado"]      = ctx_data.get("halteado", False)

        todos_cumplen        = True
        filtros_que_cumplieron: list[str] = []

        for filtro in filtros:
            enum_filtro = filtro.get("enum_filtro", "")
            parametros  = filtro.get("parametros", [])

            evaluador = _EVALUADORES.get(enum_filtro)
            if evaluador is None:
                # Filtro no registrado → stub permisivo
                filtros_que_cumplieron.append(enum_filtro)
                continue

            if evaluador(df, parametros):
                filtros_que_cumplieron.append(enum_filtro)
            else:
                todos_cumplen = False
                break

        if todos_cumplen and filtros_que_cumplieron:
            senales.append({
                "idEscaner":       id_escaner,
                "nombreEscaner":   nombre_escaner,
                "symbol":          symbol,
                "tipoSenal":       "ALERTA_FILTROS",
                "filtrosAplicados": ",".join(filtros_que_cumplieron),
                "precioDeteccion": float(df["close"].iloc[-1]),
                "volumenDeteccion": float(df["volume"].iloc[-1]),
                "servicioOrigen":  "signal-processing-service",
            })

    return senales
