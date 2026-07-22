import json
import logging
from multiprocessing.connection import Connection

from app.models.events import TunnelMessage

logger = logging.getLogger(__name__)


class PipeReceiver:

    def __init__(self, connection: Connection):
        self._connection = connection

    def receive(self) -> TunnelMessage:
        raw = self._connection.recv_bytes()
        line = raw.decode("utf-8").strip()
        data = json.loads(line)
        return TunnelMessage.model_validate(data)

    def poll(self, timeout: float) -> TunnelMessage | None:
        if not self._connection.poll(timeout):
            return None
        return self.receive()

    def close(self):
        self._connection.close()
