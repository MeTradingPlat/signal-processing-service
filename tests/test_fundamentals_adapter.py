"""Tests para fundamentals_adapter.

Verifica: batch fetching, conversión de unidades, manejo de errores,
mercados sin fundamentales (CRYPTO/FOREX), normalización de símbolos,
reintentos ante rate-limit y sesión cacheada.
"""
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.fundamentals_adapter import (
    obtener_fundamentales_batch,
    obtener_volumen_extendido_batch,
    _fetch_info,
    _fetch_info_yfinance,
    _fetch_fundamentales_finviz,
    _calcular_dias_earnings,
    _parse_finviz_numero,
    _parse_finviz_porcentaje,
    _normalizar_simbolo_yahoo,
    _ejecutar_con_reintento,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers para crear mocks de yfinance
# ──────────────────────────────────────────────────────────────────────────────

def _ticker_mock(info: dict, calendar=None, earnings_dates=None):
    ticker = MagicMock()
    ticker.info = info
    ticker.calendar = calendar
    try:
        ticker.earnings_dates = earnings_dates
    except Exception:
        pass
    return ticker


# ──────────────────────────────────────────────────────────────────────────────
# Tests: _calcular_dias_earnings
# ──────────────────────────────────────────────────────────────────────────────

class TestCalcularDiasEarnings:

    def test_retorna_dias_desde_info_nextEarningsDate(self):
        hoy = date.today()
        en_15_dias = hoy + timedelta(days=15)
        ticker = _ticker_mock({"nextEarningsDate": en_15_dias})
        resultado = _calcular_dias_earnings(ticker, ticker.info)
        assert resultado == 15

    def test_retorna_none_si_fecha_pasada(self):
        ayer = date.today() - timedelta(days=1)
        ticker = _ticker_mock({"nextEarningsDate": ayer})
        resultado = _calcular_dias_earnings(ticker, ticker.info)
        assert resultado is None

    def test_retorna_dias_desde_calendar_dict(self):
        hoy = date.today()
        en_20 = datetime(hoy.year, hoy.month, hoy.day) + timedelta(days=20)
        cal_dict = {"Earnings Date": [en_20]}
        ticker = _ticker_mock({}, calendar=cal_dict)
        resultado = _calcular_dias_earnings(ticker, {})
        assert resultado == 20

    def test_retorna_none_si_no_hay_fecha(self):
        ticker = _ticker_mock({})
        ticker.calendar = None
        ticker.earnings_dates = None
        resultado = _calcular_dias_earnings(ticker, {})
        assert resultado is None

    def test_maneja_excepcion_en_calendar(self):
        ticker = _ticker_mock({})
        ticker.calendar = MagicMock(side_effect=Exception("API error"))
        # No debe lanzar
        resultado = _calcular_dias_earnings(ticker, {})
        assert resultado is None


# ──────────────────────────────────────────────────────────────────────────────
# Tests: _fetch_info
# ──────────────────────────────────────────────────────────────────────────────

class TestFetchInfo:
    """Aisla completamente ambas fuentes (finviz + yfinance) para que los tests
    no dependan de la red ni de si finvizfinance está instalado."""

    def test_retorna_fundamentales_basicos(self):
        hoy = date.today()
        info = {
            "floatShares": 15_000_000,
            "sharesOutstanding": 16_500_000,
            "marketCap": 3_000_000_000,
            "shortPercentOfFloat": 0.10,  # 10%
            "shortRatio": 2.5,
            "nextEarningsDate": hoy + timedelta(days=30),
        }
        mock_ticker = _ticker_mock(info)
        mock_ticker.calendar = None

        with patch("app.adapters.fundamentals_adapter._fetch_fundamentales_finviz", return_value=("AAPL", {})), \
             patch("yfinance.Ticker", return_value=mock_ticker):
            sym, datos = _fetch_info("AAPL")

        assert sym == "AAPL"
        assert datos["float_shares"] == 15_000_000
        assert datos["shares_outstanding"] == 16_500_000
        assert datos["market_cap"] == 3_000_000_000
        assert datos["short_interest"] == pytest.approx(10.0)  # 0.10 * 100
        assert datos["short_ratio"] == 2.5
        assert datos["days_until_earnings"] == 30

    def test_short_interest_convertido_a_porcentaje(self):
        """short_interest debe ser % (5.5%), no decimal (0.055)."""
        info = {"shortPercentOfFloat": 0.055}
        mock_ticker = _ticker_mock(info)
        mock_ticker.calendar = None
        with patch("app.adapters.fundamentals_adapter._fetch_fundamentales_finviz", return_value=("TEST", {})), \
             patch("yfinance.Ticker", return_value=mock_ticker):
            _, datos = _fetch_info("TEST")
        assert datos["short_interest"] == pytest.approx(5.5)

    def test_retorna_dict_vacio_si_ambas_fuentes_fallan(self):
        """Si yfinance falla y finviz no tiene datos, retorna dict vacío."""
        with patch("app.adapters.fundamentals_adapter._fetch_fundamentales_finviz", return_value=("FAIL", {})), \
             patch("yfinance.Ticker", side_effect=Exception("Blocked")):
            sym, datos = _fetch_info("FAIL")
        assert sym == "FAIL"
        assert datos == {}

    def test_campos_ausentes_si_info_incompleta(self):
        """Con info vacía y finviz sin datos, el orquestador retorna dict vacío."""
        mock_ticker = _ticker_mock({})  # info vacía → todos los campos son None
        mock_ticker.calendar = None
        with patch("app.adapters.fundamentals_adapter._fetch_fundamentales_finviz", return_value=("EMPTY", {})), \
             patch("yfinance.Ticker", return_value=mock_ticker):
            _, datos = _fetch_info("EMPTY")
        # El orquestador filtra valores None, así que el dict queda vacío
        assert datos == {}


# ──────────────────────────────────────────────────────────────────────────────
# Tests: obtener_fundamentales_batch
# ──────────────────────────────────────────────────────────────────────────────

class TestObtenerFundamentalesBatch:

    def test_retorna_dict_vacio_para_crypto(self):
        resultado = obtener_fundamentales_batch(["BTC-USD"], "CRYPTO")
        assert resultado == {}

    def test_retorna_dict_vacio_para_forex(self):
        resultado = obtener_fundamentales_batch(["EURUSD"], "FOREX")
        assert resultado == {}

    def test_retorna_dict_vacio_si_lista_vacia(self):
        resultado = obtener_fundamentales_batch([], "NYSE")
        assert resultado == {}

    def test_batch_multiples_simbolos(self):
        """Verifica que se procesan múltiples símbolos."""
        info = {"marketCap": 1e9, "floatShares": 1e6}
        mock_ticker = _ticker_mock(info)
        mock_ticker.calendar = None

        with patch("yfinance.Ticker", return_value=mock_ticker):
            resultado = obtener_fundamentales_batch(["AAPL", "MSFT", "GOOGL"], "NYSE")

        assert "AAPL" in resultado
        assert "MSFT" in resultado
        assert "GOOGL" in resultado

    def test_simbolo_con_error_retorna_dict_vacio(self):
        """Si un símbolo falla, el resto sigue procesándose."""
        def ticker_factory(sym):
            if sym == "FAIL":
                t = MagicMock()
                t.info = MagicMock(side_effect=Exception("Error"))
                return t
            t = _ticker_mock({"marketCap": 1e9})
            t.calendar = None
            return t

        with patch("yfinance.Ticker", side_effect=ticker_factory):
            resultado = obtener_fundamentales_batch(["OK", "FAIL"], "NYSE", max_workers=2)

        assert "OK" in resultado
        assert "FAIL" in resultado
        # FAIL puede retornar dict vacío
        assert resultado["FAIL"] == {} or isinstance(resultado["FAIL"], dict)


# ──────────────────────────────────────────────────────────────────────────────
# Tests: obtener_volumen_extendido_batch
# ──────────────────────────────────────────────────────────────────────────────

class TestObtenerVolumenExtendidoBatch:

    def test_retorna_vacio_para_crypto(self):
        resultado = obtener_volumen_extendido_batch(["BTC"], "CRYPTO")
        assert resultado == {}

    def test_retorna_vacio_lista_vacia(self):
        resultado = obtener_volumen_extendido_batch([], "NYSE")
        assert resultado == {}

    def test_error_en_download_retorna_vacio(self):
        with patch("yfinance.download", side_effect=Exception("Timeout")):
            resultado = obtener_volumen_extendido_batch(["AAPL"], "NYSE", max_workers=1)
        assert resultado.get("AAPL", {}) == {}

    def test_columnas_multiindex_son_aplanadas(self):
        """yfinance >= 0.2.36 retorna columnas MultiIndex para un solo ticker.
        El adaptador debe aplanarlas para poder acceder a 'Volume' como Series."""
        import pandas as pd

        # Simular DataFrame con MultiIndex como retorna yfinance nuevo
        idx = pd.date_range(
            "2024-01-15 04:00", periods=6, freq="1min",
            tz="America/New_York",
        )
        cols = pd.MultiIndex.from_tuples([("Open", "AAPL"), ("Volume", "AAPL")])
        # 2 barras pre-market (04:00–09:30), 2 durante sesión, 2 post-market (>= 16:00)
        # pre_vol = 1000 + 2000 = 3000 | post_vol = 0 (ninguna barra >= 16:00 en idx)
        data = [
            [100, 1_000],
            [101, 2_000],
            [102, 3_000],
            [103, 4_000],
            [104, 5_000],
            [105, 6_000],
        ]
        df_multi = pd.DataFrame(data, index=idx, columns=cols)

        with patch("yfinance.download", return_value=df_multi):
            resultado = obtener_volumen_extendido_batch(["AAPL"], "NYSE", max_workers=1)

        assert "AAPL" in resultado
        datos = resultado["AAPL"]
        # Debe retornar enteros, no lanzar TypeError
        assert isinstance(datos.get("pre_market_volume"), int)
        assert isinstance(datos.get("post_market_volume"), int)


# ──────────────────────────────────────────────────────────────────────────────
# Tests: _parse_finviz_numero
# ──────────────────────────────────────────────────────────────────────────────

class TestParseFinvizNumero:

    def test_parsea_billones(self):
        assert _parse_finviz_numero("15.44B") == pytest.approx(15_440_000_000.0)

    def test_parsea_trillones(self):
        assert _parse_finviz_numero("3.42T") == pytest.approx(3_420_000_000_000.0)

    def test_parsea_millones(self):
        assert _parse_finviz_numero("500M") == pytest.approx(500_000_000.0)

    def test_parsea_miles(self):
        assert _parse_finviz_numero("2.5K") == pytest.approx(2_500.0)

    def test_parsea_sin_sufijo(self):
        assert _parse_finviz_numero("3.2") == pytest.approx(3.2)

    def test_parsea_con_comas(self):
        assert _parse_finviz_numero("1,500.5") == pytest.approx(1500.5)

    def test_guion_retorna_none(self):
        assert _parse_finviz_numero("-") is None

    def test_na_retorna_none(self):
        assert _parse_finviz_numero("N/A") is None

    def test_vacio_retorna_none(self):
        assert _parse_finviz_numero("") is None

    def test_none_retorna_none(self):
        assert _parse_finviz_numero(None) is None

    def test_invalido_retorna_none(self):
        assert _parse_finviz_numero("abc") is None


# ──────────────────────────────────────────────────────────────────────────────
# Tests: _parse_finviz_porcentaje
# ──────────────────────────────────────────────────────────────────────────────

class TestParseFinvizPorcentaje:

    def test_parsea_porcentaje_con_simbolo(self):
        assert _parse_finviz_porcentaje("2.35%") == pytest.approx(2.35)

    def test_parsea_porcentaje_entero(self):
        assert _parse_finviz_porcentaje("15%") == pytest.approx(15.0)

    def test_parsea_sin_simbolo(self):
        assert _parse_finviz_porcentaje("10.5") == pytest.approx(10.5)

    def test_guion_retorna_none(self):
        assert _parse_finviz_porcentaje("-") is None

    def test_na_retorna_none(self):
        assert _parse_finviz_porcentaje("N/A") is None

    def test_vacio_retorna_none(self):
        assert _parse_finviz_porcentaje("") is None

    def test_none_retorna_none(self):
        assert _parse_finviz_porcentaje(None) is None


# ──────────────────────────────────────────────────────────────────────────────
# Tests: _fetch_fundamentales_finviz
# ──────────────────────────────────────────────────────────────────────────────

class TestFetchFundamentalesFinviz:

    def _mock_httpx(self, html_content: str, status_code: int = 200):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.text = html_content
        
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.get.return_value = mock_resp
        return mock_client

    def test_parsea_datos_completos(self):
        html = """
        <html><table class="snapshot-table2">
            <tr>
                <td>Shs Float</td><td>15.44B</td>
                <td>Shs Outstand</td><td>16.50B</td>
            </tr>
            <tr>
                <td>Market Cap</td><td>3.42T</td>
                <td>Short Float</td><td>2.35%</td>
            </tr>
            <tr>
                <td>Short Ratio</td><td>3.2</td>
                <td>Rel Volume</td><td>1.5</td>
            </tr>
        </table></html>
        """
        mock_client = self._mock_httpx(html)
        with patch("httpx.Client", return_value=mock_client), patch("time.sleep"):
            sym, datos = _fetch_fundamentales_finviz("AAPL")

        assert sym == "AAPL"
        assert datos["float_shares"] == pytest.approx(15_440_000_000.0)
        assert datos["shares_outstanding"] == pytest.approx(16_500_000_000.0)
        assert datos["market_cap"] == pytest.approx(3_420_000_000_000.0)
        assert datos["short_interest"] == pytest.approx(2.35)
        assert datos["short_ratio"] == pytest.approx(3.2)

    def test_campos_con_guion_son_none(self):
        html = """
        <html><table class="snapshot-table2">
            <tr>
                <td>Shs Float</td><td>15.44B</td>
                <td>Shs Outstand</td><td>-</td>
            </tr>
            <tr>
                <td>Market Cap</td><td>-</td>
                <td>Short Float</td><td>-</td>
            </tr>
            <tr>
                <td>Short Ratio</td><td>3.2</td>
                <td>Rel Volume</td><td>1.5</td>
            </tr>
        </table></html>
        """
        mock_client = self._mock_httpx(html)
        with patch("httpx.Client", return_value=mock_client), patch("time.sleep"):
            _, datos = _fetch_fundamentales_finviz("TEST")

        assert datos["float_shares"] is not None
        assert datos.get("shares_outstanding") is None
        assert datos.get("market_cap") is None
        assert datos.get("short_interest") is None
        assert datos["short_ratio"] is not None

    def test_excepcion_retorna_dict_vacio(self):
        """Si finviz lanza excepción (símbolo OTC no encontrado o 404), retorna {}."""
        mock_client = self._mock_httpx("", 404)
        with patch("httpx.Client", return_value=mock_client), patch("time.sleep"):
            sym, datos = _fetch_fundamentales_finviz("OTCSYM")

        assert sym == "OTCSYM"
        assert datos == {}


# ──────────────────────────────────────────────────────────────────────────────
# Tests: _fetch_info (orquestador dual finviz + yfinance)
# ──────────────────────────────────────────────────────────────────────────────

class TestFetchInfoOrquestador:
    """Verifica la lógica de prioridad: finviz primario, yfinance fallback."""

    def test_finviz_sobreescribe_yfinance_para_campos_comunes(self):
        """Finviz tiene market_cap más preciso: debe ganar sobre yfinance."""
        finviz_data = {
            "float_shares": 100_000_000.0,
            "market_cap": 5_000_000_000.0,
            "short_interest": 5.0,
            "short_ratio": 2.0,
        }
        yf_info = {
            "floatShares": 90_000_000,      # yfinance (menos preciso)
            "sharesOutstanding": 110_000_000,
            "marketCap": 4_500_000_000,     # yfinance (menos preciso)
            "shortPercentOfFloat": 0.04,    # 4%
            "shortRatio": 1.5,
        }
        mock_ticker = _ticker_mock(yf_info)
        mock_ticker.calendar = None

        with patch("app.adapters.fundamentals_adapter._fetch_fundamentales_finviz", return_value=("AAPL", finviz_data)), \
             patch("yfinance.Ticker", return_value=mock_ticker):
            _, datos = _fetch_info("AAPL")

        # Finviz gana donde tiene datos
        assert datos["float_shares"] == pytest.approx(100_000_000.0)
        assert datos["market_cap"] == pytest.approx(5_000_000_000.0)
        assert datos["short_interest"] == pytest.approx(5.0)
        assert datos["short_ratio"] == pytest.approx(2.0)
        # yfinance gana donde finviz no devolvió data (ej. outstanding)
        assert datos["shares_outstanding"] == 110_000_000

    def test_days_until_earnings_siempre_de_yfinance(self):
        """Incluso si finviz funciona, days_until_earnings viene de yfinance."""
        finviz_data = {"float_shares": 50_000_000.0}
        yf_info = {"nextEarningsDate": date.today() + timedelta(days=10)}
        mock_ticker = _ticker_mock(yf_info)
        mock_ticker.calendar = None

        with patch("app.adapters.fundamentals_adapter._fetch_fundamentales_finviz", return_value=("AAPL", finviz_data)), \
             patch("yfinance.Ticker", return_value=mock_ticker):
            _, datos = _fetch_info("AAPL")

        assert datos["days_until_earnings"] == 10

    def test_finviz_falla_yfinance_es_fallback_completo(self):
        """Si finviz falla (OTC sin cobertura), yfinance provee todo."""
        yf_info = {
            "floatShares": 5_000_000,
            "sharesOutstanding": 6_000_000,
            "marketCap": 100_000_000,
            "shortPercentOfFloat": 0.15,
            "shortRatio": 3.0,
        }
        mock_ticker = _ticker_mock(yf_info)
        mock_ticker.calendar = None

        with patch("app.adapters.fundamentals_adapter._fetch_fundamentales_finviz", return_value=("OTCSYM", {})), \
             patch("yfinance.Ticker", return_value=mock_ticker):
            _, datos = _fetch_info("OTCSYM")

        assert datos["float_shares"] == 5_000_000
        assert datos["shares_outstanding"] == 6_000_000
        assert datos["market_cap"] == 100_000_000
        assert datos["short_interest"] == pytest.approx(15.0)
        assert datos["short_ratio"] == 3.0

    def test_ambos_fallan_retorna_dict_vacio(self):
        """Si finviz y yfinance fallan, retorna dict vacío (permisivo en filtros)."""
        with patch("app.adapters.fundamentals_adapter._fetch_fundamentales_finviz", return_value=("BAD", {})), \
             patch("yfinance.Ticker", side_effect=Exception("Error")):
            _, datos = _fetch_info("BAD")

        assert datos == {}


# ──────────────────────────────────────────────────────────────────────────────
# Tests: _normalizar_simbolo_yahoo (Anti-ban: '/' → '-')
# ──────────────────────────────────────────────────────────────────────────────

class TestNormalizarSimboloYahoo:
    """Yahoo Finance usa '-' como separador de clase, no '/'."""

    def test_convierte_barra_a_guion(self):
        assert _normalizar_simbolo_yahoo("AKO/A")  == "AKO-A"
        assert _normalizar_simbolo_yahoo("UHAL/B") == "UHAL-B"
        # Units: /U y -U siempre se convierten a -UN (convención Yahoo Finance)
        assert _normalizar_simbolo_yahoo("FTW/U")  == "FTW-UN"
        assert _normalizar_simbolo_yahoo("MTAL/U") == "MTAL-UN"

    def test_simbolo_normal_no_cambia(self):
        assert _normalizar_simbolo_yahoo("AAPL")  == "AAPL"
        assert _normalizar_simbolo_yahoo("MSFT")  == "MSFT"
        assert _normalizar_simbolo_yahoo("BTC-USD") == "BTC-USD"

    def test_simbolo_yfinance_usa_simbolo_normalizado(self):
        """_fetch_info_yfinance debe llamar a yf.Ticker con el símbolo normalizado."""
        mock_ticker = MagicMock()
        mock_ticker.info = {}
        mock_ticker.calendar = None

        with patch("yfinance.Ticker", return_value=mock_ticker) as mock_yf:
            _fetch_info_yfinance("AKO/A")

        # yfinance debe recibir "AKO-A", no "AKO/A"
        llamado_con = mock_yf.call_args[0][0]
        assert llamado_con == "AKO-A"


# ──────────────────────────────────────────────────────────────────────────────
# Tests: _ejecutar_con_reintento (Anti-ban: backoff exponencial)
# ──────────────────────────────────────────────────────────────────────────────

class TestEjecutarConReintento:
    """Verifica la lógica de reintentos ante rate-limit de Yahoo."""

    def test_exito_a_la_primera_no_reintenta(self):
        llamadas = []
        def fn():
            llamadas.append(1)
            return "ok"

        resultado = _ejecutar_con_reintento(fn)
        assert resultado == "ok"
        assert len(llamadas) == 1

    def test_reintenta_ante_error_401(self):
        """Debe reintentar hasta 3 veces ante errores de rate-limit."""
        intentos = []

        def fn():
            intentos.append(1)
            if len(intentos) < 3:
                raise Exception("HTTP 401 Unauthorized: Invalid Crumb")
            return "ok_en_3er_intento"

        with patch("time.sleep"):   # evitar esperar en tests
            resultado = _ejecutar_con_reintento(fn)

        assert resultado == "ok_en_3er_intento"
        assert len(intentos) == 3

    def test_reintenta_ante_error_429(self):
        intentos = []

        def fn():
            intentos.append(1)
            if len(intentos) < 2:
                raise Exception("HTTP 429 Too Many Requests")
            return "ok"

        with patch("time.sleep"):
            resultado = _ejecutar_con_reintento(fn)

        assert resultado == "ok"
        assert len(intentos) == 2

    def test_no_reintenta_errores_distintos_a_rate_limit(self):
        """Errores como 404 o de red no deben reintentarse."""
        intentos = []

        def fn():
            intentos.append(1)
            raise ValueError("Symbol not found")

        with pytest.raises(ValueError):
            _ejecutar_con_reintento(fn)

        assert len(intentos) == 1   # no reintentó

    def test_agota_reintentos_y_propaga_excepcion(self):
        """Si los 3 intentos fallan por rate-limit, propaga la excepción."""
        def fn():
            raise Exception("401 Invalid Crumb")

        with patch("time.sleep"), pytest.raises(Exception, match="401"):
            _ejecutar_con_reintento(fn)

    def test_pausa_entre_reintentos(self):
        """Verifica que se llama a time.sleep con backoff exponencial."""
        intentos = []

        def fn():
            intentos.append(1)
            if len(intentos) < 3:
                raise Exception("401 Unauthorized")
            return "ok"

        with patch("time.sleep") as mock_sleep:
            _ejecutar_con_reintento(fn)

        pausas = [call.args[0] for call in mock_sleep.call_args_list]
        assert pausas[0] == pytest.approx(2.0)   # 2s primer reintento
        assert pausas[1] == pytest.approx(4.0)   # 4s segundo reintento
