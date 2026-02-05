"""Modelos de dominio: Escaner y sus componentes."""

from dataclasses import dataclass, field


@dataclass
class Valor:
    etiqueta: str = ""
    enum_tipo_valor: str = ""


@dataclass
class ValorCondicional(Valor):
    valor1: float = 0.0
    valor2: float = 0.0


@dataclass
class ValorFloat(Valor):
    valor: float = 0.0


@dataclass
class ValorInteger(Valor):
    valor: int = 0


@dataclass
class ValorString(Valor):
    valor: str = ""


@dataclass
class Parametro:
    enum_parametro: str = ""
    etiqueta: str = ""
    obj_valor_seleccionado: Valor = field(default_factory=Valor)
    opciones: list = field(default_factory=list)


@dataclass
class CategoriaFiltro:
    enum_categoria_filtro: str = ""
    etiqueta: str = ""


@dataclass
class Filtro:
    enum_filtro: str = ""
    etiqueta_nombre: str = ""
    etiqueta_descripcion: str = ""
    obj_categoria: CategoriaFiltro = field(default_factory=CategoriaFiltro)
    parametros: list[Parametro] = field(default_factory=list)

    def obtener_parametro(self, enum_parametro: str) -> Parametro | None:
        """Busca un parametro por su enum."""
        for p in self.parametros:
            if p.enum_parametro == enum_parametro:
                return p
        return None


@dataclass
class EstadoEscaner:
    enum_estado_escaner: str = ""
    fecha_registro: str = ""


@dataclass
class TipoEjecucion:
    etiqueta: str = ""
    enum_tipo_ejecucion: str = ""


@dataclass
class Mercado:
    enum_mercado: str = ""
    etiqueta: str = ""


@dataclass
class Escaner:
    id_escaner: int = 0
    nombre: str = ""
    descripcion: str = ""
    hora_inicio: str = ""
    hora_fin: str = ""
    fecha_creacion: str = ""
    obj_estado: EstadoEscaner = field(default_factory=EstadoEscaner)
    obj_tipo_ejecucion: TipoEjecucion = field(default_factory=TipoEjecucion)
    mercados: list[Mercado] = field(default_factory=list)
    filtros: list[Filtro] = field(default_factory=list)

    def esta_activo(self) -> bool:
        return self.obj_estado.enum_estado_escaner == "INICIADO"
