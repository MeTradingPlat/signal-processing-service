from datetime import date
from typing import Optional

from pydantic import BaseModel

from app.models.enums import EnumEstadoEscaner


class EstadoEscaner(BaseModel):
    enumEstadoEscaner: EnumEstadoEscaner = EnumEstadoEscaner.DETENIDO
    fechaRegistro: Optional[date] = None
