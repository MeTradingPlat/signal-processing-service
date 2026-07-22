import logging

from fastapi import APIRouter, HTTPException, Request

from app.ipc.sender import PipeSender
from app.models.escaner import Escaner
from app.models.events import EventType, TunnelMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/signal-processing", tags=["scanner"])


def _get_sender(request: Request) -> PipeSender:
    return request.app.state.pipe_sender


@router.post("/escaner", status_code=202)
def scanner_started(escaner: Escaner, request: Request):
    sender: PipeSender = request.app.state.pipe_sender
    logger.info("API: scanner started id=%d name='%s'", escaner.idEscaner, escaner.nombre)
    message = TunnelMessage(
        type=EventType.SCANNER_STARTED,
        payload=escaner.model_dump(mode="json"),
    )
    try:
        sender.send(message)
    except (BrokenPipeError, EOFError, OSError) as exc:
        logger.error("API: pipe error sending SCANNER_STARTED id=%d: %s", escaner.idEscaner, exc)
        raise HTTPException(status_code=503, detail="Orchestrator unavailable") from exc
    return {"ok": True, "idEscaner": escaner.idEscaner}


@router.post("/escaner/{scanner_id}/detener", status_code=202)
def scanner_stopped(scanner_id: int, request: Request):
    sender: PipeSender = request.app.state.pipe_sender
    logger.info("API: scanner stopped id=%d", scanner_id)
    message = TunnelMessage(
        type=EventType.SCANNER_STOPPED,
        payload={"idEscaner": scanner_id},
    )
    try:
        sender.send(message)
    except (BrokenPipeError, EOFError, OSError) as exc:
        logger.error("API: pipe error sending SCANNER_STOPPED id=%d: %s", scanner_id, exc)
        raise HTTPException(status_code=503, detail="Orchestrator unavailable") from exc
    return {"ok": True, "idEscaner": scanner_id}
