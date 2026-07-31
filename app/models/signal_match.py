from datetime import datetime

from pydantic import BaseModel

from app.models.filtro import Filtro


class SignalMatch(BaseModel):
    filtro: Filtro
    vela_timestamp: datetime
    precio: float | None = None
