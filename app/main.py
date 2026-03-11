import asyncio
import logging
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.core.fundamentals_cache import FundamentalsCache
from app.core.gestor_escaneres import GestorEscaneres
from app.core.halt_monitor import HaltMonitor
from app.infrastructure.input.kafka_listener import EstadoEscanerKafkaListener
from app.infrastructure.input.rest_controller import crear_router
from app.infrastructure.output.escaner_rest_adapter import EscanerRestAdapter
from app.infrastructure.output.kafka_producer_adapter import KafkaProducerAdapter
from app.infrastructure.output.marketdata_rest_adapter import MarketdataRestAdapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
# Silenciar librerías ruidosas para ver solo logs de la aplicación
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("aiokafka").setLevel(logging.WARNING)
logging.getLogger("kafka").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando signal-processing-service...")

    # Singletons compartidos entre todos los escáneres
    fundamentals_cache = FundamentalsCache()
    halt_monitor = HaltMonitor()
    halt_monitor.iniciar()

    process_pool = ProcessPoolExecutor(max_workers=settings.max_workers_pool)

    kafka_producer = KafkaProducerAdapter(settings.kafka_bootstrap_servers)
    await kafka_producer.iniciar()

    escaner_rest = EscanerRestAdapter(settings.scanner_management_url)
    marketdata_rest = MarketdataRestAdapter(settings.marketdata_url)

    gestor = GestorEscaneres(
        kafka_producer=kafka_producer,
        marketdata_rest=marketdata_rest,
        escaner_rest=escaner_rest,
        process_pool=process_pool,
        fundamentals_cache=fundamentals_cache,
        halt_monitor=halt_monitor,
    )

    app.state.gestor = gestor

    tarea_recuperacion = asyncio.create_task(
        gestor.recuperar_escaneres_activos()
    )

    listener = EstadoEscanerKafkaListener(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_group_id,
        gestor=gestor,
        escaner_rest=escaner_rest,
    )
    tarea_listener = asyncio.create_task(listener.iniciar())

    logger.info("signal-processing-service iniciado correctamente")

    yield

    logger.info("Deteniendo signal-processing-service...")
    tarea_listener.cancel()
    tarea_recuperacion.cancel()
    halt_monitor.detener()
    await gestor.detener_todos()
    process_pool.shutdown(wait=False)
    await kafka_producer.detener()
    await escaner_rest.cerrar()
    await marketdata_rest.cerrar()
    logger.info("signal-processing-service detenido")


app = FastAPI(
    title="Signal Processing Service",
    lifespan=lifespan,
)

app.include_router(crear_router())
