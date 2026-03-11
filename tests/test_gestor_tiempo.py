"""Tests unitarios para GestorTiempo.

Cubre:
  - festivos_nyse: fechas conocidas de NYSE para años concretos
  - es_dia_habil: días normales, fines de semana, festivos, mercados 24/7
  - siguiente_dia_habil: salto de fin de semana, festivo, secuencia larga
  - dormir_hasta: anti-drift (wakeup temprano, tardío, ya pasó el objetivo)
  - dormir_hasta_hora: hora futura del mismo día / día siguiente
  - calcular_espera_vela: alineamiento al timeframe con y sin margen

Ejecutar:
    cd signal-processing-service
    pytest tests/ -v
"""

import asyncio
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.core.gestor_tiempo import (
    GestorTiempo,
    _nth_weekday,
    _observado,
    _ultimo_weekday,
    _viernes_santo,
    festivos_nyse,
)


# ---------------------------------------------------------------------------
# Utilidades de test
# ---------------------------------------------------------------------------

def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Tests: helpers de cálculo de fechas
# ---------------------------------------------------------------------------

class TestHelpersCalculo:
    def test_observado_dia_normal(self):
        # Miércoles normal → no cambia
        assert _observado(date(2025, 7, 4)) == date(2025, 7, 4)  # viernes 2025

    def test_observado_sabado_da_viernes(self):
        # Sábado → viernes anterior
        sabado = date(2026, 7, 4)  # 4 Jul 2026 es sábado
        assert _observado(sabado) == date(2026, 7, 3)

    def test_observado_domingo_da_lunes(self):
        # Domingo → lunes siguiente
        domingo = date(2021, 7, 4)  # 4 Jul 2021 es domingo
        assert _observado(domingo) == date(2021, 7, 5)

    def test_nth_weekday_primer_lunes_septiembre(self):
        # Labor Day 2025 → 1er lunes de septiembre
        assert _nth_weekday(2025, 9, 0, 1) == date(2025, 9, 1)

    def test_nth_weekday_tercer_lunes_enero(self):
        # MLK Day 2025 → 3er lunes de enero
        assert _nth_weekday(2025, 1, 0, 3) == date(2025, 1, 20)

    def test_ultimo_weekday_lunes_mayo(self):
        # Memorial Day 2025 → último lunes de mayo
        assert _ultimo_weekday(2025, 5, 0) == date(2025, 5, 26)

    def test_viernes_santo_2025(self):
        # Good Friday 2025
        assert _viernes_santo(2025) == date(2025, 4, 18)

    def test_viernes_santo_2024(self):
        # Good Friday 2024
        assert _viernes_santo(2024) == date(2024, 3, 29)


# ---------------------------------------------------------------------------
# Tests: festivos_nyse
# ---------------------------------------------------------------------------

class TestFestivosNYSE:
    """Verifica festivos reales del NYSE usando fechas conocidas."""

    def test_festivos_2025_contiene_fechas_correctas(self):
        festivos = festivos_nyse(2025)
        # Festivos confirmados para 2025
        esperados = {
            date(2025, 1, 1),   # New Year's Day (miércoles)
            date(2025, 1, 20),  # MLK Day (3er lunes enero)
            date(2025, 2, 17),  # Presidents Day (3er lunes febrero)
            date(2025, 4, 18),  # Good Friday
            date(2025, 5, 26),  # Memorial Day (último lunes mayo)
            date(2025, 6, 19),  # Juneteenth (jueves)
            date(2025, 7, 4),   # Independence Day (viernes)
            date(2025, 9, 1),   # Labor Day (1er lunes septiembre)
            date(2025, 11, 27), # Thanksgiving (4° jueves noviembre)
            date(2025, 12, 25), # Christmas (jueves)
        }
        for d in esperados:
            assert d in festivos, f"{d} debería ser festivo NYSE 2025"

    def test_festivos_2025_tiene_cantidad_correcta(self):
        # NYSE tiene exactamente 10 festivos en 2025
        assert len(festivos_nyse(2025)) == 10

    def test_juneteenth_no_existe_antes_2022(self):
        festivos_2021 = festivos_nyse(2021)
        assert date(2021, 6, 19) not in festivos_2021

    def test_juneteenth_existe_desde_2022(self):
        festivos_2022 = festivos_nyse(2022)
        # 19 Jun 2022 es domingo → observado el lunes 20
        assert date(2022, 6, 20) in festivos_2022

    def test_new_year_observado_2021(self):
        # 1 Ene 2021 es viernes → no se mueve
        festivos_2021 = festivos_nyse(2021)
        assert date(2021, 1, 1) in festivos_2021

    def test_navidad_observado_sabado(self):
        # 25 Dic 2021 es sábado → observado viernes 24
        festivos_2021 = festivos_nyse(2021)
        assert date(2021, 12, 24) in festivos_2021
        assert date(2021, 12, 25) not in festivos_2021

    def test_independence_day_observado_domingo_2021(self):
        # 4 Jul 2021 es domingo → observado lunes 5
        festivos_2021 = festivos_nyse(2021)
        assert date(2021, 7, 5) in festivos_2021
        assert date(2021, 7, 4) not in festivos_2021


