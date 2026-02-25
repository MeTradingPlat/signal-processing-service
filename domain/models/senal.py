"""Modelo de dominio: Senal (resultado de evaluacion de un escaner)."""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Senal:
    escaner_id: int
    escaner_nombre: str
    symbol: str
    filtros_evaluados: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __str__(self) -> str:
        return (
            f"[SENAL] Escaner: {self.escaner_nombre} (ID:{self.escaner_id}) | "
            f"Symbol: {self.symbol} | "
            f"Filtros: {', '.join(self.filtros_evaluados)} | "
            f"Timestamp: {self.timestamp}"
        )
