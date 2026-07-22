import threading
from multiprocessing import Pipe

from app.ipc.receiver import PipeReceiver
from app.ipc.sender import PipeSender
from app.models.events import EventType, TunnelMessage


def test_send_and_receive_roundtrip():
    parent_conn, child_conn = Pipe()

    sender = PipeSender(parent_conn)
    receiver = PipeReceiver(child_conn)

    message = TunnelMessage(
        type=EventType.SCANNER_STARTED,
        payload={"idEscaner": 10, "nombre": "pipe-test"},
    )

    sender.send(message)

    received = receiver.receive()

    assert received.type == EventType.SCANNER_STARTED
    assert received.payload["idEscaner"] == 10
    assert received.payload["nombre"] == "pipe-test"

    sender.close()
    receiver.close()


def test_concurrent_sends_do_not_corrupt():
    parent_conn, child_conn = Pipe()
    sender = PipeSender(parent_conn)
    errors = []

    def send_message(scanner_id: int):
        try:
            msg = TunnelMessage(
                type=EventType.SCANNER_STARTED,
                payload={"idEscaner": scanner_id},
            )
            sender.send(msg)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=send_message, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    sender.close()

    assert len(errors) == 0

    receiver = PipeReceiver(child_conn)
    received_ids = set()
    for _ in range(50):
        msg = receiver.receive()
        received_ids.add(msg.payload["idEscaner"])

    assert len(received_ids) == 50
    receiver.close()
