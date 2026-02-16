"""
Signal Processing Service - Entry Point

Microservicio que ejecuta los calculos de los escaneres creados en scanner-management-service.
Obtiene escaneres activos, obtiene simbolos por mercado, obtiene data historica y datos
fundamentales, y ejecuta los filtros configurados. Si todos los filtros pasan, genera una senal.
"""

import logging
import sys
import os

# Configurar logging ANTES de cualquier import para capturar errores de importacion
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,  # Forzar salida a stdout
)
logger = logging.getLogger("signal-processing-service")

# Flush inmediato para que los logs aparezcan
sys.stdout.flush()

logger.info("=" * 60)
logger.info("  SIGNAL PROCESSING SERVICE - INICIANDO")
logger.info("=" * 60)
logger.info(f"Python version: {sys.version}")
logger.info(f"Working directory: {os.getcwd()}")
logger.info(f"KAFKA_BOOTSTRAP_SERVERS env: {os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'NOT SET')}")
sys.stdout.flush()

# Agregar el directorio raiz al path para imports
logger.info("Agregando directorio raiz al path...")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.flush()

# --- IMPORTS CON LOGGING ---
logger.info("Importando config...")
sys.stdout.flush()
try:
    from config import KAFKA_BOOTSTRAP_SERVERS
    logger.info(f"Config importado. KAFKA_BOOTSTRAP_SERVERS={KAFKA_BOOTSTRAP_SERVERS}")
except Exception as e:
    logger.error(f"Error importando config: {e}", exc_info=True)
    sys.exit(1)
sys.stdout.flush()

logger.info("Importando YahooFinanceAdapter...")
sys.stdout.flush()
try:
    from infrastructure.output.comunicacion_externa.yahoo_finance_adapter import YahooFinanceAdapter
    logger.info("YahooFinanceAdapter importado OK")
except Exception as e:
    logger.error(f"Error importando YahooFinanceAdapter: {e}", exc_info=True)
    sys.exit(1)
sys.stdout.flush()

logger.info("Importando ComunicacionExternaAdapter...")
sys.stdout.flush()
try:
    from infrastructure.output.comunicacion_externa.comunicacion_externa_adapter import ComunicacionExternaAdapter
    logger.info("ComunicacionExternaAdapter importado OK")
except Exception as e:
    logger.error(f"Error importando ComunicacionExternaAdapter: {e}", exc_info=True)
    sys.exit(1)
sys.stdout.flush()

logger.info("Importando KafkaProducerAdapter...")
sys.stdout.flush()
try:
    from infrastructure.output.kafka.kafka_producer_adapter import KafkaProducerAdapter
    logger.info("KafkaProducerAdapter importado OK")
except Exception as e:
    logger.error(f"Error importando KafkaProducerAdapter: {e}", exc_info=True)
    sys.exit(1)
sys.stdout.flush()

logger.info("Importando FiltroRegistry...")
sys.stdout.flush()
try:
    from infrastructure.business.strategies.filtro_registry import FiltroRegistry
    logger.info("FiltroRegistry importado OK")
except Exception as e:
    logger.error(f"Error importando FiltroRegistry: {e}", exc_info=True)
    sys.exit(1)
sys.stdout.flush()

logger.info("Importando FiltroExecutor...")
sys.stdout.flush()
try:
    from infrastructure.business.strategies.filtro_executor import FiltroExecutor
    logger.info("FiltroExecutor importado OK")
except Exception as e:
    logger.error(f"Error importando FiltroExecutor: {e}", exc_info=True)
    sys.exit(1)
sys.stdout.flush()

logger.info("Importando EscanerScheduler...")
sys.stdout.flush()
try:
    from infrastructure.input.scheduler.escaner_scheduler import EscanerScheduler
    logger.info("EscanerScheduler importado OK")
except Exception as e:
    logger.error(f"Error importando EscanerScheduler: {e}", exc_info=True)
    sys.exit(1)
sys.stdout.flush()

logger.info("Importando EventLoopScheduler...")
sys.stdout.flush()
try:
    from infrastructure.input.scheduler.event_loop_scheduler import EventLoopScheduler
    logger.info("EventLoopScheduler importado OK")
except Exception as e:
    logger.error(f"Error importando EventLoopScheduler: {e}", exc_info=True)
    sys.exit(1)
