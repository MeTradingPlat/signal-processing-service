from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.enums import EnumParametro
from app.models.valor import Valor


class Parametro(BaseModel):
    enumParametro: EnumParametro
    etiqueta: Optional[str] = None
    objValorSeleccionado: Optional[Valor] = None
    opciones: List[Valor] = Field(default_factory=list)
