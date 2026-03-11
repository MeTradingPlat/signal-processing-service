"""Tests para GestorEscaneres — manejo de múltiples escáneres simultáneos.

Verifica:
  - Iniciar múltiples escáneres crea Tasks independientes
  - Iniciar el mismo escáner dos veces es idempotente
  - Detener uno no afecta a los demás
  - detener_todos() limpia todos los Tasks
  - obtener_estado() refleja correctamente los escáneres activos
  - Recuperación de errores en un escáner no afecta a los otros

Ejecutar:
    pytest tests/test_gestor_escaneres.py -v
"""

import asyncio
from concurrent.futures import ProcessPoolExecutor
from datetime import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.ejecutor_escaner import EjecutorEscaner
from app.core.gestor_escaneres import GestorEscaneres
from app.core.gestor_tiempo import GestorTiempo
from app.domain.models.escaner import Escaner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_escaner(id_escaner: int, nombre: str = "", tipo: str = "DIARIA") -> Escaner:
    return Escaner(
        id_escaner=id_escaner,
        nombre=nombre or f"Escaner-{id_escaner}",
        tipo_ejecucion=tipo,
        hora_inicio=time(9, 30),
        hora_fin=time(16, 0),
        mercados=["NYSE"],
    )


def make_gestor() -> GestorEscaneres:
    kafka = MagicMock()
    kafka.publicar_log = AsyncMock()
    kafka.publicar_cambio_estado = AsyncMock()

    marketdata = MagicMock()
    marketdata.obtener_simbolos_por_mercados = AsyncMock(return_value=["AAPL"])
    marketdata.obtener_barras_batch = AsyncMock(return_value={"AAPL": []})

    escaner_rest = MagicMock()
    pool = MagicMock(spec=ProcessPoolExecutor)
    gestor_tiempo = MagicMock(spec=GestorTiempo)

    return GestorEscaneres(
        kafka_producer=kafka,
        marketdata_rest=marketdata,
        escaner_rest=escaner_rest,
        process_pool=pool,
        gestor_tiempo=gestor_tiempo,
    )


# ---------------------------------------------------------------------------
# Tests: inicio de escáneres
# ---------------------------------------------------------------------------

class TestIniciarEscaner:
    @pytest.mark.asyncio
    async def test_iniciar_escaner_crea_task(self):
        """Un escáner iniciado aparece en _tareas."""
        pausa = asyncio.Event()

        async def ejecutar_bloqueante():
            await pausa.wait()

        gestor = make_gestor()
        e = make_escaner(1)

        with patch.object(EjecutorEscaner, "ejecutar", side_effect=ejecutar_bloqueante):
            await gestor.iniciar_escaner(e)
            await asyncio.sleep(0)

            assert 1 in gestor._tareas
            assert not gestor._tareas[1].done()

        pausa.set()
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_iniciar_mismo_escaner_dos_veces_es_idempotente(self):
        """Llamar iniciar_escaner dos veces con el mismo id no duplica el Task."""
        pausa = asyncio.Event()

        async def ejecutar_bloqueante():
            await pausa.wait()

        gestor = make_gestor()
        e = make_escaner(1)

        with patch.object(EjecutorEscaner, "ejecutar", side_effect=ejecutar_bloqueante):
            await gestor.iniciar_escaner(e)
            await gestor.iniciar_escaner(e)  # segunda llamada — debe ignorarse
            await asyncio.sleep(0)

            assert len(gestor._tareas) == 1

        pausa.set()
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_iniciar_tres_escaneres_crea_tres_tasks(self):
        """Tres escáneres distintos → tres Tasks independientes."""
        pausa = asyncio.Event()

        async def ejecutar_bloqueante():
            await pausa.wait()

        gestor = make_gestor()

        with patch.object(EjecutorEscaner, "ejecutar", side_effect=ejecutar_bloqueante):
            await gestor.iniciar_escaner(make_escaner(1))
            await gestor.iniciar_escaner(make_escaner(2))
            await gestor.iniciar_escaner(make_escaner(3))
            await asyncio.sleep(0)

            assert 1 in gestor._tareas
            assert 2 in gestor._tareas
            assert 3 in gestor._tareas
            assert len(gestor._tareas) == 3

        pausa.set()
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_tasks_tienen_nombre_correcto(self):
        """Cada Task lleva el nombre 'escaner-{id}'."""
        pausa = asyncio.Event()

        async def ejecutar_bloqueante():
            await pausa.wait()

        gestor = make_gestor()

        with patch.object(EjecutorEscaner, "ejecutar", side_effect=ejecutar_bloqueante):
            await gestor.iniciar_escaner(make_escaner(42))
            await asyncio.sleep(0)

            tarea = gestor._tareas[42]
            assert tarea.get_name() == "escaner-42"

        pausa.set()
        await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# Tests: detención individual
# ---------------------------------------------------------------------------

class TestDetenerEscaner:
    @pytest.mark.asyncio
    async def test_detener_escaner_limpia_tarea(self):
        """Tras detener, el escáner desaparece de _tareas."""
        pausa = asyncio.Event()

        async def ejecutar_bloqueante():
            await pausa.wait()

        gestor = make_gestor()
        e = make_escaner(1)

        with patch.object(EjecutorEscaner, "ejecutar", side_effect=ejecutar_bloqueante):
            await gestor.iniciar_escaner(e)
            await asyncio.sleep(0)
            assert 1 in gestor._tareas

            await gestor.detener_escaner(1, "test")
            await asyncio.sleep(0)

        assert 1 not in gestor._tareas

    @pytest.mark.asyncio
    async def test_detener_uno_no_afecta_a_los_otros(self):
        """Detener el escáner 2 deja intactos el 1 y el 3."""
        pausa = asyncio.Event()

        async def ejecutar_bloqueante():
            await pausa.wait()

        gestor = make_gestor()

        with patch.object(EjecutorEscaner, "ejecutar", side_effect=ejecutar_bloqueante):
            await gestor.iniciar_escaner(make_escaner(1))
            await gestor.iniciar_escaner(make_escaner(2))
            await gestor.iniciar_escaner(make_escaner(3))
            await asyncio.sleep(0)

            await gestor.detener_escaner(2, "test")
            await asyncio.sleep(0)

            assert 1 in gestor._tareas
            assert 2 not in gestor._tareas
            assert 3 in gestor._tareas

        pausa.set()
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_detener_escaner_inexistente_no_falla(self):
        """Detener un id que no existe no lanza excepción."""
        gestor = make_gestor()
        await gestor.detener_escaner(999, "no existe")  # no debe lanzar


