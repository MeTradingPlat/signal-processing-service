"""Adaptador para datos fundamentales — Extracción MASIVA vía marketdata-service.

Consume el endpoint batch del marketdata-service para obtener Market Cap, 
Float, Short Interest y Earnings de forma oficial y eficiente.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import random
import re
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx

_SYMBOL_MAPPING = {}
_MAPPING_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "symbol_mapping.json")
try:
    if os.path.exists(_MAPPING_PATH):
        with open(_MAPPING_PATH, "r", encoding="utf-8") as _f:
            _SYMBOL_MAPPING = json.load(_f)
except Exception:
    pass

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/119.0",
]

_ET = ZoneInfo("America/New_York")
_MERCADOS_SIN_FUNDAMENTALES = {"CRYPTO", "FOREX"}

_SIMBOLOS_MALOS: set[str] = set()

_RE_WARRANT  = re.compile(r"/WS(/|$)")
_RE_UNIT     = re.compile(r"/U(/|$)")
_RE_RIGHTS   = re.compile(r"[A-Z]r$")
_RE_TEST     = re.compile(r"^(ATEST|NTEST|PTEST|CTEST)(/|$)|^(ZVZZT|ZJZZT|ZWZZT)$")

def _sin_fundamentales(symbol: str) -> bool:
    return bool(
        _RE_WARRANT.search(symbol)
        or _RE_UNIT.search(symbol)
        or _RE_RIGHTS.search(symbol)
        or _RE_TEST.search(symbol)
    )

_MULTIPLICADORES: dict[str, float] = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "T": 1_000_000_000_000}

def _parse_finviz_numero(valor: str | None) -> float | None:
    if not valor or valor.strip() in ("-", "N/A", ""): return None
    try:
        v = valor.strip().replace(",", "")
        sufijo = v[-1].upper()
        if sufijo in _MULTIPLICADORES: return float(v[:-1]) * _MULTIPLICADORES[sufijo]
        return float(v)
    except (ValueError, IndexError): return None

def _parse_finviz_porcentaje(valor: str | None) -> float | None:
    if not valor or valor.strip() in ("-", "N/A", ""): return None
    try: return float(valor.strip().rstrip("%"))
    except ValueError: return None

def _normalizar_simbolo_yahoo(symbol: str) -> str:
    if symbol in _SYMBOL_MAPPING and "yfinance" in _SYMBOL_MAPPING[symbol]:
        return _SYMBOL_MAPPING[symbol]["yfinance"]
    s = symbol.replace("/", "-")
    if s.endswith("-U") and len(s) > 2: s = s + "N"
    m = re.match(r"^([A-Z]+)p([A-Z]{1,2})$", s)
    if m: return f"{m.group(1)}-P{m.group(2)}"
    m2 = re.match(r"^([A-Z]{2,})p$", s)
    if m2: return f"{m2.group(1)}-P"
    return s

def _normalizar_simbolo_finviz(symbol: str) -> str:
    if symbol in _SYMBOL_MAPPING and "finviz" in _SYMBOL_MAPPING[symbol]:
        return _SYMBOL_MAPPING[symbol]["finviz"]
    return symbol.replace("/", "-").replace(" ", "-")


# ─── NATIVE MARKETDATA-SERVICE ADAPTER (EX FINVIZ/YAHOO) ──────────────────────



# ─── YAHOO PRE/POST VOLUME (ProcessPoolExecutor) ──────────────────────────────

def _descargar_yfinance_volumen_sincrono(chunk: list[str]) -> dict[str, dict]:
    """Rutina bloqueante empacada pura ejecutada bajo proceso OS aislado para evadir el GIL Python."""
    import pandas as pd
    import yfinance as yf
    
    simbolos_yf = [_normalizar_simbolo_yahoo(s) for s in chunk if s not in _SIMBOLOS_MALOS]
    resultados = {}
    if not simbolos_yf: return resultados
    
    try:
        df = yf.download(
            " ".join(simbolos_yf), period="1d", interval="1m",
            prepost=True, auto_adjust=True, progress=False, threads=False
        )
        if df is None or df.empty: return {}
        
        now_et = datetime.now(_ET)
        market_open  = now_et.replace(hour=9,  minute=30, second=0, microsecond=0)
        market_close = now_et.replace(hour=16, minute=0,  second=0, microsecond=0)

        if len(simbolos_yf) == 1:
            df_sym = df
            if df_sym.index.tz is None:
                df_sym.index = df_sym.index.tz_localize("UTC").tz_convert(_ET)
            else:
                df_sym.index = df_sym.index.tz_convert(_ET)
            try:
                pre_vol  = int(df_sym.loc[df_sym.index < market_open, "Volume"].sum())
                post_vol = int(df_sym.loc[df_sym.index >= market_close, "Volume"].sum())
                resultados[chunk[0]] = {"pre_market_volume": pre_vol, "post_market_volume": post_vol}
            except Exception: pass
            return resultados

        if isinstance(df.columns, pd.MultiIndex):
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC").tz_convert(_ET)
            else:
                df.index = df.index.tz_convert(_ET)
                
            for orig, yf_s in zip(chunk, simbolos_yf):
                try:
                    if yf_s in df["Volume"]:
                        serie_vol = df["Volume"][yf_s]
                        pre_vol  = int(serie_vol.loc[serie_vol.index < market_open].sum())
                        post_vol = int(serie_vol.loc[serie_vol.index >= market_close].sum())
                        resultados[orig] = {"pre_market_volume": pre_vol, "post_market_volume": post_vol}
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"ProcessPool yf.download falló: {e}")
        
    return resultados

async def obtener_volumen_extendido_batch(simbolos: list[str], mercado: str) -> dict[str, dict]:
    """Interfáz asincrónica para obtener volumen sin pisar el hilo principal."""
    if mercado in _MERCADOS_SIN_FUNDAMENTALES or not simbolos:
        return {}
        
    simbolos_unicos = [s for s in dict.fromkeys(simbolos) if not _sin_fundamentales(s)]
    chunk_size = 500
    chunks = [simbolos_unicos[i:i+chunk_size] for i in range(0, len(simbolos_unicos), chunk_size)]
    
    resultados = {}
    loop = asyncio.get_running_loop()
    
    # Usar ProcessPoolExecutor asegura no violar la política "NO HILOS" en Python
    with ProcessPoolExecutor(max_workers=2) as pool:
        tareas = [
            loop.run_in_executor(pool, _descargar_yfinance_volumen_sincrono, c)
            for c in chunks
        ]
        for chunk_res in await asyncio.gather(*tareas):
            resultados.update(chunk_res)
            
    return resultados


# ─── API PÚBLICA ──────────────────────────────────────────────────────────────

def _escribir_reporte_fundamentales(mercado: str, resultados: dict[str, dict], campos: tuple) -> None:
    for base in ("/tmp/fundamentals_reports", "./reports/fundamentals"):
        try:
            os.makedirs(base, exist_ok=True)
            reporte_dir = base
            break
        except OSError:
            continue
    else: return

    fecha = datetime.now().strftime("%Y-%m-%d_%H%M")
    csv_path = os.path.join(reporte_dir, f"fundamentals_{mercado}_{fecha}.csv")
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
                    writer.writerow([sym, estado, *[datos.get(c, "") for c in campos], ",".join(faltantes_list)])

        with open(sin_datos_path, "w", encoding="utf-8") as f:
            sin_datos = sorted(s for s, v in resultados.items() if not v)
            f.write(f"# SIN DATOS — {mercado} — {fecha}\n\n" + "\n".join(sin_datos))
    except Exception: pass

async def obtener_fundamentales_batch(
    simbolos: list[str],
    mercado: str,
    *args, **kwargs
) -> dict[str, dict]:
    """Descarga de golpe (BULK) la data mediante marketdata-service (Tastytrade/dxLink)."""
    if mercado in _MERCADOS_SIN_FUNDAMENTALES or not simbolos:
        return {}

    simbolos_unicos = [s for s in dict.fromkeys(simbolos) if not _sin_fundamentales(s)]
    
    # El marketdata-service corre en el puerto 8082 según su configuración
    url = "http://localhost:8082/api/marketdata/fundamentals/batch"
    resultados = {}

    logger.info("Solicitando fundamentales batch a marketdata-service para %d símbolos...", len(simbolos_unicos))
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=simbolos_unicos)
            if resp.status_code == 200:
                data = resp.json()
                for sym, fund in data.items():
                    if not fund: continue
                    resultados[sym] = {
                        "market_cap":         fund.get("marketCap"),
                        "shares_outstanding": fund.get("sharesOutstanding"),
                        "float_shares":       fund.get("floatShares"),
                        "short_interest":     fund.get("shortInterest"),
                        "short_ratio":        fund.get("shortRatio"),
                        "days_until_earnings": fund.get("daysUntilEarnings"),
                    }
                logger.info("Recibidos %d perfiles desde marketdata-service.", len(resultados))
            else:
                logger.error("Error en marketdata-service fundamentals/batch: %d %s", resp.status_code, resp.text)
    except Exception as e:
        logger.error("Fallo al conectar con marketdata-service: %s", e)

    # Asegurar que todos los símbolos tengan una entrada (aunque esté vacía)
    for sym in simbolos_unicos:
        if sym not in resultados:
            resultados[sym] = {}

    _CAMPOS = ("float_shares", "shares_outstanding", "market_cap", "short_interest", "short_ratio", "days_until_earnings")
    _escribir_reporte_fundamentales(mercado, resultados, _CAMPOS)
    return resultados
