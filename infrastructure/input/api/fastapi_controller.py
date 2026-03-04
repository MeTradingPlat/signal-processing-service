"""Controlador FastAPI: recibe webhooks de scanner-management-service.

Endpoints:
  POST /api/signal-processing/escaner        → iniciar escaner
  POST /api/signal-processing/escaner/{id}/detener → detener escaner
"""

from fastapi import FastAPI, HTTPException
from typing import Dict, Any
import logging

app = FastAPI()
logger = logging.getLogger(__name__)

# Referencias globales inyectadas desde main.py
_process_manager = None
_comunicacion = None


def set_process_manager(process_manager, comunicacion_adapter) -> None:
    """Inyecta ProcessManager y ComunicacionExternaAdapter en el controlador."""
    global _process_manager, _comunicacion
    _process_manager = process_manager
    _comunicacion = comunicacion_adapter


@app.post("/api/signal-processing/escaner")
async def registrar_escaner(escaner_data: Dict[str, Any]):
    """Recibe un escaner desde scanner-management-service y lo inicia."""
    nombre = escaner_data.get('nombre', 'unknown')
    id_escaner = escaner_data.get('idEscaner', '?')
    logger.info(
        f"[API] POST /api/signal-processing/escaner "
        f"- id={id_escaner}, nombre={nombre}"
    )

    if _process_manager is None or _comunicacion is None:
        logger.error("[API] Service not fully initialized")
        raise HTTPException(status_code=503, detail="Service not fully initialized")

    try:
        # Mapear dict a objeto Escaner usando el adaptador de comunicacion
        escaner = _comunicacion._mapear_escaner(escaner_data)

        if not escaner.esta_activo():
            logger.info(f"[API] Escaner '{nombre}' no esta activo, ignorando")
            return {"status": "ok", "message": "Escaner no activo, ignorado"}

        _process_manager.iniciar_escaner(escaner)
        logger.info(f"[API] Escaner '{nombre}' iniciado OK")
        return {"status": "ok", "message": "Escaner iniciado"}

    except Exception as e:
        logger.error(
            f"[API] Error iniciando escaner '{nombre}': {e}", exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/signal-processing/escaner/{id}/detener")
async def detener_escaner(id: int):
    """Detiene el ScannerProcess del escaner dado."""
    logger.info(f"[API] POST /api/signal-processing/escaner/{id}/detener")

    if _process_manager is None:
        logger.error("[API] Service not fully initialized")
        raise HTTPException(status_code=503, detail="Service not fully initialized")

    try:
        _process_manager.detener_escaner(id)
        logger.info(f"[API] Escaner {id} detenido OK")
        return {"status": "ok", "message": "Escaner detenido"}

    except Exception as e:
        logger.error(
            f"[API] Error deteniendo escaner {id}: {e}", exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))
