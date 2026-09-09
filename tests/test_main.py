import threading
import time
from multiprocessing import Process

import app.main as main_module
from app.main import _monitor_orchestrator
from app.orchestrator.process_termination import terminate_and_reap


def _exit_immediately(child_conn=None):
    pass


def test_monitor_orchestrator_restarts_on_crash(monkeypatch):
    monkeypatch.setattr(main_module, "run_orchestrator", _exit_immediately)

    process = Process(target=_exit_immediately, daemon=True)
    process.start()
    original_pid = process.pid

    holder = [process]
    monitor = threading.Thread(
        target=_monitor_orchestrator, args=(holder, None), daemon=True
    )
    monitor.start()

    time.sleep(main_module._RESTART_DELAY + 1.5)

    new_process = holder[0]
    assert new_process.pid != original_pid
    assert new_process.is_alive()

    terminate_and_reap(new_process, timeout=2)