# ---------------------------------------------------------------------------
# Tests: es_dia_habil
# ---------------------------------------------------------------------------

class TestEsDiaHabil:
    def setup_method(self):
        self.g = GestorTiempo()

    def test_lunes_normal_es_habil(self):
        # Lunes 3 Mar 2025, no es festivo
        assert self.g.es_dia_habil("NYSE", date(2025, 3, 3)) is True

    def test_sabado_no_es_habil(self):
        assert self.g.es_dia_habil("NYSE", date(2025, 3, 1)) is False

    def test_domingo_no_es_habil(self):
        assert self.g.es_dia_habil("NYSE", date(2025, 3, 2)) is False

    def test_festivo_no_es_habil(self):
        # MLK Day 2025
        assert self.g.es_dia_habil("NYSE", date(2025, 1, 20)) is False

    def test_dia_antes_de_festivo_es_habil(self):
        # Viernes previo a MLK Day
        assert self.g.es_dia_habil("NYSE", date(2025, 1, 17)) is True

    def test_crypto_domingo_es_habil(self):
        assert self.g.es_dia_habil("CRYPTO", date(2025, 3, 2)) is True

    def test_crypto_navidad_es_habil(self):
        assert self.g.es_dia_habil("CRYPTO", date(2025, 12, 25)) is True

    def test_crypto_sabado_es_habil(self):
        assert self.g.es_dia_habil("CRYPTO", date(2025, 3, 1)) is True

    def test_nasdaq_es_tratado_como_nyse(self):
        # NASDAQ sigue mismo calendario
        assert self.g.es_dia_habil("NASDAQ", date(2025, 1, 20)) is False

    def test_case_insensitive(self):
        assert self.g.es_dia_habil("nasdaq", date(2025, 3, 3)) is True
        assert self.g.es_dia_habil("crypto", date(2025, 3, 2)) is True

    def test_cache_festivos_se_reutiliza(self):
        # Llamar dos veces al mismo año no recalcula
        self.g.es_dia_habil("NYSE", date(2025, 6, 1))
        self.g.es_dia_habil("NYSE", date(2025, 7, 1))
        assert ("NYSE", 2025) in self.g._cache_festivos


# ---------------------------------------------------------------------------
# Tests: siguiente_dia_habil
# ---------------------------------------------------------------------------

class TestSiguienteDiaHabil:
    def setup_method(self):
        self.g = GestorTiempo()

    def test_viernes_siguiente_es_lunes(self):
        # Viernes 28 Feb 2025 → siguiente hábil es lunes 3 Mar
        result = self.g.siguiente_dia_habil(["NYSE"], desde=date(2025, 2, 28))
        assert result == date(2025, 3, 3)

    def test_jueves_antes_de_viernes_festivo(self):
        # Jueves 17 Abr 2025, viernes 18 es Good Friday → lunes 21
        result = self.g.siguiente_dia_habil(["NYSE"], desde=date(2025, 4, 17))
        assert result == date(2025, 4, 21)

    def test_jueves_thanksgiving_siguiente_es_lunes(self):
        # Jueves 27 Nov 2025 (Thanksgiving) es festivo
        # Desde miércoles 26 → jueves es festivo, viernes no es festivo NYSE
        # Viernes 28 Nov es día hábil (Black Friday no es festivo NYSE)
        result = self.g.siguiente_dia_habil(["NYSE"], desde=date(2025, 11, 26))
        assert result == date(2025, 11, 28)

    def test_lunes_siguiente_es_martes(self):
        result = self.g.siguiente_dia_habil(["NYSE"], desde=date(2025, 3, 3))
        assert result == date(2025, 3, 4)

    def test_crypto_siempre_siguiente_dia(self):
        # Crypto: el siguiente día siempre es el inmediato siguiente
        result = self.g.siguiente_dia_habil(["CRYPTO"], desde=date(2025, 3, 1))
        assert result == date(2025, 3, 2)

    def test_multiples_mercados_espera_todos(self):
        # NYSE + CRYPTO: el siguiente día hábil para NYSE desde viernes
        result = self.g.siguiente_dia_habil(["NYSE", "CRYPTO"], desde=date(2025, 2, 28))
        assert result == date(2025, 3, 3)  # Crypto acepta cualquier día, NYSE necesita lunes


