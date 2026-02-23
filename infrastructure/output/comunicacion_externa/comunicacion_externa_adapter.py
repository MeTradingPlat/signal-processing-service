"""
Adaptador de salida: comunicacion con todos los servicios externos via REST.

Implementa ComunicacionExternaIntPort.
Combina llamadas a market-data-service (Java) y Yahoo Finance (yahooquery).
"""

import logging
import sys

import requests

from application.output.comunicacion_externa_int_port import ComunicacionExternaIntPort
from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import (
    Escaner, EstadoEscaner, TipoEjecucion, Mercado, Filtro,
    Parametro, Valor, ValorCondicional, ValorFloat, ValorInteger, ValorString,
    CategoriaFiltro,
)
from infrastructure.output.comunicacion_externa.yahoo_finance_adapter import YahooFinanceAdapter
from infrastructure.output.comunicacion_externa.scanner_management_adapter import ScannerManagementAdapter
from infrastructure.output.comunicacion_externa.market_data_adapter import MarketDataAdapter
from config import SCANNER_SERVICE_URL, MARKETDATA_SERVICE_URL, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


class ComunicacionExternaAdapter(ComunicacionExternaIntPort):

    def __init__(
        self,
        yahoo_adapter: YahooFinanceAdapter | None = None,
        scanner_adapter: ScannerManagementAdapter | None = None,
        market_adapter: MarketDataAdapter | None = None,
    ):
        logger.info("Inicializando ComunicacionExternaAdapter...")
        logger.info(f"  -> SCANNER_SERVICE_URL: {SCANNER_SERVICE_URL}")
        logger.info(f"  -> MARKETDATA_SERVICE_URL: {MARKETDATA_SERVICE_URL}")
        sys.stdout.flush()

        self._yahoo = yahoo_adapter or YahooFinanceAdapter()
        logger.info("  -> YahooFinanceAdapter OK")

        self._scanner_management = scanner_adapter or ScannerManagementAdapter(
            base_url=f"{SCANNER_SERVICE_URL}/escaner"
        )
        logger.info("  -> ScannerManagementAdapter OK")

        self._market_data = market_adapter or MarketDataAdapter()
        logger.info("  -> MarketDataAdapter OK")

        logger.info("ComunicacionExternaAdapter inicializado correctamente")
        sys.stdout.flush()

    # =========================================================================
    # Scanner Management Service
    # =========================================================================

    def obtener_escaneres_activos(self) -> list[Escaner]:
        """GET /api/escaner -> filtra los que tienen estado INICIADO."""
        logger.info("Obteniendo escaneres activos desde scanner-management-service...")
        sys.stdout.flush()
        try:
            data = self._scanner_management.obtener_escaneres_activos()
            logger.info(f"Respuesta del scanner-management-service: {len(data)} escaneres")
            escaneres = [self._mapear_escaner(item) for item in data]
            logger.info(f"Escaneres mapeados exitosamente: {len(escaneres)}")
            for esc in escaneres:
                logger.debug(f"  - Escaner: {esc.nombre} (ID: {esc.id_escaner})")
            sys.stdout.flush()
            return escaneres
        except Exception as e:
            logger.error(f"Error obteniendo escaneres activos: {e}", exc_info=True)
            sys.stdout.flush()
            return []

    # =========================================================================
    # Market Data Service - Mercados y Simbolos
    # =========================================================================

    def obtener_mercados_disponibles(self) -> list[dict]:
        """GET /api/marketdata/markets"""
        url = f"{MARKETDATA_SERVICE_URL}/marketdata/markets"
        logger.debug(f"Obteniendo mercados disponibles desde {url}")
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            mercados = response.json()
            logger.debug(f"Mercados obtenidos: {len(mercados)}")
            return mercados
        except requests.RequestException as e:
            logger.error(f"Error obteniendo mercados desde {url}: {e}")
            return []

    def obtener_simbolos_por_mercado(self, enum_mercado: str) -> list[str]:
        """GET /api/marketdata/symbols?markets={enum_mercado}"""
        url = f"{MARKETDATA_SERVICE_URL}/marketdata/symbols"
        logger.debug(f"Obteniendo simbolos para mercado {enum_mercado}...")
        try:
            response = requests.get(url, params={"markets": enum_mercado}, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            equities = response.json()  # List of {symbol, description, listedMarket}
            # Extraer solo los simbolos (strings)
            simbolos = [equity['symbol'] for equity in equities]
            logger.info(f"Simbolos obtenidos para {enum_mercado}: {len(simbolos)}")
            return simbolos
        except requests.RequestException as e:
            logger.warning(f"No se pudo obtener simbolos para mercado {enum_mercado}: {e}")
            return []

    # =========================================================================
    # Market Data Service - Data Historica
    # =========================================================================

    def obtener_candles_historicos(
        self, symbol: str, timeframe: str, from_date: str, to_date: str
    ) -> list[Candle]:
        """GET /api/marketdata/historical/{symbol}?timeframe=..."""
        logger.debug(f"Obteniendo candles para {symbol} tf={timeframe}...")
        try:
            data = self._market_data.obtener_velas_historicas(symbol, timeframe, bars=500, end_date=to_date)

            candles = [
                Candle(
                    symbol=item.get("symbol", symbol),
                    timestamp=item.get("timestamp", ""),
                    open=float(item.get("open", 0)),
                    high=float(item.get("high", 0)),
                    low=float(item.get("low", 0)),
                    close=float(item.get("close", 0)),
                    volume=float(item.get("volume", 0)),
                )
                for item in data
            ]
            logger.debug(f"Candles obtenidos para {symbol}: {len(candles)}")
            return candles

        except Exception as e:
            logger.error(f"Error obteniendo candles para {symbol}: {e}")
            return []

    def obtener_candles_historicos_batch(
        self, symbols: list[str], timeframe: str, bars: int
    ) -> dict[str, list[Candle]]:
        """POST /api/marketdata/historical/batch - obtiene candles para multiples simbolos."""
        logger.info(f"Batch: obteniendo candles para {len(symbols)} symbols, tf={timeframe}, bars={bars}")
        try:
            data = self._market_data.obtener_velas_historicas_batch(symbols, timeframe, bars)

            # Convertir data (dict {symbol: [dict, ...]}) a dict {symbol: [Candle, ...]}
            resultado = {}
            for symbol, candles_data in data.items():
                candles = [
                    Candle(
                        symbol=item.get("symbol", symbol),
                        timestamp=item.get("timestamp", ""),
                        open=float(item.get("open", 0)),
                        high=float(item.get("high", 0)),
                        low=float(item.get("low", 0)),
                        close=float(item.get("close", 0)),
                        volume=float(item.get("volume", 0)),
                    )
                    for item in candles_data
                ]
                resultado[symbol] = candles

            logger.info(f"Batch complete: {len(resultado)} symbols procesados, "
                       f"{sum(len(c) for c in resultado.values())} candles totales")
            return resultado

        except Exception as e:
            logger.error(f"Error en batch candles ({len(symbols)} symbols): {e}")
            return {}

    # =========================================================================
    # Market Data Service - Barra en Formacion
    # =========================================================================

    def obtener_barra_en_formacion(self, symbol: str, timeframe: str) -> Candle | None:
        """GET /historical/{symbol}/current — barra en formacion (periodo aun no cerrado)."""
        try:
            data = self._market_data.obtener_barra_en_formacion(symbol, timeframe)
            if not data:
                return None
            return Candle(
                symbol=data.get("symbol", symbol),
                timestamp=data.get("timestamp", ""),
                open=float(data.get("open", 0)),
                high=float(data.get("high", 0)),
                low=float(data.get("low", 0)),
                close=float(data.get("close", 0)),
                volume=float(data.get("volume", 0)),
            )
        except Exception as e:
            logger.error(f"Error obteniendo barra en formacion para {symbol}: {e}")
            return None

    def obtener_ultima_barra_completa_batch(self, symbols: list[str], timeframe: str) -> dict[str, Candle]:
        """POST /historical/batch/last - obtiene la ultima barra cerrada para multiples simbolos."""
        logger.info(f"Batch Last: obteniendo ultima barra para {len(symbols)} symbols, tf={timeframe}")
        try:
            data = self._market_data.obtener_ultima_barra_completa_batch(symbols, timeframe)
            resultado = {}
            for symbol, candle_data in data.items():
                if candle_data:
                    resultado[symbol] = Candle(
                        symbol=candle_data.get("symbol", symbol),
                        timestamp=candle_data.get("timestamp", ""),
                        open=float(candle_data.get("open", 0)),
                        high=float(candle_data.get("high", 0)),
                        low=float(candle_data.get("low", 0)),
                        close=float(candle_data.get("close", 0)),
                        volume=float(candle_data.get("volume", 0)),
                    )
            logger.info(f"Batch Last complete: {len(resultado)} candles obtenidas")
            return resultado
        except Exception as e:
            logger.error(f"Error en batch last candles ({len(symbols)} symbols): {e}")
            return {}

    def obtener_barra_en_formacion_batch(self, symbols: list[str], timeframe: str) -> dict[str, Candle]:
        """POST /historical/batch/current - obtiene la barra en formacion para multiples simbolos."""
        logger.info(f"Batch Current: obteniendo barra formando para {len(symbols)} symbols, tf={timeframe}")
        try:
            data = self._market_data.obtener_barra_en_formacion_batch(symbols, timeframe)
            resultado = {}
            for symbol, candle_data in data.items():
                if candle_data:
                    resultado[symbol] = Candle(
                        symbol=candle_data.get("symbol", symbol),
                        timestamp=candle_data.get("timestamp", ""),
                        open=float(candle_data.get("open", 0)),
                        high=float(candle_data.get("high", 0)),
                        low=float(candle_data.get("low", 0)),
                        close=float(candle_data.get("close", 0)),
                        volume=float(candle_data.get("volume", 0)),
                    )
            logger.info(f"Batch Current complete: {len(resultado)} candles obtenidas")
            return resultado
        except Exception as e:
            logger.error(f"Error en batch current candles ({len(symbols)} symbols): {e}")
            return {}


    def obtener_datos_fundamentales(self, symbol: str) -> DatosFundamentales:
        """
        Obtiene datos fundamentales (solo Yahoo Finance por ahora).
        """
        return self._yahoo.obtener_datos_fundamentales(symbol)


    # =========================================================================
    # Mapeo de JSON a modelos de dominio (Escaner)
    # =========================================================================

    def _mapear_escaner(self, data: dict) -> Escaner:
        obj_estado = data.get("objEstado") or {}
        estado = EstadoEscaner(
            enum_estado_escaner=obj_estado.get("enumEstadoEscaner", ""),
            fecha_registro=obj_estado.get("fechaRegistro", ""),
        )
        obj_tipo_ejecucion = data.get("objTipoEjecucion") or {}
        tipo_ejecucion = TipoEjecucion(
            etiqueta=obj_tipo_ejecucion.get("etiqueta", ""),
            enum_tipo_ejecucion=obj_tipo_ejecucion.get("enumTipoEjecucion", ""),
        )
        mercados = [
            Mercado(
                enum_mercado=m.get("enumMercado", ""),
                etiqueta=m.get("etiqueta", ""),
            )
            for m in data.get("mercados", [])
        ]
        filtros = [self._mapear_filtro(f) for f in data.get("filtros", [])]

        return Escaner(
            id_escaner=data.get("idEscaner", 0),
            nombre=data.get("nombre", ""),
            descripcion=data.get("descripcion", ""),
            hora_inicio=self._parse_time_value(data.get("horaInicio", "")),
            hora_fin=self._parse_time_value(data.get("horaFin", "")),
            fecha_creacion=self._parse_date_value(data.get("fechaCreacion", "")),
            obj_estado=estado,
            obj_tipo_ejecucion=tipo_ejecucion,
            mercados=mercados,
            filtros=filtros,
        )

    def _parse_time_value(self, value) -> str:
        """Convierte un valor de tiempo (lista o string) a formato string HH:MM:SS."""
        if isinstance(value, list):
            # Java LocalTime serializado como [hour, minute, second] o [hour, minute]
            hour = value[0] if len(value) > 0 else 0
            minute = value[1] if len(value) > 1 else 0
            second = value[2] if len(value) > 2 else 0
            return f"{hour:02d}:{minute:02d}:{second:02d}"
        elif isinstance(value, str):
            return value
        else:
            return ""

    def _parse_date_value(self, value) -> str:
        """Convierte un valor de fecha (lista o string) a formato string YYYY-MM-DD."""
        if isinstance(value, list):
            # Java LocalDate serializado como [year, month, day]
            year = value[0] if len(value) > 0 else 1970
            month = value[1] if len(value) > 1 else 1
            day = value[2] if len(value) > 2 else 1
            return f"{year:04d}-{month:02d}-{day:02d}"
        elif isinstance(value, str):
            return value
        else:
            return ""

    def _mapear_filtro(self, data: dict) -> Filtro:
        obj_categoria = data.get("objCategoria") or {}
        categoria = CategoriaFiltro(
            enum_categoria_filtro=obj_categoria.get("enumCategoriaFiltro", ""),
            etiqueta=obj_categoria.get("etiqueta", ""),
        )
        parametros = [self._mapear_parametro(p) for p in data.get("parametros", [])]

        return Filtro(
            enum_filtro=data.get("enumFiltro", ""),
            etiqueta_nombre=data.get("etiquetaNombre", ""),
            etiqueta_descripcion=data.get("etiquetaDescripcion", ""),
            obj_categoria=categoria,
            parametros=parametros,
        )

    def _mapear_parametro(self, data: dict) -> Parametro:
        valor_data = data.get("objValorSeleccionado") or {}
        valor = self._mapear_valor(valor_data)

        opciones_data = data.get("opciones", [])
        opciones = [self._mapear_valor(o) for o in opciones_data]

        return Parametro(
            enum_parametro=data.get("enumParametro", ""),
            etiqueta=data.get("etiqueta", ""),
            obj_valor_seleccionado=valor,
            opciones=opciones,
        )

    def _mapear_valor(self, data: dict) -> Valor:
        if not data:
            return Valor()

        tipo = data.get("enumTipoValor", "")

        if tipo == "CONDICIONAL":
            return ValorCondicional(
                etiqueta=data.get("etiqueta", ""),
                enum_tipo_valor=tipo,
                valor1=float(data.get("valor1", 0)),
                valor2=float(data.get("valor2", 0)),
                enum_condicional=data.get("enumCondicional", ""),
            )
        elif tipo == "FLOAT":
            return ValorFloat(
                etiqueta=data.get("etiqueta", ""),
                enum_tipo_valor=tipo,
                valor=float(data.get("valor", 0)),
            )
        elif tipo == "INTEGER":
            return ValorInteger(
                etiqueta=data.get("etiqueta", ""),
                enum_tipo_valor=tipo,
                valor=int(data.get("valor", 0)),
            )
        elif tipo == "STRING":
            return ValorString(
                etiqueta=data.get("etiqueta", ""),
                enum_tipo_valor=tipo,
                valor=str(data.get("valor", "")),
            )
        else:
            return Valor(
                etiqueta=data.get("etiqueta", ""),
                enum_tipo_valor=tipo,
            )
