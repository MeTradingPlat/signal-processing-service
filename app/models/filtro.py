from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.enums import EnumCategoriaFiltro, EnumFiltro
from app.models.parametro import Parametro


class CategoriaFiltro(BaseModel):
    etiqueta: Optional[str] = None
    enumCategoriaFiltro: EnumCategoriaFiltro


class Filtro(BaseModel):
    enumFiltro: EnumFiltro
    etiquetaNombre: Optional[str] = None
    etiquetaDescripcion: Optional[str] = None
    objCategoria: Optional[CategoriaFiltro] = None
    parametros: List[Parametro] = Field(default_factory=list)
    revisionTiempoReal: bool = False
    # None = filtro requerido (AND estricto, comportamiento de siempre). Dos
    # o mas filtros con el MISMO valor forman un grupo alternativo dentro de
    # su grupo de temporalidad -- ver symbols.py:_todos_los_requeridos_pasan.
    grupoAlternativo: Optional[int] = None
