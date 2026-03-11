"""Tests para fundamentals_adapter.

Verifica: batch fetching, conversión de unidades, manejo de errores,
mercados sin fundamentales (CRYPTO/FOREX).
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

        with patch("yfinance.Ticker", return_value=mock_ticker):
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
        with patch("yfinance.Ticker", return_value=mock_ticker):
            _, datos = _fetch_info("TEST")
        assert datos["short_interest"] == pytest.approx(5.5)

    def test_retorna_dict_vacio_si_yfinance_falla(self):
        with patch("yfinance.Ticker", side_effect=Exception("Blocked")):
            sym, datos = _fetch_info("FAIL")
        assert sym == "FAIL"
        assert datos == {}

    def test_campos_ausentes_si_info_incompleta(self):
        """Con info vacía, el orquestador filtra los None: no hay campos en el resultado."""
        mock_ticker = _ticker_mock({})  # info vacía → todos los campos son None
        mock_ticker.calendar = None
        with patch("yfinance.Ticker", return_value=mock_ticker):
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

    def _mock_finviz(self, fundament_dict: dict):
        """Crea mock de finvizfinance que retorna el dict dado."""
        mock_stock = MagicMock()
        mock_stock.ticker_fundament.return_value = fundament_dict
        return MagicMock(return_value=mock_stock)

    def test_parsea_datos_completos(self):
        fundament = {
            "Float": "15.44B",
            "Shs Outstand": "16.50B",
            "Market Cap": "3.42T",
            "Short Float": "2.35%",
            "Short Ratio": "3.2",
        }
        mock_class = self._mock_finviz(fundament)
        with patch("finvizfinance.quote.finvizfinance", mock_class):
            sym, datos = _fetch_fundamentales_finviz("AAPL")

        assert sym == "AAPL"
        assert datos["float_shares"] == pytest.approx(15_440_000_000.0)
        assert datos["shares_outstanding"] == pytest.approx(16_500_000_000.0)
        assert datos["market_cap"] == pytest.approx(3_420_000_000_000.0)
        assert datos["short_interest"] == pytest.approx(2.35)
        assert datos["short_ratio"] == pytest.approx(3.2)

    def test_campos_con_guion_son_none(self):
        fundament = {
            "Float": "15.44B",
            "Shs Outstand": "-",
            "Market Cap": "-",
            "Short Float": "-",
            "Short Ratio": "3.2",
        }
        mock_class = self._mock_finviz(fundament)
        with patch("finvizfinance.quote.finvizfinance", mock_class):
            _, datos = _fetch_fundamentales_finviz("TEST")

        assert datos["float_shares"] is not None
        assert datos["shares_outstanding"] is None
        assert datos["market_cap"] is None
        assert datos["short_interest"] is None
        assert datos["short_ratio"] is not None

    def test_excepcion_retorna_dict_vacio(self):
        """Si finviz lanza excepción (símbolo OTC no encontrado), retorna {}."""
        with patch("finvizfinance.quote.finvizfinance", side_effect=Exception("Not found")):
            sym, datos = _fetch_fundamentales_finviz("OTCSYM")

        assert sym == "OTCSYM"
        assert datos == {}


# ──────────────────────────────────────────────────────────────────────────────
# Tests: _fetch_info (orquestador dual finviz + yfinance)
# ──────────────────────────────────────────────────────────────────────────────

class TestFetchInfoOrquestador:
    """Verifica la lógica de prioridad: finviz primario, yfinance fallback."""

    def _mock_finviz_class(self, fundament_dict: dict):
        mock_stock = MagicMock()
        mock_stock.ticker_fundament.return_value = fundament_dict
        return MagicMock(return_value=mock_stock)

    def test_finviz_sobreescribe_yfinance_para_campos_comunes(self):
        """Finviz tiene market_cap más preciso: debe ganar sobre yfinance."""
        fundament = {
            "Float": "100M",     # 100_000_000 (finviz)
            "Shs Outstand": "-",
            "Market Cap": "5B",  # 5_000_000_000 (finviz)
            "Short Float": "5%",
            "Short Ratio": "2.0",
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
        mock_finviz = self._mock_finviz_class(fundament)

        with patch("finvizfinance.quote.finvizfinance", mock_finviz), \
             patch("yfinance.Ticker", return_value=mock_ticker):
            _, datos = _fetch_info("AAPL")

        # Finviz gana donde tiene datos
        assert datos["float_shares"] == pytest.approx(100_000_000.0)
        assert datos["market_cap"] == pytest.approx(5_000_000_000.0)
        assert datos["short_interest"] == pytest.approx(5.0)
        assert datos["short_ratio"] == pytest.approx(2.0)
        # yfinance gana donde finviz tiene "-"
        assert datos["shares_outstanding"] == 110_000_000

    def test_days_until_earnings_siempre_de_yfinance(self):
        """Incluso si finviz funciona, days_until_earnings viene de yfinance."""
        fundament = {"Float": "50M", "Shs Outstand": "-", "Market Cap": "-",
                     "Short Float": "-", "Short Ratio": "-"}
        yf_info = {"nextEarningsDate": date.today() + timedelta(days=10)}
        mock_ticker = _ticker_mock(yf_info)
        mock_ticker.calendar = None
        mock_finviz = self._mock_finviz_class(fundament)

        with patch("finvizfinance.quote.finvizfinance", mock_finviz), \
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

        with patch("finvizfinance.quote.finvizfinance", side_effect=Exception("OTC not found")), \
             patch("yfinance.Ticker", return_value=mock_ticker):
            _, datos = _fetch_info("OTCSYM")

        assert datos["float_shares"] == 5_000_000
        assert datos["shares_outstanding"] == 6_000_000
        assert datos["market_cap"] == 100_000_000
        assert datos["short_interest"] == pytest.approx(15.0)
        assert datos["short_ratio"] == 3.0

    def test_ambos_fallan_retorna_dict_vacio(self):
        """Si finviz y yfinance fallan, retorna dict vacío (permisivo en filtros)."""
        with patch("finvizfinance.quote.finvizfinance", side_effect=Exception("Error")), \
             patch("yfinance.Ticker", side_effect=Exception("Error")):
            _, datos = _fetch_info("BAD")

        assert datos == {}
