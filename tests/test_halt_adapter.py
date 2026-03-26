"""Tests para halt_adapter.obtener_simbolos_halted."""
import io
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.halt_adapter import obtener_simbolos_halted


# CSV simulando el formato pipe-delimited de NASDAQ
_CSV_CON_HALTS_ACTIVOS = """\
Symbol|HaltDate|HaltTime|ReasonCode|ResumptionDate|ResumptionQuoteTime|ResumptionTradeTime
MULN|20250310|09:30:00|T1|20250310|09:45:00|
ILUS|20250310|10:00:00|T12|||
AAPL|20250310|11:00:00|T1|20250310|11:15:00|11:16:00
"""

_CSV_TODOS_REANUDADOS = """\
Symbol|HaltDate|HaltTime|ReasonCode|ResumptionDate|ResumptionQuoteTime|ResumptionTradeTime
AAPL|20250310|09:30:00|T1|20250310|09:45:00|09:46:00
MSFT|20250310|10:00:00|T12|20250310|10:15:00|10:16:00
"""

_CSV_VACIO = "Symbol|HaltDate|HaltTime|ReasonCode|ResumptionDate|ResumptionQuoteTime|ResumptionTradeTime\n"


def _mock_response(text: str, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


class TestObtenerSimbolosHalted:

    def test_retorna_simbolos_sin_tiempo_reanudacion(self):
        with patch("httpx.get", return_value=_mock_response(_CSV_CON_HALTS_ACTIVOS)):
            resultado = obtener_simbolos_halted()
        # MULN y ILUS no tienen ResumptionTradeTime → activos
        assert "MULN" in resultado
        assert "ILUS" in resultado
        # AAPL tiene ResumptionTradeTime → ya reanudado
        assert "AAPL" not in resultado

    def test_retorna_set_vacio_si_todos_reanudados(self):
        with patch("httpx.get", return_value=_mock_response(_CSV_TODOS_REANUDADOS)):
            resultado = obtener_simbolos_halted()
        assert len(resultado) == 0

    def test_retorna_set_vacio_si_csv_sin_datos(self):
        with patch("httpx.get", return_value=_mock_response(_CSV_VACIO)):
            resultado = obtener_simbolos_halted()
        assert len(resultado) == 0

    def test_retorna_set_vacio_si_status_no_200(self):
        with patch("httpx.get", return_value=_mock_response("", status_code=403)):
            resultado = obtener_simbolos_halted()
        assert resultado == set()

    def test_retorna_vacio_si_error_de_red(self):
        with patch("httpx.get", side_effect=Exception("Timeout")):
            resultado = obtener_simbolos_halted()
        assert resultado == set()

    def test_retorna_set_vacio_si_respuesta_vacia(self):
        with patch("httpx.get", return_value=_mock_response("")):
            resultado = obtener_simbolos_halted()
        assert resultado == set()

    def test_retorna_tipo_set(self):
        with patch("httpx.get", return_value=_mock_response(_CSV_CON_HALTS_ACTIVOS)):
            resultado = obtener_simbolos_halted()
        assert isinstance(resultado, set)

    def test_excluye_cabecera_duplicada(self):
        """A veces el archivo tiene la cabecera repetida como fila de datos."""
        csv = _CSV_CON_HALTS_ACTIVOS + "Symbol||||||\n"
        with patch("httpx.get", return_value=_mock_response(csv)):
            resultado = obtener_simbolos_halted()
        assert "Symbol" not in resultado
        assert "SYMBOL" not in resultado
