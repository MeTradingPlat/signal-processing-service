from app.strategies.base import FilterStrategy, MarketData

_DIAS_COMPARACION = 5


class RelativeVolumeSameTimeStrategy(FilterStrategy):
    """Volumen actual vs. promedio de volumen en esa MISMA franja horaria en
    los _DIAS_COMPARACION dias anteriores -- a diferencia de RELATIVE_VOLUME
    (que promedia TODAS las barras previas de la ventana sin importar la
    hora del dia), este filtro busca, para cada uno de los ultimos dias,
    la vela cuyo HH:MM coincide exactamente con la vela actual (las velas
    ya vienen alineadas a una grilla UTC fija por timeframe). Antes este
    filtro estaba mapeado directo a RelativeVolumeStrategy, calculando
    exactamente lo mismo que RELATIVE_VOLUME pese a su nombre."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles:
            return None
        current = data.candles[-1]
        if current.volume is None or current.timestamp is None:
            return None
        today = current.timestamp.date()
        target_hm = (current.timestamp.hour, current.timestamp.minute)

        same_time_volumes = []
        seen_days = set()
        for c in reversed(data.candles[:-1]):
            if c.timestamp is None or c.volume is None:
                continue
            day = c.timestamp.date()
            if day == today or day in seen_days:
                continue
            if (c.timestamp.hour, c.timestamp.minute) == target_hm:
                same_time_volumes.append(c.volume)
                seen_days.add(day)
                if len(seen_days) >= _DIAS_COMPARACION:
                    break

        if not same_time_volumes:
            return None
        avg = sum(same_time_volumes) / len(same_time_volumes)
        if avg == 0:
            return None
        return (current.volume / avg) * 100.0
