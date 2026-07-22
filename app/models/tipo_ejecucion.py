from typing import Optional

from pydantic import BaseModel

from app.models.enums import EnumTipoEjecucion


class TipoEjecucion(BaseModel):
    etiqueta: Optional[str] = None
    enumTipoEjecucion: EnumTipoEjecucion
