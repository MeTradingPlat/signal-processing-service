from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field

from app.models.enums import EnumCondicional, EnumTipoValor


class ValorFloat(BaseModel):
    enumTipoValor: Literal[EnumTipoValor.FLOAT] = EnumTipoValor.FLOAT
    etiqueta: str = ""
    valor: Optional[float] = None


class ValorInteger(BaseModel):
    enumTipoValor: Literal[EnumTipoValor.INTEGER] = EnumTipoValor.INTEGER
    etiqueta: str = ""
    valor: Optional[int] = None


class ValorString(BaseModel):
    enumTipoValor: Literal[EnumTipoValor.STRING] = EnumTipoValor.STRING
    etiqueta: str = ""
    valor: Optional[str] = None


class ValorCondicional(BaseModel):
    enumTipoValor: Literal[EnumTipoValor.CONDICIONAL] = EnumTipoValor.CONDICIONAL
    etiqueta: str = ""
    enumCondicional: Optional[EnumCondicional] = None
    isInteger: bool = False
    valor1: Optional[float] = None
    valor2: Optional[float] = None


Valor = Annotated[
    Union[ValorFloat, ValorInteger, ValorString, ValorCondicional],
    Field(discriminator="enumTipoValor"),
]
