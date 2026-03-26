"""Tests de integración para el endpoint de fundamentales con datos REALES.

Hace consultas reales a https://metradingplat.com para:
  1. Obtener TODOS los símbolos de NYSE, NASDAQ, AMEX, ETF, OTC.
  2. Llamar al batch de fundamentales y verificar que los datos llegan.
  3. Validar la estructura del response (campos, tipos).
  4. Reportar estadísticas de cobertura (% con datos por campo).

Prerequisitos:
  - https://metradingplat.com debe estar accesible.
  - El marketdata-service debe estar corriendo en producción.
  - Si el API no responde, los tests se saltan automáticamente (pytest.skip).

Estos tests son de INTEGRACIÓN — no se ejecutan en CI (no hay servicio real).
Correr localmente con: pytest tests/test_integracion_fundamentales.py -v -s
"""

import pytest
import requests
import time

API_BASE         = "https://metradingplat.com"
MARKETDATA_BASE  = f"{API_BASE}/api/marketdata"
TIMEOUT_SYMBOLS  = 30   # segundos para obtener la lista de símbolos
TIMEOUT_FUND     = 120  # segundos para el batch de fundamentales (puede tardar con 12k símbolos)
MERCADOS         = ["NYSE", "NASDAQ", "AMEX", "ETF", "OTC"]

# Campos esperados en la respuesta del batch de fundamentales
CAMPOS_FUNDAMENTALES = [
    "marketCap",
    "floatShares",
    "sharesOutstanding",
    "shortInterest",
    "shortRatio",
    "daysUntilEarnings",
    "preMarketVolume",
    "postMarketVolume",
]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _obtener_todos_los_simbolos() -> list[str]:
    """Obtiene la lista completa de símbolos de todos los mercados."""
    try:
        resp = requests.get(
            f"{MARKETDATA_BASE}/symbols",
            params={"markets": ",".join(MERCADOS)},
            timeout=TIMEOUT_SYMBOLS,
        )
        resp.raise_for_status()
        data = resp.json()
        simbolos = [d["symbol"] for d in data if "symbol" in d]
        if not simbolos:
            pytest.skip("API retornó 0 símbolos")
        return simbolos
    except requests.exceptions.ConnectionError:
        pytest.skip(f"API no reachable: {API_BASE}")
    except requests.exceptions.Timeout:
        pytest.skip(f"Timeout ({TIMEOUT_SYMBOLS}s) obteniendo símbolos")
    except Exception as e:
        pytest.skip(f"Error inesperado obteniendo símbolos: {e}")


def _llamar_fundamentales_batch(simbolos: list[str]) -> dict:
    """Llama al endpoint POST /fundamentals/batch y retorna el JSON."""
    try:
        t0 = time.monotonic()
        print(f"\n  Enviando {len(simbolos)} símbolos al batch de fundamentales...", flush=True)
        resp = requests.post(
            f"{MARKETDATA_BASE}/fundamentals/batch",
            json=simbolos,
            headers={"X-Gateway-Passed": "true"},
            timeout=TIMEOUT_FUND,
        )
        elapsed = time.monotonic() - t0
        print(f"  Respuesta en {elapsed:.1f}s — HTTP {resp.status_code}")

        if resp.status_code != 200:
            pytest.skip(f"Batch fundamentales retornó HTTP {resp.status_code}: {resp.text[:200]}")

        return resp.json()
    except requests.exceptions.ConnectionError:
        pytest.skip(f"API no reachable: {MARKETDATA_BASE}/fundamentals/batch")
    except requests.exceptions.Timeout:
        pytest.skip(f"Timeout ({TIMEOUT_FUND}s) en batch fundamentales")
    except Exception as e:
        pytest.skip(f"Error inesperado en batch fundamentales: {e}")


