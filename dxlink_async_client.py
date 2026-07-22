"""
Cliente Asíncrono dxLink para Ingesta de Datos de Mercado

Mantiene conexión persistente con dxLink (WebSocket).
Recibe Quote (Bid/Ask) y Trade (Precio/Volumen) a latencia sub-milisegundo.

Protocolo dxLink:
- Canal 0: Control (SETUP, AUTH, KEEPALIVE)
- Canales impares: Datos (FEED)

Formato: COMPACT (optimizado para HFT, no FULL)
"""

import asyncio
import websockets
import json
import logging
from typing import Callable, Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class MarketDataSnapshot:
    """Snapshot de datos de mercado"""
    symbol: str
    type: str  # QUOTE, TRADE, GREEKS, UNDERLYING, CANDLE
    bid_price: Optional[float] = None
    ask_price: Optional[float] = None
    bid_size: Optional[int] = None
    ask_size: Optional[int] = None
    price: Optional[float] = None
    size: Optional[int] = None
    timestamp: int = None
    
    # ✅ CORRECCIÓN: Campos para Greeks
    volatility: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    
    # ✅ CORRECCIÓN: Campos para Underlying
    put_call_ratio: Optional[float] = None
    call_volume: Optional[int] = None
    put_volume: Optional[int] = None
    
    # ✅ CORRECCIÓN: Campos para Candle
    close: Optional[float] = None
    vwap: Optional[float] = None
    volume: Optional[int] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = int(datetime.now().timestamp() * 1000)


