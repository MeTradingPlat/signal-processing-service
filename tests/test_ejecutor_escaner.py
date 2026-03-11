"""Tests unitarios para EjecutorEscaner — comportamiento de tiempo y control de flujo.

Verifica:
  - Día no hábil al arrancar: duerme hasta el siguiente día hábil
  - Antes de hora_inicio: duerme hasta hora_inicio del mismo día
  - UNA_VEZ llega a hora_fin: publica estado DETENIDO y termina
  - DIARIA llega a hora_fin: duerme hasta siguiente día hábil, NO termina
  - Loop normal: obtiene velas, evalúa filtros, publica señales

Ejecutar:
    pytest tests/test_ejecutor_escaner.py -v
"""

from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.core.ejecutor_escaner import EjecutorEscaner
from app.core.gestor_tiempo import GestorTiempo
from app.domain.models.escaner import Escaner, Filtro, Parametro


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def make_escaner(
    id_escaner: int = 1,
    nombre: str = "Test",
    tipo_ejecucion: str = "DIARIA",
    hora_inicio: time = time(9, 30),
    hora_fin: time = time(16, 0),
    mercados: list[str] | None = None,
) -> Escaner:
    return Escaner(
        id_escaner=id_escaner,
        nombre=nombre,
        tipo_ejecucion=tipo_ejecucion,
        hora_inicio=hora_inicio,
        hora_fin=hora_fin,
        mercados=mercados or ["NYSE"],
    )


def make_ejecutor(escaner: Escaner, gestor_tiempo: GestorTiempo) -> EjecutorEscaner:
    """Crea un EjecutorEscaner con todos los adapters mockeados."""
    kafka = MagicMock()
    kafka.publicar_log = AsyncMock()
    kafka.publicar_cambio_estado = AsyncMock()
    kafka.publicar_senal = AsyncMock()

    marketdata = MagicMock()
    marketdata.obtener_simbolos_por_mercados = AsyncMock(return_value=["AAPL", "MSFT"])
    marketdata.obtener_barras_batch = AsyncMock(return_value={"AAPL": [], "MSFT": []})
    marketdata.obtener_ultima_vela_batch = AsyncMock(return_value={})

    pool = MagicMock(spec=ProcessPoolExecutor)

    return EjecutorEscaner(
        escaner=escaner,
        kafka_producer=kafka,
        marketdata_rest=marketdata,
        process_pool=pool,
        gestor_tiempo=gestor_tiempo,
    )


def make_gestor_tiempo_mock() -> MagicMock:
    """Crea un GestorTiempo mockeado con comportamiento por defecto sensato."""
    gt = MagicMock(spec=GestorTiempo)
    gt.es_dia_habil = MagicMock(return_value=True)
    gt.siguiente_dia_habil = MagicMock(return_value=date(2025, 3, 3))
    gt.construir_datetime_utc = MagicMock(return_value=utc(2025, 3, 3, 9, 30))
    gt.calcular_espera_vela = MagicMock(return_value=5.0)
    gt.dormir_hasta = AsyncMock()
    return gt


# ---------------------------------------------------------------------------
# Tests: día no hábil
# ---------------------------------------------------------------------------

