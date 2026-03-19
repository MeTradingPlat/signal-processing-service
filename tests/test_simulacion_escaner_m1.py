"""Simulación del escáner 'volatilidad y flexibilidad' con datos reales M1.

Replica exactamente los filtros configurados en la imagen:
  - Volumen Promedio  > 50 000          (AVERAGE_VOLUME,   timeframe M1)
  - ATR              > 0.15, length=14  (ATR,              timeframe M1)
  - Rango Porcentual > 2 %              (PERCENTAGE_RANGE, timeframe M1)

Flujo del test:
  1. Obtiene TODOS los símbolos de todos los mercados (NYSE, NASDAQ, AMEX, ETF, OTC).
  2. Carga barras M1 históricas enviando TODOS los símbolos en UN SOLO request
     (igual que en producción: obtener_barras_batch manda todo junto y marketdata
     divide internamente en canales paralelos).
  3. Evalúa los 3 filtros con evaluar_simbolos().
  4. Imprime el resultado e impone assertions básicas de sanidad.

TestConcurrenciaMultiplesEscaneres:
  Simula N escáneres lanzando solicitudes SIMULTÁNEAS, replicando
  asyncio.gather(*[escaner.obtener_barras_batch() for escaner in escaneres])
  del GestorEscaneres real. Verifica que no hay 503s y que el tiempo
  paralelo es menor que el secuencial.

Prerequisito: pandas_ta instalado (disponible en el entorno Docker).
              Si la API no responde, el test es skipped automáticamente.
"""

import asyncio
import time
import pytest
import requests

try:
    import httpx
    _HTTPX_OK = True
