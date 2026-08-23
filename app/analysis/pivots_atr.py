from app.scanner.marketdata_models import CandleResponse


def calculate_atr(candles: list[CandleResponse], length: int) -> float:
    # Sin numpy a proposito: no es una dependencia real del servicio (solo la
    # traia el archivo huerfano technical_analysis_service.py) y una ventana
    # de 15 velas no necesita vectorizacion.
    window = candles[-(length + 1):]
    true_ranges = []
    for i in range(1, len(window)):
        prev_close = window[i - 1].close
        true_ranges.append(max(
            window[i].high - window[i].low,
            abs(window[i].high - prev_close),
            abs(window[i].low - prev_close),
        ))
    return sum(true_ranges) / len(true_ranges)
