"""Monitor de trading halts en tiempo real.

Descarga el archivo oficial de NASDAQ cada 30 segundos y mantiene un set
en memoria de los símbolos actualmente halteados. Hilo daemon — se detiene
automáticamente cuando muere el proceso principal.

Escalabilidad:
  - Un solo hilo compartido entre TODOS los escáneres activos.
  - Consulta es O(1): lookup en set en memoria.
  - El estado viaja al ProcessPoolExecutor como bool en el ctx_data.

Uso:
    monitor = HaltMonitor()
    monitor.iniciar()
    # ... durante la ejecución ...
    if monitor.esta_halteado("MULN"):
        ...
    monitor.detener()
"""
from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

_INTERVALO_SEG = 30


class HaltMonitor:
    """Monitor de halts de trading basado en NASDAQ Trader. Thread-safe."""

    def __init__(self, intervalo_seg: int = _INTERVALO_SEG) -> None:
        self._halted: set[str] = set()
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._intervalo = intervalo_seg

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    def iniciar(self) -> None:
        """Inicia el hilo de polling. Carga inicial inmediata."""
        if self._running:
            return
        self._running = True
        # Carga sincrónica inicial antes de arrancar el hilo
        self._refrescar()
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="halt-monitor",
        )
        self._thread.start()
        logger.info("HaltMonitor iniciado (intervalo=%ds)", self._intervalo)

    def detener(self) -> None:
        """Detiene el hilo de polling."""
        self._running = False
        logger.info("HaltMonitor detenido")

    # ── Consulta ──────────────────────────────────────────────────────────────

    def esta_halteado(self, symbol: str) -> bool:
        """Retorna True si el símbolo está actualmente halteado."""
        with self._lock:
            return symbol in self._halted

    def simbolos_halteados(self) -> frozenset[str]:
        """Retorna copia inmutable del set de símbolos halteados."""
        with self._lock:
            return frozenset(self._halted)

    def total_halteados(self) -> int:
        with self._lock:
            return len(self._halted)

    # ── Internos ──────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        while self._running:
            time.sleep(self._intervalo)
            if self._running:
                self._refrescar()

    def _refrescar(self) -> None:
        from app.adapters.halt_adapter import obtener_simbolos_halted
        try:
            nuevos = obtener_simbolos_halted()
            with self._lock:
                self._halted = nuevos
            if nuevos:
                logger.info("HaltMonitor: %d símbolo(s) halteado(s): %s",
                            len(nuevos), list(nuevos)[:10])
        except Exception as exc:
            logger.warning("HaltMonitor: error en refresh: %s", exc)
