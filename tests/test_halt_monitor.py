"""Tests para HaltMonitor.

Verifica: iniciar/detener, polling, acceso thread-safe, consulta de símbolos.
"""
import threading
import time
from unittest.mock import patch

import pytest

from app.core.halt_monitor import HaltMonitor


class TestHaltMonitorBasico:

    def test_no_esta_halteado_por_defecto(self):
        monitor = HaltMonitor()
        assert monitor.esta_halteado("AAPL") is False

    def test_total_halteados_inicial_es_cero(self):
        monitor = HaltMonitor()
        assert monitor.total_halteados() == 0

    def test_simbolos_halteados_retorna_frozenset(self):
        monitor = HaltMonitor()
        resultado = monitor.simbolos_halteados()
        assert isinstance(resultado, frozenset)
        assert len(resultado) == 0


class TestHaltMonitorInicioYRefresco:

    def test_iniciar_carga_datos_inmediatamente(self):
        """Al iniciar, hace una carga sincrónica antes de arrancar el hilo."""
        with patch("app.adapters.halt_adapter.obtener_simbolos_halted",
                   return_value={"MULN", "ILUS"}) as mock_fetch:
            monitor = HaltMonitor(intervalo_seg=9999)
            monitor.iniciar()
            monitor.detener()

            mock_fetch.assert_called_once()
            assert monitor.esta_halteado("MULN") is True
            assert monitor.esta_halteado("ILUS") is True
            assert monitor.esta_halteado("AAPL") is False

    def test_iniciar_dos_veces_no_duplica_hilo(self):
        with patch("app.adapters.halt_adapter.obtener_simbolos_halted",
                   return_value=set()):
            monitor = HaltMonitor(intervalo_seg=9999)
            monitor.iniciar()
            hilo_original = monitor._thread
            monitor.iniciar()  # segunda llamada
            assert monitor._thread is hilo_original
            monitor.detener()

    def test_detener_pone_running_en_false(self):
        with patch("app.adapters.halt_adapter.obtener_simbolos_halted",
                   return_value=set()):
            monitor = HaltMonitor(intervalo_seg=9999)
            monitor.iniciar()
            monitor.detener()
            assert monitor._running is False

    def test_refresh_actualiza_halted(self):
        """Verifica que el set de halteados se actualiza en cada refresh."""
        with patch("app.adapters.halt_adapter.obtener_simbolos_halted",
                   return_value=set()):
            monitor = HaltMonitor(intervalo_seg=9999)
            monitor.iniciar()
            assert monitor.total_halteados() == 0

        # Simular que llega un nuevo halt
        with patch("app.adapters.halt_adapter.obtener_simbolos_halted",
                   return_value={"NEWB"}):
            monitor._refrescar()
            assert monitor.esta_halteado("NEWB") is True

        monitor.detener()

    def test_refresh_limpia_halts_expirados(self):
        """Si un símbolo ya no está en el archivo → se elimina del set."""
        with patch("app.adapters.halt_adapter.obtener_simbolos_halted",
                   return_value={"OLD1", "OLD2"}):
            monitor = HaltMonitor(intervalo_seg=9999)
            monitor.iniciar()
            assert monitor.esta_halteado("OLD1") is True

        # Siguiente poll: OLD1 ya no está halteado
        with patch("app.adapters.halt_adapter.obtener_simbolos_halted",
                   return_value={"OLD2"}):
            monitor._refrescar()
            assert monitor.esta_halteado("OLD1") is False
            assert monitor.esta_halteado("OLD2") is True

        monitor.detener()

    def test_error_en_adapter_no_revienta_monitor(self):
        """Si el adapter lanza excepción, el monitor sigue vivo."""
        with patch("app.adapters.halt_adapter.obtener_simbolos_halted",
                   side_effect=Exception("Red caída")):
            monitor = HaltMonitor(intervalo_seg=9999)
            monitor._refrescar()  # no debe lanzar
            assert monitor.total_halteados() == 0


class TestHaltMonitorThreadSafety:

    def test_acceso_concurrente_no_falla(self):
        """Múltiples threads leyendo al mismo tiempo no deben causar race conditions."""
        with patch("app.adapters.halt_adapter.obtener_simbolos_halted",
                   return_value={"SYM1", "SYM2", "SYM3"}):
            monitor = HaltMonitor(intervalo_seg=9999)
            monitor.iniciar()

        resultados = []
        errores = []

        def leer():
            try:
                for _ in range(100):
                    resultados.append(monitor.esta_halteado("SYM1"))
                    resultados.append(monitor.total_halteados())
            except Exception as e:
                errores.append(e)

        hilos = [threading.Thread(target=leer) for _ in range(10)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()

        monitor.detener()
        assert len(errores) == 0
