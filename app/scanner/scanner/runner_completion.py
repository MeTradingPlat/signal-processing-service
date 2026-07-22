import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def publish_scanner_completed(scanner_id: int):
    event = {
        "idEscaner": scanner_id,
        "nombreEscaner": "",
        "estadoAnterior": "INICIADO",
        "estadoNuevo": "DETENIDO",
        "razon": "ESCANER_UNA_VEZ completado",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "servicioOrigen": "signal-processing-service",
    }
    logger.info(
        "KAFKA-SIM: publishing to scanner.state -> %s",
        json.dumps(event),
    )