class TestDiaNohabil:
    @pytest.mark.asyncio
    async def test_dia_no_habil_duerme_hasta_siguiente_dia(self):
        """Si hoy es sábado/festivo, duerme hasta hora_inicio del siguiente día hábil."""
        escaner = make_escaner(mercados=["NYSE"], hora_inicio=time(9, 30))
        gt = make_gestor_tiempo_mock()

        sabado = utc(2025, 3, 1, 10, 0)
        lunes = date(2025, 3, 3)
        objetivo = utc(2025, 3, 3, 9, 30)

        # Primera llamada: es sábado (no hábil) → duerme
        # Segunda llamada: nunca llega porque detenemos el loop en dormir_hasta
        gt.ahora_utc = MagicMock(return_value=sabado)
        gt.es_dia_habil = MagicMock(return_value=False)
        gt.siguiente_dia_habil = MagicMock(return_value=lunes)
        gt.construir_datetime_utc = MagicMock(return_value=objetivo)

        ejecutor = make_ejecutor(escaner, gt)

        async def dormir_y_detener(obj, poll=None):
            ejecutor.detener()

        gt.dormir_hasta = AsyncMock(side_effect=dormir_y_detener)

        await ejecutor.ejecutar()

        gt.siguiente_dia_habil.assert_called_once_with(["NYSE"], sabado.date())
        gt.construir_datetime_utc.assert_called_once_with(time(9, 30), lunes)
        gt.dormir_hasta.assert_called_once_with(objetivo)

    @pytest.mark.asyncio
    async def test_dia_habil_no_duerme_por_festivo(self):
        """Un lunes normal no activa la rama de día no hábil."""
        escaner = make_escaner(hora_inicio=time(9, 30), hora_fin=time(16, 0))
        gt = make_gestor_tiempo_mock()

        # Lunes 09:45 → día hábil, dentro de horario
        gt.ahora_utc = MagicMock(return_value=utc(2025, 3, 3, 9, 45))
        gt.es_dia_habil = MagicMock(return_value=True)

        ejecutor = make_ejecutor(escaner, gt)

        # El loop entra al paso de vela: detenemos tras el primer sleep
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            async def stop_after_sleep(n):
                ejecutor.detener()
            mock_sleep.side_effect = stop_after_sleep

            await ejecutor.ejecutar()

        # dormir_hasta NO debe haberse llamado por día no hábil
        gt.dormir_hasta.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: control de hora_inicio / hora_fin
# ---------------------------------------------------------------------------

class TestHorarioEscaner:
    @pytest.mark.asyncio
    async def test_antes_de_hora_inicio_duerme(self):
        """Si la hora actual es anterior a hora_inicio, duerme hasta ella."""
        escaner = make_escaner(hora_inicio=time(9, 30), hora_fin=time(16, 0))
        gt = make_gestor_tiempo_mock()

        # Son las 08:00, hora_inicio es 09:30
        gt.ahora_utc = MagicMock(return_value=utc(2025, 3, 3, 8, 0))
        objetivo = utc(2025, 3, 3, 9, 30)
        gt.construir_datetime_utc = MagicMock(return_value=objetivo)

        ejecutor = make_ejecutor(escaner, gt)

        async def dormir_y_detener(obj, poll=None):
            ejecutor.detener()

        gt.dormir_hasta = AsyncMock(side_effect=dormir_y_detener)

        await ejecutor.ejecutar()

        gt.construir_datetime_utc.assert_called_once_with(time(9, 30), date(2025, 3, 3))
        gt.dormir_hasta.assert_called_once_with(objetivo)

    @pytest.mark.asyncio
    async def test_una_vez_llega_hora_fin_publica_detenido(self):
        """UNA_VEZ: al llegar hora_fin publica cambio a DETENIDO y termina el loop."""
        escaner = make_escaner(
            tipo_ejecucion="UNA_VEZ",
            hora_inicio=time(9, 30),
            hora_fin=time(16, 0),
        )
        gt = make_gestor_tiempo_mock()

        # Son las 16:05 → hora_fin superada
        gt.ahora_utc = MagicMock(return_value=utc(2025, 3, 3, 16, 5))

        ejecutor = make_ejecutor(escaner, gt)

        await ejecutor.ejecutar()

        ejecutor._kafka.publicar_cambio_estado.assert_called_once_with(
            escaner.id_escaner,
            escaner.nombre,
            "INICIADO",
            "DETENIDO",
            "ESCANER_UNA_VEZ completado",
        )
        # No debe dormir por DIARIA
        gt.dormir_hasta.assert_not_called()

    @pytest.mark.asyncio
    async def test_diaria_llega_hora_fin_no_termina(self):
        """DIARIA: al llegar hora_fin duerme hasta siguiente día hábil, NO publica DETENIDO."""
        escaner = make_escaner(
            tipo_ejecucion="DIARIA",
            hora_inicio=time(9, 30),
            hora_fin=time(16, 0),
        )
        gt = make_gestor_tiempo_mock()

        lunes = date(2025, 3, 3)
        martes = date(2025, 3, 4)
        objetivo = utc(2025, 3, 4, 9, 30)

        # Son las 16:05 del lunes → hora_fin superada
        gt.ahora_utc = MagicMock(return_value=utc(2025, 3, 3, 16, 5))
        gt.siguiente_dia_habil = MagicMock(return_value=martes)
        gt.construir_datetime_utc = MagicMock(return_value=objetivo)

        ejecutor = make_ejecutor(escaner, gt)

        async def dormir_y_detener(obj, poll=None):
            ejecutor.detener()

        gt.dormir_hasta = AsyncMock(side_effect=dormir_y_detener)

        await ejecutor.ejecutar()

        # NO publicó cambio de estado a DETENIDO
        ejecutor._kafka.publicar_cambio_estado.assert_not_called()

        # Durmió hasta el siguiente día hábil
        gt.siguiente_dia_habil.assert_called_once_with(["NYSE"], lunes)
        gt.construir_datetime_utc.assert_called_once_with(time(9, 30), martes)
        gt.dormir_hasta.assert_called_once_with(objetivo)

    @pytest.mark.asyncio
    async def test_diaria_reinicia_despues_del_sleep(self):
        """DIARIA: tras el sleep overnight, el loop continúa (vuelve a iterar)."""
        escaner = make_escaner(
            tipo_ejecucion="DIARIA",
            hora_inicio=time(9, 30),
            hora_fin=time(16, 0),
        )
        gt = make_gestor_tiempo_mock()

        martes = date(2025, 3, 4)
        objetivo = utc(2025, 3, 4, 9, 30)

        llamadas_ahora = [
            utc(2025, 3, 3, 16, 5),   # 1ª iteración: hora_fin superada
            utc(2025, 3, 4, 9, 45),   # 2ª iteración tras dormir: dentro de horario
        ]
        gt.ahora_utc = MagicMock(side_effect=llamadas_ahora)
        gt.siguiente_dia_habil = MagicMock(return_value=martes)
        gt.construir_datetime_utc = MagicMock(return_value=objetivo)

        ejecutor = make_ejecutor(escaner, gt)

        dormir_count = {"n": 0}

        async def dormir_controlado(obj, poll=None):
            dormir_count["n"] += 1
            # Tras el primer sleep, la siguiente iteración detenemos en la vela
            # (lo hace el sleep de vela abajo)

        gt.dormir_hasta = AsyncMock(side_effect=dormir_controlado)

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_vela_sleep:
            async def stop_after_candle(n):
                ejecutor.detener()
            mock_vela_sleep.side_effect = stop_after_candle

            await ejecutor.ejecutar()

        # dormir_hasta se llamó una vez (por DIARIA al llegar hora_fin)
        assert dormir_count["n"] == 1
        # El loop continuó y llegó al sleep de vela
        mock_vela_sleep.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: sin símbolos
