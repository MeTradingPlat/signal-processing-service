"""
Signal Processing Service - Entry Point

Microservicio que ejecuta los calculos de los escaneres creados en scanner-management-service.
Obtiene escaneres activos, obtiene simbolos por mercado, obtiene data historica y datos
fundamentales, y ejecuta los filtros configurados. Si todos los filtros pasan, genera una senal.
"""

import logging
import sys
import os

# Agregar el directorio raiz al path para imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from infrastructure.output.comunicacion_externa.comunicacion_externa_adapter import ComunicacionExternaAdapter
from infrastructure.output.comunicacion_externa.yahoo_finance_adapter import YahooFinanceAdapter
from infrastructure.output.kafka.kafka_producer_adapter import KafkaProducerAdapter
from infrastructure.business.strategies.filtro_registry import FiltroRegistry
from infrastructure.business.strategies.filtro_executor import FiltroExecutor
from infrastructure.input.scheduler.escaner_scheduler import EscanerScheduler
from infrastructure.input.scheduler.event_loop_scheduler import EventLoopScheduler
from domain.usecases.procesar_senales_cu_adapter import ProcesarSenalesCUAdapter
from config import KAFKA_BOOTSTRAP_SERVERS

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("signal-processing-service")


def main():
    logger.info("=" * 60)
    logger.info("  SIGNAL PROCESSING SERVICE")
    logger.info("=" * 60)

    # --- Composicion de dependencias (equivalente a BeanConfigurations) ---

    # Output adapters
    obj_yahoo = YahooFinanceAdapter()
    obj_comunicacion_externa = ComunicacionExternaAdapter(yahoo_adapter=obj_yahoo)
    obj_kafka_producer = KafkaProducerAdapter(KAFKA_BOOTSTRAP_SERVERS)

    # Business
    obj_filtro_registry = FiltroRegistry()
    obj_filtro_executor = FiltroExecutor(obj_filtro_registry)

    # Use case
    obj_procesar_senales = ProcesarSenalesCUAdapter(
        obj_comunicacion_externa=obj_comunicacion_externa,
        obj_filtro_executor=obj_filtro_executor,
        obj_kafka_producer=obj_kafka_producer,
    )

    # Input adapter (scheduler)
    obj_scheduler = EscanerScheduler(obj_procesar_senales)

    # Inyeccion circular para soportar programacion dinamica desde UseCase
    obj_procesar_senales.obj_scheduler = obj_scheduler

    # Event loop para filtros de evento en tiempo real (0.1s)
    obj_event_loop = EventLoopScheduler(obj_procesar_senales)
    obj_procesar_senales.obj_event_loop = obj_event_loop

    # --- Iniciar servicio ---
    try:
        # 1. Obtener escaneres iniciales
        escaneres_activos = obj_procesar_senales.iniciar()
        
        if not escaneres_activos:
            logger.warning("No se encontraron escaneres activos. El servicio esperara.")
        
        # 2. Programar escaneres iniciales
        obj_scheduler.programar_escaneres(escaneres_activos)
        
        # 3. Iniciar API (FastAPI) y Scheduler
        # Para correr ambos necesitamos Threading o AsyncIO co-routine si Scheduler fuera AsyncIOScheduler
        # Como BlockingScheduler es bloqueante, lo corremos en un hilo o usamos AsyncIOScheduler + Uvicorn
        # O corremos Uvicorn en hilo aparte.
        # Mejor approach: Uvicorn main, scheduler en hilo background (BackgroundScheduler)
        # Pero EscanerScheduler usa BlockingScheduler. Cambiémoslo a BackgroundScheduler?
        # O simplemente corremos BlockingScheduler en un thread.
        
        from threading import Thread
        import uvicorn
        from infrastructure.input.api.fastapi_controller import app, set_use_case
        
        set_use_case(obj_procesar_senales)
        
        scheduler_thread = Thread(target=obj_scheduler.iniciar)
        scheduler_thread.daemon = True
        scheduler_thread.start()
        logger.info("Scheduler iniciado en hilo background.")

        obj_event_loop.start()
        logger.info("Event loop para filtros de evento iniciado.")
        
        logger.info("Iniciando servidor API...")
        # Corremos uvicorn.run bloqueante en main thread
        uvicorn.run(app, host="0.0.0.0", port=8000)

    except KeyboardInterrupt:
        logger.info("Deteniendo servicio...")
        obj_event_loop.detener()
        obj_scheduler.detener()
        obj_procesar_senales.detener()
        logger.info("Servicio detenido.")

    except Exception as e:
        logger.error(f"Error fatal: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
