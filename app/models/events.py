from datetime import datetime, timezone
from typing import Union

from pydantic import BaseModel, Field

from app.models.escaner import Escaner


class ScannerStoppedPayload(BaseModel):
    idEscaner: int


EventPayload = Union[Escaner, ScannerStoppedPayload]


class TunnelMessage(BaseModel):
    type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict = Field(default_factory=dict)


class EventType:
    SCANNER_STARTED = "SCANNER_STARTED"
    SCANNER_STOPPED = "SCANNER_STOPPED"
