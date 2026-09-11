from app.analysis.indicators import (
    body_size, candle_range, has_fair_value_gap, is_bearish, is_bullish, lower_wick, near_zone,
    swing_range, upper_wick, zonas_cercanas,
)
from app.models.enums import EnumParametro
from app.strategies.base import FilterStrategy, MarketData


class OrderBlockImbalanceStrategy(FilterStrategy):
    """Order Block + Fair Value Gap (imbalance de 3 velas, definicion
    estandar ICT) en algun punto de las ultimas LOOKBACK_VELAS_ORDER_BLOCK_IMBALANCE
    velas: un hueco entre una vela y la que quedo 2 despues que ningun
    cuerpo llego a cubrir, en la direccion configurada (DIRECCION).

    Sirve dos roles del embudo con la misma clase (asi lo describe el
    curso: 'buscas algo muy similar al primer punto' en M15/M1): si
    `data.zona` viene vacio (primer uso, tipicamente H4/H1) cualquier
    imbalance del lookback cuenta; si ya viene una zona de un grupo
    anterior (uso como 'refinamiento'), solo cuenta un imbalance cuya
    propia zona caiga cerca de esa -- si no hay ninguno cerca, sigue
    buscando en el resto del lookback antes de descartar el simbolo."""

    def __init__(self, filtro=None):
        super().__init__(filtro)
        self.ultima_zona: tuple[float, float] | None = None

    def compute_value(self, data: MarketData) -> float | None:
        lookback = self._param_int(EnumParametro.LOOKBACK_VELAS_ORDER_BLOCK_IMBALANCE, 20)
        self.ultima_zona = None
        if not data.candles or len(data.candles) < lookback + 2:
            return None
        recent = data.candles[-(lookback + 2):]
        if any(c.high is None or c.low is None for c in recent):
            return None
        alcista = self._param_str(EnumParametro.DIRECCION_ORDER_BLOCK_IMBALANCE, "ALCISTA") == "ALCISTA"
        for i in range(1, len(recent) - 1):
            if not has_fair_value_gap(recent[i - 1], recent[i + 1], alcista):
                continue
            zona = (recent[i - 1].high, recent[i + 1].low) if alcista else (recent[i + 1].high, recent[i - 1].low)
            if data.zona is not None and not zonas_cercanas(zona, data.zona, data.candles):
                continue
            self.ultima_zona = zona
            return 1.0
        return 0.0


class LiquidityGrabCandleStrategy(FilterStrategy):
    """Vela de toma de liquidez: mecha >= PROPORCION_MECHA_CUERPO veces su
    cuerpo, que perfora el extremo de las ultimas LOOKBACK_VELAS_LIQUIDITY_GRAB_CANDLE
    velas previas pero cierra de vuelta dentro de ese rango -- barrida de
    liquidez clasica (hammer/shooting star con sweep confirmado). Es una de
    las 3 variantes de 'aceleracion y desaceleracion' que describe el curso
    (la mecha larga que 'le saca los estoblos a todo mundo'), no un paso
    aparte -- si `data.zona` viene seteada, la mecha debe tocar esa zona."""

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
            if not (curr.low < prev_low and curr.close > prev_low):
                return 0.0
        else:
            if cuerpo <= 0 or upper_wick(curr) < proporcion * cuerpo:
                return 0.0
            prev_high = max(c.high for c in prior)
            if not (curr.high > prev_high and curr.close < prev_high):
                return 0.0
        extremo = curr.low if alcista else curr.high
        if data.zona is not None and not near_zone(extremo, data.zona, data.candles):
            return 0.0
        return 1.0


class AccelerationDecelerationStrategy(FilterStrategy):
    """Aceleracion seguida de desaceleracion: el cuerpo promedio de las
    ultimas VELAS_DESACELERACION velas cae por debajo de
    PROPORCION_DESACELERACION del cuerpo promedio de las VELAS_ACELERACION
    velas inmediatamente anteriores -- concepto propio del curso analizado
    (no un patron con nombre estandar), aproximado como una caida abrupta
    del tamano medio de cuerpo tras un tramo de cuerpos grandes. El curso
    exige que la desaceleracion ocurra DENTRO de la zona, no en cualquier
    punto reciente -- si `data.zona` viene seteada, el cierre de la ultima
    vela (la que desacelera) debe caer cerca de ella."""

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
        if desacel_avg > proporcion * acel_avg:
            return 0.0
        ultima = desacel[-1]
        if data.zona is not None and not near_zone(ultima.close, data.zona, data.candles):
            return 0.0
        return 1.0


