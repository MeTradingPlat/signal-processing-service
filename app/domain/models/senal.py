from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class Senal:
    id_escaner: int
    nombre_escaner: str
    symbol: str
    tipo_senal: str
    filtros_aplicados: str
    precio_deteccion: float
    volumen_deteccion: float
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def a_dict(self) -> dict:
        return {
            "idEscaner": self.id_escaner,
            "nombreEscaner": self.nombre_escaner,
            "symbol": self.symbol,
            "tipoSenal": self.tipo_senal,
            "filtrosAplicados": self.filtros_aplicados,
            "precioDeteccion": self.precio_deteccion,
            "volumenDeteccion": self.volumen_deteccion,
            "timestamp": self.timestamp,
            "servicioOrigen": "signal-processing-service",
        }
