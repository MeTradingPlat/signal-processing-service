"""Simulación del escáner 'volatilidad y flexibilidad' con datos reales M1.

Replica exactamente los filtros configurados en la imagen:
  - Volumen Promedio  > 50 000          (AVERAGE_VOLUME,   timeframe M1)
  - ATR              > 0.15, length=14  (ATR,              timeframe M1)
  - Rango Porcentual > 2 %              (PERCENTAGE_RANGE, timeframe M1)

Flujo del test:
  1. Obtiene TODOS los símbolos de todos los mercados (NYSE, NASDAQ, AMEX, ETF, OTC).
  2. Carga barras M1 históricas en batches POST de BATCH_SIZE símbolos.
  3. Evalúa los 3 filtros con evaluar_simbolos().
  4. Imprime el resultado e impone assertions básicas de sanidad.

El test también verifica que _determinar_timeframe() resuelve M1 correctamente
cuando los filtros tienen TIMEFRAME_* = "_1M" (fix de enums.py).

Prerequisito: pandas_ta instalado (disponible en el entorno Docker).
              Si la API no responde, el test es skipped automáticamente.
"""

import importlib
import pytest
import requests

def _check_pandas_ta_completo() -> bool:
    """Verifica que pandas_ta importa correctamente (requiere numba)."""
    try:
        import pandas_ta  # noqa: F401  — falla si numba no está
        return True
    except (ImportError, ModuleNotFoundError):
        return False

_PANDAS_TA_OK = _check_pandas_ta_completo()
_SKIP_TA = pytest.mark.skipif(
    not _PANDAS_TA_OK,
    reason="pandas_ta requiere numba; no disponible en Python 3.14+. Correr en Docker.",
)

from app.domain.enums import SCANNER_TF_A_MARKETDATA, EnumTimeframe
from app.domain.models.escaner import Escaner, _parsear_filtro

if _PANDAS_TA_OK:
    from app.core.worker_filtros import evaluar_simbolos

# ──────────────────────────────────────────────────────────────────────────────
# Configuración
# ──────────────────────────────────────────────────────────────────────────────

API_BASE = "https://metradingplat.com"
MERCADOS = ["NYSE", "NASDAQ", "AMEX", "ETF", "OTC"]
BARS_M1 = 60              # Barras M1 a cargar por símbolo
BATCH_SIZE = 50           # Símbolos por batch POST (>50 genera timeout en el server)
TIMEOUT_API = 15          # segundos máximos por request


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _api_get(path: str, **params) -> dict | list:
    """GET a la API pública. Falla el test con skip si no hay conectividad."""
    try:
        resp = requests.get(f"{API_BASE}{path}", params=params, timeout=TIMEOUT_API)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        pytest.skip(f"API no reachable: {API_BASE}")
    except requests.exceptions.Timeout:
        pytest.skip(f"API timeout ({TIMEOUT_API}s): {path}")


