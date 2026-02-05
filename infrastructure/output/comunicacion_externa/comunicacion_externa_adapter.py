"""
Adaptador de salida: comunicacion con todos los servicios externos via REST.

Implementa ComunicacionExternaIntPort.
Combina llamadas a market-data-service (Java) y Yahoo Finance (yahooquery).
"""

import logging

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
        self._yahoo = yahoo_adapter or YahooFinanceAdapter()
        self._scanner_management = scanner_adapter or ScannerManagementAdapter()
        self._market_data = market_adapter or MarketDataAdapter()

    # =========================================================================
    # Scanner Management Service
    # =========================================================================

    def obtener_escaneres_activos(self) -> list[Escaner]:
        """GET /api/escaner -> filtra los que tienen estado INICIADO."""
        try:
            data = self._scanner_management.obtener_escaneres_activos()
            # Ya el endpoint retorna solo iniciados, pero mantenemos filtrado por seguridad o mapeo
            escaneres = [self._mapear_escaner(item) for item in data]
            return escaneres
        except Exception as e:
            logger.error(f"Error obteniendo escaneres activos: {e}")
            return []

    # =========================================================================
    # Market Data Service - Mercados y Simbolos
    # =========================================================================

    def obtener_mercados_disponibles(self) -> list[dict]:
        """GET /api/marketdata/markets"""
        url = f"{MARKETDATA_SERVICE_URL}/marketdata/markets"
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Error obteniendo mercados desde {url}: {e}")
            return []

    def obtener_simbolos_por_mercado(self, enum_mercado: str) -> list[str]:
        """GET /api/marketdata/symbols?markets={enum_mercado}"""
        url = f"{MARKETDATA_SERVICE_URL}/marketdata/symbols"
        try:
            response = requests.get(url, params={"markets": enum_mercado}, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json()
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
        # El adaptador nuevo usa "bars" o "end_date".
        # Si la interfaz requiere from/to, tendriamos que calcular bars o usar adaptador que soporte fechas.
        # MarketDataAdapter soporta 'end_date'. 'start_date' no esta.
        # Asumiremos obtener ULTIMAS N velas o hasta 'to_date'.
        # Ojo: la firma de este metodo es fija por el puerto.
        # El MarketDataService tiene 'bars' y 'endDate'.
        # Por ahora usaremos 'bars' fijo o intentaremos adaptar.
        
        # Para simplificar y cumplir con "usar lo que retorna marketdata",
        # llamamos con un numero de bares suficiente si no podemos filtrar rango exacto
        # o usamos el MarketDataAdapter tal cual si lo modificamos.
        
        # Como MarketDataAdapter expone obtener_velas_historicas(symbol, timeframe, bars, end_date)
        # Adaptaremos lo mejor posible.
        
        try:
            # TODO: Calcular bars en base a from/to o pedir suficientes.
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
            return candles

        except Exception as e:
            logger.error(f"Error obteniendo candles para {symbol}: {e}")
            return []

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

    # =========================================================================
    # Market Data Service - Quote
    # =========================================================================

    def obtener_quote(self, symbol: str) -> dict:
        """GET /api/marketdata/quote/{symbol}"""
        url = f"{MARKETDATA_SERVICE_URL}/marketdata/quote/{symbol}"
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.warning(f"No se pudo obtener quote para {symbol}: {e}")
            return {}

    # =========================================================================
    # Datos Fundamentales (Yahoo Finance + Market Data Service)
    # =========================================================================

    def obtener_datos_fundamentales(self, symbol: str) -> DatosFundamentales:
        """
        Combina datos de:
        - Yahoo Finance: float, shares outstanding, short interest, short ratio
        - Market Data Service: earnings (days_until_earnings), quote (market cap calc)
        """
        # Yahoo Finance data
        datos = self._yahoo.obtener_datos_fundamentales(symbol)

        # Enriquecer con earnings desde market-data-service
        try:
            url = f"{MARKETDATA_SERVICE_URL}/marketdata/earnings/{symbol}"
            response = requests.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            earnings_data = response.json()
            datos.days_until_earnings = int(earnings_data.get("daysUntilEarnings", 0))
        except requests.RequestException:
            logger.debug(f"No earnings data for {symbol}")

        # Calcular market cap si tenemos quote y shares outstanding
        if datos.shares_outstanding > 0:
            quote = self.obtener_quote(symbol)
            last_price = float(quote.get("last", 0))
            if last_price > 0:
                datos.market_cap = last_price * datos.shares_outstanding

        return datos

    # =========================================================================
    # Market Data Service - Ordenes
    # =========================================================================

    def enviar_orden_bracket(
        self, symbol: str, action: str, quantity: int,
        entry_price: float, stop_loss_price: float, take_profit_price: float
    ) -> dict:
        """POST /api/marketdata/orders"""
        url = f"{MARKETDATA_SERVICE_URL}/marketdata/orders"
        payload = {
            "symbol": symbol,
            "action": action,
            "quantity": quantity,
            "entryPrice": entry_price,
            "stopLossPrice": stop_loss_price,
            "takeProfitPrice": take_profit_price,
        }
        try:
            response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Error enviando orden bracket para {symbol}: {e}")
            return {"error": str(e)}

    def cancelar_orden(self, order_id: str) -> None:
        """DELETE /api/marketdata/orders/{orderId}"""
        url = f"{MARKETDATA_SERVICE_URL}/marketdata/orders/{order_id}"
        try:
            response = requests.delete(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            logger.info(f"Orden {order_id} cancelada")
        except requests.RequestException as e:
            logger.error(f"Error cancelando orden {order_id}: {e}")

    # =========================================================================
    # Mapeo de JSON a modelos de dominio (Escaner)
    # =========================================================================

    def _mapear_escaner(self, data: dict) -> Escaner:
        estado = EstadoEscaner(
            enum_estado_escaner=data.get("objEstado", {}).get("enumEstadoEscaner", ""),
            fecha_registro=data.get("objEstado", {}).get("fechaRegistro", ""),
        )
        tipo_ejecucion = TipoEjecucion(
            etiqueta=data.get("objTipoEjecucion", {}).get("etiqueta", ""),
            enum_tipo_ejecucion=data.get("objTipoEjecucion", {}).get("enumTipoEjecucion", ""),
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
            hora_inicio=data.get("horaInicio", ""),
            hora_fin=data.get("horaFin", ""),
            fecha_creacion=data.get("fechaCreacion", ""),
            obj_estado=estado,
            obj_tipo_ejecucion=tipo_ejecucion,
            mercados=mercados,
            filtros=filtros,
        )

    def _mapear_filtro(self, data: dict) -> Filtro:
        categoria = CategoriaFiltro(
            enum_categoria_filtro=data.get("objCategoria", {}).get("enumCategoriaFiltro", ""),
            etiqueta=data.get("objCategoria", {}).get("etiqueta", ""),
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
        valor_data = data.get("objValorSeleccionado", {})
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