sys.stdout.flush()

logger.info("Importando ProcesarSenalesCUAdapter...")
sys.stdout.flush()
try:
    from domain.usecases.procesar_senales_cu_adapter import ProcesarSenalesCUAdapter
    logger.info("ProcesarSenalesCUAdapter importado OK")
except Exception as e:
    logger.error(f"Error importando ProcesarSenalesCUAdapter: {e}", exc_info=True)
    sys.exit(1)
sys.stdout.flush()

logger.info("Importando CandleCache...")
sys.stdout.flush()
try:
    from domain.usecases.candle_cache import CandleCache
    logger.info("CandleCache importado OK")
except Exception as e:
    logger.error(f"Error importando CandleCache: {e}", exc_info=True)
    sys.exit(1)
sys.stdout.flush()

logger.info("=" * 60)
logger.info("  TODOS LOS IMPORTS COMPLETADOS EXITOSAMENTE")
logger.info("=" * 60)
sys.stdout.flush()


def main():
    logger.info("Iniciando funcion main()...")
    sys.stdout.flush()

    # --- Composicion de dependencias ---
    logger.info("PASO 1: Creando YahooFinanceAdapter...")
    sys.stdout.flush()
    try:
        obj_yahoo = YahooFinanceAdapter()
        logger.info("YahooFinanceAdapter creado OK")
    except Exception as e:
        logger.error(f"Error creando YahooFinanceAdapter: {e}", exc_info=True)
        sys.exit(1)
    sys.stdout.flush()

    logger.info("PASO 2: Creando ComunicacionExternaAdapter...")
    sys.stdout.flush()
    try:
        obj_comunicacion_externa = ComunicacionExternaAdapter(yahoo_adapter=obj_yahoo)
        logger.info("ComunicacionExternaAdapter creado OK")
    except Exception as e:
        logger.error(f"Error creando ComunicacionExternaAdapter: {e}", exc_info=True)
        sys.exit(1)
    sys.stdout.flush()

    logger.info("PASO 3: Creando KafkaProducerAdapter...")
    logger.info(f"  -> Conectando a Kafka: {KAFKA_BOOTSTRAP_SERVERS}")
    sys.stdout.flush()
    try:
        obj_kafka_producer = KafkaProducerAdapter(KAFKA_BOOTSTRAP_SERVERS)
        logger.info("KafkaProducerAdapter creado OK")
    except Exception as e:
        logger.error(f"Error creando KafkaProducerAdapter: {e}", exc_info=True)
        sys.exit(1)
    sys.stdout.flush()

    logger.info("PASO 4: Creando FiltroRegistry...")
    sys.stdout.flush()
    try:
        obj_filtro_registry = FiltroRegistry()
        logger.info(f"FiltroRegistry creado OK - {len(obj_filtro_registry._filtros) if hasattr(obj_filtro_registry, '_filtros') else '?'} filtros registrados")
    except Exception as e:
        logger.error(f"Error creando FiltroRegistry: {e}", exc_info=True)
        sys.exit(1)
    sys.stdout.flush()

    logger.info("PASO 5: Creando FiltroExecutor...")
    sys.stdout.flush()
    try:
        obj_filtro_executor = FiltroExecutor(obj_filtro_registry)
        logger.info("FiltroExecutor creado OK")
    except Exception as e:
        logger.error(f"Error creando FiltroExecutor: {e}", exc_info=True)
        sys.exit(1)
    sys.stdout.flush()

    logger.info("PASO 6: Creando CandleCache...")
    sys.stdout.flush()
    try:
        obj_candle_cache = CandleCache()
        logger.info("CandleCache creado OK")
    except Exception as e:
        logger.error(f"Error creando CandleCache: {e}", exc_info=True)
        sys.exit(1)
    sys.stdout.flush()

    logger.info("PASO 7: Creando ProcesarSenalesCUAdapter...")
    sys.stdout.flush()
    try:
        obj_procesar_senales = ProcesarSenalesCUAdapter(
            obj_comunicacion_externa=obj_comunicacion_externa,
            obj_filtro_executor=obj_filtro_executor,
            obj_kafka_producer=obj_kafka_producer,
            obj_candle_cache=obj_candle_cache,
        )
        logger.info("ProcesarSenalesCUAdapter creado OK")
    except Exception as e:
        logger.error(f"Error creando ProcesarSenalesCUAdapter: {e}", exc_info=True)
        sys.exit(1)
    sys.stdout.flush()

    logger.info("PASO 8: Creando EscanerScheduler...")
    sys.stdout.flush()
    try:
        obj_scheduler = EscanerScheduler(obj_procesar_senales, obj_filtro_executor=obj_filtro_executor)
        logger.info("EscanerScheduler creado OK")
    except Exception as e:
        logger.error(f"Error creando EscanerScheduler: {e}", exc_info=True)
        sys.exit(1)
    sys.stdout.flush()

    # Inyeccion circular
    logger.info("PASO 9: Configurando inyeccion circular scheduler -> use case...")
    obj_procesar_senales.obj_scheduler = obj_scheduler
    logger.info("Inyeccion circular configurada OK")
    sys.stdout.flush()

    logger.info("PASO 10: Creando EventLoopScheduler...")
    sys.stdout.flush()
    try:
        obj_event_loop = EventLoopScheduler(obj_procesar_senales)
        obj_procesar_senales.obj_event_loop = obj_event_loop
        logger.info("EventLoopScheduler creado OK")
    except Exception as e:
        logger.error(f"Error creando EventLoopScheduler: {e}", exc_info=True)
        sys.exit(1)
    sys.stdout.flush()

    logger.info("=" * 60)
    logger.info("  DEPENDENCIAS CREADAS - INICIANDO SERVICIO")
    logger.info("=" * 60)
    sys.stdout.flush()

    # --- Iniciar servicio ---
    try:
        logger.info("PASO 11: Obteniendo escaneres activos desde scanner-management-service...")
        sys.stdout.flush()
        escaneres_activos = obj_procesar_senales.iniciar()

        if not escaneres_activos:
            logger.warning("No se encontraron escaneres activos. El servicio esperara nuevos escaneres.")
        else:
            logger.info(f"Escaneres activos obtenidos: {len(escaneres_activos)}")
            for esc in escaneres_activos:
                logger.info(f"  - Escaner: {esc.nombre} (ID: {esc.id_escaner})")
        sys.stdout.flush()

        logger.info("PASO 12: Programando escaneres en scheduler...")
        sys.stdout.flush()
        obj_scheduler.programar_escaneres(escaneres_activos)
        logger.info("Escaneres programados OK")
        sys.stdout.flush()

        logger.info("PASO 13: Importando dependencias de API (FastAPI, uvicorn)...")
        sys.stdout.flush()
        from threading import Thread
        import uvicorn
        from infrastructure.input.api.fastapi_controller import app, set_use_case
        logger.info("Dependencias de API importadas OK")
        sys.stdout.flush()

        logger.info("PASO 14: Configurando use case en FastAPI controller...")
        set_use_case(obj_procesar_senales)
        logger.info("Use case configurado en controller OK")
        sys.stdout.flush()

        logger.info("PASO 15: Iniciando scheduler en hilo background...")
        sys.stdout.flush()
        scheduler_thread = Thread(target=obj_scheduler.iniciar)
        scheduler_thread.daemon = True
        scheduler_thread.start()
        logger.info("Scheduler iniciado en hilo background OK")
        sys.stdout.flush()

        logger.info("PASO 16: Iniciando event loop...")
        sys.stdout.flush()
        obj_event_loop.start()
        logger.info("Event loop iniciado OK")
        sys.stdout.flush()

        logger.info("=" * 60)
        logger.info("  SIGNAL PROCESSING SERVICE LISTO")
        logger.info("  API disponible en http://0.0.0.0:8000")
        logger.info("=" * 60)
        sys.stdout.flush()

        logger.info("PASO 17: Iniciando servidor uvicorn (bloqueante)...")
        sys.stdout.flush()
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

    except KeyboardInterrupt:
        logger.info("Interrupcion de teclado recibida. Deteniendo servicio...")
        obj_event_loop.detener()
        obj_scheduler.detener()
        obj_procesar_senales.detener()
        logger.info("Servicio detenido correctamente.")

    except Exception as e:
        logger.error(f"ERROR FATAL: {e}", exc_info=True)
        sys.stdout.flush()
        sys.exit(1)


if __name__ == "__main__":
    logger.info("Ejecutando desde __main__...")
    sys.stdout.flush()
    main()