class AsyncDxLinkClient:
    """
    Cliente Asíncrono dxLink de Alta Frecuencia
    
    Mantiene conexión persistente y recibe datos de mercado en tiempo real.
    """

    def __init__(self, wss_url: str, quote_token: str, on_market_data: Optional[Callable] = None):
        """
        Inicializa el cliente dxLink
        
        Args:
            wss_url: URL WebSocket de dxLink (ej: wss://stream.dxfeed.com/webapi)
            quote_token: Token de 24h obtenido de /api-quote-tokens
            on_market_data: Callback para procesar datos de mercado
        """
        self.wss_url = wss_url
        self.quote_token = quote_token
        self.on_market_data = on_market_data
        self.ws = None
        self.keepalive_task = None
        self.price_cache: Dict[str, MarketDataSnapshot] = {}
        self.subscribed_symbols: List[str] = []

    async def keepalive_worker(self):
        """
        Mantiene la conexión viva enviando KEEPALIVE cada 30 segundos
        
        Si el servidor dxLink no recibe KEEPALIVE en 60 segundos,
        cierra brutalmente el socket con error TIMEOUT.
        """
        try:
            while True:
                await asyncio.sleep(30)
                if self.ws:
                    await self.ws.send(json.dumps({"type": "KEEPALIVE", "channel": 0}))
                    logger.trace("[DXLINK] KEEPALIVE enviado")
        except asyncio.CancelledError:
            logger.info("[DXLINK] Keepalive worker cancelado")
            pass

    async def connect_and_stream(self):
        """
        Conecta a dxLink y mantiene el stream de datos
        
        Protocolo:
        1. SETUP en canal 0
        2. AUTH en canal 0
        3. CHANNEL_REQUEST para FEED
        4. FEED_SETUP con formato COMPACT
        5. FEED_SUBSCRIPTION para símbolos
        6. Loop de KEEPALIVE cada 30s
        """
        try:
            async with websockets.connect(self.wss_url) as ws:
                self.ws = ws
                logger.info("[DXLINK] ✅ Conectado a dxLink")

                # 1. SETUP en Canal 0
                setup_msg = {
                    "type": "SETUP",
                    "channel": 0,
                    "keepaliveTimeout": 60,
                    "acceptKeepaliveTimeout": 60,
                    "version": "0.1"
                }
                await ws.send(json.dumps(setup_msg))
                logger.debug("[DXLINK] SETUP enviado")

                # 2. AUTH en Canal 0
                auth_msg = {
                    "type": "AUTH",
                    "channel": 0,
                    "token": self.quote_token
                }
                await ws.send(json.dumps(auth_msg))
                logger.debug("[DXLINK] AUTH enviado")

                # 3. Lanzar daemon de Heartbeat
                self.keepalive_task = asyncio.create_task(self.keepalive_worker())

                # 4. Loop de recepción de mensajes
                async for message in ws:
                    try:
                        data = json.loads(message)
                        await self.handle_message(data, ws)
                    except json.JSONDecodeError:
                        logger.error("[DXLINK] Error decodificando JSON: %s", message)
                    except Exception as e:
                        logger.error("[DXLINK] Error procesando mensaje", exc_info=e)

        except asyncio.CancelledError:
            logger.info("[DXLINK] Conexión cancelada")
            if self.keepalive_task:
                self.keepalive_task.cancel()
        except Exception as e:
            logger.error("[DXLINK] Error en conexión", exc_info=e)
            await asyncio.sleep(5)  # Esperar antes de reconectar
            await self.connect_and_stream()

    async def handle_message(self, data: dict, ws):
        """
        Enrutador de protocolo dxLink
        
        Maneja diferentes tipos de mensajes:
        - AUTH_STATE: Respuesta de autenticación
        - CHANNEL_OPENED: Canal FEED abierto
        - FEED_DATA: Datos de mercado (Quote/Trade)
        - ERROR: Errores del servidor
        """
        msg_type = data.get("type")
        logger.trace("[DXLINK] Mensaje recibido: type=%s", msg_type)

        if msg_type == "AUTH_STATE":
            await self.handle_auth_state(data, ws)
        elif msg_type == "CHANNEL_OPENED":
            await self.handle_channel_opened(data, ws)
        elif msg_type == "FEED_DATA":
            await self.handle_feed_data(data)
        elif msg_type == "ERROR":
            await self.handle_error(data)
        else:
            logger.debug("[DXLINK] Tipo de mensaje desconocido: %s", msg_type)

    async def handle_auth_state(self, data: dict, ws):
        """Maneja respuesta de autenticación"""
        state = data.get("state")
        
        if state == "AUTHORIZED":
            logger.info("[DXLINK] 🔐 Autorizado. Abriendo canal FEED...")
            
            # Solicitar Canal FEED (Canal impar: 1)
            channel_request = {
                "type": "CHANNEL_REQUEST",
                "channel": 1,
                "service": "FEED",
                "parameters": {"contract": "AUTO"}
            }
            await ws.send(json.dumps(channel_request))
            logger.debug("[DXLINK] CHANNEL_REQUEST enviado")
        else:
            logger.warning("[DXLINK] Autorización fallida: state=%s", state)

    async def handle_channel_opened(self, data: dict, ws):
        """Maneja apertura de canal FEED"""
        channel = data.get("channel")
        logger.info("[DXLINK] Canal %d abierto", channel)

        if channel == 1:
            # ✅ CORRECCIÓN: Configurar formato COMPACT con Greeks, Underlying y Candles
            feed_setup = {
                "type": "FEED_SETUP",
                "channel": 1,
                "acceptDataFormat": "COMPACT",
                "acceptEventFields": {
                    "Quote": ["eventSymbol", "bidPrice", "askPrice", "bidSize", "askSize"],
                    "Trade": ["eventSymbol", "price", "size", "time"],
                    "Candle": ["eventSymbol", "close", "vwap", "volume"],
                    "Greeks": ["eventSymbol", "volatility", "delta", "gamma", "theta", "vega"],
                    "Underlying": ["eventSymbol", "volatility", "putCallRatio", "callVolume", "putVolume"]
                }
            }
            await ws.send(json.dumps(feed_setup))
            logger.info("[DXLINK] FEED_SETUP enviado (incluye Greeks, Underlying y Candles)")

            # Suscribir símbolos iniciales
            await self.subscribe_symbols(ws, ["SPY", "AAPL", "MSFT"])

    async def subscribe_symbols(self, ws, symbols: List[str]):
        """Suscribe a símbolos específicos"""
        try:
            subscription = {
                "type": "FEED_SUBSCRIPTION",
                "channel": 1,
                "add": []
            }
            
            # Suscribir a Quote para equities
            for symbol in symbols:
                subscription["add"].append({"type": "Quote", "symbol": symbol})
            
            # ✅ CORRECCIÓN: Suscribir a Candles (velas de 5 minutos)
            for symbol in symbols:
                subscription["add"].append({"type": "Candle", "symbol": f"{symbol}{{=5m}}"})
            
            # ✅ CORRECCIÓN: Suscribir a Underlying (para Put/Call ratio)
            for symbol in symbols:
                subscription["add"].append({"type": "Underlying", "symbol": symbol})
            
            # ✅ CORRECCIÓN: Suscribir a Greeks (ejemplo con opciones)
            # Nota: En producción, estos símbolos vendrían de una lista de opciones suscritas
            subscription["add"].append({"type": "Greeks", "symbol": ".AAPL261218C150"})
            subscription["add"].append({"type": "Greeks", "symbol": ".AAPL261218P150"})
            
            await ws.send(json.dumps(subscription))
            self.subscribed_symbols.extend(symbols)
            logger.info("[DXLINK] Suscripción enviada para %d símbolos (incluye Candles, Underlying y Greeks)", len(symbols))
        except Exception as e:
            logger.error("[DXLINK] Error suscribiendo símbolos", exc_info=e)

    async def handle_feed_data(self, data: dict):
        """
        Maneja datos de mercado (Quote/Trade/Greeks/Underlying/Candle)
        
        Formato COMPACT: arreglos planos en lugar de diccionarios anidados
        """
        try:
            event_symbol = data.get("eventSymbol")
            
            snapshot = MarketDataSnapshot(
                symbol=event_symbol,
                type="QUOTE" if "bidPrice" in data else ("TRADE" if "price" in data else "UNKNOWN")
            )

            # Quote: [eventSymbol, bidPrice, askPrice, bidSize, askSize]
            if "bidPrice" in data:
                snapshot.bid_price = data.get("bidPrice")
                snapshot.ask_price = data.get("askPrice")
                snapshot.bid_size = data.get("bidSize")
                snapshot.ask_size = data.get("askSize")
                snapshot.type = "QUOTE"

            # Trade: [eventSymbol, price, size, time]
            if "price" in data and "bidPrice" not in data:
                snapshot.price = data.get("price")
                snapshot.size = data.get("size")
                snapshot.type = "TRADE"
            
            # ✅ CORRECCIÓN: Greeks: [eventSymbol, volatility, delta, gamma, theta, vega]
            if "delta" in data:
                snapshot.volatility = data.get("volatility")
                snapshot.delta = data.get("delta")
                snapshot.gamma = data.get("gamma")
                snapshot.theta = data.get("theta")
                snapshot.vega = data.get("vega")
                snapshot.type = "GREEKS"
            
            # ✅ CORRECCIÓN: Underlying: [eventSymbol, volatility, putCallRatio, callVolume, putVolume]
            if "putCallRatio" in data:
                snapshot.volatility = data.get("volatility")
                snapshot.put_call_ratio = data.get("putCallRatio")
                snapshot.call_volume = data.get("callVolume")
                snapshot.put_volume = data.get("putVolume")
                snapshot.type = "UNDERLYING"
            
            # ✅ CORRECCIÓN: Candle: [eventSymbol, close, vwap, volume]
            if "close" in data and "bidPrice" not in data and "delta" not in data:
                snapshot.close = data.get("close")
                snapshot.vwap = data.get("vwap")
                snapshot.volume = data.get("volume")
                snapshot.type = "CANDLE"

            # Actualizar caché
            self.price_cache[event_symbol] = snapshot

            # Notificar callback
            if self.on_market_data:
                await self.on_market_data(snapshot)

            logger.trace("[DXLINK] Datos actualizados: %s - Type: %s",
                event_symbol, snapshot.type)

        except Exception as e:
            logger.error("[DXLINK] Error procesando FEED_DATA", exc_info=e)

    async def handle_error(self, data: dict):
        """Maneja errores del servidor dxLink"""
        error = data.get("error")
        logger.error("[DXLINK] ❌ Error del servidor: %s", error)

        if error == "TIMEOUT":
            logger.error("[DXLINK] TIMEOUT - Reconectando...")
            await self.reconnect()

    def get_snapshot(self, symbol: str) -> Optional[MarketDataSnapshot]:
        """Obtiene snapshot de precio para un símbolo"""
        return self.price_cache.get(symbol)

    def get_all_snapshots(self) -> Dict[str, MarketDataSnapshot]:
        """Obtiene todos los snapshots"""
        return dict(self.price_cache)

    async def reconnect(self):
        """Reconecta a dxLink"""
        logger.warning("[DXLINK] Reconectando...")
        if self.keepalive_task:
            self.keepalive_task.cancel()
        await asyncio.sleep(2)
        await self.connect_and_stream()

    async def close(self):
        """Cierra la conexión"""
        logger.info("[DXLINK] Cerrando conexión...")
        if self.keepalive_task:
            self.keepalive_task.cancel()
        if self.ws:
            await self.ws.close()


# ===== Ejemplo de Uso =====

async def on_market_data(snapshot: MarketDataSnapshot):
    """Callback para procesar datos de mercado"""
    logger.info("[MARKET-DATA] %s: Bid=%.2f Ask=%.2f | BidSize=%d AskSize=%d",
        snapshot.symbol,
        snapshot.bid_price or 0,
        snapshot.ask_price or 0,
        snapshot.bid_size or 0,
        snapshot.ask_size or 0
    )


async def main():
    """Ejemplo de uso del cliente dxLink"""
    
    # Configuración (obtener de variables de entorno en producción)
    WSS_URL = "wss://stream.dxfeed.com/webapi"
    QUOTE_TOKEN = "YOUR_QUOTE_TOKEN_HERE"  # Obtener de /api-quote-tokens

    # Crear cliente
    client = AsyncDxLinkClient(WSS_URL, QUOTE_TOKEN, on_market_data)

    # Conectar y mantener stream
    try:
        await client.connect_and_stream()
    except KeyboardInterrupt:
        logger.info("Cerrando cliente...")
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
