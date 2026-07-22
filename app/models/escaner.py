from datetime import date, time
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.estado_escaner import EstadoEscaner
from app.models.filtro import Filtro
from app.models.mercado import Mercado
from app.models.tipo_ejecucion import TipoEjecucion


class Escaner(BaseModel):
    idEscaner: int
    nombre: str = ""
    descripcion: str = ""
    horaInicio: time
    horaFin: time
    fechaCreacion: Optional[date] = None
    objEstado: Optional[EstadoEscaner] = None
    objTipoEjecucion: Optional[TipoEjecucion] = None
    mercados: List[Mercado] = Field(default_factory=list)
    filtros: List[Filtro] = Field(default_factory=list)
