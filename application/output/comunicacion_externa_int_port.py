"""Puerto de salida: toda comunicacion con servicios externos."""

from abc import ABC, abstractmethod


class ComunicacionExternaIntPort(ABC):

    # =========================================================================
    # Scanner Management Service
    # =========================================================================

    @abstractmethod
    def obtener_escaneres_activos(self) -> list:
        """Obtiene todos los escaneres con estado INICIADO."""
        pass

    # =========================================================================
    # Market Data Service - Mercados y Simbolos
    # =========================================================================

    @abstractmethod
    def obtener_mercados_disponibles(self) -> list[dict]:
        """Obtiene los mercados disponibles (NYSE, NASDAQ, AMEX, ETF, OTC)."""
        pass

    @abstractmethod
    def obtener_simbolos_por_mercado(self, enum_mercado: str) -> list[str]:
        """Obtiene simbolos filtrados por mercado."""
        pass

    # =========================================================================
    # Market Data Service - Data Historica
    # =========================================================================

    @abstractmethod
    def obtener_candles_historicos(self, symbol: str, timeframe: str, from_date: str, to_date: str) -> list:
        """Obtiene candles OHLCV historicos."""
        pass

    # =========================================================================
    # Market Data Service - Quote
    # =========================================================================

    @abstractmethod
    def obtener_quote(self, symbol: str) -> dict:
        """Obtiene quote actual (bid, ask, last, halt status, etc)."""
        pass

    # =========================================================================
    # Datos Fundamentales (Yahoo Finance + Market Data Service)
    # =========================================================================

    @abstractmethod
    def obtener_datos_fundamentales(self, symbol: str) -> "DatosFundamentales":
        """
        Obtiene datos fundamentales combinando:
        - Yahoo Finance: float, shares outstanding, short interest, short ratio
        - Market Data Service: days until earnings, halt status
        - Calculado: market cap = last_price * shares_outstanding
        """
        pass

    # =========================================================================
    # Market Data Service - Ordenes
    # =========================================================================

    @abstractmethod
    def enviar_orden_bracket(
        self, symbol: str, action: str, quantity: int,
        entry_price: float, stop_loss_price: float, take_profit_price: float
    ) -> dict:
        """
        Envia una orden bracket (OTOCO) con stop loss y take profit.
        Retorna dict con orderId, status.
        """
        pass

    @abstractmethod
    def cancelar_orden(self, order_id: str) -> None:
        """Cancela una orden por su ID."""
        pass
