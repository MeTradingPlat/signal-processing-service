import threading
import time
from multiprocessing import Process

import app.main as main_module
from app.main import _monitor_orchestrator


def _exit_immediately(child_conn=None):
    pass


def _short_lived_stand_in(child_conn=None):
    time.sleep(5)


# _monitor_orchestrator no expone forma de detenerse -- corre en un hilo
# daemon que sobrevive al final de este test. Por eso el reemplazo de
# run_orchestrator se deja pisado a proposito (sin usar el fixture
# monkeypatch, que lo revertiria apenas termine el test): si revirtiera al
# real mientras el hilo sigue reiniciando en el fondo, el proximo reinicio
# llamaria a run_orchestrator(None) de verdad y crashearia sin parar,
# contaminando el log de los tests siguientes (reproducido antes de este
# comentario). El stand-in nunca crashea y muere solo cada ~5s, asi que el
# hilo de fondo sigue reiniciandolo sin ruido por el resto de la sesion.
main_module.run_orchestrator = _short_lived_stand_in


def test_monitor_orchestrator_restarts_on_crash():
    process = Process(target=_exit_immediately, daemon=True)
    process.start()
    original_pid = process.pid

    holder = [process]
    monitor = threading.Thread(
        target=_monitor_orchestrator, args=(holder, None), daemon=True
    )
    monitor.start()

    time.sleep(main_module._RESTART_DELAY + 1.0)

    new_process = holder[0]
    assert new_process.pid != original_pid
    assert new_process.is_alive()
