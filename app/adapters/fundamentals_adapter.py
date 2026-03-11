"""Adaptador para datos fundamentales — estrategia dual:

  PRIMARIO   : finvizfinance (float, shares_outstanding, market_cap,
                              short_interest, short_ratio)
               Cobertura óptima para NYSE / NASDAQ / AMEX.
  FALLBACK   : yfinance (para OTC / ETF con cobertura limitada en finviz,
                         o para campos que finviz devuelve como "-").
  EXCLUSIVO  : yfinance para days_until_earnings y volumen pre/post-market.
  SIN DATOS  : CRYPTO / FOREX → dict vacío (filtros permisivos).

Unidades estandarizadas (igual que scanner-management):
  float_shares        : acciones raw  (ej. 5_000_000 = 5M shares)
  shares_outstanding  : acciones raw
  market_cap          : dólares raw   (ej. 1_000_000_000 = $1B)
  short_interest      : % del float   (ej. 10.5 = 10.5 %)
  short_ratio         : días raw       (ej. 3.2 = 3.2 días para cubrir)
  days_until_earnings : días enteros  (ej. 15 = faltan 15 días)
  pre_market_volume   : acciones raw de la sesión pre-market (4:00–9:30 ET)
  post_market_volume  : acciones raw de la sesión post-market (16:00–20:00 ET)

Batch:
  - Finviz: ThreadPoolExecutor(max_workers=5) — límite menor por rate-limits de scraping
  - yfinance: ThreadPoolExecutor(max_workers=10) — más rápido, API oficial
  - Para 500 símbolos ~2-4 min al arranque (una vez/día)
  - El caché vive en memoria todo el día; los filtros leen en O(1)
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
_MAX_WORKERS_YFINANCE = 10
_MAX_WORKERS_FINVIZ = 5   # Menor por rate-limits del scraping de finviz
_MERCADOS_SIN_FUNDAMENTALES = {"CRYPTO", "FOREX"}

# Multiplicadores para parsear strings de finviz ("15.44B", "3.42T", etc.)
_MULTIPLICADORES: dict[str, float] = {
    "K": 1_000,
    "M": 1_000_000,
    "B": 1_000_000_000,
    "T": 1_000_000_000_000,
}


# ──────────────────────────────────────────────────────────────────────────────
# Parsers de strings de finviz
# ──────────────────────────────────────────────────────────────────────────────

def _parse_finviz_numero(valor: str | None) -> float | None:
    """Convierte strings de finviz a float raw.

    Ejemplos:
      '15.44B' → 15_440_000_000.0
      '3.42T'  → 3_420_000_000_000.0
      '500M'   → 500_000_000.0
      '2.5K'   → 2_500.0
      '2.5'    → 2.5
      '-'      → None
      'N/A'    → None
    """
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
    """Convierte '2.35%' → 2.35. Retorna None si '-', vacío o inválido."""
    if not valor or valor.strip() in ("-", "N/A", ""):
        return None
    try:
        return float(valor.strip().rstrip("%"))
    except ValueError:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Fuente primaria: finvizfinance
# ──────────────────────────────────────────────────────────────────────────────

def _fetch_fundamentales_finviz(symbol: str) -> tuple[str, dict]:
    """Obtiene fundamentales vía finvizfinance (fuente primaria). Thread-safe.

    Retorna dict vacío si el símbolo no está en finviz (OTC sin cobertura,
    error de red, etc.). En ese caso _fetch_info usará yfinance como fallback.
    """
    try:
        from finvizfinance.quote import finvizfinance  # type: ignore[import]

        f = finvizfinance(symbol).ticker_fundament()
        return symbol, {
            "float_shares":       _parse_finviz_numero(f.get("Float")),
            "shares_outstanding": _parse_finviz_numero(f.get("Shs Outstand")),
            "market_cap":         _parse_finviz_numero(f.get("Market Cap")),
            "short_interest":     _parse_finviz_porcentaje(f.get("Short Float")),
            "short_ratio":        _parse_finviz_numero(f.get("Short Ratio")),
        }
    except Exception as exc:
        logger.warning("Finviz error [%s]: %s", symbol, exc)
        return symbol, {}


# ──────────────────────────────────────────────────────────────────────────────
# Fuente secundaria / fallback: yfinance
# ──────────────────────────────────────────────────────────────────────────────

def _fetch_info_yfinance(symbol: str) -> tuple[str, dict]:
    """Obtiene fundamentales de un símbolo vía yfinance. Thread-safe."""
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        info = ticker.info or {}

        # short_interest: yfinance devuelve decimal (0.05 = 5%) → convertir a %
        short_pct_raw = info.get("shortPercentOfFloat")
        short_interest = round(float(short_pct_raw) * 100, 2) if short_pct_raw is not None else None

        # Earnings: intentar varias APIs de yfinance (cambian entre versiones)
        days_earnings = _calcular_dias_earnings(ticker, info)

        return symbol, {
            "float_shares":        info.get("floatShares"),
            "shares_outstanding":  info.get("sharesOutstanding"),
            "market_cap":          info.get("marketCap"),
            "short_interest":      short_interest,
            "short_ratio":         info.get("shortRatio"),
            "days_until_earnings": days_earnings,
        }
    except Exception as exc:
        logger.warning("yfinance error [%s]: %s", symbol, exc)
        return symbol, {}


def _calcular_dias_earnings(ticker, info: dict) -> int | None:
    """Extrae la fecha del próximo earnings y calcula días hasta él."""
    hoy = date.today()

    # Intento 1: info["nextEarningsDate"] (algunos tickers lo tienen)
    fecha_raw = info.get("nextEarningsDate") or info.get("earningsDate")
    if fecha_raw:
        try:
            if isinstance(fecha_raw, (int, float)):
                fecha = datetime.fromtimestamp(fecha_raw).date()
            elif isinstance(fecha_raw, datetime):
                fecha = fecha_raw.date()
            elif isinstance(fecha_raw, date):
                fecha = fecha_raw
            else:
                fecha = date.fromisoformat(str(fecha_raw)[:10])
            if fecha >= hoy:
                return (fecha - hoy).days
        except Exception:
            pass

    # Intento 2: ticker.calendar
    try:
        cal = ticker.calendar
        if cal is not None:
            # Puede ser dict o DataFrame según la versión
            if hasattr(cal, "get"):
                earnings_dates = cal.get("Earnings Date", [])
            elif hasattr(cal, "loc"):
                earnings_dates = cal.loc["Earnings Date"].tolist() if "Earnings Date" in cal.index else []
            else:
                earnings_dates = []

            for ed in (earnings_dates if hasattr(earnings_dates, "__iter__") else [earnings_dates]):
                if ed is None:
                    continue
                if hasattr(ed, "date"):
                    ed = ed.date()
                if isinstance(ed, date) and ed >= hoy:
                    return (ed - hoy).days
    except Exception:
        pass

    # Intento 3: ticker.earnings_dates (DataFrame con fechas históricas y futuras)
    try:
        ed_df = ticker.earnings_dates
        if ed_df is not None and not ed_df.empty:
            futuras = [
                idx.date() for idx in ed_df.index
                if hasattr(idx, "date") and idx.date() >= hoy
            ]
            if futuras:
                return (min(futuras) - hoy).days
    except Exception:
        pass

    return None


# ──────────────────────────────────────────────────────────────────────────────
# Orquestador: finviz primario + yfinance fallback
# ──────────────────────────────────────────────────────────────────────────────

def _fetch_info(symbol: str) -> tuple[str, dict]:
    """Fundamentales con estrategia dual: finviz primario + yfinance fallback.

    Lógica de prioridad:
    1. Llama a finviz y yfinance para cada símbolo.
    2. Base: yfinance (cobertura total, incluye OTC/ETF).
    3. Sobrescribir con finviz donde tenga datos no-None (más confiables).
    4. days_until_earnings: SIEMPRE de yfinance (finviz no lo provee).

    Para OTC/ETF sin cobertura en finviz: finviz retorna dict vacío (excepción
    capturada internamente) → resultado final es 100% yfinance.
    """
    _, finviz_data = _fetch_fundamentales_finviz(symbol)
    _, yf_data     = _fetch_info_yfinance(symbol)

    # Base: yfinance (cobertura completa para todos los mercados)
    resultado: dict = {k: v for k, v in yf_data.items() if v is not None}

    # Sobrescribir con finviz donde tenga datos (más actualizados/confiables)
    for clave, valor in finviz_data.items():
        if valor is not None:
            resultado[clave] = valor

    # days_until_earnings SIEMPRE de yfinance (finviz no lo provee de forma confiable)
    due = yf_data.get("days_until_earnings")
    if due is not None:
        resultado["days_until_earnings"] = due

    return symbol, resultado


def _fetch_volumen_extendido(symbol: str) -> tuple[str, dict]:
    """Obtiene volumen pre/post-market vía yfinance (barras de 1 min con prepost=True)."""
    try:
        import yfinance as yf

        df = yf.download(
            symbol, period="1d", interval="1m",
            prepost=True, auto_adjust=True, progress=False,
        )
        if df.empty:
            return symbol, {}

        # Normalizar índice a ET
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(_ET)
        else:
            df.index = df.index.tz_convert(_ET)

        now_et = datetime.now(_ET)
        market_open  = now_et.replace(hour=9,  minute=30, second=0, microsecond=0)
        market_close = now_et.replace(hour=16, minute=0,  second=0, microsecond=0)

        vol_col = "Volume"
        pre_vol  = int(df.loc[df.index < market_open,  vol_col].sum())
        post_vol = int(df.loc[df.index >= market_close, vol_col].sum())

        return symbol, {
            "pre_market_volume":  pre_vol,
            "post_market_volume": post_vol,
        }
    except Exception as exc:
        logger.warning("Error volumen extendido [%s]: %s", symbol, exc)
        return symbol, {}


# ──────────────────────────────────────────────────────────────────────────────
# API pública
# ──────────────────────────────────────────────────────────────────────────────

def obtener_fundamentales_batch(
    simbolos: list[str],
    mercado: str,
    max_workers: int = _MAX_WORKERS_FINVIZ,
) -> dict[str, dict]:
    """Obtiene fundamentales para todos los símbolos en paralelo.

    Usa estrategia dual finviz → yfinance por símbolo.
    Retorna {symbol: {float_shares, shares_outstanding, market_cap,
                       short_interest, short_ratio, days_until_earnings}}.
    Símbolos sin datos retornan dict vacío (filtros serán permisivos).
    """
    if mercado in _MERCADOS_SIN_FUNDAMENTALES or not simbolos:
        return {}

    resultados: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="fund") as pool:
        futures = {pool.submit(_fetch_info, sym): sym for sym in simbolos}
        for future in as_completed(futures):
            sym, data = future.result()
            resultados[sym] = data

    exitosos = sum(1 for v in resultados.values() if v)
    logger.info(
        "Fundamentales: %d/%d símbolos con datos (mercado=%s)",
        exitosos, len(simbolos), mercado,
    )
    return resultados


def obtener_volumen_extendido_batch(
    simbolos: list[str],
    mercado: str,
    max_workers: int = _MAX_WORKERS_YFINANCE,
) -> dict[str, dict]:
    """Obtiene volumen pre/post-market para todos los símbolos en paralelo.

    Retorna {symbol: {pre_market_volume, post_market_volume}}.
    """
    if mercado in _MERCADOS_SIN_FUNDAMENTALES or not simbolos:
        return {}

    resultados: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="exthr") as pool:
        futures = {pool.submit(_fetch_volumen_extendido, sym): sym for sym in simbolos}
        for future in as_completed(futures):
            sym, data = future.result()
            resultados[sym] = data

    return resultados