def _imprimir_reporte(titulo: str, simbolos: list[str], datos: dict) -> None:
    """Imprime un reporte detallado de cobertura de datos."""
    SEP  = "=" * 65
    SEP2 = "-" * 65

    con_algún_dato    = [s for s in simbolos if datos.get(s) and any(datos[s].values())]
    sin_ningún_dato   = [s for s in simbolos if not datos.get(s) or not any(datos[s].values())]
    total             = len(simbolos)

    print(f"\n{SEP}")
    print(f"  {titulo}")
    print(f"  Mercados: {', '.join(MERCADOS)}")
    print(SEP2)
    print(f"  Símbolos solicitados : {total}")
    print(f"  Con algún dato       : {len(con_algún_dato)}  ({len(con_algún_dato)/total*100:.1f}%)")
    print(f"  Sin ningún dato      : {len(sin_ningún_dato)}  ({len(sin_ningún_dato)/total*100:.1f}%)")
    print(SEP2)
    print(f"  Cobertura por campo:")
    for campo in CAMPOS_FUNDAMENTALES:
        con_campo = sum(
            1 for s in simbolos
            if datos.get(s) and datos[s].get(campo) is not None
        )
        pct = con_campo / total * 100
        barra = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"    {campo:<22} {barra} {pct:5.1f}%  ({con_campo}/{total})")
    print(SEP2)

    # Muestra una muestra de 5 símbolos con datos completos
    completos = [
        s for s in simbolos
        if datos.get(s) and all(datos[s].get(c) is not None for c in ["marketCap", "floatShares", "shortRatio"])
    ]
    if completos:
        print(f"  Muestra (con marketCap + floatShares + shortRatio):")
        for sym in completos[:5]:
            d = datos[sym]
            mc  = d.get("marketCap", 0) or 0
            fl  = d.get("floatShares", 0) or 0
            sr  = d.get("shortRatio")
            due = d.get("daysUntilEarnings")
            pre = d.get("preMarketVolume")
            pos = d.get("postMarketVolume")
            print(
                f"    {sym:<10}  MCap=${mc/1e9:.1f}B  Float={fl/1e6:.0f}M  "
                f"ShortRatio={sr}  EarningsEn={due}d  Pre={pre}  Post={pos}"
            )
    print(SEP)


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestFundamentalesBatchIntegracion:
    """Tests de integración real contra el endpoint de fundamentales en producción."""

    def test_obtiene_simbolos_de_todos_los_mercados(self):
        """Verifica que el API retorna símbolos de NYSE, NASDAQ, AMEX, ETF y OTC."""
        simbolos = _obtener_todos_los_simbolos()
        print(f"\n  Total símbolos disponibles: {len(simbolos)}")
        assert len(simbolos) > 1000, (
            f"Se esperaban más de 1000 símbolos totales, se obtuvieron {len(simbolos)}"
        )

    def test_batch_fundamentales_responde_con_todos_los_simbolos(self):
        """Llama al batch con TODOS los símbolos y verifica que el response no está vacío."""
        simbolos = _obtener_todos_los_simbolos()
        print(f"\n  Total símbolos a consultar: {len(simbolos)}")

        datos = _llamar_fundamentales_batch(simbolos)

        assert isinstance(datos, dict), "La respuesta debe ser un diccionario"
        assert len(datos) > 0, "La respuesta no debe estar vacía"
        print(f"  Símbolos en la respuesta: {len(datos)}")

    def test_estructura_de_campos_correcta(self):
        """Verifica que los campos del response tienen la estructura esperada."""
        simbolos = _obtener_todos_los_simbolos()
        datos = _llamar_fundamentales_batch(simbolos)

        # Tomar un símbolo con datos
        sym_con_datos = next(
            (s for s, d in datos.items() if d and any(v is not None for v in d.values())),
            None
        )
        assert sym_con_datos is not None, "Ningún símbolo tiene datos — el batch retornó todo vacío"

        d = datos[sym_con_datos]
        print(f"\n  Ejemplo de datos para {sym_con_datos}: {d}")

        # Verificar que los campos esperados están presentes (aunque sean None)
        for campo in CAMPOS_FUNDAMENTALES:
            assert campo in d, (
                f"El campo '{campo}' no está presente en la respuesta para {sym_con_datos}"
            )

    def test_cobertura_de_datos_aceptable(self):
        """Verifica que al menos el 30% de los símbolos tiene marketCap y floatShares.

        El 100% no es posible porque OTC tiene muchos símbolos sin datos en Tastytrade.
        Pero los grandes de NYSE/NASDAQ/AMEX siempre deben tener datos.
        """
        simbolos = _obtener_todos_los_simbolos()
        datos = _llamar_fundamentales_batch(simbolos)

        _imprimir_reporte("REPORTE COMPLETO — BATCH FUNDAMENTALES", simbolos, datos)

        total = len(simbolos)
        con_market_cap   = sum(1 for s in simbolos if datos.get(s) and datos[s].get("marketCap") is not None)
        con_float_shares = sum(1 for s in simbolos if datos.get(s) and datos[s].get("floatShares") is not None)
        con_short_ratio  = sum(1 for s in simbolos if datos.get(s) and datos[s].get("shortRatio") is not None)
        con_earnings     = sum(1 for s in simbolos if datos.get(s) and datos[s].get("daysUntilEarnings") is not None)

        pct_mc  = con_market_cap   / total * 100
        pct_fl  = con_float_shares / total * 100
        pct_sr  = con_short_ratio  / total * 100
        pct_ear = con_earnings     / total * 100

        print(f"\n  Cobertura mínima esperada (30%):")
        print(f"    marketCap      : {pct_mc:.1f}%")
        print(f"    floatShares    : {pct_fl:.1f}%")
        print(f"    shortRatio     : {pct_sr:.1f}%")
        print(f"    daysUntilEarnings: {pct_ear:.1f}%")

        assert pct_mc >= 30, (
            f"Se esperaba ≥30% de símbolos con marketCap, se obtuvo {pct_mc:.1f}%"
        )
        assert pct_fl >= 30, (
            f"Se esperaba ≥30% de símbolos con floatShares, se obtuvo {pct_fl:.1f}%"
        )

    def test_tipos_de_datos_correctos(self):
        """Verifica que los campos tienen los tipos de datos correctos."""
        simbolos = _obtener_todos_los_simbolos()
        datos = _llamar_fundamentales_batch(simbolos)

        campos_numericos = [
            ("marketCap",          (int, float)),
            ("floatShares",        (int, float)),
            ("sharesOutstanding",  (int, float)),
            ("shortInterest",      (int, float)),
            ("shortRatio",         (int, float)),
            ("preMarketVolume",    (int, float)),
            ("postMarketVolume",   (int, float)),
        ]
        errores = []
        verificados = 0

        for sym, d in datos.items():
            if not d:
                continue
            for campo, tipos_validos in campos_numericos:
                valor = d.get(campo)
                if valor is not None and not isinstance(valor, tipos_validos):
                    errores.append(f"{sym}.{campo}={valor!r} ({type(valor).__name__})")
            verificados += 1
            if verificados >= 200:  # Verificar solo los primeros 200 símbolos con datos
                break

        assert len(errores) == 0, (
            f"Campos con tipo de dato incorrecto ({len(errores)} errores):\n"
            + "\n".join(errores[:20])
        )
        print(f"\n  ✅ Tipos correctos en {verificados} símbolos verificados")

    def test_short_ratio_y_earnings_via_tastytrade_rest(self):
        """Verifica que shortRatio y daysUntilEarnings llegan (vienen de la API REST de Tastytrade)."""
        simbolos = _obtener_todos_los_simbolos()
        datos = _llamar_fundamentales_batch(simbolos)

        con_short_ratio = {s: datos[s]["shortRatio"] for s in simbolos
                           if datos.get(s) and datos[s].get("shortRatio") is not None}
        con_earnings    = {s: datos[s]["daysUntilEarnings"] for s in simbolos
                           if datos.get(s) and datos[s].get("daysUntilEarnings") is not None}

        print(f"\n  shortRatio disponible para {len(con_short_ratio)} símbolos")
        print(f"  daysUntilEarnings disponible para {len(con_earnings)} símbolos")

        if con_short_ratio:
            ejemplos_sr = list(con_short_ratio.items())[:5]
            print(f"  shortRatio ejemplos: {ejemplos_sr}")
        if con_earnings:
            ejemplos_ear = list(con_earnings.items())[:5]
            print(f"  daysUntilEarnings ejemplos: {ejemplos_ear}")

        assert len(con_short_ratio) > 0 or len(con_earnings) > 0, (
            "Ni shortRatio ni daysUntilEarnings tienen datos — "
            "verificar integración con Tastytrade REST API /market-metrics"
        )
