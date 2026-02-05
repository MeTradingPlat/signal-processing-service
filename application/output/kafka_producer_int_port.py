"""Puerto de salida: publicacion de mensajes a Kafka."""

from abc import ABC, abstractmethod


class KafkaProducerIntPort(ABC):

    @abstractmethod
    def publicar_senal(self, mensaje: dict) -> None:
        """Publica una senal al topic 'signals'."""
        pass

    @abstractmethod
    def publicar_estado_activo(self, mensaje: dict) -> None:
        """Publica cambio de estado de activo al topic 'asset-state'."""
        pass

    @abstractmethod
    def publicar_log(self, mensaje: dict) -> None:
        """Publica un log al topic 'logs'."""
        pass
