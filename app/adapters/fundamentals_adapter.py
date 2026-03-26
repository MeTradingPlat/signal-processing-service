"""Adaptador para datos fundamentales — Extracción MASIVA vía marketdata-service.

Consume el endpoint batch del marketdata-service (Tastytrade / dxLink) para
obtener Market Cap, Float, Short Interest, Earnings, y volumen pre/post-market
de forma oficial y eficiente, sin scraping externo.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime

import httpx

_SYMBOL_MAPPING: dict = {}
_MAPPING_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "symbol_mapping.json")
try:
    if os.path.exists(_MAPPING_PATH):
        with open(_MAPPING_PATH, "r", encoding="utf-8") as _f:
            _SYMBOL_MAPPING = json.load(_f)
except Exception:
    pass

logger = logging.getLogger(__name__)

_MERCADOS_SIN_FUNDAMENTALES = {"CRYPTO", "FOREX"}

_RE_WARRANT = re.compile(r"/WS(/|$)")
_RE_UNIT    = re.compile(r"/U(/|$)")
_RE_RIGHTS  = re.compile(r"[A-Z]r$")
_RE_TEST    = re.compile(r"^(ATEST|NTEST|PTEST|CTEST)(/|$)|^(ZVZZT|ZJZZT|ZWZZT)$")

_MARKETDATA_URL = os.getenv("MARKETDATA_SERVICE_URL", "http://localhost:8082")


def _sin_fundamentales(symbol: str) -> bool:
    return bool(
        _RE_WARRANT.search(symbol)
        or _RE_UNIT.search(symbol)
        or _RE_RIGHTS.search(symbol)
        or _RE_TEST.search(symbol)
    )


# ─── UTILIDADES PRIVADAS ──────────────────────────────────────────────────────

_MULTIPLICADORES: dict[str, float] = {
    "K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "T": 1_000_000_000_000
}


def _parse_finviz_numero(valor: str | None) -> float | None:
    """Mantiene compatibilidad con código legado que aún llame a esta función."""
    if not valor or valor.strip() in ("-", "N/A", ""):
        return None
    try:
        v = valor.strip().replace(",", "")
        sufijo = v[-1].upper()
        if sufijo in _MULTIPLICADORES:
            return float(v[:-1]) * _MULTIPLICADORES[sufijo]
        return float(v)
    except (ValueError, IndexError):
        return None


def _parse_finviz_porcentaje(valor: str | None) -> float | None:
    """Mantiene compatibilidad con código legado."""
    if not valor or valor.strip() in ("-", "N/A", ""):
        return None
    try:
        return float(valor.strip().rstrip("%"))
    except ValueError:
        return None


def _normalizar_simbolo_yahoo(symbol: str) -> str:
    """Mantiene compatibilidad con código legado."""
    if symbol in _SYMBOL_MAPPING and "yfinance" in _SYMBOL_MAPPING[symbol]:
        return _SYMBOL_MAPPING[symbol]["yfinance"]
    s = symbol.replace("/", "-")
    if s.endswith("-U") and len(s) > 2:
        s = s + "N"
    m = re.match(r"^([A-Z]+)p([A-Z]{1,2})$", s)
    if m:
        return f"{m.group(1)}-P{m.group(2)}"
    m2 = re.match(r"^([A-Z]{2,})p$", s)
    if m2:
        return f"{m2.group(1)}-P"
    return s


def _normalizar_simbolo_finviz(symbol: str) -> str:
    """Mantiene compatibilidad con código legado."""
    if symbol in _SYMBOL_MAPPING and "finviz" in _SYMBOL_MAPPING[symbol]:
        return _SYMBOL_MAPPING[symbol]["finviz"]
    return symbol.replace("/", "-").replace(" ", "-")


# ─── REPORTE CSV ──────────────────────────────────────────────────────────────

def _escribir_reporte_fundamentales(mercado: str, resultados: dict[str, dict], campos: tuple) -> None:
    import csv
    for base in ("/tmp/fundamentals_reports", "./reports/fundamentals"):
        try:
            os.makedirs(base, exist_ok=True)
            reporte_dir = base
            break
        except OSError:
            continue
    else:
        return

    fecha = datetime.now().strftime("%Y-%m-%d_%H%M")
    csv_path      = os.path.join(reporte_dir, f"fundamentals_{mercado}_{fecha}.csv")
    sin_datos_path = os.path.join(reporte_dir, f"fundamentals_{mercado}_{fecha}_sin_datos.txt")

    try:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["symbol", "estado", *campos, "campos_faltantes"])
            for sym in sorted(resultados.keys()):
                datos = resultados[sym]
                if not datos:
                    writer.writerow([sym, "SIN_DATOS", *["" for _ in campos], ",".join(campos)])
                else:
                    faltantes_list = [c for c in campos if datos.get(c) is None]
                    estado = "COMPLETO" if not faltantes_list else "PARCIAL"
                    writer.writerow(
                        [sym, estado, *[datos.get(c, "") for c in campos], ",".join(faltantes_list)]
                    )
        with open(sin_datos_path, "w", encoding="utf-8") as f:
            sin_datos = sorted(s for s, v in resultados.items() if not v)
            f.write(f"# SIN DATOS — {mercado} — {fecha}\n\n" + "\n".join(sin_datos))
    except Exception:
        pass


# ─── API PÚBLICA ──────────────────────────────────────────────────────────────

_CAMPOS = (
    "float_shares", "shares_outstanding", "market_cap",
    "short_interest", "short_ratio", "days_until_earnings",
    "pre_market_volume", "post_market_volume",
)


async def obtener_fundamentales_batch(
    simbolos: list[str],
    mercado: str,
    *args, **kwargs,
) -> dict[str, dict]:
    """Descarga de golpe (BULK) la data mediante marketdata-service (Tastytrade/dxLink).

    Incluye: market_cap, float_shares, shares_outstanding, short_interest,
             short_ratio, days_until_earnings, pre_market_volume, post_market_volume.
    """
    if mercado in _MERCADOS_SIN_FUNDAMENTALES or not simbolos:
        return {}

    simbolos_unicos = [s for s in dict.fromkeys(simbolos) if not _sin_fundamentales(s)]

    url = f"{_MARKETDATA_URL}/api/marketdata/fundamentals/batch"
    resultados: dict[str, dict] = {}

    logger.info(
        "Solicitando fundamentales batch a marketdata-service para %d símbolos...",
        len(simbolos_unicos),
    )

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=simbolos_unicos)
            if resp.status_code == 200:
                data = resp.json()
                for sym, fund in data.items():
                    if not fund:
                        continue
                    resultados[sym] = {
                        "market_cap":          fund.get("marketCap"),
                        "shares_outstanding":  fund.get("sharesOutstanding"),
                        "float_shares":        fund.get("floatShares"),
                        "short_interest":      fund.get("shortInterest"),
                        "short_ratio":         fund.get("shortRatio"),
                        "days_until_earnings": fund.get("daysUntilEarnings"),
                        "pre_market_volume":   fund.get("preMarketVolume"),
                        "post_market_volume":  fund.get("postMarketVolume"),
                    }
                logger.info("Recibidos %d perfiles desde marketdata-service.", len(resultados))
            else:
                logger.error(
                    "Error en marketdata-service fundamentals/batch: %d %s",
                    resp.status_code, resp.text,
                )
    except Exception as e:
        logger.error("Fallo al conectar con marketdata-service: %s", e)

    # Asegurar entrada vacía para símbolos sin datos
    for sym in simbolos_unicos:
        if sym not in resultados:
            resultados[sym] = {}

    _escribir_reporte_fundamentales(mercado, resultados, _CAMPOS)
    return resultados


async def obtener_volumen_extendido_batch(
    simbolos: list[str],
    mercado: str,
) -> dict[str, dict]:
    """Stub: el volumen extendido ahora viene incluido en obtener_fundamentales_batch.

    Se mantiene la firma para compatibilidad con FundamentalsCache que hace gather()
    de ambas corutinas. Retorna vacío porque el merge ya ocurrió en el batch principal.
    """
    return {}
