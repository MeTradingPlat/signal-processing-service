"""Enumeracion de tipos de ejecucion."""

from enum import Enum


class EnumTipoEjecucion(str, Enum):
    UNA_VEZ = "UNA_VEZ"
    DIARIA = "DIARIA"
