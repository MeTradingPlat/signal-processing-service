"""Tests para FundamentalsCache.

Verifica: refresh, acceso thread-safe, condición de "ya refrescado",
merge de fundamentales + volúmenes extendidos, mercados sin fundamentales.
"""
import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.fundamentals_cache import FundamentalsCache


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _cache_con_datos(data: dict) -> FundamentalsCache:
    cache = FundamentalsCache()
    cache._cache = data
    cache._ultima_fecha_refresh = date.today()
    return cache


# ──────────────────────────────────────────────────────────────────────────────
# Tests básicos
# ──────────────────────────────────────────────────────────────────────────────

class TestFundamentalsCacheBasico:

    def test_obtener_retorna_dict_vacio_si_no_hay_datos(self):
        cache = FundamentalsCache()
        assert cache.obtener("AAPL") == {}

    def test_obtener_retorna_copia_no_referencia(self):
        cache = _cache_con_datos({"AAPL": {"market_cap": 3e12}})
        datos = cache.obtener("AAPL")
        datos["market_cap"] = 0  # modificar la copia
        assert cache.obtener("AAPL")["market_cap"] == 3e12  # caché intacto

    def test_necesita_refresh_si_nunca_refrescado(self):
        cache = FundamentalsCache()
        assert cache.necesita_refresh() is True

    def test_no_necesita_refresh_si_ya_refrescado_hoy(self):
        cache = FundamentalsCache()
        cache._ultima_fecha_refresh = date.today()
        assert cache.necesita_refresh() is False

    def test_necesita_refresh_si_fue_ayer(self):
        from datetime import timedelta
        cache = FundamentalsCache()
        cache._ultima_fecha_refresh = date.today() - timedelta(days=1)
        assert cache.necesita_refresh() is True

    def test_total_simbolos(self):
        cache = _cache_con_datos({"AAPL": {"market_cap": 1}, "MSFT": {"market_cap": 2}})
        assert cache.total_simbolos() == 2

    def test_limpiar_resetea_cache(self):
        cache = _cache_con_datos({"AAPL": {"market_cap": 1}})
        cache.limpiar()
        assert cache.obtener("AAPL") == {}
        assert cache.necesita_refresh() is True


# ──────────────────────────────────────────────────────────────────────────────
# Tests de refresh
# ──────────────────────────────────────────────────────────────────────────────

class TestFundamentalsCacheRefresh:

    @pytest.mark.asyncio
    async def test_refresh_popula_cache(self):
        cache = FundamentalsCache()

        fund_data = {"AAPL": {"float_shares": 15e9, "market_cap": 3e12}}
        vol_data  = {"AAPL": {"pre_market_volume": 500_000, "post_market_volume": 200_000}}

        with patch("app.adapters.fundamentals_adapter.obtener_fundamentales_batch",
                   new_callable=AsyncMock, return_value=fund_data), \
             patch("app.adapters.fundamentals_adapter.obtener_volumen_extendido_batch",
                   new_callable=AsyncMock, return_value=vol_data):
            await cache.refrescar(["AAPL"], "NYSE")

        datos = cache.obtener("AAPL")
        assert datos["float_shares"] == 15e9
        assert datos["market_cap"] == 3e12
        assert datos["pre_market_volume"] == 500_000
        assert datos["post_market_volume"] == 200_000

    @pytest.mark.asyncio
    async def test_refresh_merge_funda_y_volumen(self):
        cache = FundamentalsCache()
        fund = {"SYM": {"market_cap": 1e9}}
        vol  = {"SYM": {"pre_market_volume": 100_000}}

        with patch("app.adapters.fundamentals_adapter.obtener_fundamentales_batch",
                   new_callable=AsyncMock, return_value=fund), \
             patch("app.adapters.fundamentals_adapter.obtener_volumen_extendido_batch",
                   new_callable=AsyncMock, return_value=vol):
            await cache.refrescar(["SYM"], "NASDAQ")

        datos = cache.obtener("SYM")
        assert datos["market_cap"] == 1e9
        assert datos["pre_market_volume"] == 100_000

    @pytest.mark.asyncio
    async def test_refresh_skip_si_ya_refrescado_hoy(self):
        cache = FundamentalsCache()
        cache._ultima_fecha_refresh = date.today()

        with patch("app.adapters.fundamentals_adapter.obtener_fundamentales_batch", new_callable=AsyncMock) as mock_f, \
             patch("app.adapters.fundamentals_adapter.obtener_volumen_extendido_batch", new_callable=AsyncMock) as mock_v:
            await cache.refrescar(["AAPL"], "NYSE")
            mock_f.assert_not_called()
            mock_v.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_forzar_ejecuta_aunque_ya_refrescado(self):
        cache = FundamentalsCache()
        cache._ultima_fecha_refresh = date.today()

        with patch("app.adapters.fundamentals_adapter.obtener_fundamentales_batch",
                   new_callable=AsyncMock, return_value={}), \
             patch("app.adapters.fundamentals_adapter.obtener_volumen_extendido_batch",
                   new_callable=AsyncMock, return_value={}) as mock_v:
            await cache.refrescar(["AAPL"], "NYSE", forzar=True)
            mock_v.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_refresh_skip_para_crypto(self):
        cache = FundamentalsCache()
        with patch("app.adapters.fundamentals_adapter.obtener_fundamentales_batch", new_callable=AsyncMock) as mock_f:
            await cache.refrescar(["BTC-USD"], "CRYPTO")
            mock_f.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_skip_para_forex(self):
        cache = FundamentalsCache()
        with patch("app.adapters.fundamentals_adapter.obtener_fundamentales_batch", new_callable=AsyncMock) as mock_f:
            await cache.refrescar(["EURUSD"], "FOREX")
            mock_f.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_skip_lista_vacia(self):
        cache = FundamentalsCache()
        with patch("app.adapters.fundamentals_adapter.obtener_fundamentales_batch", new_callable=AsyncMock) as mock_f:
            await cache.refrescar([], "NYSE")
            mock_f.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_simbolo_sin_datos_no_entra_al_cache(self):
        """Símbolo con dict vacío no debe sobrescribir entradas anteriores."""
        cache = FundamentalsCache()
        # Pre-popular con datos
        cache._cache["AAPL"] = {"market_cap": 3e12}
        cache._ultima_fecha_refresh = None  # forzar refresh

        with patch("app.adapters.fundamentals_adapter.obtener_fundamentales_batch",
                   new_callable=AsyncMock, return_value={"AAPL": {}}), \
             patch("app.adapters.fundamentals_adapter.obtener_volumen_extendido_batch",
                   new_callable=AsyncMock, return_value={}):
            await cache.refrescar(["AAPL"], "NYSE")

        # Dict vacío no sobreescribe
        assert cache.obtener("AAPL").get("market_cap") == 3e12

    @pytest.mark.asyncio
    async def test_refresh_multiples_simbolos(self):
        cache = FundamentalsCache()
        simbolos = [f"SYM{i}" for i in range(50)]
        fund = {s: {"market_cap": i * 1e9} for i, s in enumerate(simbolos)}

        with patch("app.adapters.fundamentals_adapter.obtener_fundamentales_batch",
                   new_callable=AsyncMock, return_value=fund), \
             patch("app.adapters.fundamentals_adapter.obtener_volumen_extendido_batch",
                   new_callable=AsyncMock, return_value={}):
            await cache.refrescar(simbolos, "NYSE")

        assert cache.total_simbolos() == 50
        assert cache.obtener("SYM5")["market_cap"] == 5e9
