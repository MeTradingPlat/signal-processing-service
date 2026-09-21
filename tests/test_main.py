import threading

from app.main import _monitor_orchestrator


class _FakeProcess:
    def __init__(self, pid: int, exitcode: int | None = 1, blocks_until: threading.Event | None = None):
        self.pid = pid
        self.exitcode = exitcode
        self._blocks_until = blocks_until

    def join(self):
        if self._blocks_until is not None:
            self._blocks_until.wait(timeout=5)


def test_monitor_orchestrator_restarts_on_crash():
    stop = threading.Event()
    restarted = threading.Event()
    holder = [_FakeProcess(pid=1)]

    def spawn(child_conn):
        restarted.set()
        return _FakeProcess(pid=2, exitcode=None, blocks_until=stop)

    monitor = threading.Thread(
        target=_monitor_orchestrator, args=(holder, None),
        kwargs={"spawn": spawn, "restart_delay": 0, "stop": stop}, daemon=True,
    )
    monitor.start()

    assert restarted.wait(timeout=5)
    assert holder[0].pid == 2
    stop.set()
    monitor.join(timeout=5)
    assert not monitor.is_alive()


def test_monitor_orchestrator_does_not_restart_after_stop():
    stop = threading.Event()
    stop.set()
    spawned = []

    _monitor_orchestrator([_FakeProcess(pid=1)], None, spawn=lambda c: spawned.append(c), restart_delay=0, stop=stop)

    assert spawned == []
