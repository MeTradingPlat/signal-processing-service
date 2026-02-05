"""Puerto de entrada: caso de uso para procesar senales."""

from abc import ABC, abstractmethod


class ProcesarSenalesCUIntPort(ABC):

    @abstractmethod
    def iniciar(self) -> None:
        """Inicia el servicio: obtiene escaneres activos y programa su ejecucion."""
        pass

    @abstractmethod
    def detener(self) -> None:
        """Detiene el servicio y libera recursos."""
        pass

    @abstractmethod
    def ejecutar_escaner(self, escaner) -> None:
        """Ejecuta un escaner especifico: obtiene data y evalua filtros."""
        pass
