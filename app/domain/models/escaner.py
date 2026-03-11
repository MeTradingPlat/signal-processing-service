from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time


@dataclass
class ValorCondicional:
    enum_condicional: str
    is_integer: bool = False
    valor1: float | None = None
    valor2: float | None = None


@dataclass
class Parametro:
    enum_parametro: str
    etiqueta: str = ""
    obj_valor_seleccionado: dict | None = None
    opciones: list[dict] = field(default_factory=list)

    def obtener_condicional(self) -> ValorCondicional | None:
        """Extrae ValorCondicional del valor seleccionado si es de tipo CONDICIONAL."""
        val = self.obj_valor_seleccionado
        if val is None:
            return None
        if val.get("enumTipoValor") == "CONDICIONAL":
            return ValorCondicional(
                enum_condicional=val.get("enumCondicional", ""),
                is_integer=val.get("isInteger", False),
                valor1=val.get("valor1"),
                valor2=val.get("valor2"),
            )
        return None

    def obtener_valor_string(self) -> str | None:
        val = self.obj_valor_seleccionado
        if val is None:
            return None
        if val.get("enumTipoValor") == "STRING":
            return val.get("valor")
        # Para enums como timeframe, el valor viene en etiqueta o como string
        return val.get("etiqueta") or val.get("valor")

    def obtener_valor_numerico(self) -> float | None:
        val = self.obj_valor_seleccionado
        if val is None:
            return None
        tipo = val.get("enumTipoValor")
        if tipo in ("INTEGER", "FLOAT"):
            return val.get("valor")
        return None


@dataclass
class Filtro:
    enum_filtro: str
    etiqueta_nombre: str = ""
    etiqueta_descripcion: str = ""
    parametros: list[Parametro] = field(default_factory=list)

    def obtener_parametro(self, enum_parametro: str) -> Parametro | None:
        for p in self.parametros:
            if p.enum_parametro == enum_parametro:
                return p
        return None

    def obtener_timeframe(self) -> str | None:
        """Busca el parametro de timeframe en los parametros del filtro."""
        for p in self.parametros:
            if "TIMEFRAME" in p.enum_parametro.upper():
                val_str = p.obtener_valor_string()
                if val_str:
                    return val_str
        return None


@dataclass
class Escaner:
    id_escaner: int
    nombre: str
    descripcion: str = ""
    hora_inicio: time = field(default_factory=lambda: time(0, 0))
    hora_fin: time = field(default_factory=lambda: time(23, 59))
    tipo_ejecucion: str = "DIARIA"
    mercados: list[str] = field(default_factory=list)
    filtros: list[Filtro] = field(default_factory=list)

    @staticmethod
    def desde_dict(data: dict, filtros_data: list[dict] | None = None) -> Escaner:
        """Parsea un Escaner desde el JSON del REST de scanner-management."""
        mercados_raw = data.get("mercados", [])
        mercados = []
        for m in mercados_raw:
            if isinstance(m, dict):
                mercados.append(m.get("enumMercado", m.get("id", "")))
            else:
                mercados.append(str(m))

        hora_inicio = _parsear_hora(data.get("horaInicio", "00:00:00"))
        hora_fin = _parsear_hora(data.get("horaFin", "23:59:00"))

        tipo_ej = data.get("objTipoEjecucion", {})
        tipo_ejecucion = tipo_ej.get("enumTipoEjecucion", "DIARIA") if isinstance(tipo_ej, dict) else str(tipo_ej)

        filtros = []
        if filtros_data:
            for f in filtros_data:
                filtros.append(_parsear_filtro(f))

        return Escaner(
            id_escaner=data.get("idEscaner", 0),
            nombre=data.get("nombre", ""),
            descripcion=data.get("descripcion", ""),
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
            tipo_ejecucion=tipo_ejecucion,
            mercados=mercados,
            filtros=filtros,
        )


def _parsear_hora(valor: str) -> time:
    partes = valor.split(":")
    h = int(partes[0]) if len(partes) > 0 else 0
    m = int(partes[1]) if len(partes) > 1 else 0
    s = int(partes[2]) if len(partes) > 2 else 0
    return time(h, m, s)


def _parsear_filtro(data: dict) -> Filtro:
    parametros = []
    for p in data.get("parametros", []):
        parametros.append(Parametro(
            enum_parametro=p.get("enumParametro", ""),
            etiqueta=p.get("etiqueta", ""),
            obj_valor_seleccionado=p.get("objValorSeleccionado"),
            opciones=p.get("opciones", []),
        ))

    return Filtro(
        enum_filtro=data.get("enumFiltro", ""),
        etiqueta_nombre=data.get("etiquetaNombre", ""),
        etiqueta_descripcion=data.get("etiquetaDescripcion", ""),
        parametros=parametros,
    )
