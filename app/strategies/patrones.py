from app.analysis.indicators import todays_candles
from app.models.enums import EnumParametro
from app.strategies.base import FilterStrategy, MarketData
from app.strategies.day_view import day_extremes, first_candle_of_day, last_close


class BearishBullishEngulfingStrategy(FilterStrategy):
    """Bullish engulfing: vela previa bajista, vela actual alcista, y el
    cuerpo de la actual envuelve por completo el de la previa (definicion
    estandar -- confirmar solo el rango sin exigir el color de cada vela
    dejaba pasar falsos positivos tipo harami, vela interior)."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or len(data.candles) < 2:
            return None
        prev = data.candles[-2]
        curr = data.candles[-1]
        if prev.open is None or prev.close is None or curr.open is None or curr.close is None:
            return None
        tipo = self._param_str(EnumParametro.TIPO_PATRON_BEARISH_BULLISH_ENGULFING_CANDLE, "BULLISH")
        prev_bearish = prev.close < prev.open
        prev_bullish = prev.close > prev.open
        curr_bullish = curr.close > curr.open
        curr_bearish = curr.close < curr.open
        # <= / >= (no estricto): un gap que abre justo en el cierre anterior
        # sigue contando como que el cuerpo lo envuelve, no solo un gap mas
        # amplio.
        bullish_engulfing = (
            prev_bearish and curr_bullish and curr.open <= prev.close and curr.close >= prev.open
        )
        bearish_engulfing = (
            prev_bullish and curr_bearish and curr.open >= prev.close and curr.close <= prev.open
        )
        if bullish_engulfing:
            return 1.0 if tipo == "BULLISH" else -1.0
        if bearish_engulfing:
            return 1.0 if tipo == "BEARISH" else -1.0
        return 0.0


class ConsecutiveCandlesStrategy(FilterStrategy):
    """N consecutive bullish or bearish candles."""

    def compute_value(self, data: MarketData) -> float | None:
        n = self._param_int(EnumParametro.NUMERO_VELAS_CONSECUTIVAS, 3)
        if not data.candles or len(data.candles) < n:
            return None
        recent = data.candles[-n:]
        if any(c.close is None or c.open is None for c in recent):
            return None
        bullish = all(c.close > c.open for c in recent)
        bearish = all(c.close < c.open for c in recent)
        return 1.0 if bullish else (-1.0 if bearish else 0.0)


class FirstCandleStrategy(FilterStrategy):
    """First candle of the day type (bullish/bearish) -- TIPO_VELA_FIRTS_CANDLE
    elige cual tipo busca el usuario (antes se ignoraba y devolvia 1.0/-1.0
    para cualquiera de los dos, sin filtrar por la seleccion real)."""

    def compute_value(self, data: MarketData) -> float | None:
        first = first_candle_of_day(data)
        if first is None or first.close is None or first.open is None:
            return None
        tipo = self._param_str(EnumParametro.TIPO_VELA_FIRTS_CANDLE, "ALCISTA")
        if first.close > first.open:
            return 1.0 if tipo == "ALCISTA" else -1.0
        if first.close < first.open:
            return 1.0 if tipo == "BAJISTA" else -1.0
        return 0.0


class HighLowOfDayStrategy(FilterStrategy):
    """Distance (%) from today's high or low -- OPCION_EXTREMO elige cual
    extremo (antes se ignoraba y siempre devolvia la posicion 0-100% en el
    rango, sin importar la seleccion): HIGH = que tan cerca del maximo del
    dia (0% = en el maximo), LOW = que tan cerca del minimo (0% = en el
    minimo)."""

    def compute_value(self, data: MarketData) -> float | None:
        extremes = day_extremes(data)
        price = last_close(data)
        if extremes is None or price is None:
            return None
        day_high, day_low = extremes
        if day_high <= day_low:
            # Un solo candle del dia (o todos al mismo precio) no tiene rango:
            # devolver 0.0 era "distancia al minimo = 0%" y pasaba cualquier
            # condicion MENOR_QUE -- los warrants que negocian 1 vela al dia
            # senialaban siempre (confirmado en vivo 2026-08-24).
            return None
        opcion = self._param_str(EnumParametro.OPCION_EXTREMO_HIGH_LOW_DAY, "HIGH")
        if opcion == "LOW":
            return ((price - day_low) / (day_high - day_low)) * 100.0
        return ((day_high - price) / (day_high - day_low)) * 100.0


class NewCandleHighLowStrategy(FilterStrategy):
    """New N-candle high or low -- OPCION_EXTREMO elige cual (antes se
    ignoraba y devolvia 1.0/-1.0 para cualquiera de los dos, sin filtrar por
    la seleccion del usuario)."""

    def compute_value(self, data: MarketData) -> float | None:
        # "Nuevo maximo/minimo de las ultimas N velas": N lo elige el usuario
        # (por defecto 20, el valor estandar del canal de Donchian). Antes se
        # comparaba contra TODAS las velas del buffer (>= 150, y mas si otro
        # filtro del grupo pedia mas), asi que el mismo filtro daba resultados
        # distintos segun con que otros filtros compartiera temporalidad.
        n = max(self._param_int(EnumParametro.NUMERO_VELAS_NEW_CANDLE, 20), 2)
        if not data.candles or len(data.candles) < n + 1:
            return None
        prior = data.candles[-(n + 1):-1]
        curr = data.candles[-1]
        if any(c.high is None or c.low is None for c in prior) or curr.high is None or curr.low is None:
            return None
        opcion = self._param_str(EnumParametro.OPCION_EXTREMO_NEW_CANDLE, "HIGH")
        if opcion == "LOW":
            prev_low = min(c.low for c in prior)
            return 1.0 if curr.low < prev_low else 0.0
        prev_high = max(c.high for c in prior)
        return 1.0 if curr.high > prev_high else 0.0


class PercentagePullbackHighsLowsStrategy(FilterStrategy):
    """Percentage pullback from recent high, or rally from recent low --
    PUNTO_REFERENCIA_PULLBACK elige cual (antes se ignoraba y siempre
    calculaba el retroceso desde el HIGH)."""

    def compute_value(self, data: MarketData) -> float | None:
        # Ventana de N velas configurable (por defecto 5, lo que antes estaba
        # fijo y oculto en el codigo).
        n = max(self._param_int(EnumParametro.NUMERO_VELAS_PULLBACK, 5), 2)
        if not data.candles or len(data.candles) < n:
            return None
        recent = data.candles[-n:]
        price = data.candles[-1].close
        if price is None:
            return None
        punto = self._param_str(EnumParametro.PUNTO_REFERENCIA_PULLBACK, "ALTO")
        if punto == "BAJO":
            if any(c.low is None for c in recent):
                return None
            low = min(c.low for c in recent)
            if low <= 0:
                return None
            return ((price - low) / low) * 100.0
        if any(c.high is None for c in recent):
            return None
        high = max(c.high for c in recent)
        if high <= 0:
            return None
        return ((high - price) / high) * 100.0


class BreakOverRecentHighsLowsStrategy(FilterStrategy):
    """Price breaking above/below recent N-bar range -- OPCION_EXTREMO elige
    cual lado (antes se ignoraba y devolvia 1.0/-1.0 para cualquiera de los
    dos, sin filtrar por la seleccion del usuario)."""

    def compute_value(self, data: MarketData) -> float | None:
        # Rompe el maximo/minimo de las ultimas N velas (N configurable, por
        # defecto 20). Exigir N previas evita las series degeneradas
        # (warrants con 1 vela al dia, confirmado en vivo 2026-08-24) que
        # rompian "el maximo reciente" contra una sola vela.
        n = max(self._param_int(EnumParametro.NUMERO_VELAS_BREAK_OVER, 20), 2)
        if not data.candles or len(data.candles) < n + 1:
            return None
        prior = data.candles[-(n + 1):-1]
        curr = data.candles[-1]
        if any(c.high is None or c.low is None for c in prior) or curr.close is None:
            return None
        opcion = self._param_str(EnumParametro.OPCION_EXTREMO_BREAK_OVER, "HIGH")
        if opcion == "LOW":
            prev_low = min(c.low for c in prior)
            return 1.0 if curr.close < prev_low else 0.0
        prev_high = max(c.high for c in prior)
        return 1.0 if curr.close > prev_high else 0.0


class OpeningRangeBreakdownStrategy(FilterStrategy):
    """Price closing below the low of the opening range candle -- la primera
    vela de HOY en la temporalidad configurada (ej. M15 = rango de los
    primeros 15 minutos), definicion estandar de Opening Range Breakout.
    Antes usaba candles[0] de la ventana pedida, que no necesariamente
    arrancaba en la apertura del dia (podia ser de ayer)."""

    def compute_value(self, data: MarketData) -> float | None:
        first = first_candle_of_day(data)
        price = last_close(data)
        if first is None or first.low is None or price is None:
            return None
        return 1.0 if price < first.low and first.low > 0 else 0.0


class OpeningRangeBreakoutStrategy(FilterStrategy):
    """Price closing above the high of the opening range candle -- la primera
    vela de HOY en la temporalidad configurada. Mismo fix que
    OpeningRangeBreakdownStrategy."""

    def compute_value(self, data: MarketData) -> float | None:
        first = first_candle_of_day(data)
        price = last_close(data)
        if first is None or first.high is None or price is None:
            return None
        return 1.0 if price > first.high and first.high > 0 else 0.0


class PivotsStrategy(FilterStrategy):
    """Price at pivot point (high or low surrounded by lower/higher)."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or len(data.candles) < 3:
            return None
        recent = data.candles[-3:]
        if any(c.high is None or c.low is None for c in recent):
            return None
        h1, h2, h3 = [c.high for c in recent]
        l1, l2, l3 = [c.low for c in recent]
        if h2 > h1 and h2 > h3:
            return 1.0
        if l2 < l1 and l2 < l3:
            return -1.0
        return 0.0


class MinutosInMarketStrategy(FilterStrategy):
    """Minutes since market open (9:30am ET)."""

    def compute_value(self, data: MarketData) -> float:
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo
        # Comparaba la hora en UTC directo contra "9:30" como si tambien
        # fuera UTC -- desfasaba 4-5 horas (EDT/EST) contra la apertura real.
        now_et = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
        minutes = now_et.hour * 60 + now_et.minute
        market_open = 9 * 60 + 30
        return float(max(0, minutes - market_open))
