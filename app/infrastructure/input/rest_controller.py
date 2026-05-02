import logging

from fastapi import APIRouter, Body, HTTPException, Request

from app.domain.models.escaner import Escaner

logger = logging.getLogger(__name__)


def crear_router() -> APIRouter:
    router = APIRouter(prefix="/signal-processing")

    @router.get("/health")
    async def health():
        return {"status": "UP", "servicio": "signal-processing-service"}

    @router.get("/status")
    async def status(request: Request):
        gestor = request.app.state.gestor
        return {
            "escaneres_activos": gestor.obtener_estado(),
            "total": len(gestor.obtener_estado()),
        }

    @router.post("/escaner")
    async def recibir_escaner_iniciado(request: Request, datos: dict = Body(...)):
        """Recibe notificación de scanner-management cuando un escáner es INICIADO.

        El cuerpo contiene el objeto Escaner completo con filtros ya enriquecidos
        (categorías incluidas), enviado por ComunicacionSignalProcessingAdapter.
        """
        gestor = request.app.state.gestor
        try:
            # Los filtros vienen embebidos en el mismo objeto Escaner
            filtros_data = datos.get("filtros", [])
            escaner = Escaner.desde_dict(datos, filtros_data)
            logger.info(
                "REST: recibida notificación inicio escaner %d '%s'",
                escaner.id_escaner, escaner.nombre,
            )
            await gestor.iniciar_escaner(escaner)
            return {"ok": True, "idEscaner": escaner.id_escaner}
        except Exception as e:
            logger.error("Error procesando inicio de escaner via REST: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/escaner/{id_escaner}/detener")
    async def recibir_escaner_detenido(id_escaner: int, request: Request):
        """Recibe notificación de scanner-management cuando un escáner es DETENIDO.

        Llamado por ComunicacionSignalProcessingAdapter.notificarEscanerDetenido().
        """
        gestor = request.app.state.gestor
        logger.info("REST: recibida notificación detención escaner %d", id_escaner)
        await gestor.detener_escaner(
            id_escaner, razon="Detenido por scanner-management (REST)"
        )
        return {"ok": True, "idEscaner": id_escaner}

    return router
