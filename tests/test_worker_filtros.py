"""Tests unitarios para worker_filtros.

Enfoque:
  - evaluar_condicional: tests puros sin dependencias externas
  - Filtros (RSI, ATR, EMA, VWAP): mock de pandas_ta para controlar el valor
    exacto del indicador → se testea la lógica condicional, no el cálculo del indicador
  - Lógica AND entre filtros, cortocircuito, stubs, formato de señal
  - Múltiples símbolos evaluados de forma independiente
  - Integración timeframes: M1/M5/H1 producen el mismo resultado con igual tendencia

Ejecutar:
    pytest tests/test_worker_filtros.py -v
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.core.worker_filtros import evaluar_condicional, evaluar_simbolos
from app.domain.models.escaner import ValorCondicional


# ---------------------------------------------------------------------------
# Generadores de datos OHLCV (estructura, no valores de indicadores)
# ---------------------------------------------------------------------------

def _barras(n: int, inicio: float = 100.0, delta: float = 0.0,
            spread: float = 0.5, volumen: float = 1_000_000.0) -> list[dict]:
    t = datetime(2025, 1, 2, 9, 30, tzinfo=timezone.utc)
    barras = []
    c = inicio
    for i in range(n):
        c += delta
        sp = max(abs(spread), 0.05)
        barras.append({
            "timestamp": (t + timedelta(minutes=i)).isoformat(),
            "open":   round(c - abs(delta) * 0.3, 4),
            "high":   round(c + sp, 4),
            "low":    round(c - sp, 4),
            "close":  round(c, 4),
            "volume": volumen,
        })
    return barras


def _contexto(barras: list[dict], symbol: str = "TEST", tf: str = "M5") -> dict:
    df = pd.DataFrame(barras)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return {
        "symbol": symbol,
        "barras_por_tf": {tf: df.to_dict(orient="list")},
        "fundamentales": {},
        "halteado": False,
    }


# ---------------------------------------------------------------------------
# Helpers para construir filtros serializados
# ---------------------------------------------------------------------------

def _cond(condicional: str, v1: float, v2: float | None = None) -> dict:
    return {"enum_parametro": "CONDICION", "obj_valor_seleccionado": {
        "enumTipoValor": "CONDICIONAL", "enumCondicional": condicional,
        "valor1": v1, "valor2": v2}}


def _periodo(n: int) -> dict:
    return {"enum_parametro": "PERIODO", "obj_valor_seleccionado": {
        "enumTipoValor": "INTEGER", "valor": n}}


def _filtro_rsi(condicional: str, v1: float, v2: float | None = None, periodo: int = 14) -> dict:
    return {"enum_filtro": "RSI", "parametros": [_periodo(periodo), _cond(condicional, v1, v2)]}


def _filtro_atr(condicional: str, v1: float, v2: float | None = None, periodo: int = 14) -> dict:
    longitud = {"enum_parametro": "LONGITUD_ATR", "obj_valor_seleccionado": {
        "enumTipoValor": "INTEGER", "valor": periodo}}
    return {"enum_filtro": "ATR", "parametros": [longitud, _cond(condicional, v1, v2)]}


def _filtro_ema(condicional: str, v1: float, v2: float | None = None, periodo: int = 20) -> dict:
    return {"enum_filtro": "DISTANCE_FROM_EMA",
            "parametros": [_periodo(periodo), _cond(condicional, v1, v2)]}


def _filtro_vwap(condicional: str, v1: float, v2: float | None = None) -> dict:
    return {"enum_filtro": "DISTANCE_FROM_VWAP", "parametros": [_cond(condicional, v1, v2)]}


# ---------------------------------------------------------------------------
# Tests: evaluar_condicional (sin pandas_ta — tests puros)
# ---------------------------------------------------------------------------

class TestEvaluarCondicional:
    """Prueba todas las condiciones con valores límite."""

    def test_mayor_que_cumple(self):
        assert evaluar_condicional(75.0, ValorCondicional("MAYOR_QUE", valor1=70.0)) is True

    def test_mayor_que_no_cumple(self):
        assert evaluar_condicional(65.0, ValorCondicional("MAYOR_QUE", valor1=70.0)) is False

    def test_mayor_que_igual_no_cumple(self):
        # > estricto, no >=
        assert evaluar_condicional(70.0, ValorCondicional("MAYOR_QUE", valor1=70.0)) is False

    def test_menor_que_cumple(self):
        assert evaluar_condicional(25.0, ValorCondicional("MENOR_QUE", valor1=30.0)) is True

    def test_menor_que_no_cumple(self):
        assert evaluar_condicional(35.0, ValorCondicional("MENOR_QUE", valor1=30.0)) is False

    def test_menor_que_igual_no_cumple(self):
        assert evaluar_condicional(30.0, ValorCondicional("MENOR_QUE", valor1=30.0)) is False

    def test_entre_cumple_en_el_medio(self):
        assert evaluar_condicional(50.0, ValorCondicional("ENTRE", valor1=30.0, valor2=70.0)) is True

    def test_entre_cumple_en_borde_inferior(self):
        assert evaluar_condicional(30.0, ValorCondicional("ENTRE", valor1=30.0, valor2=70.0)) is True

    def test_entre_cumple_en_borde_superior(self):
        assert evaluar_condicional(70.0, ValorCondicional("ENTRE", valor1=30.0, valor2=70.0)) is True

    def test_entre_no_cumple_por_abajo(self):
        assert evaluar_condicional(20.0, ValorCondicional("ENTRE", valor1=30.0, valor2=70.0)) is False

    def test_entre_no_cumple_por_arriba(self):
        assert evaluar_condicional(80.0, ValorCondicional("ENTRE", valor1=30.0, valor2=70.0)) is False

    def test_entre_sin_valor2_siempre_true(self):
        assert evaluar_condicional(200.0, ValorCondicional("ENTRE", valor1=30.0, valor2=None)) is True

    def test_fuera_cumple_por_abajo(self):
        assert evaluar_condicional(20.0, ValorCondicional("FUERA", valor1=30.0, valor2=70.0)) is True

    def test_fuera_cumple_por_arriba(self):
        assert evaluar_condicional(80.0, ValorCondicional("FUERA", valor1=30.0, valor2=70.0)) is True

    def test_fuera_no_cumple_en_rango(self):
        assert evaluar_condicional(50.0, ValorCondicional("FUERA", valor1=30.0, valor2=70.0)) is False

    def test_fuera_sin_valor2_siempre_true(self):
        assert evaluar_condicional(50.0, ValorCondicional("FUERA", valor1=30.0, valor2=None)) is True

    def test_igual_a_cumple(self):
        assert evaluar_condicional(50.0, ValorCondicional("IGUAL_A", valor1=50.0)) is True

    def test_igual_a_no_cumple(self):
        assert evaluar_condicional(51.0, ValorCondicional("IGUAL_A", valor1=50.0)) is False

    def test_valor1_none_siempre_true(self):
        assert evaluar_condicional(999.0, ValorCondicional("MAYOR_QUE", valor1=None)) is True

    def test_condicion_desconocida_retorna_true(self):
        assert evaluar_condicional(100.0, ValorCondicional("CONDICION_INEXISTENTE", valor1=50.0)) is True


# ---------------------------------------------------------------------------
# Tests: filtro RSI
# ---------------------------------------------------------------------------

class TestFiltroRSI:
    """Verifica la lógica del filtro RSI controlando el valor que retorna el indicador."""

    _BARRAS = _barras(30, 100.0, 0.0)  # 30 barras (suficientes para RSI 14)

    def test_rsi_mayor_70_genera_senal(self, mock_pandas_ta):
        mock_pandas_ta.rsi.return_value = pd.Series([80.0])  # RSI = 80
        ctx = {"TEST": _contexto(self._BARRAS)}
        senales = evaluar_simbolos(ctx, [_filtro_rsi("MAYOR_QUE", 70.0)], 1, "E1")
        assert len(senales) == 1

    def test_rsi_mayor_70_no_cumple_no_genera_senal(self, mock_pandas_ta):
        mock_pandas_ta.rsi.return_value = pd.Series([60.0])  # RSI = 60 → no > 70
        ctx = {"TEST": _contexto(self._BARRAS)}
        senales = evaluar_simbolos(ctx, [_filtro_rsi("MAYOR_QUE", 70.0)], 1, "E1")
        assert len(senales) == 0

    def test_rsi_menor_30_genera_senal(self, mock_pandas_ta):
        mock_pandas_ta.rsi.return_value = pd.Series([20.0])  # RSI = 20
        ctx = {"TEST": _contexto(self._BARRAS)}
        senales = evaluar_simbolos(ctx, [_filtro_rsi("MENOR_QUE", 30.0)], 1, "E1")
        assert len(senales) == 1

    def test_rsi_entre_40_60_genera_senal(self, mock_pandas_ta):
        mock_pandas_ta.rsi.return_value = pd.Series([50.0])  # RSI = 50
        ctx = {"TEST": _contexto(self._BARRAS)}
        senales = evaluar_simbolos(ctx, [_filtro_rsi("ENTRE", 40.0, 60.0)], 1, "E1")
        assert len(senales) == 1

    def test_rsi_fuera_40_60_genera_senal(self, mock_pandas_ta):
        mock_pandas_ta.rsi.return_value = pd.Series([75.0])  # RSI = 75 → fuera del rango
        ctx = {"TEST": _contexto(self._BARRAS)}
        senales = evaluar_simbolos(ctx, [_filtro_rsi("FUERA", 40.0, 60.0)], 1, "E1")
        assert len(senales) == 1

    def test_rsi_llama_a_ta_con_periodo_correcto(self, mock_pandas_ta):
        """Verifica que se pasa el periodo correcto a pandas_ta.rsi."""
        ctx = {"TEST": _contexto(self._BARRAS)}
        evaluar_simbolos(ctx, [_filtro_rsi("MAYOR_QUE", 70.0, periodo=7)], 1, "E1")
        _, kwargs = mock_pandas_ta.rsi.call_args
        assert kwargs.get("length") == 7

    def test_rsi_datos_insuficientes_retorna_true(self, mock_pandas_ta):
        """Menos barras que periodo+1 → el filtro pasa sin evaluar el indicador."""
        barras_pocas = _barras(5, 100.0)  # menos de 14+1
        ctx = {"TEST": _contexto(barras_pocas)}
        # Con datos insuficientes la función retorna True → genera señal
        senales = evaluar_simbolos(ctx, [_filtro_rsi("MAYOR_QUE", 70.0)], 1, "E1")
        assert len(senales) == 1
        mock_pandas_ta.rsi.assert_not_called()  # no se llegó a llamar pandas_ta


# ---------------------------------------------------------------------------
# Tests: filtro ATR
# ---------------------------------------------------------------------------

class TestFiltroATR:
    _BARRAS = _barras(30, 100.0, 0.0, spread=1.0)

    def test_atr_mayor_que_genera_senal(self, mock_pandas_ta):
        mock_pandas_ta.atr.return_value = pd.Series([2.5])  # ATR = 2.5
        ctx = {"TEST": _contexto(self._BARRAS)}
        senales = evaluar_simbolos(ctx, [_filtro_atr("MAYOR_QUE", 1.0)], 1, "E1")
        assert len(senales) == 1

    def test_atr_mayor_que_no_cumple(self, mock_pandas_ta):
        mock_pandas_ta.atr.return_value = pd.Series([0.5])  # ATR = 0.5 → no > 1.0
        ctx = {"TEST": _contexto(self._BARRAS)}
        senales = evaluar_simbolos(ctx, [_filtro_atr("MAYOR_QUE", 1.0)], 1, "E1")
        assert len(senales) == 0

    def test_atr_menor_que_genera_senal(self, mock_pandas_ta):
        mock_pandas_ta.atr.return_value = pd.Series([0.3])  # ATR bajo
        ctx = {"TEST": _contexto(self._BARRAS)}
        senales = evaluar_simbolos(ctx, [_filtro_atr("MENOR_QUE", 0.5)], 1, "E1")
        assert len(senales) == 1

    def test_atr_llama_con_periodo_correcto(self, mock_pandas_ta):
        ctx = {"TEST": _contexto(self._BARRAS)}
        evaluar_simbolos(ctx, [_filtro_atr("MAYOR_QUE", 1.0, periodo=10)], 1, "E1")
        _, kwargs = mock_pandas_ta.atr.call_args
        assert kwargs.get("length") == 10

    def test_atr_datos_insuficientes_retorna_true(self, mock_pandas_ta):
        barras_pocas = _barras(5, 100.0)
        ctx = {"TEST": _contexto(barras_pocas)}
        senales = evaluar_simbolos(ctx, [_filtro_atr("MAYOR_QUE", 100.0)], 1, "E1")
        assert len(senales) == 1
        mock_pandas_ta.atr.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: filtro DISTANCE_FROM_EMA
# ---------------------------------------------------------------------------

class TestFiltroDistanceEMA:
    """La distancia se calcula como ((close - EMA) / EMA) * 100."""

    _BARRAS = _barras(30, 100.0, 0.0)

    def test_precio_sobre_ema_distancia_positiva(self, mock_pandas_ta):
        """close=110, EMA=100 → distancia = +10% → MAYOR_QUE 5 cumple."""
        mock_pandas_ta.ema.return_value = pd.Series([100.0])
        # El close de la última barra es 100 (precio plano), pero lo controlamos
        # vía el valor de EMA. Para distancia positiva: close > EMA
        # Usamos barras donde close = 110 y EMA mock = 100
        barras = _barras(30, 110.0, 0.0)  # close = 110
        barras_mock_ema_100 = barras
        ctx = {"TEST": _contexto(barras_mock_ema_100)}
        senales = evaluar_simbolos(ctx, [_filtro_ema("MAYOR_QUE", 5.0)], 1, "E1")
        # close=110, EMA=100 → distancia = (110-100)/100*100 = +10% > 5% ✓
        assert len(senales) == 1

    def test_precio_bajo_ema_distancia_negativa(self, mock_pandas_ta):
        """close=90, EMA=100 → distancia = -10% → MENOR_QUE -5 cumple."""
        mock_pandas_ta.ema.return_value = pd.Series([100.0])
        barras = _barras(30, 90.0, 0.0)  # close = 90
        ctx = {"TEST": _contexto(barras)}
        senales = evaluar_simbolos(ctx, [_filtro_ema("MENOR_QUE", -5.0)], 1, "E1")
        # close=90, EMA=100 → distancia = (90-100)/100*100 = -10% < -5% ✓
        assert len(senales) == 1

    def test_distancia_ema_entre_rango(self, mock_pandas_ta):
        """close=101, EMA=100 → distancia = +1% → ENTRE -2 y +2 cumple."""
        mock_pandas_ta.ema.return_value = pd.Series([100.0])
        barras = _barras(30, 101.0, 0.0)
        ctx = {"TEST": _contexto(barras)}
        senales = evaluar_simbolos(ctx, [_filtro_ema("ENTRE", -2.0, 2.0)], 1, "E1")
        assert len(senales) == 1

    def test_ema_llama_con_periodo_correcto(self, mock_pandas_ta):
        barras = _barras(60, 100.0, 0.0)  # > periodo(50)+1 para que se llame a ta.ema
        ctx = {"TEST": _contexto(barras)}
        evaluar_simbolos(ctx, [_filtro_ema("MAYOR_QUE", 0.0, periodo=50)], 1, "E1")
        _, kwargs = mock_pandas_ta.ema.call_args
        assert kwargs.get("length") == 50

    def test_ema_datos_insuficientes_retorna_true(self, mock_pandas_ta):
        barras_pocas = _barras(5, 100.0)
        ctx = {"TEST": _contexto(barras_pocas)}
        senales = evaluar_simbolos(ctx, [_filtro_ema("MAYOR_QUE", 100.0)], 1, "E1")
        assert len(senales) == 1
        mock_pandas_ta.ema.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: filtro DISTANCE_FROM_VWAP
# ---------------------------------------------------------------------------

class TestFiltroDistanceVWAP:
    _BARRAS = _barras(30, 100.0, 0.0)

    def test_precio_sobre_vwap_genera_senal(self, mock_pandas_ta):
        """close=110, VWAP=100 → distancia = +10% → MAYOR_QUE 0 cumple."""
        mock_pandas_ta.vwap.return_value = pd.Series([100.0])
        barras = _barras(30, 110.0, 0.0)
        ctx = {"TEST": _contexto(barras)}
        senales = evaluar_simbolos(ctx, [_filtro_vwap("MAYOR_QUE", 0.0)], 1, "E1")
        assert len(senales) == 1

    def test_precio_bajo_vwap_genera_senal(self, mock_pandas_ta):
        """close=90, VWAP=100 → distancia = -10% → MENOR_QUE 0 cumple."""
        mock_pandas_ta.vwap.return_value = pd.Series([100.0])
        barras = _barras(30, 90.0, 0.0)
        ctx = {"TEST": _contexto(barras)}
        senales = evaluar_simbolos(ctx, [_filtro_vwap("MENOR_QUE", 0.0)], 1, "E1")
        assert len(senales) == 1

    def test_vwap_datos_insuficientes_retorna_true(self, mock_pandas_ta):
        barras = _barras(1, 100.0)  # solo 1 barra → < 2
        ctx = {"TEST": _contexto(barras)}
        senales = evaluar_simbolos(ctx, [_filtro_vwap("MAYOR_QUE", 100.0)], 1, "E1")
        assert len(senales) == 1
        mock_pandas_ta.vwap.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: lógica AND entre múltiples filtros
# ---------------------------------------------------------------------------

class TestLogicaMultiplesFiltros:
    _BARRAS = _barras(30, 100.0, 0.0)

    def test_dos_filtros_ambos_cumplen_genera_senal(self, mock_pandas_ta):
        """RSI > 70 AND ATR > 1.0 → ambos cumplen → señal."""
        mock_pandas_ta.rsi.return_value = pd.Series([80.0])
        mock_pandas_ta.atr.return_value = pd.Series([2.0])
        ctx = {"TEST": _contexto(self._BARRAS)}
        senales = evaluar_simbolos(ctx, [
            _filtro_rsi("MAYOR_QUE", 70.0),
            _filtro_atr("MAYOR_QUE", 1.0),
        ], 1, "E1")
        assert len(senales) == 1

    def test_primer_filtro_falla_cortocircuito(self, mock_pandas_ta):
        """RSI falla → corto-circuito → ATR no se evalúa → no señal."""
        mock_pandas_ta.rsi.return_value = pd.Series([60.0])  # RSI < 70 → falla
        ctx = {"TEST": _contexto(self._BARRAS)}
        senales = evaluar_simbolos(ctx, [
            _filtro_rsi("MAYOR_QUE", 70.0),
            _filtro_atr("MAYOR_QUE", 1.0),
        ], 1, "E1")
        assert len(senales) == 0
        mock_pandas_ta.atr.assert_not_called()  # Nunca se evaluó ATR

    def test_segundo_filtro_falla_no_genera_senal(self, mock_pandas_ta):
        """RSI cumple, ATR falla → no señal."""
        mock_pandas_ta.rsi.return_value = pd.Series([80.0])  # RSI ok
        mock_pandas_ta.atr.return_value = pd.Series([0.2])   # ATR < 1.0 → falla
        ctx = {"TEST": _contexto(self._BARRAS)}
        senales = evaluar_simbolos(ctx, [
            _filtro_rsi("MAYOR_QUE", 70.0),
            _filtro_atr("MAYOR_QUE", 1.0),
        ], 1, "E1")
        assert len(senales) == 0

    def test_tres_filtros_todos_cumplen(self, mock_pandas_ta):
        """RSI > 70 AND ATR > 1.0 AND EMA_dist > 5% → todos cumplen."""
        mock_pandas_ta.rsi.return_value = pd.Series([80.0])
        mock_pandas_ta.atr.return_value = pd.Series([2.0])
        mock_pandas_ta.ema.return_value = pd.Series([100.0])
        barras = _barras(30, 110.0, 0.0)  # close=110, EMA=100 → +10%
        ctx = {"TEST": _contexto(barras)}
        senales = evaluar_simbolos(ctx, [
            _filtro_rsi("MAYOR_QUE", 70.0),
            _filtro_atr("MAYOR_QUE", 1.0),
            _filtro_ema("MAYOR_QUE", 5.0),
        ], 1, "E1")
        assert len(senales) == 1

    def test_filtros_aplicados_contiene_todos_los_cumplidos(self, mock_pandas_ta):
        """filtrosAplicados debe listar todos los filtros que pasaron."""
        mock_pandas_ta.rsi.return_value = pd.Series([80.0])
        mock_pandas_ta.atr.return_value = pd.Series([2.0])
        ctx = {"TEST": _contexto(self._BARRAS)}
        senales = evaluar_simbolos(ctx, [
            _filtro_rsi("MAYOR_QUE", 70.0),
            _filtro_atr("MAYOR_QUE", 1.0),
        ], 1, "E1")
        filtros = senales[0]["filtrosAplicados"].split(",")
        assert "RSI" in filtros
        assert "ATR" in filtros


# ---------------------------------------------------------------------------
# Tests: filtro no implementado (stub)
# ---------------------------------------------------------------------------

class TestFiltroNoImplementado:
    _BARRAS = _barras(30, 100.0, 0.0)

    def test_filtro_no_implementado_siempre_pasa(self, mock_pandas_ta):
        """VOLUME no está implementado → actúa como stub → genera señal."""
        ctx = {"TEST": _contexto(self._BARRAS)}
        senales = evaluar_simbolos(ctx, [{"enum_filtro": "VOLUME", "parametros": []}], 1, "E1")
        assert len(senales) == 1

    def test_stub_aparece_en_filtros_aplicados(self, mock_pandas_ta):
        ctx = {"TEST": _contexto(self._BARRAS)}
        senales = evaluar_simbolos(ctx, [{"enum_filtro": "VOLUME", "parametros": []}], 1, "E1")
        assert "VOLUME" in senales[0]["filtrosAplicados"]

    def test_stub_y_filtro_real_que_falla_no_genera_senal(self, mock_pandas_ta):
        """Stub pasa, pero RSI falla → no señal."""
        mock_pandas_ta.rsi.return_value = pd.Series([50.0])  # RSI < 70
        ctx = {"TEST": _contexto(self._BARRAS)}
        senales = evaluar_simbolos(ctx, [
            {"enum_filtro": "VOLUME", "parametros": []},
            _filtro_rsi("MAYOR_QUE", 70.0),
        ], 1, "E1")
        assert len(senales) == 0

    def test_sin_filtros_no_genera_senal(self, mock_pandas_ta):
        """Sin filtros → filtros_que_cumplieron vacío → no señal."""
        ctx = {"TEST": _contexto(self._BARRAS)}
        senales = evaluar_simbolos(ctx, [], 1, "E1")
        assert len(senales) == 0


# ---------------------------------------------------------------------------
# Tests: formato de la señal generada
# ---------------------------------------------------------------------------

class TestFormatoSenal:
    def test_senal_tiene_todas_las_claves_requeridas(self, mock_pandas_ta):
        mock_pandas_ta.rsi.return_value = pd.Series([80.0])
        barras = _barras(30, 150.25, 0.0, volumen=2_500_000.0)
        ctx = {"AAPL": _contexto(barras, "AAPL")}
        senales = evaluar_simbolos(ctx, [_filtro_rsi("MAYOR_QUE", 70.0)], 42, "Mi Escaner")
        s = senales[0]
        assert s["idEscaner"] == 42
        assert s["nombreEscaner"] == "Mi Escaner"
        assert s["symbol"] == "AAPL"
        assert s["tipoSenal"] == "ALERTA_FILTROS"
        assert "filtrosAplicados" in s
        assert "precioDeteccion" in s
        assert "volumenDeteccion" in s
        assert s["servicioOrigen"] == "signal-processing-service"

    def test_precio_deteccion_es_close_ultima_vela(self, mock_pandas_ta):
        mock_pandas_ta.rsi.return_value = pd.Series([80.0])
        barras = _barras(30, 150.25, 0.0)
        close_ultima = barras[-1]["close"]
        ctx = {"TEST": _contexto(barras)}
        senales = evaluar_simbolos(ctx, [_filtro_rsi("MAYOR_QUE", 70.0)], 1, "E1")
        assert senales[0]["precioDeteccion"] == pytest.approx(close_ultima)

    def test_volumen_deteccion_es_volumen_ultima_vela(self, mock_pandas_ta):
        mock_pandas_ta.rsi.return_value = pd.Series([80.0])
        barras = _barras(30, 100.0, 0.0, volumen=3_000_000.0)
        ctx = {"TEST": _contexto(barras)}
        senales = evaluar_simbolos(ctx, [_filtro_rsi("MAYOR_QUE", 70.0)], 1, "E1")
        assert senales[0]["volumenDeteccion"] == pytest.approx(3_000_000.0)

    def test_tipo_senal_siempre_es_alerta_filtros(self, mock_pandas_ta):
        mock_pandas_ta.rsi.return_value = pd.Series([80.0])
        ctx = {"TEST": _contexto(_barras(30, 100.0, 0.0))}
        senales = evaluar_simbolos(ctx, [_filtro_rsi("MAYOR_QUE", 70.0)], 1, "E1")
        assert senales[0]["tipoSenal"] == "ALERTA_FILTROS"


# ---------------------------------------------------------------------------
# Tests: múltiples símbolos evaluados independientemente
# ---------------------------------------------------------------------------

class TestMultiplesSimbolos:
    def test_dos_simbolos_ambos_cumplen(self, mock_pandas_ta):
        """AAPL y MSFT → RSI mock = 80 → ambos generan señal."""
        mock_pandas_ta.rsi.return_value = pd.Series([80.0])
        barras = _barras(30, 100.0, 0.0)
        ctx = {
            "AAPL": _contexto(barras, "AAPL"),
            "MSFT": _contexto(barras, "MSFT"),
        }
        senales = evaluar_simbolos(ctx, [_filtro_rsi("MAYOR_QUE", 70.0)], 1, "E1")
        symbols = {s["symbol"] for s in senales}
        assert "AAPL" in symbols
        assert "MSFT" in symbols
        assert len(senales) == 2

    def test_un_simbolo_cumple_otro_no(self, mock_pandas_ta):
        """Mock retorna diferentes RSI por símbolo usando side_effect."""
        # Primera llamada (AAPL o MSFT) = 80, segunda = 50
        mock_pandas_ta.rsi.side_effect = [pd.Series([80.0]), pd.Series([50.0])]
        barras = _barras(30, 100.0, 0.0)
        ctx = {
            "AAPL": _contexto(barras, "AAPL"),
            "MSFT": _contexto(barras, "MSFT"),
        }
        senales = evaluar_simbolos(ctx, [_filtro_rsi("MAYOR_QUE", 70.0)], 1, "E1")
        assert len(senales) == 1  # Solo uno cumple

    def test_tres_simbolos_ninguno_cumple(self, mock_pandas_ta):
        mock_pandas_ta.rsi.return_value = pd.Series([50.0])  # nunca > 70
        barras = _barras(30, 100.0, 0.0)
        ctx = {s: _contexto(barras, s) for s in ["A", "B", "C"]}
        senales = evaluar_simbolos(ctx, [_filtro_rsi("MAYOR_QUE", 70.0)], 1, "E1")
        assert len(senales) == 0

    def test_contexto_vacio_no_genera_senal(self, mock_pandas_ta):
        ctx = {"TEST": {"symbol": "TEST", "barras_por_tf": {}, "fundamentales": {}, "halteado": False}}
        senales = evaluar_simbolos(ctx, [_filtro_rsi("MAYOR_QUE", 70.0)], 1, "E1")
        assert len(senales) == 0


# ---------------------------------------------------------------------------
# Tests: timeframes — M1, M5, M15, M30, H1 se evalúan con la misma lógica
# ---------------------------------------------------------------------------

class TestTimeframes:
    """El timeframe afecta la frecuencia de actualización, no la evaluación de filtros.
    Barras de cualquier TF tienen la misma estructura OHLCV."""

    def _barras_tf(self, n: int, intervalo_min: int) -> list[dict]:
        t = datetime(2025, 1, 2, 9, 30, tzinfo=timezone.utc)
        c = 100.0
        barras = []
        for i in range(n):
            c += 1.0
            barras.append({
                "timestamp": (t + timedelta(minutes=i * intervalo_min)).isoformat(),
                "open": c - 0.3, "high": c + 0.5, "low": c - 0.5,
                "close": round(c, 4), "volume": 500_000.0,
            })
        return barras

    @pytest.mark.parametrize("intervalo_min,nombre_tf", [
        (1, "M1"), (5, "M5"), (15, "M15"), (30, "M30"), (60, "H1"),
    ])
    def test_filtro_rsi_funciona_en_cualquier_timeframe(
        self, mock_pandas_ta, intervalo_min, nombre_tf
    ):
        """El filtro RSI genera señal independientemente del timeframe de las barras."""
        mock_pandas_ta.rsi.return_value = pd.Series([80.0])
        barras = self._barras_tf(30, intervalo_min)
        ctx = {"TEST": _contexto(barras)}
        senales = evaluar_simbolos(ctx, [_filtro_rsi("MAYOR_QUE", 70.0)], 1, f"E_{nombre_tf}")
        assert len(senales) == 1, f"Falló para timeframe {nombre_tf}"

    def test_resultado_consistente_entre_timeframes(self, mock_pandas_ta):
        """Misma condición, distintos TF → mismo resultado."""
        mock_pandas_ta.rsi.return_value = pd.Series([80.0])
        resultados = []
        for intervalo in [1, 5, 15, 30, 60]:
            barras = self._barras_tf(30, intervalo)
            ctx = {"TEST": _contexto(barras)}
            s = evaluar_simbolos(ctx, [_filtro_rsi("MAYOR_QUE", 70.0)], 1, "E")
            resultados.append(len(s) > 0)
        assert len(set(resultados)) == 1  # Todos iguales (True)


# ---------------------------------------------------------------------------
# Tests: selección de barras por timeframe configurado en cada filtro
# ---------------------------------------------------------------------------

def _ctx_multitf(symbol: str = "TEST") -> dict:
    """Contexto con M5 (close≈100) y M15 (close≈200).
    Los valores distintos permiten verificar qué TF recibió cada evaluador."""
    barras_m5  = _barras(30, inicio=100.0)
    barras_m15 = _barras(30, inicio=200.0)
    df5  = pd.DataFrame(barras_m5)
    df15 = pd.DataFrame(barras_m15)
    for col in ["open", "high", "low", "close", "volume"]:
        df5[col]  = pd.to_numeric(df5[col],  errors="coerce")
        df15[col] = pd.to_numeric(df15[col], errors="coerce")
    return {
        symbol: {
            "symbol": symbol,
            "barras_por_tf": {
                "M5":  df5.to_dict(orient="list"),
                "M15": df15.to_dict(orient="list"),
            },
            "fundamentales": {},
            "halteado": False,
        }
    }


def _tf_param(enum_name: str, clave: str = "TIMEFRAME_RSI") -> dict:
    """Parámetro TIMEFRAME serializado igual que Java (ej. '_15M')."""
    return {
        "enum_parametro": clave,
        "obj_valor_seleccionado": {"enumTipoValor": "STRING", "valor": enum_name},
    }


class TestSeleccionTFPorFiltro:
    """Verifica que cada filtro recibe las barras del TF configurado, no el default.

    Estrategia: contexto con M5 (close≈100) y M15 (close≈200).
    Comprobamos qué Series se pasó a pandas_ta para saber qué TF se usó.
    """

    def test_filtro_rsi_con_tf_m15_recibe_barras_m15(self, mock_pandas_ta):
        """RSI configurado TIMEFRAME=_15M debe recibir barras M15 (close≈200), no M5 (close≈100)."""
        mock_pandas_ta.rsi.return_value = pd.Series([80.0])
        filtro = {
            "enum_filtro": "RSI",
            "parametros": [_periodo(14), _cond("MAYOR_QUE", 70.0), _tf_param("_15M")],
        }
        evaluar_simbolos(_ctx_multitf(), [filtro], 1, "E1")

        close_recibido = mock_pandas_ta.rsi.call_args[0][0]
        assert float(close_recibido.iloc[-1]) > 150, (
            f"RSI debía usar M15 (close≈200) pero recibió close={float(close_recibido.iloc[-1]):.1f} (¿M5?)"
        )

    def test_filtro_rsi_sin_timeframe_usa_tf_minimo_m5(self, mock_pandas_ta):
        """RSI sin parámetro TIMEFRAME usa el TF mínimo del contexto (M5, close≈100)."""
        mock_pandas_ta.rsi.return_value = pd.Series([80.0])
        filtro = _filtro_rsi("MAYOR_QUE", 70.0)  # sin _tf_param

        evaluar_simbolos(_ctx_multitf(), [filtro], 1, "E1")

        close_recibido = mock_pandas_ta.rsi.call_args[0][0]
        assert float(close_recibido.iloc[-1]) < 150, (
            f"RSI sin TF debía usar M5 (close≈100) pero recibió close={float(close_recibido.iloc[-1]):.1f} (¿M15?)"
        )

    def test_rsi_m5_y_atr_m15_cada_uno_recibe_sus_barras(self, mock_pandas_ta):
        """RSI@M5 + ATR@M15: RSI recibe barras M5 (close≈100) y ATR recibe M15 (high≈202)."""
        mock_pandas_ta.rsi.return_value = pd.Series([80.0])
        mock_pandas_ta.atr.return_value = pd.Series([2.0])

        filtro_rsi = {
            "enum_filtro": "RSI",
            "parametros": [_periodo(14), _cond("MAYOR_QUE", 70.0), _tf_param("_5M", "TIMEFRAME_RSI")],
        }
        filtro_atr = {
            "enum_filtro": "ATR",
            "parametros": [
                {"enum_parametro": "LONGITUD_ATR",
                 "obj_valor_seleccionado": {"enumTipoValor": "INTEGER", "valor": 14}},
                _cond("MAYOR_QUE", 1.0),
                _tf_param("_15M", "TIMEFRAME_ATR"),
            ],
        }
        senales = evaluar_simbolos(_ctx_multitf(), [filtro_rsi, filtro_atr], 1, "E1")
        assert len(senales) == 1, "Ambos filtros deberían cumplir y generar una señal"

        close_rsi = mock_pandas_ta.rsi.call_args[0][0]
        assert float(close_rsi.iloc[-1]) < 150, (
            f"RSI debía usar M5 (close≈100) pero recibió {float(close_rsi.iloc[-1]):.1f}"
        )
        high_atr = mock_pandas_ta.atr.call_args[0][0]
        assert float(high_atr.iloc[-1]) > 150, (
            f"ATR debía usar M15 (high≈202) pero recibió {float(high_atr.iloc[-1]):.1f}"
        )

    def test_tf_configurado_no_disponible_cae_en_default(self, mock_pandas_ta):
        """Si las barras del TF del filtro no existen, cae al TF mínimo disponible (no lanza excepción)."""
        mock_pandas_ta.rsi.return_value = pd.Series([80.0])
        # Solo hay M5, el filtro pide M1 que no está
        filtro = {
            "enum_filtro": "RSI",
            "parametros": [_periodo(14), _cond("MAYOR_QUE", 70.0), _tf_param("_1M")],
        }
        barras = _barras(30, inicio=100.0)
        ctx = {"TEST": _contexto(barras, tf="M5")}  # solo M5, sin M1

        senales = evaluar_simbolos(ctx, [filtro], 1, "E1")
        assert len(senales) == 1, "Debe evaluar con el TF disponible (M5) y no lanzar excepción"

    def test_multiples_simbolos_cada_uno_usa_su_tf(self, mock_pandas_ta):
        """Con dos símbolos, cada uno tiene sus propios barras_por_tf y se evalúan independientemente."""
        mock_pandas_ta.rsi.side_effect = [
            pd.Series([80.0]),  # AAPL: RSI=80 → cumple M15
            pd.Series([50.0]),  # MSFT: RSI=50 → no cumple M15
        ]
        filtro = {
            "enum_filtro": "RSI",
            "parametros": [_periodo(14), _cond("MAYOR_QUE", 70.0), _tf_param("_15M")],
        }
        ctx = {**_ctx_multitf("AAPL"), **_ctx_multitf("MSFT")}
        senales = evaluar_simbolos(ctx, [filtro], 1, "E1")

        assert len(senales) == 1
        assert senales[0]["symbol"] == "AAPL"
