"""Enumeracion de estados del escaner."""

from enum import Enum


class EnumEstadoEscaner(str, Enum):
    ARCHIVADO = "ARCHIVADO"
    INICIADO = "INICIADO"
    DETENIDO = "DETENIDO"
    DESARCHIVADO = "DESARCHIVADO"
