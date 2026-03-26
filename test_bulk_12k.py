import asyncio
import logging
import time
from app.infrastructure.output.marketdata_rest_adapter import MarketdataRestAdapter
from app.adapters.fundamentals_adapter import obtener_fundamentales_batch

# Configuramos logging exhaustivo para monitorizar la ejecución en tiempo real
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def main():
    start_total = time.time()
    
    url = "https://metradingplat.com"
    marketdata = MarketdataRestAdapter(url)
    mercados = ["NYSE", "NASDAQ", "AMEX", "ETF", "OTC"]
    
    logging.info(f"[PASO 1] Obteniendo SÍMBOLOS TOTALES de {url} para: {mercados}")
    simbolos = await marketdata.obtener_simbolos_por_mercados(mercados)
    
    if not simbolos:
        logging.error("No se obtuvieron símbolos desde el servidor.")
        await marketdata.cerrar()
        return
        
    logging.info(f"-> ¡Se descargarán datos fundamentales para un total de {len(simbolos)} símbolos!")
    
    # === EJECUTAR EL EXTRATOR MASIVO (BULK) ===
    logging.info("[PASO 2] Iniciando Extractor Masivo ASINCRONO (Cero Hilos)...")
    start_bulk = time.time()
    
    # La nueva arquitectura exige "await" ya que es una corrutina asíncrona pura
    resultados = await obtener_fundamentales_batch(simbolos, "TEST_FULL_MARKET")
    
    end_bulk = time.time()
    
    logging.info("=== RESULTADOS DEL TEST DE 12K SÍMBOLOS ===")
    logging.info(f"Símbolos con algún dato encontrado: {len(resultados)} / {len(simbolos)}")
    logging.info(f"Tiempo de extracción masiva: {end_bulk - start_bulk:.2f} segundos ({(end_bulk - start_bulk)/60:.2f} minutos)")
    
    # Muestra representativa de los primeros 5
    for sym in list(resultados.keys())[:5]:
        logging.info(f"Muestra {sym}: {resultados[sym]}")
        
    await marketdata.cerrar()
    logging.info(f"Script completado en {time.time() - start_total:.2f} segundos.")

if __name__ == "__main__":
    # Necesario para evitar RuntimeErrors en Windows con ProactorEventLoop
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
