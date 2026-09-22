import logging
import threading
import time

logger = logging.getLogger(__name__)

_RETRY_SECONDS = 30.0


def start_max_pending_from_universe(clients: list, client_factory) -> None:
    """El tope de la cola de reintento de cada cliente WS saliente arranca en
    un valor fijo (10 mil) -- lo suficientemente grande para no perder nada
    hoy, pero arbitrario. Esto lo reemplaza por el numero real de simbolos
    que marketdata-service tiene rastreados (el techo real de cuantas
    señales distintas puede haber a la vez, no puede haber mas señales
    simultaneas que simbolos que existen) apenas se puede resolver, y
    reintenta en el fondo si marketdata-service todavia no esta arriba."""
    def _resolve():
        client = client_factory()
        while True:
            try:
                total = len(client.fetch_symbols([]))
                if total > 0:
                    for c in clients:
                        c.set_max_pending(total)
                    logger.info("outbound ws clients: max_pending ajustado a %d simbolos rastreados", total)
                    return
            except Exception as e:
                logger.warning("outbound ws clients: no se pudo resolver el universo de simbolos, reintentando: %s", e)
            time.sleep(_RETRY_SECONDS)

    threading.Thread(target=_resolve, daemon=True, name="max-pending-from-universe").start()
