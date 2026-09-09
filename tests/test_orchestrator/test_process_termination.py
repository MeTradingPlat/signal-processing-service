import signal
import time
from multiprocessing import Process

from app.orchestrator.process_termination import terminate_and_reap


def _ignore_sigterm_and_sleep():
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    time.sleep(30)


def test_terminate_and_reap_escalates_to_kill_when_sigterm_is_ignored():
    process = Process(target=_ignore_sigterm_and_sleep, daemon=True)
    process.start()
    time.sleep(0.2)

    start = time.monotonic()
    terminate_and_reap(process, timeout=1)
    elapsed = time.monotonic() - start

    assert not process.is_alive()
    assert elapsed < 10


def test_terminate_and_reap_no_escalation_needed():
    process = Process(target=time.sleep, args=(30,), daemon=True)
    process.start()
    time.sleep(0.2)

    terminate_and_reap(process, timeout=3)

    assert not process.is_alive()
