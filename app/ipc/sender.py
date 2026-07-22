import json
import logging
import threading
from multiprocessing.connection import Connection

from app.models.events import TunnelMessage

logger = logging.getLogger(__name__)


class PipeSender:

    def __init__(self, connection: Connection):
        self._connection = connection
        self._lock = threading.Lock()

    def send(self, message: TunnelMessage):
        data = message.model_dump(mode="json")
        line = json.dumps(data) + "\n"
        with self._lock:
            self._connection.send_bytes(line.encode("utf-8"))

    def close(self):
        self._connection.close()
