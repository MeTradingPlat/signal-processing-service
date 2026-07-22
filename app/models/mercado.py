from typing import Optional

from pydantic import BaseModel

from app.models.enums import EnumMercado


class Mercado(BaseModel):
    etiqueta: Optional[str] = None
    enumMercado: EnumMercado
