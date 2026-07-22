from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.enums import EnumCategoriaFiltro, EnumFiltro
from app.models.parametro import Parametro


class CategoriaFiltro(BaseModel):
    etiqueta: str = ""
    enumCategoriaFiltro: EnumCategoriaFiltro


class Filtro(BaseModel):
    enumFiltro: EnumFiltro
    etiquetaNombre: str = ""
    etiquetaDescripcion: str = ""
    objCategoria: Optional[CategoriaFiltro] = None
    parametros: List[Parametro] = Field(default_factory=list)
