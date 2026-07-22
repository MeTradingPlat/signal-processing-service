from pydantic import BaseModel

from app.models.enums import EnumMercado


class Mercado(BaseModel):
    etiqueta: str = ""
    enumMercado: EnumMercado
