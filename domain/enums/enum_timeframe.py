"""Enumeracion de timeframes."""

from enum import Enum


class EnumTimeframe(str, Enum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    D1 = "D1"
    W1 = "W1"
    MO1 = "MO1"

    def to_api_value(self) -> str:
        """Valor que espera la API de market-data."""
        return self.value
