from dataclasses import dataclass, field

import pandas as pd


@dataclass
class ContextoSimbolo:
    symbol: str
    # Barras históricas por timeframe: {"M1": DataFrame, "M5": DataFrame, ...}
    # Las claves son los valores de EnumTimeframe (ej. "M1", "M5", "M15", "M30", "H1").
    # El primer key insertado es siempre el TF mínimo (el executor inserta en orden ascendente).
    barras_por_tf: dict[str, pd.DataFrame] = field(default_factory=dict)
    # Último timestamp recibido por TF (dedup para no re-agregar la misma vela)
    ultima_vela_por_tf: dict[str, str | None] = field(default_factory=dict)
    fundamentales: dict = field(default_factory=dict)
    halteado: bool = False

    def tiene_barras(self) -> bool:
        """True si al menos un TF tiene barras no vacías."""
        return any(not df.empty for df in self.barras_por_tf.values())

    def a_dict_serializable(self) -> dict:
        """Convierte a dict serializable para enviar al ProcessPoolExecutor."""
        return {
            "symbol": self.symbol,
            "barras_por_tf": {
                tf: df.to_dict(orient="list")
                for tf, df in self.barras_por_tf.items()
            },
            "fundamentales": self.fundamentales,
            "halteado": self.halteado,
        }