# ---------------------------------------------------------------------------
# Tests: detener_todos
# ---------------------------------------------------------------------------

class TestDetenerTodos:
    @pytest.mark.asyncio
    async def test_detener_todos_limpia_dict_completo(self):
        pausa = asyncio.Event()

        async def ejecutar_bloqueante():
            await pausa.wait()

        gestor = make_gestor()

        with patch.object(EjecutorEscaner, "ejecutar", side_effect=ejecutar_bloqueante):
            await gestor.iniciar_escaner(make_escaner(1))
            await gestor.iniciar_escaner(make_escaner(2))
            await gestor.iniciar_escaner(make_escaner(3))
            await asyncio.sleep(0)
            assert len(gestor._tareas) == 3

            await gestor.detener_todos()
            await asyncio.sleep(0)

        assert len(gestor._tareas) == 0

    @pytest.mark.asyncio
    async def test_detener_todos_sin_escaneres_no_falla(self):
        gestor = make_gestor()
        await gestor.detener_todos()  # no debe lanzar


# ---------------------------------------------------------------------------
# Tests: obtener_estado
# ---------------------------------------------------------------------------

class TestObtenerEstado:
    @pytest.mark.asyncio
    async def test_estado_incluye_todos_los_escaneres_activos(self):
        pausa = asyncio.Event()

        async def ejecutar_bloqueante():
            await pausa.wait()

        gestor = make_gestor()

        with patch.object(EjecutorEscaner, "ejecutar", side_effect=ejecutar_bloqueante):
            await gestor.iniciar_escaner(make_escaner(1, "Escaner A"))
            await gestor.iniciar_escaner(make_escaner(2, "Escaner B"))
            await asyncio.sleep(0)

            estado = gestor.obtener_estado()

        assert 1 in estado
        assert 2 in estado
        assert estado[1]["nombre"] == "Escaner A"
        assert estado[2]["nombre"] == "Escaner B"

        pausa.set()
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_estado_tiene_campos_correctos(self):
        pausa = asyncio.Event()

        async def ejecutar_bloqueante():
            await pausa.wait()

        gestor = make_gestor()
        e = make_escaner(5, "Test Escaner", tipo="DIARIA")

        with patch.object(EjecutorEscaner, "ejecutar", side_effect=ejecutar_bloqueante):
            await gestor.iniciar_escaner(e)
            await asyncio.sleep(0)

            estado = gestor.obtener_estado()

        s = estado[5]
        assert s["nombre"] == "Test Escaner"
        assert s["tipo_ejecucion"] == "DIARIA"
        assert s["mercados"] == ["NYSE"]
        assert "hora_inicio" in s
        assert "hora_fin" in s
        assert s["tarea_activa"] is True

        pausa.set()
        await asyncio.sleep(0)

    def test_estado_vacio_sin_escaneres(self):
        gestor = make_gestor()
        assert gestor.obtener_estado() == {}


# ---------------------------------------------------------------------------
# Tests: resiliencia — error en un escáner no afecta a los otros
# ---------------------------------------------------------------------------

class TestResiliencia:
    @pytest.mark.asyncio
    async def test_error_en_un_escaner_no_detiene_los_demas(self):
        """Si el escáner 2 lanza excepción, los escáneres 1 y 3 siguen corriendo."""
        pausa = asyncio.Event()
        calls: dict[int, int] = {}

        async def ejecutar_por_id(self_executor):
            id_esc = self_executor._escaner.id_escaner
            calls[id_esc] = calls.get(id_esc, 0) + 1
            if id_esc == 2:
                raise RuntimeError("Falla simulada en escáner 2")
            await pausa.wait()

        gestor = make_gestor()

        with patch.object(EjecutorEscaner, "ejecutar", new=ejecutar_por_id):
            await gestor.iniciar_escaner(make_escaner(1))
            await gestor.iniciar_escaner(make_escaner(2))
            await gestor.iniciar_escaner(make_escaner(3))
            # Dar tiempo para que el escáner 2 falle y sea limpiado
            await asyncio.sleep(0.05)

            # 1 y 3 siguen en _tareas, 2 fue limpiado tras el error
            assert 1 in gestor._tareas
            assert 2 not in gestor._tareas  # limpiado por el finally
            assert 3 in gestor._tareas

        pausa.set()
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_error_publica_log_de_error(self):
        """Cuando un escáner falla, se publica un log de ERROR en Kafka."""
        async def ejecutar_con_error(self_executor):
            raise ValueError("Error de prueba")

        gestor = make_gestor()

        with patch.object(EjecutorEscaner, "ejecutar", new=ejecutar_con_error):
            await gestor.iniciar_escaner(make_escaner(1, "Escaner Fallido"))
            await asyncio.sleep(0.05)

        calls = gestor._kafka.publicar_log.call_args_list
        errores = [c for c in calls if "ERROR" in str(c)]
        assert len(errores) >= 1
