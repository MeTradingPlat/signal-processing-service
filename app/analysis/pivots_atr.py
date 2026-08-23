import numpy as np

from app.scanner.marketdata_models import CandleResponse


def calculate_atr(candles: list[CandleResponse], length: int) -> float:
    window = candles[-(length + 1):]
    highs = np.array([c.high for c in window])
    lows = np.array([c.low for c in window])
    closes = np.array([c.close for c in window])
    prev_closes = closes[:-1]
    true_range = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(np.abs(highs[1:] - prev_closes), np.abs(lows[1:] - prev_closes)),
    )
    return float(np.mean(true_range))