# ---------------------------------------------------------------------------
# Tests: dormir_hasta (async, mock de asyncio.sleep)
# ---------------------------------------------------------------------------

class TestDormirHasta:
    def setup_method(self):
        self.g = GestorTiempo(poll_seg=30)

    @pytest.mark.asyncio
    async def test_retorna_inmediatamente_si_objetivo_ya_paso(self):
        objetivo = utc(2025, 3, 3, 10, 0, 0)
        # ahora_utc retorna un momento posterior al objetivo
        self.g.ahora_utc = MagicMock(return_value=utc(2025, 3, 3, 10, 0, 5))

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await self.g.dormir_hasta(objetivo)

        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_retorna_inmediatamente_si_objetivo_es_ahora_exacto(self):
        objetivo = utc(2025, 3, 3, 10, 0, 0)
        self.g.ahora_utc = MagicMock(return_value=objetivo)

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await self.g.dormir_hasta(objetivo)

        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_duerme_tiempo_restante_menor_que_poll(self):
        # Faltan 10 segundos, poll=30 → debe dormir los 10 s exactos
        ahora = utc(2025, 3, 3, 10, 0, 0)
        objetivo = utc(2025, 3, 3, 10, 0, 10)
        llamadas = [ahora, objetivo]  # primera llamada: faltan 10 s; segunda: ya llegó
        self.g.ahora_utc = MagicMock(side_effect=llamadas)

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await self.g.dormir_hasta(objetivo)

        mock_sleep.assert_called_once_with(10.0)

    @pytest.mark.asyncio
    async def test_duerme_en_poll_si_queda_mas_tiempo(self):
        # Faltan 120 s, poll=30 → primer sleep debe ser 30 s
        ahora = utc(2025, 3, 3, 10, 0, 0)
        objetivo = utc(2025, 3, 3, 10, 2, 0)  # 120 segundos después
        # Simular que tras cada sleep el reloj avanza poll segundos
        tick1 = utc(2025, 3, 3, 10, 0, 30)
        tick2 = utc(2025, 3, 3, 10, 1, 0)
        tick3 = utc(2025, 3, 3, 10, 1, 30)
        tick4 = utc(2025, 3, 3, 10, 2, 0)   # igual al objetivo → sale
        self.g.ahora_utc = MagicMock(side_effect=[ahora, tick1, tick2, tick3, tick4])

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await self.g.dormir_hasta(objetivo, poll=30)

        assert mock_sleep.call_count == 4
        # Todos los sleeps deben ser <= 30
        for c in mock_sleep.call_args_list:
            assert c.args[0] <= 30.0

    @pytest.mark.asyncio
    async def test_anti_drift_wakeup_temprano(self):
        """Si asyncio.sleep devuelve el control antes de tiempo (drift),
        el método debe volver a dormir el tiempo restante correcto."""
        ahora = utc(2025, 3, 3, 10, 0, 0)
        objetivo = utc(2025, 3, 3, 10, 0, 30)

        # Simula: ahora=T+0, después del sleep el reloj solo avanzó 5s (drift),
        # en la segunda iteración ya llegó al objetivo
        t_tras_drift = utc(2025, 3, 3, 10, 0, 5)
        t_final = utc(2025, 3, 3, 10, 0, 30)
        self.g.ahora_utc = MagicMock(side_effect=[ahora, t_tras_drift, t_final])

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await self.g.dormir_hasta(objetivo, poll=60)

        # Debe haber dormido dos veces: 30 s la primera, 25 s la segunda (corrigiendo drift)
        assert mock_sleep.call_count == 2
        primer_sleep = mock_sleep.call_args_list[0].args[0]
        segundo_sleep = mock_sleep.call_args_list[1].args[0]
        assert primer_sleep == 30.0
        assert segundo_sleep == 25.0

    @pytest.mark.asyncio
    async def test_poll_personalizado_sobreescribe_defecto(self):
        ahora = utc(2025, 3, 3, 10, 0, 0)
        objetivo = utc(2025, 3, 3, 10, 0, 10)
        self.g.ahora_utc = MagicMock(side_effect=[ahora, objetivo])

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await self.g.dormir_hasta(objetivo, poll=5)

        # Faltan 10 s pero poll=5 → duerme min(5, 10) = 5 s
        mock_sleep.assert_called_once_with(5.0)


# ---------------------------------------------------------------------------
# Tests: dormir_hasta_hora
# ---------------------------------------------------------------------------

