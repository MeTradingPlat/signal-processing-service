import pandas as pd

from app.config import settings
from app.domain.models.vela import Vela


class GestorBarras:
    """Gestiona el DataFrame de barras para un símbolo.

    Agrega nuevas velas incrementalmente y recorta las más antiguas
    para mantener el tamaño controlado.
    """

    @staticmethod
    def crear_dataframe_desde_velas(velas_raw: list[dict]) -> pd.DataFrame:
        """Crea un DataFrame a partir de una lista de velas (dicts del REST)."""
        if not velas_raw:
            return pd.DataFrame(
                columns=["timestamp", "open", "high", "low", "close", "volume"]
            )

        df = pd.DataFrame(velas_raw)
        columnas_requeridas = ["timestamp", "open", "high", "low", "close", "volume"]
        for col in columnas_requeridas:
            if col not in df.columns:
                df[col] = 0.0

        df = df[columnas_requeridas].copy()
        df["open"] = pd.to_numeric(df["open"], errors="coerce")
        df["high"] = pd.to_numeric(df["high"], errors="coerce")
        df["low"] = pd.to_numeric(df["low"], errors="coerce")
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")

        return df.reset_index(drop=True)

    @staticmethod
    def agregar_vela(df: pd.DataFrame, vela: Vela) -> pd.DataFrame:
        """Agrega una nueva vela al DataFrame y recorta si excede el máximo."""
        nueva_fila = pd.DataFrame([{
            "timestamp": vela.timestamp,
            "open": vela.open,
            "high": vela.high,
            "low": vela.low,
            "close": vela.close,
            "volume": vela.volume,
        }])

        df = pd.concat([df, nueva_fila], ignore_index=True)

        max_barras = settings.max_barras_por_simbolo
        if len(df) > max_barras:
            df = df.iloc[-max_barras:].reset_index(drop=True)

        return df