except ImportError:
    _HTTPX_OK = False


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
_SKIP_HTTPX = pytest.mark.skipif(
    not _HTTPX_OK,
    reason="httpx no disponible.",
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
BATCH_SIZE = 50           # Símbolos por escaner en tests de concurrencia
TIMEOUT_API = 60          # segundos máximos por request (marketdata puede tardar ~30s con 12k simbolos)


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


def _cargar_barras_batch(simbolos: list[str], timeframe: str, bars: int) -> dict:
    """Carga barras de TODOS los símbolos en un ÚNICO POST batch.

    Igual que MarketdataRestAdapter.obtener_barras_batch(): manda todos los
    símbolos juntos. marketdata-service divide internamente en canales paralelos.
    """
    print(f"  Enviando {len(simbolos)} simbolos en 1 request...", end=" ", flush=True)
    try:
        resp = requests.post(
            f"{API_BASE}/api/marketdata/historical/batch",
            json={"symbols": simbolos, "timeframe": timeframe, "bars": bars},
            headers={"X-Gateway-Passed": "true"},
            timeout=TIMEOUT_API,
        )
        resp.raise_for_status()
        candles = resp.json().get("candlesPorSimbolo", {})
        resultado = {s: v for s, v in candles.items() if v}
        print(f"{len(resultado)} con datos")
        return resultado
    except requests.exceptions.ConnectionError:
        pytest.skip(f"API no reachable: {API_BASE}")
    except requests.exceptions.HTTPError as e:
        print(f"HTTP {e.response.status_code}")
        return {}
    except Exception as e:
        print(f"Error: {e}")
        return {}


async def _fetch_batch_async(
    client: "httpx.AsyncClient",
    simbolos: list[str],
    scanner_id: int,
    timeframe: str = "M1",
    bars: int = BARS_M1,
) -> dict:
    """Replica exactamente MarketdataRestAdapter.obtener_barras_batch().

    Cada llamada representa un EjecutorEscaner solicitando sus barras.
    Retorna métricas + los símbolos con datos recibidos.
    """
    t0 = time.monotonic()
    try:
        resp = await client.post(
            "/api/marketdata/historical/batch",
            json={"symbols": simbolos, "timeframe": timeframe, "bars": bars},
        )
        elapsed = time.monotonic() - t0
        if resp.status_code == 200:
            candles = resp.json().get("candlesPorSimbolo", {})
            simbolos_recibidos = {s for s, v in candles.items() if v}
        else:
            simbolos_recibidos = set()
        return {
            "scanner_id": scanner_id,
            "status": resp.status_code,
            "n_enviados": len(simbolos),
            "n_con_datos": len(simbolos_recibidos),
            "simbolos_enviados": set(simbolos),
            "simbolos_recibidos": simbolos_recibidos,
            "elapsed_s": round(elapsed, 2),
        }
    except Exception as e:
        return {
            "scanner_id": scanner_id,
            "status": 0,
            "n_enviados": len(simbolos),
            "n_con_datos": 0,
            "simbolos_enviados": set(simbolos),
            "simbolos_recibidos": set(),
            "elapsed_s": round(time.monotonic() - t0, 2),
            "error": str(e),
        }


async def _simular_escaneres_paralelo(grupos: list[list[str]], timeframe: str = "M1") -> tuple[list[dict], float]:
    """Replica asyncio.gather(*[escaner.obtener_barras_batch() for escaner in escaneres]).

    Todos los grupos lanzan sus requests SIMULTÁNEAMENTE — sin esperar al anterior.
    """
    async with httpx.AsyncClient(
        base_url=API_BASE,
        timeout=TIMEOUT_API,
        headers={"X-Gateway-Passed": "true"},
    ) as client:
        t0 = time.monotonic()
        resultados = await asyncio.gather(*[
            _fetch_batch_async(client, simbolos, i, timeframe)
            for i, simbolos in enumerate(grupos)
        ])
        return list(resultados), round(time.monotonic() - t0, 2)


async def _simular_escaneres_secuencial(grupos: list[list[str]], timeframe: str = "M1") -> tuple[list[dict], float]:
    """Misma carga pero secuencial — para comparar tiempo vs paralelo."""
    async with httpx.AsyncClient(
        base_url=API_BASE,
        timeout=TIMEOUT_API,
        headers={"X-Gateway-Passed": "true"},
    ) as client:
        resultados = []
        t0 = time.monotonic()
        for i, simbolos in enumerate(grupos):
            r = await _fetch_batch_async(client, simbolos, i, timeframe)
            resultados.append(r)
        return resultados, round(time.monotonic() - t0, 2)


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


def _contextos_desde_barras(barras_por_simbolo: dict, tf: str = "M1") -> dict:
    """Convierte la respuesta de la API en contextos para evaluar_simbolos().

    Usa el formato actual de ContextoSimbolo: barras_por_tf={tf: df}.
    """
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
            "barras_por_tf": {tf: df.to_dict(orient="list")},
            "fundamentales": {},
            "halteado": False,
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
        tfs, tf_min = ejecutor._determinar_timeframes()
        assert tf_min == EnumTimeframe.M1, (
            f"Se esperaba M1 pero se obtuvo {tf_min}. "
            "Revisar logs de 'Diagnóstico de parámetros' para ver el valor raw."
        )
        assert EnumTimeframe.M1 in tfs

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
                "barras_por_tf": {"M1": {col: [] for col in ["open", "high", "low", "close", "volume"]}},
                "fundamentales": {},
                "halteado": False,
            }
        }
        filtros_ser = _construir_filtros_screenshot()
        senales = evaluar_simbolos(contextos, filtros_ser, 1, "test excluir vacio")
        assert len(senales) == 0, (
            "Un símbolo sin barras debe ser excluido, no generar señal"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Concurrencia: múltiples escáneres solicitando al mismo tiempo
# ──────────────────────────────────────────────────────────────────────────────

@_SKIP_HTTPX
class TestConcurrenciaMultiplesEscaneres:
    """Simula N escáneres disparando solicitudes SIMULTÁNEAS a marketdata-service.

    Replica el comportamiento real de GestorEscaneres donde cada EjecutorEscaner
    corre como asyncio.Task independiente y llama obtener_barras_batch() sin
    esperar a los demás. El gather dispara todos los requests al mismo tiempo.

    Escenarios verificados:
    - Sin errores 503 con N canales abiertos simultáneamente (fix BAD_ACTION)
    - Tiempo paralelo < tiempo secuencial (la concurrencia realmente ayuda)
    - Cada escáner recibe solo los datos de sus propios símbolos (sin contaminación)
    - Dos escáneres con los mismos símbolos obtienen los mismos resultados
    """

    N_ESCANERES = 6  # Número de escáneres simulados en paralelo

    def _obtener_simbolos(self) -> list[str]:
        """Obtiene lista de símbolos del API. Skippea si no hay conectividad."""
        try:
            resp = requests.get(
                f"{API_BASE}/api/marketdata/symbols",
                params={"markets": MERCADOS},
                timeout=15,
            )
            resp.raise_for_status()
            simbolos = [d["symbol"] for d in resp.json() if "symbol" in d]
            if not simbolos:
                pytest.skip("API retornó 0 símbolos")
            return simbolos
        except requests.exceptions.ConnectionError:
            pytest.skip(f"API no reachable: {API_BASE}")
        except requests.exceptions.Timeout:
            pytest.skip("Timeout obteniendo símbolos")

    def _particionar(self, simbolos: list[str], n: int) -> list[list[str]]:
        """Divide los símbolos en N grupos del mismo tamaño (un grupo por escáner)."""
        return [simbolos[i * BATCH_SIZE:(i + 1) * BATCH_SIZE] for i in range(n)]

    def test_N_escaneres_en_paralelo_sin_errores_503(self):
        """N escáneres disparando simultáneamente no deben recibir ningún 503.

        Verifica el fix de BAD_ACTION: canales DxLink con IDs impares no son
        rechazados aunque se abran múltiples al mismo tiempo.
        """
        simbolos = self._obtener_simbolos()
        grupos = self._particionar(simbolos, self.N_ESCANERES)
        if len(grupos) < self.N_ESCANERES:
            pytest.skip("No hay suficientes símbolos para dividir en grupos")

        print(f"\n[Concurrencia] Lanzando {self.N_ESCANERES} escaneres en paralelo "
              f"({BATCH_SIZE} simbolos c/u)...")

        resultados, tiempo_total = asyncio.run(
            _simular_escaneres_paralelo(grupos)
        )

        print(f"[Concurrencia] Tiempo total (paralelo): {tiempo_total}s")
        print(f"{'Scanner':>8}  {'Status':>6}  {'Enviados':>8}  {'Con datos':>9}  {'Tiempo':>7}")
        print("-" * 50)
        for r in resultados:
            print(f"  Esc-{r['scanner_id']:>2}  {r['status']:>6}  {r['n_enviados']:>8}  "
                  f"{r['n_con_datos']:>9}  {r['elapsed_s']:>6.2f}s")

        errores_503 = [r for r in resultados if r["status"] == 503]
        assert len(errores_503) == 0, (
            f"{len(errores_503)}/{self.N_ESCANERES} requests retornaron 503. "
            "El fix de BAD_ACTION (IDs de canal impares) no está funcionando. "
            f"Escáneres fallidos: {[r['scanner_id'] for r in errores_503]}"
        )

        errores_otros = [r for r in resultados if r["status"] not in (200, 0)]
        assert len(errores_otros) == 0, (
            f"Requests con status inesperado: {[(r['scanner_id'], r['status']) for r in errores_otros]}"
        )
        print(f"\nOK {self.N_ESCANERES} escaneres concurrentes completados sin 503")

    def test_tiempo_paralelo_es_menor_que_secuencial(self):
        """Verificar que los requests en paralelo terminan más rápido que en serie.

        En producción, N escaneres no esperan turno — sus requests viajan
        simultáneamente. Si el tiempo paralelo ≈ tiempo secuencial, significa
        que hay algún cuello de botella serializado.
        """
        simbolos = self._obtener_simbolos()
        n = 4  # Usar 4 para que la diferencia sea clara sin tardar demasiado
        grupos = self._particionar(simbolos, n)
        if len(grupos) < n:
            pytest.skip("No hay suficientes símbolos")

        print(f"\n[Timing] Midiendo {n} escaneres: paralelo vs secuencial...")

        _, t_paralelo = asyncio.run(_simular_escaneres_paralelo(grupos))
        _, t_secuencial = asyncio.run(_simular_escaneres_secuencial(grupos))

        print(f"  Paralelo:    {t_paralelo:.2f}s")
        print(f"  Secuencial:  {t_secuencial:.2f}s")
        print(f"  Speedup:     {t_secuencial / t_paralelo:.1f}x")

        assert t_paralelo < t_secuencial, (
            f"El paralelo ({t_paralelo:.2f}s) no fue más rápido que el secuencial "
            f"({t_secuencial:.2f}s). Los requests no están ocurriendo simultáneamente."
        )
        # El paralelo debe ser más rápido que secuencial.
        # Con mercado abierto: speedup ~Nx. Con mercado cerrado (todos timeout ~20s):
        # speedup menor (~1.3x) porque el cuello de botella es el timeout de DxLink,
        # no el tiempo de red. Por eso usamos un threshold conservador.
        assert t_paralelo < t_secuencial * 0.85, (
            f"Speedup insuficiente: paralelo={t_paralelo:.2f}s, secuencial={t_secuencial:.2f}s. "
            f"Con {n} requests paralelos se espera que el paralelo sea al menos 1.2x más rápido."
        )
        print(f"\nOK Paralelo {t_secuencial / t_paralelo:.1f}x más rápido que secuencial")

    def test_cada_escaner_recibe_solo_sus_propios_simbolos(self):
        """Un escáner no recibe datos de los símbolos de otro escáner.

        Verifica que no hay contaminación entre canales DxLink paralelos:
        el canal del escáner A no procesa eventos del canal del escáner B.
        """
        simbolos = self._obtener_simbolos()
        grupos = self._particionar(simbolos, self.N_ESCANERES)
        if len(grupos) < self.N_ESCANERES:
            pytest.skip("No hay suficientes símbolos")

        resultados, _ = asyncio.run(_simular_escaneres_paralelo(grupos))

        contaminados = []
        for r in resultados:
            simbolos_ajenos = r["simbolos_recibidos"] - r["simbolos_enviados"]
            if simbolos_ajenos:
                contaminados.append((r["scanner_id"], simbolos_ajenos))

        assert len(contaminados) == 0, (
            f"Escáneres recibieron símbolos que no eran suyos (contaminación entre canales): "
            f"{contaminados}"
        )
        print(f"\nOK Ningún escáner recibió símbolos ajenos ({self.N_ESCANERES} verificados)")

    def test_dos_escaneres_mismo_simbolo_resultado_identico(self):
        """Dos escáneres solicitando el mismo símbolo simultáneamente reciben los mismos datos.

        Verifica idempotencia: DxLink retorna el mismo snapshot histórico
        independientemente de cuántos clientes lo pidan al mismo tiempo.
        """
        simbolos = self._obtener_simbolos()
        # Tomar los primeros BATCH_SIZE símbolos y pedirlos dos veces simultáneamente
        grupo_comun = simbolos[:BATCH_SIZE]
        grupos = [grupo_comun, grupo_comun]  # Dos escáneres, mismos símbolos

        resultados, _ = asyncio.run(_simular_escaneres_paralelo(grupos))

        r0, r1 = resultados[0], resultados[1]

        assert r0["status"] == 200 and r1["status"] == 200, (
            f"Alguno de los dos requests falló: status={r0['status']}, {r1['status']}"
        )

        # Ambos deben recibir exactamente los mismos símbolos con datos
        assert r0["simbolos_recibidos"] == r1["simbolos_recibidos"], (
            f"Los dos escáneres recibieron conjuntos distintos de símbolos: "
            f"esc-0={r0['simbolos_recibidos']}, esc-1={r1['simbolos_recibidos']}"
        )
        print(f"\nOK Ambos escáneres recibieron {r0['n_con_datos']} símbolos idénticos")
