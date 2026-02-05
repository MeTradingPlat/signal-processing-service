"""Modelo de dominio: Datos fundamentales de un simbolo."""

from dataclasses import dataclass


@dataclass
class DatosFundamentales:
    symbol: str = ""
    market_cap: float = 0.0
    float_shares: float = 0.0
    shares_outstanding: float = 0.0
    short_interest: float = 0.0
    short_ratio: float = 0.0
    days_until_earnings: int = 0
    estado_noticia: str = ""  # NINGUNA, POSITIVA, NEGATIVA
    halt_status: str = ""  # Estado de halt del exchange
