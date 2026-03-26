import asyncio
import json
import logging
from app.infrastructure.output.marketdata_rest_adapter import MarketdataRestAdapter
from app.adapters.fundamentals_adapter import _normalizar_simbolo_yahoo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def generar_mapeo():
    # Instanciar el cliente de marketdata (Cambiar la URL a producción si es distinto)
    marketdata = MarketdataRestAdapter("http://localhost:8000") # Asumiendo default
    
    mercados = ["NYSE", "NASDAQ", "AMEX"]
    logger.info("Obteniendo todos los símbolos de %s...", mercados)
    simbolos = await marketdata.obtener_simbolos_por_mercados(mercados)
    
    logger.info("Se encontraron %d símbolos. Generando mapeos base...", len(simbolos))
    
    mapeo = {}
    for sym in simbolos:
        # Aquí se usa la lógica heurística inicial
        yf_sym = _normalizar_simbolo_yahoo(sym)
        yf_sym = _normalizar_simbolo_yahoo(sym)

        # Correcciones manuales conocidas para ciertos símbolos
        if sym == "BRK/A" or sym == "BRK.A":
            yf_sym = "BRK-A"
        elif sym == "BRK/B" or sym == "BRK.B":
            yf_sym = "BRK-B"
        elif sym == "BF/B" or sym == "BF.B":
            yf_sym = "BF-B"
        
        # Puedes añadir scripts para hacer ping a yfinance aquí si deseas validación 100% estricta.
        mapeo[sym] = {
            "yfinance": yf_sym
        }
        
    with open("symbol_mapping.json", "w", encoding="utf-8") as f:
        json.dump(mapeo, f, indent=4)
        
    logger.info("Mapeo generado y guardado en symbol_mapping.json con %d entradas.", len(mapeo))
    await marketdata.cerrar()

if __name__ == "__main__":
    asyncio.run(generar_mapeo())
