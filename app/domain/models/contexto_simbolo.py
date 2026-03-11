from dataclasses import dataclass, field

import pandas as pd


@dataclass
class ContextoSimbolo:
    symbol: str
    df_barras: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(
        columns=["timestamp", "open", "high", "low", "close", "volume"]
    ))
    ultima_vela_timestamp: str | None = None
    fundamentales: dict = field(default_factory=dict)
    halteado: bool = False

    def a_dict_serializable(self) -> dict:
        """Convierte a dict serializable para enviar al ProcessPoolExecutor."""
        return {
            "symbol": self.symbol,
            "barras": self.df_barras.to_dict(orient="list"),
            "ultima_vela_timestamp": self.ultima_vela_timestamp,
            "fundamentales": self.fundamentales,
            "halteado": self.halteado,
        }

    @staticmethod
    def desde_dict_serializable(data: dict) -> "ContextoSimbolo":
        """Reconstruye desde dict serializado (en el worker del pool)."""
        df = pd.DataFrame(data["barras"])
        return ContextoSimbolo(
            symbol=data["symbol"],
            df_barras=df,
            ultima_vela_timestamp=data.get("ultima_vela_timestamp"),
            fundamentales=data.get("fundamentales", {}),
            halteado=data.get("halteado", False),
        )