class TestDormirHastaHora:
    def setup_method(self):
        self.g = GestorTiempo(poll_seg=30)

    @pytest.mark.asyncio
    async def test_duerme_hasta_hora_futura_mismo_dia(self):
        ahora = utc(2025, 3, 3, 9, 0, 0)
        hora_obj = time(9, 30, 0)
        objetivo_esperado = utc(2025, 3, 3, 9, 30, 0)

        self.g.ahora_utc = MagicMock(side_effect=[ahora, objetivo_esperado])

        # poll grande para que el primer sleep sea el tiempo completo (min(poll, restante))
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await self.g.dormir_hasta_hora(hora_obj, fecha_base=ahora, poll=999999)

        mock_sleep.assert_called_once_with(1800.0)  # 30 minutos

    @pytest.mark.asyncio
    async def test_si_hora_ya_paso_espera_dia_siguiente(self):
        # Son las 10:00 y la hora objetivo es las 09:30 → espera al día siguiente
        ahora = utc(2025, 3, 3, 10, 0, 0)
        hora_obj = time(9, 30, 0)
        # Objetivo: 4 Mar 2025 09:30
        objetivo_esperado = utc(2025, 3, 4, 9, 30, 0)

        self.g.ahora_utc = MagicMock(side_effect=[ahora, objetivo_esperado])

        # poll grande para que el primer sleep sea el tiempo completo
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await self.g.dormir_hasta_hora(hora_obj, fecha_base=ahora, poll=999999)

        # 23h 30min = 84600 segundos
        mock_sleep.assert_called_once_with(84600.0)


# ---------------------------------------------------------------------------
# Tests: calcular_espera_vela
# ---------------------------------------------------------------------------

class TestCalcularEsperaVela:

    def setup_method(self):
        self.g = GestorTiempo()

    def test_alineacion_m5_exacta(self):
        # Son exactamente las 10:00:00 UTC → la siguiente vela M5 cierra a 10:05:00
        # Faltan 300 s + margen
        ahora = utc(2025, 3, 3, 10, 0, 0)
        self.g.ahora_utc = MagicMock(return_value=ahora)
        espera = self.g.calcular_espera_vela(intervalo_seg=300, margen_seg=2)
        assert espera == 302.0

    def test_alineacion_m5_a_mitad_de_vela(self):
        # Son las 10:02:30 → quedan 2:30 (150 s) para cierre + margen
        ahora = utc(2025, 3, 3, 10, 2, 30)
        self.g.ahora_utc = MagicMock(return_value=ahora)
        espera = self.g.calcular_espera_vela(intervalo_seg=300, margen_seg=2)
        assert espera == 152.0  # 150 + 2 margen

    def test_alineacion_m1(self):
        # Son las 10:00:45 → faltan 15 s para el próximo minuto + margen
        ahora = utc(2025, 3, 3, 10, 0, 45)
        self.g.ahora_utc = MagicMock(return_value=ahora)
        espera = self.g.calcular_espera_vela(intervalo_seg=60, margen_seg=0)
        assert espera == 15.0

    def test_alineacion_h1(self):
        # Son las 10:15:00 → faltan 45 min (2700 s) para la hora + margen
        ahora = utc(2025, 3, 3, 10, 15, 0)
        self.g.ahora_utc = MagicMock(return_value=ahora)
        espera = self.g.calcular_espera_vela(intervalo_seg=3600, margen_seg=5)
        assert espera == 2705.0  # 2700 + 5

    def test_margen_cero(self):
        ahora = utc(2025, 3, 3, 10, 0, 30)  # 30 s dentro de vela M5
        self.g.ahora_utc = MagicMock(return_value=ahora)
        espera = self.g.calcular_espera_vela(intervalo_seg=300, margen_seg=0)
        assert espera == 270.0


# ---------------------------------------------------------------------------
# Tests: construir_datetime_utc
# ---------------------------------------------------------------------------

class TestConstruirDatetimeUtc:
    def test_construye_correctamente(self):
        g = GestorTiempo()
        resultado = g.construir_datetime_utc(time(9, 30, 0), fecha=date(2025, 3, 3))
        assert resultado == utc(2025, 3, 3, 9, 30, 0)

    def test_usa_fecha_actual_si_no_se_pasa(self):
        g = GestorTiempo()
        hoy = date(2025, 3, 3)
        g.ahora_utc = MagicMock(return_value=utc(2025, 3, 3, 8, 0, 0))
        resultado = g.construir_datetime_utc(time(14, 0, 0))
        assert resultado.date() == hoy
        assert resultado.hour == 14
