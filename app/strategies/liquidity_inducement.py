from app.analysis.indicators import (
    body_size, candle_range, has_fair_value_gap, is_bearish, is_bullish, lower_wick, upper_wick,
)
from app.models.enums import EnumParametro
from app.strategies.base import FilterStrategy, MarketData


class OrderBlockImbalanceStrategy(FilterStrategy):
    """Order Block + Fair Value Gap (imbalance de 3 velas, definicion
    estandar ICT) en algun punto de las ultimas LOOKBACK_VELAS_ORDER_BLOCK_IMBALANCE
    velas: un hueco entre una vela y la que quedo 2 despues que ningun
    cuerpo llego a cubrir, en la direccion configurada (DIRECCION)."""

    def compute_value(self, data: MarketData) -> float | None:
        lookback = self._param_int(EnumParametro.LOOKBACK_VELAS_ORDER_BLOCK_IMBALANCE, 20)
        if not data.candles or len(data.candles) < lookback + 2:
            return None
        recent = data.candles[-(lookback + 2):]
        if any(c.high is None or c.low is None for c in recent):
            return None
        alcista = self._param_str(EnumParametro.DIRECCION_ORDER_BLOCK_IMBALANCE, "ALCISTA") == "ALCISTA"
        for i in range(1, len(recent) - 1):
            if has_fair_value_gap(recent[i - 1], recent[i + 1], alcista):
                return 1.0
        return 0.0


class LiquidityGrabCandleStrategy(FilterStrategy):
    """Vela de toma de liquidez: mecha >= PROPORCION_MECHA_CUERPO veces su
    cuerpo, que perfora el extremo de las ultimas LOOKBACK_VELAS_LIQUIDITY_GRAB_CANDLE
    velas previas pero cierra de vuelta dentro de ese rango -- barrida de
    liquidez clasica (hammer/shooting star con sweep confirmado)."""

    def compute_value(self, data: MarketData) -> float | None:
        lookback = self._param_int(EnumParametro.LOOKBACK_VELAS_LIQUIDITY_GRAB_CANDLE, 10)
        if not data.candles or len(data.candles) < lookback + 1:
            return None
        prior = data.candles[-(lookback + 1):-1]
        curr = data.candles[-1]
        if any(c.high is None or c.low is None for c in prior):
            return None
        if curr.open is None or curr.high is None or curr.low is None or curr.close is None:
            return None
        proporcion = self._param_float(EnumParametro.PROPORCION_MECHA_CUERPO_LIQUIDITY_GRAB_CANDLE, 2.0)
        cuerpo = body_size(curr)
        alcista = self._param_str(EnumParametro.DIRECCION_LIQUIDITY_GRAB_CANDLE, "ALCISTA") == "ALCISTA"
        if alcista:
            if cuerpo <= 0 or lower_wick(curr) < proporcion * cuerpo:
                return 0.0
            prev_low = min(c.low for c in prior)
            return 1.0 if curr.low < prev_low and curr.close > prev_low else 0.0
        if cuerpo <= 0 or upper_wick(curr) < proporcion * cuerpo:
            return 0.0
        prev_high = max(c.high for c in prior)
        return 1.0 if curr.high > prev_high and curr.close < prev_high else 0.0


class AccelerationDecelerationStrategy(FilterStrategy):
    """Aceleracion seguida de desaceleracion: el cuerpo promedio de las
    ultimas VELAS_DESACELERACION velas cae por debajo de
    PROPORCION_DESACELERACION del cuerpo promedio de las VELAS_ACELERACION
    velas inmediatamente anteriores -- concepto propio del curso analizado
    (no un patron con nombre estandar), aproximado como una caida abrupta
    del tamano medio de cuerpo tras un tramo de cuerpos grandes."""

    def compute_value(self, data: MarketData) -> float | None:
        n_acel = self._param_int(EnumParametro.VELAS_ACELERACION_ACCELERATION_DECELERATION, 4)
        n_desacel = self._param_int(EnumParametro.VELAS_DESACELERACION_ACCELERATION_DECELERATION, 2)
        total = n_acel + n_desacel
        if not data.candles or len(data.candles) < total:
            return None
        window = data.candles[-total:]
        if any(c.open is None or c.close is None for c in window):
            return None
        acel, desacel = window[:n_acel], window[n_acel:]
        acel_avg = sum(body_size(c) for c in acel) / len(acel)
        if acel_avg <= 0:
            return None
        desacel_avg = sum(body_size(c) for c in desacel) / len(desacel)
        proporcion = self._param_float(EnumParametro.PROPORCION_DESACELERACION_ACCELERATION_DECELERATION, 0.4)
        return 1.0 if desacel_avg <= proporcion * acel_avg else 0.0


class RangeExtremeProximityStrategy(FilterStrategy):
    """Verifica que el precio actual este cerca del extremo (maximo o
    minimo) del rango formado por las ultimas LOOKBACK_VELAS velas -- el
    contexto de 'Rango D1/H4/H1' del video, la referencia que le da sentido
    a que un Order Block ubicado en ese extremo sea un POI real y no una
    coincidencia."""

    def compute_value(self, data: MarketData) -> float | None:
        lookback = self._param_int(EnumParametro.LOOKBACK_VELAS_RANGE_EXTREME_PROXIMITY, 20)
        if not data.candles or len(data.candles) < lookback:
            return None
        window = data.candles[-lookback:]
        if any(c.high is None or c.low is None for c in window):
            return None
        range_high = max(c.high for c in window)
        range_low = min(c.low for c in window)
        rango = range_high - range_low
        if rango <= 0:
            return None
        curr = data.candles[-1]
        if curr.close is None:
            return None
        proporcion = self._param_float(EnumParametro.PROPORCION_PROXIMIDAD_RANGE_EXTREME_PROXIMITY, 0.15)
        alcista = self._param_str(EnumParametro.DIRECCION_RANGE_EXTREME_PROXIMITY, "ALCISTA") == "ALCISTA"
        if alcista:
            return 1.0 if (curr.close - range_low) <= proporcion * rango else 0.0
        return 1.0 if (range_high - curr.close) <= proporcion * rango else 0.0


class ConfirmationCandleStrategy(FilterStrategy):
    """Vela de confirmacion ('vela de poder'): cuerpo/rango >=
    PROPORCION_CUERPO_MINIMA que ademas deja un imbalance de 2 velas contra
    la anterior (sin solape de rangos), en la direccion configurada."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or len(data.candles) < 2:
            return None
        prev, curr = data.candles[-2], data.candles[-1]
        if prev.high is None or prev.low is None:
            return None
        if curr.open is None or curr.high is None or curr.low is None or curr.close is None:
            return None
        rango = candle_range(curr)
        if rango <= 0:
            return None
        proporcion_min = self._param_float(EnumParametro.PROPORCION_CUERPO_MINIMA_CONFIRMATION_CANDLE, 0.7)
        if (body_size(curr) / rango) < proporcion_min:
            return 0.0
        alcista = self._param_str(EnumParametro.DIRECCION_CONFIRMATION_CANDLE, "ALCISTA") == "ALCISTA"
        if alcista:
            return 1.0 if is_bullish(curr) and curr.low > prev.high else 0.0
        return 1.0 if is_bearish(curr) and curr.high < prev.low else 0.0