# ---------------------------------------------------------------------------

class TestSinSimbolos:
    @pytest.mark.asyncio
    async def test_sin_simbolos_termina_sin_loop(self):
        """Si no hay símbolos el ejecutor termina sin entrar al loop."""
        escaner = make_escaner()
        gt = make_gestor_tiempo_mock()

        ejecutor = make_ejecutor(escaner, gt)
        ejecutor._marketdata.obtener_simbolos_por_mercados = AsyncMock(return_value=[])

        await ejecutor.ejecutar()

        gt.dormir_hasta.assert_not_called()
        ejecutor._kafka.publicar_log.assert_called()
        # Verificar que el log de advertencia se publicó
        calls = [str(c) for c in ejecutor._kafka.publicar_log.call_args_list]
        assert any("WARN" in c for c in calls)


# ---------------------------------------------------------------------------
# Tests: detener()
# ---------------------------------------------------------------------------

class TestDetener:
    @pytest.mark.asyncio
    async def test_detener_interrumpe_loop(self):
        """detener() hace que el loop salga en la próxima iteración."""
        escaner = make_escaner(hora_inicio=time(9, 30), hora_fin=time(16, 0))
        gt = make_gestor_tiempo_mock()
        gt.ahora_utc = MagicMock(return_value=utc(2025, 3, 3, 9, 45))

        ejecutor = make_ejecutor(escaner, gt)

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            async def stop_via_detener(n):
                ejecutor.detener()
            mock_sleep.side_effect = stop_via_detener

            await ejecutor.ejecutar()

        assert ejecutor._activo is False

    def test_detener_pone_activo_false(self):
        escaner = make_escaner()
        gt = make_gestor_tiempo_mock()
        ejecutor = make_ejecutor(escaner, gt)

        assert ejecutor._activo is True
        ejecutor.detener()
        assert ejecutor._activo is False
