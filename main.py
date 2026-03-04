"""
Signal Processing Service - Entry Point

Microservicio que ejecuta los calculos de los escaneres creados en
scanner-management-service. Obtiene escaneres activos y lanza un proceso
OS independiente por cada uno, resolviendo los problemas de timing y escalado
que tenia el modelo anterior basado en threads/APScheduler.

Arquitectura:
  main process  → ProcessManager
                    ├─ KafkaPublisherProcess (publica mensajes en Kafka)
                    └─ ScannerProcess × N   (uno por escaner activo)
  uvicorn       → FastAPI (webhooks para iniciar/detener escaners en caliente)
"""

import logging
import sys
import os

# Configurar logging ANTES de cualquier import para capturar errores de importacion
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("signal-processing-service")
sys.stdout.flush()

logger.info("=" * 60)
logger.info("  SIGNAL PROCESSING SERVICE - INICIANDO")
logger.info("=" * 60)
logger.info(f"Python version: {sys.version}")
logger.info(f"Working directory: {os.getcwd()}")
logger.info(f"KAFKA_BOOTSTRAP_SERVERS env: {os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'NOT SET')}")
sys.stdout.flush()

# Agregar el directorio raiz al path para imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def wait_for_gateway(url: str, timeout_seconds: int = 600) -> bool:
    """Espera a que el Gateway este disponible antes de continuar."""
    import time
    import requests

    health_url = f"{url.rstrip('/')}/health"
    start_time = time.time()
    logger.info(
        f"Esperando a que el Gateway este listo en {health_url} "
        f"(timeout {timeout_seconds}s)..."
    )

    while time.time() - start_time < timeout_seconds:
        try:
            response = requests.get(health_url, timeout=2)
            if response.status_code == 200:
                logger.info("Gateway detectado y responde OK")
                return True
        except Exception:
            pass

        logger.debug("Gateway no disponible, reintentando en 2s...")
        time.sleep(2)

    logger.warning(
        "Gateway no detectado despues del tiempo de espera. Continuando de todos modos..."
    )
    return False


def main():
    logger.info("Iniciando funcion main()...")
    sys.stdout.flush()

    # --- Esperar gateway ---
    from config import SCANNER_SERVICE_URL
    wait_for_gateway(SCANNER_SERVICE_URL)

    # --- Obtener escaneres activos via HTTP ---
    logger.info("Obteniendo escaneres activos...")
    sys.stdout.flush()
    try:
        from infrastructure.output.comunicacion_externa.yahoo_finance_adapter import YahooFinanceAdapter
        from infrastructure.output.comunicacion_externa.comunicacion_externa_adapter import ComunicacionExternaAdapter

        obj_yahoo = YahooFinanceAdapter()
        obj_comunicacion = ComunicacionExternaAdapter(yahoo_adapter=obj_yahoo)
        escaneres_activos = obj_comunicacion.obtener_escaneres_activos()

        logger.info(f"Escaneres activos encontrados: {len(escaneres_activos)}")
        for esc in escaneres_activos:
            logger.info(
                f"  - {esc.nombre} (ID:{esc.id_escaner}) | "
                f"{esc.hora_inicio}-{esc.hora_fin} UTC | "
                f"Tipo: {esc.obj_tipo_ejecucion.enum_tipo_ejecucion}"
            )
        sys.stdout.flush()
    except Exception as e:
        logger.error(f"Error obteniendo escaneres activos: {e}", exc_info=True)
        escaneres_activos = []

    # --- Iniciar ProcessManager ANTES de uvicorn (fork en proceso single-threaded) ---
    logger.info("=" * 60)
    logger.info("  INICIANDO PROCESOS")
    logger.info("=" * 60)
    sys.stdout.flush()

    import multiprocessing
    from infrastructure.input.process.process_manager import ProcessManager

    manager = ProcessManager()
    manager.iniciar(escaneres_activos)

    # --- Configurar FastAPI con referencias necesarias ---
    logger.info("Configurando FastAPI...")
    sys.stdout.flush()
    try:
        import uvicorn
        from infrastructure.input.api.fastapi_controller import app, set_process_manager

        set_process_manager(manager, obj_comunicacion)
        logger.info("FastAPI configurado OK")
    except Exception as e:
        logger.error(f"Error configurando FastAPI: {e}", exc_info=True)
        sys.exit(1)
    sys.stdout.flush()

    logger.info("=" * 60)
    logger.info("  SIGNAL PROCESSING SERVICE LISTO")
    logger.info("  API disponible en http://0.0.0.0:8000")
    logger.info("=" * 60)
    sys.stdout.flush()

    try:
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
    except KeyboardInterrupt:
        logger.info("Interrupcion de teclado recibida. Deteniendo servicio...")
        manager.shutdown()
        logger.info("Servicio detenido correctamente.")
    except Exception as e:
        logger.error(f"ERROR FATAL: {e}", exc_info=True)
        manager.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    logger.info("Ejecutando desde __main__...")
    sys.stdout.flush()
    main()