def _api_get_historical(symbol: str, timeframe: str, bars: int) -> list:
    """GET /api/marketdata/historical/{symbol}?timeframe=M1&bars=60 → lista de velas."""
    try:
        resp = requests.get(
            f"{API_BASE}/api/marketdata/historical/{symbol}",
            params={"timeframe": timeframe, "bars": bars},
            timeout=TIMEOUT_API,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("candles", "candlesPorSimbolo", "data", "bars"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        return []
    except Exception:
        return []


def _cargar_barras_batch(simbolos: list[str], timeframe: str, bars: int) -> dict:
    """Carga barras de TODOS los símbolos via POST batch en chunks de BATCH_SIZE."""
    resultado = {}
    chunks = [simbolos[i:i + BATCH_SIZE] for i in range(0, len(simbolos), BATCH_SIZE)]
    for i, chunk in enumerate(chunks):
        print(f"  Batch {i+1}/{len(chunks)}: {len(chunk)} simbolos...", end=" ", flush=True)
        try:
            resp = requests.post(
                f"{API_BASE}/api/marketdata/historical/batch",
                json={"symbols": chunk, "timeframe": timeframe, "bars": bars},
                headers={"X-Gateway-Passed": "true"},
                timeout=TIMEOUT_API,
            )
            resp.raise_for_status()
            candles = resp.json().get("candlesPorSimbolo", {})
            con_data = {s: v for s, v in candles.items() if v}
            resultado.update(con_data)
            print(f"{len(con_data)} con datos")
        except requests.exceptions.HTTPError as e:
            print(f"HTTP {e.response.status_code} — skip chunk")
        except Exception as e:
            print(f"Error: {e} — skip chunk")
    return resultado


def _construir_filtros_screenshot() -> list[dict]:
    """Construye los 3 filtros de la imagen exactamente como los envía el scanner-management."""
    def _tf_param(enum_param: str):
        return {
            "enum_parametro": enum_param,
            "obj_valor_seleccionado": {
                "enumTipoValor": "STRING",
                "etiqueta": "timeframe.1m",
                "valor": "_1M",
            },
        }

    filtro_volumen = {
        "enum_filtro": "AVERAGE_VOLUME",
        "parametros": [
            {
                "enum_parametro": "CONDICION",
                "obj_valor_seleccionado": {
                    "enumTipoValor": "CONDICIONAL",
                    "enumCondicional": "MAYOR_QUE",
                    "isInteger": True,
                    "valor1": 50000,
                    "valor2": None,
                },
            },
            _tf_param("TIMEFRAME_AVERAGE_VOLUME"),
        ],
    }

    filtro_atr = {
        "enum_filtro": "ATR",
        "parametros": [
            {
                "enum_parametro": "CONDICION",
                "obj_valor_seleccionado": {
                    "enumTipoValor": "CONDICIONAL",
                    "enumCondicional": "MAYOR_QUE",
                    "isInteger": False,
                    "valor1": 0.15,
                    "valor2": None,
                },
            },
            {
                "enum_parametro": "LONGITUD_ATR",
                "obj_valor_seleccionado": {"enumTipoValor": "INTEGER", "valor": 14},
            },
            _tf_param("TIMEFRAME_ATR"),
        ],
    }

    filtro_rango = {
        "enum_filtro": "PERCENTAGE_RANGE",
        "parametros": [
            {
                "enum_parametro": "CONDICION",
                "obj_valor_seleccionado": {
                    "enumTipoValor": "CONDICIONAL",
                    "enumCondicional": "MAYOR_QUE",
                    "isInteger": False,
                    "valor1": 2.0,
                    "valor2": None,
                },
            },
            _tf_param("TIMEFRAME_PERCENTAGE_RANGE_PERCENT"),
        ],
    }

    return [filtro_volumen, filtro_atr, filtro_rango]


def _construir_filtros_java_format() -> list[dict]:
    """Construye los 3 filtros en formato camelCase del API Java (para _parsear_filtro)."""
    def _tf_param(enum_param: str):
        return {
            "enumParametro": enum_param,
            "objValorSeleccionado": {
                "enumTipoValor": "STRING",
                "etiqueta": "timeframe.1m",
                "valor": "_1M",
            },
        }

    filtro_volumen = {
        "enumFiltro": "AVERAGE_VOLUME",
        "parametros": [
            {
                "enumParametro": "CONDICION",
                "objValorSeleccionado": {
                    "enumTipoValor": "CONDICIONAL",
                    "enumCondicional": "MAYOR_QUE",
                    "isInteger": True,
                    "valor1": 50000,
                    "valor2": None,
                },
            },
            _tf_param("TIMEFRAME_AVERAGE_VOLUME"),
        ],
    }

    filtro_atr = {
        "enumFiltro": "ATR",
        "parametros": [
            {
                "enumParametro": "CONDICION",
                "objValorSeleccionado": {
                    "enumTipoValor": "CONDICIONAL",
                    "enumCondicional": "MAYOR_QUE",
                    "isInteger": False,
                    "valor1": 0.15,
                    "valor2": None,
                },
            },
            {
                "enumParametro": "LONGITUD_ATR",
                "objValorSeleccionado": {"enumTipoValor": "INTEGER", "valor": 14},
            },
            _tf_param("TIMEFRAME_ATR"),
        ],
    }

    filtro_rango = {
        "enumFiltro": "PERCENTAGE_RANGE",
        "parametros": [
            {
                "enumParametro": "CONDICION",
                "objValorSeleccionado": {
                    "enumTipoValor": "CONDICIONAL",
                    "enumCondicional": "MAYOR_QUE",
                    "isInteger": False,
                    "valor1": 2.0,
                    "valor2": None,
                },
            },
            _tf_param("TIMEFRAME_PERCENTAGE_RANGE_PERCENT"),
        ],
    }

    return [filtro_volumen, filtro_atr, filtro_rango]


def _contextos_desde_barras(barras_por_simbolo: dict) -> dict:
    """Convierte la respuesta de la API en contextos para evaluar_simbolos()."""
    import pandas as pd
    contextos = {}
    for symbol, velas in barras_por_simbolo.items():
        if not velas:
            continue
        df = pd.DataFrame(velas)
        for col in ("open", "high", "low", "close", "volume"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        contextos[symbol] = {
            "symbol": symbol,
            "barras": df.to_dict(orient="list"),
            "ultima_vela_timestamp": velas[-1].get("timestamp", ""),
        }
    return contextos


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestTimeframeDeteccionDesdeAPI:
    """Verifica que _determinar_timeframe() resuelve M1 con los filtros del screenshot."""

    def test_filtros_con_valor_enum_resuelven_m1(self):
        """TIMEFRAME_ATR="_1M" → _determinar_timeframe() debe retornar M1."""
        from app.core.ejecutor_escaner import EjecutorEscaner
        from app.domain.models.escaner import Escaner
        from unittest.mock import MagicMock

        filtros_data = _construir_filtros_java_format()
        filtros = [_parsear_filtro(f) for f in filtros_data]

        escaner = Escaner(
            id_escaner=1,
            nombre="test_m1",
            mercados=["NYSE"],
            filtros=filtros,
        )
        ejecutor = EjecutorEscaner(
            escaner=escaner,
            kafka_producer=MagicMock(),
            marketdata_rest=MagicMock(),
            process_pool=MagicMock(),
            gestor_tiempo=MagicMock(),
        )
        tf = ejecutor._determinar_timeframe()
        assert tf == EnumTimeframe.M1, (
            f"Se esperaba M1 pero se obtuvo {tf}. "
            "Revisar logs de 'Diagnóstico de parámetros' para ver el valor raw."
        )

    def test_filtro_timeframe_i18n_resuelve_m1(self):
        """'timeframe.1m' (clave i18n) también debe resolverse como M1."""
        assert "timeframe.1m" in SCANNER_TF_A_MARKETDATA
        assert SCANNER_TF_A_MARKETDATA["timeframe.1m"] == EnumTimeframe.M1

    def test_mapeo_completo_de_timeframes_soportados(self):
        """Todos los timeframes soportados deben estar en el mapeo (ambos formatos)."""
        pares = [
            ("_1M", "timeframe.1m", EnumTimeframe.M1),
            ("_5M", "timeframe.5m", EnumTimeframe.M5),
            ("_15M", "timeframe.15m", EnumTimeframe.M15),
            ("_30M", "timeframe.30m", EnumTimeframe.M30),
            ("_1H", "timeframe.1h", EnumTimeframe.H1),
        ]
        for enum_name, i18n_key, expected_tf in pares:
            assert SCANNER_TF_A_MARKETDATA[enum_name] == expected_tf, f"Fallo: {enum_name}"
            assert SCANNER_TF_A_MARKETDATA[i18n_key] == expected_tf, f"Fallo: {i18n_key}"


@_SKIP_TA
class TestSimulacionEscanerM1ConDatosReales:
    """Simula el escáner 'volatilidad y flexibilidad' con datos reales del API."""

    def test_obtiene_simbolos_de_todos_los_mercados(self):
        """Verifica que el API retorna símbolos de todos los mercados soportados."""
        datos = _api_get("/api/marketdata/symbols", markets=",".join(MERCADOS))
        simbolos = [d["symbol"] for d in datos if "symbol" in d]
        assert len(simbolos) > 0, f"No se obtuvieron símbolos de {MERCADOS}"
        print(f"\n[Todos los mercados] Total símbolos disponibles: {len(simbolos)}")

    def test_carga_barras_m1_para_subset(self):
        """Verifica que el batch POST /historical/batch retorna datos M1."""
        datos = _api_get("/api/marketdata/symbols", markets=",".join(MERCADOS))
        todos_simbolos = [d["symbol"] for d in datos if "symbol" in d]
        # Prueba rápida con un solo batch de BATCH_SIZE simbolos
        simbolos = todos_simbolos[:BATCH_SIZE]
        print(f"\n[Barras M1 batch] Probando {len(simbolos)} simbolos...")

        barras = _cargar_barras_batch(simbolos, "M1", BARS_M1)

        print(
            f"[Barras M1 batch] Solicitados: {len(simbolos)}, "
            f"con datos: {len(barras)}, "
            f"sin datos: {len(simbolos) - len(barras)}"
        )
        if barras:
            primer_sym = next(iter(barras))
            primer_vela = barras[primer_sym][0]
            print(f"  Ejemplo {primer_sym}: {len(barras[primer_sym])} velas, primera={primer_vela}")

        assert len(barras) > 0, (
            "Ningun simbolo retorno barras M1. "
            "Verificar endpoint POST /api/marketdata/historical/batch"
        )

    def test_filtros_screenshot_con_datos_reales_m1(self):
        """
        SIMULACIÓN COMPLETA: obtiene barras M1 reales y aplica los 3 filtros.

        Filtros (exactamente como en la imagen):
          • AVERAGE_VOLUME > 50 000       (timeframe M1)
          • ATR(14, EMA)   > 0.15         (timeframe M1)
          • PERCENTAGE_RANGE > 2 %        (timeframe M1)
        """
        # 1. Obtener TODOS los símbolos de todos los mercados
        datos = _api_get("/api/marketdata/symbols", markets=",".join(MERCADOS))
        todos_simbolos = [d["symbol"] for d in datos if "symbol" in d]
        print(f"\n[Simulacion] {len(todos_simbolos)} simbolos totales ({', '.join(MERCADOS)})")
        print(f"[Simulacion] Cargando barras M1 en batches de {BATCH_SIZE}...")

        # 2. Cargar barras M1 vía batch POST para TODOS los símbolos
        simbolos_con_data = _cargar_barras_batch(todos_simbolos, "M1", BARS_M1)

        if not simbolos_con_data:
            pytest.skip("Ningun simbolo retorno barras M1 via batch POST")

        print(f"[Simulacion] {len(simbolos_con_data)} de {len(todos_simbolos)} simbolos con barras M1")

        # 3. Construir contextos
        contextos = _contextos_desde_barras(simbolos_con_data)

        # 4. Construir filtros (screenshot)
        filtros_ser = _construir_filtros_screenshot()

        # 5. Evaluar
        senales = evaluar_simbolos(contextos, filtros_ser, 1, "volatilidad y flexibilidad")
        simbolos_que_pasan = [s["symbol"] for s in senales]

        # 6. Reporte
        SEP = "=" * 60
        SEP2 = "-" * 60
        print(f"\n{SEP}")
        print(f"RESULTADO SIMULACION  --  Escaner: volatilidad y flexibilidad")
        print(f"Timeframe: M1  |  Mercados: {', '.join(MERCADOS)}  |  Barras: {BARS_M1}")
        print(SEP2)
        print(f"Filtros aplicados:")
        print(f"  1. AVERAGE_VOLUME   > 50 000")
        print(f"  2. ATR(14)          > 0.15")
        print(f"  3. PERCENTAGE_RANGE > 2%")
        print(SEP2)
        print(f"Simbolos evaluados:     {len(contextos)}")
        print(f"Simbolos que PASAN:     {len(simbolos_que_pasan)}")
        print(f"Simbolos que NO pasan:  {len(contextos) - len(simbolos_que_pasan)}")
        if simbolos_que_pasan:
            print(SEP2)
            print(f"Simbolos que pasan los 3 filtros:")
            for sym in sorted(simbolos_que_pasan):
                senal = next(s for s in senales if s["symbol"] == sym)
                precio = senal.get("precioDeteccion", "N/A")
                volumen = senal.get("volumenDeteccion", "N/A")
                print(f"  {sym:10s}  precio={precio}  volumen={volumen}")
        print(SEP)

        # 7. Assertions de sanidad
        assert len(contextos) > 0, "No hubo contextos para evaluar"
        tasa_aprobacion = len(simbolos_que_pasan) / len(contextos)
        assert tasa_aprobacion < 0.8, (
            f"El {tasa_aprobacion:.0%} de los simbolos pasa los filtros -- "
            "parece que los filtros no estan funcionando (demasiado permisivos)"
        )
        print(f"\nOK Tasa de aprobacion: {tasa_aprobacion:.1%} (esperado < 80%)")

    def test_simbolo_sin_barras_es_excluido(self):
        """Un símbolo con DataFrame vacío es excluido (evaluar_simbolos hace continue)."""
        contextos = {
            "VACIO": {
                "symbol": "VACIO",
                "barras": {col: [] for col in ["open", "high", "low", "close", "volume"]},
                "ultima_vela_timestamp": "",
            }
        }
        filtros_ser = _construir_filtros_screenshot()
        # evaluar_simbolos hace `if df.empty: continue` → el símbolo no genera señal
        senales = evaluar_simbolos(contextos, filtros_ser, 1, "test excluir vacio")
        assert len(senales) == 0, (
            "Un símbolo sin barras debe ser excluido, no generar señal"
        )
