from dataclasses import dataclass


@dataclass
class Vela:
    symbol: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    @staticmethod
    def desde_dict(data: dict, symbol: str = "") -> "Vela":
        return Vela(
            symbol=data.get("symbol", symbol),
            timestamp=data.get("timestamp", ""),
            open=float(data.get("open", 0)),
            high=float(data.get("high", 0)),
            low=float(data.get("low", 0)),
            close=float(data.get("close", 0)),
            volume=float(data.get("volume", 0)),
        )
