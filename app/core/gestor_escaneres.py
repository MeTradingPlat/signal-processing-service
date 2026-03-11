import asyncio
import logging
from concurrent.futures import ProcessPoolExecutor

from app.core.ejecutor_escaner import EjecutorEscaner
from app.core.fundamentals_cache import FundamentalsCache
from app.core.gestor_tiempo import GestorTiempo
from app.core.halt_monitor import HaltMonitor
from app.domain.models.escaner import Escaner
from app.infrastructure.output.escaner_rest_adapter import EscanerRestAdapter
from app.infrastructure.output.kafka_producer_adapter import KafkaProducerAdapter
from app.infrastructure.output.marketdata_rest_adapter import MarketdataRestAdapter

logger = logging.getLogger(__name__)


class GestorEscaneres:
    """Administrador central de escáneres activos.

    Mantiene un diccionario de id_escaner → asyncio.Task
    y un ProcessPoolExecutor para cálculos de indicadores.

    FundamentalsCache y HaltMonitor son singletons compartidos entre
    todos los escáneres — se crean una vez y se reutilizan.
    """

    def __init__(
        self,
        kafka_producer: KafkaProducerAdapter,
        marketdata_rest: MarketdataRestAdapter,
        escaner_rest: EscanerRestAdapter,
        process_pool: ProcessPoolExecutor,
        gestor_tiempo: GestorTiempo | None = None,
        fundamentals_cache: FundamentalsCache | None = None,
        halt_monitor: HaltMonitor | None = None,
    ):
        self._kafka = kafka_producer
        self._marketdata = marketdata_rest
        self._escaner_rest = escaner_rest
        self._pool = process_pool
        self._gestor_tiempo = gestor_tiempo or GestorTiempo()
        self._fundamentals_cache = fundamentals_cache or FundamentalsCache()
        self._halt_monitor = halt_monitor or HaltMonitor()
        self._tareas: dict[int, asyncio.Task] = {}
        self._ejecutores: dict[int, EjecutorEscaner] = {}
        self._escaneres: dict[int, Escaner] = {}

    async def iniciar_escaner(self, escaner: Escaner):
        """Crea un asyncio.Task para ejecutar el escáner."""
        if escaner.id_escaner in self._tareas:
            logger.warning("Escaner %d ya está en ejecución, ignorando", escaner.id_escaner)
            return

        ejecutor = EjecutorEscaner(
            escaner=escaner,
            kafka_producer=self._kafka,
            marketdata_rest=self._marketdata,
            process_pool=self._pool,
            gestor_tiempo=self._gestor_tiempo,
            fundamentals_cache=self._fundamentals_cache,
            halt_monitor=self._halt_monitor,
        )

        tarea = asyncio.create_task(
            self._ejecutar_con_manejo_errores(escaner, ejecutor),
            name=f"escaner-{escaner.id_escaner}",
        )

        self._tareas[escaner.id_escaner] = tarea
        self._ejecutores[escaner.id_escaner] = ejecutor
        self._escaneres[escaner.id_escaner] = escaner

        logger.info("Escaner %d '%s' iniciado como Task", escaner.id_escaner, escaner.nombre)

    async def _ejecutar_con_manejo_errores(self, escaner: Escaner, ejecutor: EjecutorEscaner):
        """Wrapper que maneja errores y limpieza del Task."""
        try:
            await ejecutor.ejecutar()
        except asyncio.CancelledError:
            logger.info("Escaner %d cancelado", escaner.id_escaner)
        except Exception as e:
            logger.error("Error en escaner %d: %s", escaner.id_escaner, e, exc_info=True)
            await self._kafka.publicar_log(
                escaner.id_escaner, "ERROR",
                f"Error en escáner {escaner.nombre}: {str(e)[:200]}",
            )
        finally:
            self._tareas.pop(escaner.id_escaner, None)
            self._ejecutores.pop(escaner.id_escaner, None)
            self._escaneres.pop(escaner.id_escaner, None)

    async def detener_escaner(self, id_escaner: int, razon: str = ""):
        """Cancela el Task del escáner y limpia recursos."""
        ejecutor = self._ejecutores.get(id_escaner)
        if ejecutor:
            ejecutor.detener()

        tarea = self._tareas.get(id_escaner)
        if tarea and not tarea.done():
            tarea.cancel()
            try:
                await tarea
            except asyncio.CancelledError:
                pass

        logger.info("Escaner %d detenido (razon: %s)", id_escaner, razon or "N/A")

    async def detener_todos(self):
        """Detiene todos los escáneres activos."""
        ids = list(self._tareas.keys())
        for id_escaner in ids:
            await self.detener_escaner(id_escaner, "shutdown del servicio")
        logger.info("Todos los escaneres detenidos (%d)", len(ids))

    async def recuperar_escaneres_activos(self):
        """Startup: consulta scanner-management por escáneres INICIADOS."""
        max_reintentos = 5
        for intento in range(max_reintentos):
            try:
                escaneres_data = await self._escaner_rest.obtener_escaneres_iniciados()
                logger.info("Recuperados %d escaneres activos", len(escaneres_data))

                for esc_data in escaneres_data:
                    id_escaner = esc_data.get("idEscaner")
                    if id_escaner is None:
                        continue

                    filtros_data = await self._escaner_rest.obtener_filtros_escaner(id_escaner)
                    escaner = Escaner.desde_dict(esc_data, filtros_data)
                    await self.iniciar_escaner(escaner)

                return
            except Exception as e:
                espera = 2 ** (intento + 1)
                logger.warning(
                    "Error recuperando escaneres activos (intento %d/%d): %s. Reintentando en %ds",
                    intento + 1, max_reintentos, e, espera,
                )
                await asyncio.sleep(espera)

        logger.error("No se pudieron recuperar escaneres activos después de %d intentos", max_reintentos)

    def obtener_estado(self) -> dict:
        """Retorna estado de todos los escáneres activos."""
        estado = {}
        for id_esc, escaner in self._escaneres.items():
            tarea = self._tareas.get(id_esc)
            estado[id_esc] = {
                "nombre": escaner.nombre,
                "mercados": escaner.mercados,
                "tipo_ejecucion": escaner.tipo_ejecucion,
                "hora_inicio": str(escaner.hora_inicio),
                "hora_fin": str(escaner.hora_fin),
                "tarea_activa": tarea is not None and not tarea.done() if tarea else False,
            }
        return estado