class RangeExtremeProximityStrategy(FilterStrategy):
    """Verifica que el precio actual este cerca del extremo (maximo o
    minimo) del rango de estructura vigente -- el contexto de 'Rango
    D1/H4/H1' del video, la referencia que le da sentido a que un Order
    Block ubicado en ese extremo sea un POI real y no una coincidencia. El
    rango se calcula con `swing_range` (rupturas confirmadas por
    retroceso), no una ventana rodante fija -- asi lo describe el curso:
    el rango 'se mueve' cuando un rompimiento se confirma con al menos 2
    velas de retroceso, en vez de ser siempre el maximo/minimo de las
    ultimas N velas sin distincion."""

    def __init__(self, filtro=None):
        super().__init__(filtro)
        self.ultima_zona: tuple[float, float] | None = None

    def compute_value(self, data: MarketData) -> float | None:
        lookback = self._param_int(EnumParametro.LOOKBACK_VELAS_RANGE_EXTREME_PROXIMITY, 20)
        self.ultima_zona = None
        if not data.candles or len(data.candles) < lookback:
            return None
        window = data.candles[-lookback:]
        rango = swing_range(window)
        if rango is None:
            return None
        range_low, range_high = rango
        altura = range_high - range_low
        if altura <= 0:
            return None
        curr = data.candles[-1]
        if curr.close is None:
            return None
        proporcion = self._param_float(EnumParametro.PROPORCION_PROXIMIDAD_RANGE_EXTREME_PROXIMITY, 0.15)
        alcista = self._param_str(EnumParametro.DIRECCION_RANGE_EXTREME_PROXIMITY, "ALCISTA") == "ALCISTA"
        if alcista:
            if (curr.close - range_low) > proporcion * altura:
                return 0.0
        elif (range_high - curr.close) > proporcion * altura:
            return 0.0
        self.ultima_zona = rango
        return 1.0


class RangeConfluenceStrategy(FilterStrategy):
    """Confluencia real entre los rangos de D1, H4 y H1 -- el curso insiste
    en que cuando los maximos/minimos de las 3 temporalidades caen en el
    mismo sector de precio hay mas fuerza ('cuando se mezclan esos maximos
    y minimos... mucho mejor el punto de entrada'), no basta con mirar una
    sola temporalidad como hace RangeExtremeProximityStrategy. Requiere
    `data.candles` (D1, la temporalidad propia de su grupo en el embudo) y
    `data.velas_extra['H4']`/`['H1']` (ver SymbolPipeline._fetch_extra_timeframes,
    el unico filtro que necesita mas de una temporalidad a la vez)."""

    def __init__(self, filtro=None):
        super().__init__(filtro)
        self.ultima_zona: tuple[float, float] | None = None

    def compute_value(self, data: MarketData) -> float | None:
        self.ultima_zona = None
        lookback = self._param_int(EnumParametro.LOOKBACK_VELAS_RANGE_CONFLUENCE_D1_H4_H1, 20)
        confirmacion = self._param_int(EnumParametro.CONFIRMACION_VELAS_RANGE_CONFLUENCE_D1_H4_H1, 2)
        if not data.candles or len(data.candles) < lookback:
            return None
        extra = data.velas_extra or {}
        velas_h4 = extra.get("H4")
        velas_h1 = extra.get("H1")
        if not velas_h4 or not velas_h1 or len(velas_h4) < lookback or len(velas_h1) < lookback:
            return None

        rango_d1 = swing_range(data.candles[-lookback:], confirmacion)
        rango_h4 = swing_range(velas_h4[-lookback:], confirmacion)
        rango_h1 = swing_range(velas_h1[-lookback:], confirmacion)
        if rango_d1 is None or rango_h4 is None or rango_h1 is None:
            return None

        pares = [(rango_d1, rango_h4), (rango_d1, rango_h1), (rango_h4, rango_h1)]
        solapados = [par for par in pares if zonas_cercanas(par[0], par[1], data.candles)]
        if not solapados:
            return 0.0

        # Interseccion del par que mas se solapa: el rango mas angosto de
        # los que coincidieron, la zona mas precisa disponible.
        rangos_en_juego = {r for par in solapados for r in par}
        low = max(r[0] for r in rangos_en_juego)
        high = min(r[1] for r in rangos_en_juego)
        if low >= high:
            low, high = min(rangos_en_juego, key=lambda r: r[1] - r[0])

        curr = data.candles[-1]
        if curr.close is None:
            return None
        altura = high - low
        if altura <= 0:
            return None
        proporcion = self._param_float(EnumParametro.PROPORCION_PROXIMIDAD_RANGE_CONFLUENCE_D1_H4_H1, 0.15)
        alcista = self._param_str(EnumParametro.DIRECCION_RANGE_CONFLUENCE_D1_H4_H1, "ALCISTA") == "ALCISTA"
        if alcista:
            if (curr.close - low) > proporcion * altura:
                return 0.0
        elif (high - curr.close) > proporcion * altura:
            return 0.0
        self.ultima_zona = (low, high)
        return 1.0


class ConfirmationCandleStrategy(FilterStrategy):
    """Vela de confirmacion: el curso la describe como 'algo muy similar al
    primer punto' -- el mismo Order Block + Imbalance de 3 velas, pero
    ademas exige que sea una 'vela de poder' (cuerpo/rango >=
    PROPORCION_CUERPO_MINIMA). No es un simple gap de 2 velas contra la
    anterior (version previa de este filtro, incorrecta). Si `data.zona`
    viene seteada, la vela de confirmacion debe ocurrir cerca de ella."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or len(data.candles) < 3:
            return None
        prev, _mid, curr = data.candles[-3], data.candles[-2], data.candles[-1]
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
        vela_poder = is_bullish(curr) if alcista else is_bearish(curr)
        if not vela_poder or not has_fair_value_gap(prev, curr, alcista):
            return 0.0
        if data.zona is not None and not near_zone(curr.close, data.zona, data.candles):
            return 0.0
        return 1.0
