from fastapi import FastAPI, HTTPException
from typing import Optional, Dict, Any
import logging

# We will inject the UseCase manually or via a simple Dependency Injection pattern
# since FastAPI's dependency injection is per-request, but we have a persistent singleton UseCase.

app = FastAPI()
logger = logging.getLogger(__name__)

# Global variable to hold the use case reference
_use_case = None

def set_use_case(use_case):
    global _use_case
    _use_case = use_case

@app.post("/api/signal-processing/escaner")
async def registrar_escaner(escaner: Dict[str, Any]):
    logger.info(f"[API] POST /api/signal-processing/escaner - Solicitud recibida")
    logger.info(f"[API] Datos escaner: id={escaner.get('idEscaner')}, nombre={escaner.get('nombre')}")

    if _use_case is None:
        logger.error("[API] Service not fully initialized - use_case is None")
        raise HTTPException(status_code=503, detail="Service not fully initialized")

    try:
        _use_case.registrar_escaner(escaner)
        logger.info(f"[API] POST /api/signal-processing/escaner - Respuesta OK: id={escaner.get('idEscaner')}")
        return {"status": "ok", "message": "Escaner registrado"}
    except Exception as e:
        logger.error(f"[API] POST /api/signal-processing/escaner - ERROR: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/signal-processing/escaner/{id}/detener")
async def detener_escaner(id: int):
    logger.info(f"[API] POST /api/signal-processing/escaner/{id}/detener - Solicitud recibida")

    if _use_case is None:
        logger.error("[API] Service not fully initialized - use_case is None")
        raise HTTPException(status_code=503, detail="Service not fully initialized")

    try:
        _use_case.detener_escaner(id)
        logger.info(f"[API] POST /api/signal-processing/escaner/{id}/detener - Respuesta OK")
        return {"status": "ok", "message": "Escaner detenido"}
    except Exception as e:
        logger.error(f"[API] POST /api/signal-processing/escaner/{id}/detener - ERROR: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
