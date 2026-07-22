from pydantic import BaseModel

from app.models.enums import EnumTipoEjecucion


class TipoEjecucion(BaseModel):
    etiqueta: str = ""
    enumTipoEjecucion: EnumTipoEjecucion
