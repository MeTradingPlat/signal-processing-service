import asyncio
import logging
import random
from app.infrastructure.output.marketdata_rest_adapter import MarketdataRestAdapter
from app.adapters.fundamentals_adapter import obtener_fundamentales_batch

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def main():
    # 1. Conectar a la API productiva como solicitaste
    url = "https://metradingplat.net"
    marketdata = MarketdataRestAdapter(url)
    mercados = ["NYSE", "NASDAQ", "AMEX", "ETF", "OTC"]
    
    logging.info(f"Obteniendo símbolos directamente de {url} para los mercados: {mercados}")
    simbolos = await marketdata.obtener_simbolos_por_mercados(mercados)
    
    logging.info(f"¡Éxito! Se obtuvieron {len(simbolos)} símbolos en total procedentes de la API.")
    
    if not simbolos:
        logging.error("No se obtuvieron símbolos. Revisa la URL o la red.")
        await marketdata.cerrar()
        return

    # 2. Extraer datos fundamentales
    # Debido a los retardos antibloqueo (IP Ban), extraer ~10,000 símbolos tomaría casi una hora.
    # Tomaremos una muestra de 50 símbolos al azar de distintos mercados para demostrar
    # que la integración completa funciona sin caerse por errores de red.
    
    cantidad_a_probar = min(50, len(simbolos))
    simbolos_prueba = random.sample(simbolos, cantidad_a_probar)
    
    logging.info(f"Iniciando extracción de fundamentales para una muestra de {cantidad_a_probar} símbolos...")
    
    # Esto llamará a la lógica de scraping resiliente que programamos (Finviz + YFinance)
    resultados = obtener_fundamentales_batch(simbolos_prueba, "LIVE_INTEGRATION_TEST")
    
    logging.info("Extracción finalizada.")
    logging.info(f"Resultados exitosos obtenidos: {len(resultados)} / {cantidad_a_probar}")
    
    # Mostrar un par de resultados para confirmar la estructura de los datos
    for sym in list(resultados.keys())[:3]:
        logging.info(f"Muestra de datos para {sym}: {resultados[sym]}")
        
    await marketdata.cerrar()

if __name__ == "__main__":
    asyncio.run(main())
