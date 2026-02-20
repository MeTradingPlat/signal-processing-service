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

    @abstractmethod
    def obtener_candles_historicos_batch(self, symbols: list[str], timeframe: str, bars: int) -> dict:
        """Obtiene candles OHLCV para multiples simbolos. Retorna dict {symbol: [Candle, ...]}."""
        pass

    @abstractmethod
    def obtener_ultima_barra_completa_batch(self, symbols: list[str], timeframe: str) -> dict:
        """Obtiene la ultima barra cerrada para multiples simbolos. Retorna dict {symbol: Candle}."""
        pass

    @abstractmethod
    def obtener_barra_en_formacion_batch(self, symbols: list[str], timeframe: str) -> dict:
        """Obtiene la barra en formacion para multiples simbolos. Retorna dict {symbol: Candle}."""
        pass


    @abstractmethod
    def obtener_datos_fundamentales(self, symbol: str) -> "DatosFundamentales":
        """
        Obtiene datos fundamentales (actualmente via Yahoo Finance).
        """
        pass

