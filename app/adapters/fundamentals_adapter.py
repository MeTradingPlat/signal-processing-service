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
  - Finviz:   ThreadPoolExecutor(max_workers=3) — scraping conservador, concurrente
  - yfinance: SECUENCIAL para .info/.calendar (crumb compartido, no soporta concurrencia)
  - yfinance: ThreadPoolExecutor(max_workers=2) solo para yf.download() (precios/volumen)
  - Para 500 símbolos ~3-5 min al arranque (una vez/día)
  - El caché vive en memoria todo el día; los filtros leen en O(1)

Anti-ban (Yahoo Finance):
  1. Normalización de símbolos: '/' → '-'  (AKO/A → AKO-A)
  2. yfinance .info/.calendar: secuencial (evita conflicto de crumb entre threads)
  3. Reintentos con backoff exponencial + crumb reset ante 401/429
  4. Sesión HTTP cacheada vía requests_cache (dependencia de yfinance)
  5. Símbolos delisted/404 se marcan y saltan automáticamente
"""
from __future__ import annotations

import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# User-Agents para evadir bloqueos por defecto
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/119.0",
]

_ET = ZoneInfo("America/New_York")
_MAX_WORKERS_YFINANCE = 2   # Reducido (era 4) — menos concurrencia = menos ban/crumb
_MAX_WORKERS_FINVIZ   = 3   # Reducido (era 5)  — scraping más conservador
_MERCADOS_SIN_FUNDAMENTALES = {"CRYPTO", "FOREX"}

# Reintentos ante rate-limit de Yahoo (401 / 429)
_MAX_REINTENTOS  = 3
_PAUSA_BASE_SEG  = 2.0   # pausa inicial; se duplica en cada reintento (2s, 4s, 8s)

# Símbolos conocidos como delisted/inválidos — se saltan para evitar errores repetitivos
# Se puebla dinámicamente durante el batch y persiste durante la vida del proceso
_SIMBOLOS_MALOS: set[str] = set()
_LOCK_SIMBOLOS_MALOS = __import__("threading").Lock()

# Multiplicadores para parsear strings de finviz ("15.44B", "3.42T", etc.)
_MULTIPLICADORES: dict[str, float] = {
    "K": 1_000,
    "M": 1_000_000,
    "B": 1_000_000_000,
    "T": 1_000_000_000_000,
}


# ──────────────────────────────────────────────────────────────────────────────
# Sesión HTTP cacheada para yfinance (anti-ban)
# ──────────────────────────────────────────────────────────────────────────────

def _crear_sesion_cacheada():
    """Crea una sesión HTTP cacheada usando requests_cache.

    requests_cache es dependencia directa de yfinance, siempre disponible.
    Cachea respuestas HTTP durante 1 hora → reduce peticiones duplicadas
    y evita el rate-limiting de Yahoo Finance.
    Retorna None si no está disponible (degradación elegante).
    """
    try:
        import requests_cache
        sesion = requests_cache.CachedSession(
            "yfinance_http_cache",
            expire_after=3_600,      # 1 hora
            allowable_codes=[200],   # solo cachear respuestas OK
        )
        logger.debug("requests_cache activado para yfinance (expire=1h)")
        return sesion
    except Exception:
        logger.debug("requests_cache no disponible — sin caché HTTP")
        return None


_YF_SESSION = _crear_sesion_cacheada()


# ──────────────────────────────────────────────────────────────────────────────
# Normalización de símbolos (Yahoo usa '-' donde los mercados usan '/')
# ──────────────────────────────────────────────────────────────────────────────

def _normalizar_simbolo_yahoo(symbol: str) -> str:
    """Convierte el formato de símbolo al esperado por Yahoo Finance.

    Yahoo Finance usa '-' como separador de clase, no '/':
      AKO/A  → AKO-A
      UHAL/B → UHAL-B
      FTW/U  → FTW-U
    Preferred shares: NLYpG → NLY-PG, FHNPE → FHN-PE
    Units: MTAL-U → MTAL-UN
    """
    import re

    had_slash = "/" in symbol
    s = symbol.replace("/", "-")

    # Units: sufijo -U → -UN (Yahoo convention)
    # Solo aplica cuando el guión era original (no vino de convertir una barra /U)
    if not had_slash and s.endswith("-U") and len(s) > 2:
        s = s + "N"

    # Preferred shares inline: letras minúsculas 'p' seguidas de 1-2 mayúsculas
    # NLYpG → NLY-PG, TRTNpE → TRTN-PE
    m = re.match(r"^([A-Z]+)p([A-Z]{1,2})$", s)
    if m:
        s = f"{m.group(1)}-P{m.group(2)}"

    # Preferred shares suffix without separator: FHNPE → FHN-PE, BACPB → BAC-PB
    # Heurística: si termina en P + 1 letra y no matcheó arriba, intentar
    # Solo si el símbolo base (sin los últimos 2 chars) tiene >= 2 chars
    # Esto es ambiguo así que solo lo aplicamos a patrones conocidos
    # (manejado caso por caso si se necesita)

    return s


# ──────────────────────────────────────────────────────────────────────────────
# Reintentos con backoff exponencial (anti rate-limit 401 / 429)
# ──────────────────────────────────────────────────────────────────────────────

def _invalidar_crumb_yfinance():
    """Fuerza a yfinance a re-obtener el crumb/cookie en el próximo request.

    El error 'Invalid Crumb' ocurre cuando la cookie de sesión expira
    pero yfinance sigue usando el crumb viejo cacheado internamente.
    """
    try:
        import yfinance as yf
        # yfinance >= 0.2.31 cachea crumb en un módulo-level dict
        if hasattr(yf, "utils") and hasattr(yf.utils, "get_json"):
            pass  # versión antigua sin crumb cache
        # Limpiar el caché de datos de yfinance para forzar re-autenticación
        if hasattr(yf, "shared") and hasattr(yf.shared, "_CACHE"):
            yf.shared._CACHE.clear()
        # yfinance >= 0.2.36 usa _TzCache y _CookieCache
        for attr_name in ("_cookies", "_cookie_cache", "_crumb"):
            for mod in (yf, getattr(yf, "data", None), getattr(yf, "shared", None)):
                if mod and hasattr(mod, attr_name):
                    obj = getattr(mod, attr_name)
                    if hasattr(obj, "clear"):
                        obj.clear()
                    elif isinstance(obj, str):
                        setattr(mod, attr_name, "")
        # Si requests_cache está activo, limpiar entradas de Yahoo
        if _YF_SESSION is not None and hasattr(_YF_SESSION, "cache"):
            try:
                _YF_SESSION.cache.clear()
            except Exception:
                pass
        logger.debug("Crumb/cookie de yfinance invalidado")
    except Exception as exc:
        logger.debug("No se pudo invalidar crumb yfinance: %s", exc)


def _ejecutar_con_reintento(fn, *args, **kwargs):
    """Ejecuta fn() con reintentos ante errores de rate-limit de Yahoo.

    Estrategia:
      - Intento 1: inmediato
      - Intento 2: pausa 2 s + invalidar crumb
      - Intento 3: pausa 4 s + invalidar crumb
    Solo reintenta ante 401 / 429 / 'Invalid Crumb' / 'Too Many Requests'.
    Otros errores se propagan inmediatamente.
    """
    _SEÑALES_RATE_LIMIT = ("401", "429", "invalid crumb", "too many requests", "unauthorized")
    _SEÑALES_DELISTED = ("delisted", "not found", "no data found", "no timezone found")

    for intento in range(_MAX_REINTENTOS):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            msg = str(exc).lower()

            # Símbolo delisted/no encontrado → no reintentar, propagar inmediatamente
            if any(s in msg for s in _SEÑALES_DELISTED):
                raise

            es_rate_limit = any(s in msg for s in _SEÑALES_RATE_LIMIT)

            if es_rate_limit and intento < _MAX_REINTENTOS - 1:
                _invalidar_crumb_yfinance()
                pausa = _PAUSA_BASE_SEG * (2 ** intento)
                logger.debug(
                    "Rate-limit detectado (intento %d/%d) — pausando %.0fs + crumb reset",
                    intento + 1, _MAX_REINTENTOS, pausa,
                )
                time.sleep(pausa)
                continue
            raise   # reintento agotado o error distinto → propagar


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
    """Obtiene fundamentales scrapeando Finviz directamente con HTTPX.
    
    Evita la librería finvizfinance porque falla con sufijos y es detectada fácilmente.
    """
    sym_finviz = symbol.replace("/", "-").replace(" ", "-")
    url = f"https://finviz.com/quote.ashx?t={sym_finviz}"
    
    # Delay anti-rate-limit orgánico
    time.sleep(random.uniform(0.5, 2.0))
    
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html",
        "DNT": "1",
    }
    
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            
        if resp.status_code != 200:
            logger.debug("Finviz devolvió HTTP %d para %s", resp.status_code, symbol)
            return symbol, {}

        soup = BeautifulSoup(resp.text, "lxml")
        tabla = soup.find("table", class_="snapshot-table2")
        if not tabla:
            return symbol, {}

        extracted_data = {}
        filas = tabla.find_all("tr")
        for fila in filas:
            celdas = fila.find_all("td")
            for i in range(0, len(celdas), 2):
                if i + 1 < len(celdas):
                    llave = celdas[i].get_text(strip=True)
                    valor = celdas[i+1].get_text(strip=True)
                    extracted_data[llave] = valor

        resultado = {
            "float_shares":       _parse_finviz_numero(extracted_data.get("Shs Float", "-")),
            "shares_outstanding": _parse_finviz_numero(extracted_data.get("Shs Outstand", "-")),
            "market_cap":         _parse_finviz_numero(extracted_data.get("Market Cap", "-")),
            "short_interest":     _parse_finviz_porcentaje(extracted_data.get("Short Float", "-")),
            "short_ratio":        _parse_finviz_numero(extracted_data.get("Short Ratio", "-")),
        }
        
        return symbol, {k: v for k, v in resultado.items() if v is not None}
        
    except Exception as exc:
        logger.warning("Finviz Scraper Falló [%s]: %s", symbol, exc)
        return symbol, {}


# ──────────────────────────────────────────────────────────────────────────────
# Fuente secundaria / fallback: yfinance
# ──────────────────────────────────────────────────────────────────────────────

def _fetch_info_yfinance(symbol: str) -> tuple[str, dict]:
    """Obtiene fundamentales de un símbolo vía yfinance de manera minimalista.
    Diseñado para tolerar el error 401 de datacenter y abortar rápidamente.
    Marca símbolos delisted/inválidos para no reintentar en futuros batches.
    """
    # Skip símbolos previamente marcados como malos
    with _LOCK_SIMBOLOS_MALOS:
        if symbol in _SIMBOLOS_MALOS:
            return symbol, {}

    symbol_yahoo = _normalizar_simbolo_yahoo(symbol)
    try:
        import yfinance as yf

        def _llamar():
            kwargs = {"session": _YF_SESSION} if _YF_SESSION is not None else {}
            ticker = yf.Ticker(symbol_yahoo, **kwargs)
            return ticker.info or {}, ticker

        info, ticker = _ejecutar_con_reintento(_llamar)

        short_pct_raw = info.get("shortPercentOfFloat")
        short_interest = round(float(short_pct_raw) * 100, 2) if short_pct_raw is not None else None

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
        msg = str(exc).lower()
        # Marcar símbolos delisted/404 para no reintentar
        if any(s in msg for s in ("delisted", "not found", "404", "no data found")):
            with _LOCK_SIMBOLOS_MALOS:
                _SIMBOLOS_MALOS.add(symbol)
            logger.debug("Símbolo marcado como inválido [%s]: %s", symbol, exc)
        else:
            logger.debug("yf.info no disponible [%s]: %s", symbol, exc)
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

def _merge_fundamentales(symbol: str, finviz_data: dict, yf_data: dict) -> tuple[str, dict]:
    """Fusiona datos de finviz (primario) y yfinance (fallback).

    Prioridad: finviz > yfinance para campos compartidos.
    days_until_earnings siempre de yfinance.
    """
    # Base: yfinance (cobertura completa para todos los mercados)
    resultado: dict = {k: v for k, v in yf_data.items() if v is not None}

    # Sobrescribir con finviz donde tenga datos (más actualizados/confiables)
    for clave, valor in finviz_data.items():
        if valor is not None:
            resultado[clave] = valor

    # days_until_earnings SIEMPRE de yfinance porque en nuestro df no lo extrajimos de finviz
    due = yf_data.get("days_until_earnings")
    if due is not None:
        resultado["days_until_earnings"] = due

    return symbol, resultado


def _fetch_info(symbol: str) -> tuple[str, dict]:
    """Wrapper de compatibilidad: finviz + yfinance secuencial para un solo símbolo."""
    _, finviz_data = _fetch_fundamentales_finviz(symbol)
    _, yf_data = _fetch_info_yfinance(symbol)
    return _merge_fundamentales(symbol, finviz_data, yf_data)


def _scrape_marketwatch_volumen(symbol: str) -> dict:
    """Extrae el volumen pre y post market leyendo MarketWatch directamente."""
    sym_mw = symbol.replace("-", ".").lower()
    url = f"https://www.marketwatch.com/investing/stock/{sym_mw}"
    
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html",
    }
    
    try:
        with httpx.Client(timeout=8.0, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
        if resp.status_code != 200:
            return {}
            
        soup = BeautifulSoup(resp.text, "lxml")
        
        # Marketwatch muestra extended hours volume en este DOM path standard (usualmente Intraday data)
        vol_div = soup.find("div", class_="intraday__volume")
        if not vol_div:
            return {}
            
        vol_text = vol_div.find("span", class_="volume__value")
        if vol_text:
            parsed_vol = _parse_finviz_numero(vol_text.get_text(strip=True))
            if parsed_vol:
                # MW arroja el after/prehours consolidado, lo dividimos como fallback
                return {
                    "pre_market_volume": parsed_vol, 
                    "post_market_volume": parsed_vol
                }
    except Exception as e:
        logger.debug("Marketwatch fallo en %s (%s)", symbol, str(e))
        
    return {}


def _fetch_volumen_extendido(symbol: str) -> tuple[str, dict]:
    """Obtiene volumen pre/post-market por Yahoo o Marketwatch scraper."""
    # Skip símbolos previamente marcados como malos
    with _LOCK_SIMBOLOS_MALOS:
        if symbol in _SIMBOLOS_MALOS:
            return symbol, {}

    symbol_yahoo = _normalizar_simbolo_yahoo(symbol)
    try:
        import pandas as pd
        import yfinance as yf

        def _descargar():
            kwargs = {}
            if _YF_SESSION is not None:
                yf.set_session(_YF_SESSION)
            return yf.download(
                symbol_yahoo, period="1d", interval="1m",
                prepost=True, auto_adjust=True, progress=False,
            )

        try:
            df = _ejecutar_con_reintento(_descargar)
        except Exception as dl_exc:
            msg = str(dl_exc).lower()
            if any(s in msg for s in ("no objects to concatenate", "delisted", "not found", "404")):
                with _LOCK_SIMBOLOS_MALOS:
                    _SIMBOLOS_MALOS.add(symbol)
                logger.debug("Símbolo sin datos de volumen [%s]: %s", symbol, dl_exc)
                return symbol, {}
            raise

        if df is None or (hasattr(df, "empty") and df.empty):
            return symbol, _scrape_marketwatch_volumen(symbol)

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        try:
            # Fix del crash: Si el index no tiene tz_localize/convert o no es DatetimeIndex
            # saltara excepcion. El fallback Scraper te salva aquí.
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
        except Exception as e:
            logger.debug("Fallo manipulación pandas en YF extendido %s: %s", symbol, e)
            return symbol, _scrape_marketwatch_volumen(symbol)

    except Exception as exc:
        logger.warning("Caída de proxy en Extendido [%s]: %s", symbol, exc)
        return symbol, {}


# ──────────────────────────────────────────────────────────────────────────────
# API pública
# ──────────────────────────────────────────────────────────────────────────────

def obtener_fundamentales_batch(
    simbolos: list[str],
    mercado: str,
    max_workers_finviz: int = _MAX_WORKERS_FINVIZ,
    max_workers: int | None = None,  # alias de compatibilidad
) -> dict[str, dict]:
    """Obtiene fundamentales para todos los símbolos.

    Arquitectura:
      1. Finviz: concurrente (ThreadPoolExecutor) — no usa crumb, tolerante
      2. yfinance .info/.calendar: SECUENCIAL — comparte crumb/cookie,
         la concurrencia causa "Invalid Crumb" 401 masivos
      3. Merge: finviz primario, yfinance fallback + days_until_earnings

    Retorna {symbol: {float_shares, shares_outstanding, market_cap,
                       short_interest, short_ratio, days_until_earnings}}.
    """
    if mercado in _MERCADOS_SIN_FUNDAMENTALES or not simbolos:
        return {}

    # Deduplicar símbolos para evitar fetch N veces del mismo
    simbolos_unicos = list(dict.fromkeys(simbolos))

    # ── Paso 1: Finviz concurrente ──────────────────────────────────────────
    finviz_por_sym: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=max_workers_finviz, thread_name_prefix="finviz") as pool:
        futures = {pool.submit(_fetch_fundamentales_finviz, sym): sym for sym in simbolos_unicos}
        for future in as_completed(futures):
            sym, data = future.result()
            finviz_por_sym[sym] = data

    # ── Paso 2: yfinance SECUENCIAL (crumb compartido) ─────────────────────
    # Siempre necesitamos yfinance para days_until_earnings (finviz no lo tiene)
    # y como fallback cuando finviz no trajo datos suficientes.
    # Se ejecuta en serie para evitar conflictos de crumb entre threads.
    yf_por_sym: dict[str, dict] = {}
    total_yf = len(simbolos_unicos)
    for i, sym in enumerate(simbolos_unicos):
        _, yf_data = _fetch_info_yfinance(sym)
        yf_por_sym[sym] = yf_data
        if (i + 1) % 50 == 0:
            logger.info("yfinance: %d/%d símbolos procesados", i + 1, total_yf)

    # ── Paso 3: Merge ──────────────────────────────────────────────────────
    resultados: dict[str, dict] = {}
    for sym in simbolos_unicos:
        _, merged = _merge_fundamentales(
            sym,
            finviz_por_sym.get(sym, {}),
            yf_por_sym.get(sym, {}),
        )
        resultados[sym] = merged

    _CAMPOS_FUNDAMENTALES = (
        "float_shares", "shares_outstanding", "market_cap",
        "short_interest", "short_ratio", "days_until_earnings",
    )
    sin_datos = [s for s, v in resultados.items() if not v]
    completos = [s for s, v in resultados.items() if all(v.get(c) is not None for c in _CAMPOS_FUNDAMENTALES)]
    parciales = [s for s, v in resultados.items() if v and s not in completos]

    logger.info(
        "Fundamentales [%s]: %d/%d con datos — %d completos, %d parciales, %d sin datos",
        mercado, len(resultados) - len(sin_datos), len(simbolos_unicos),
        len(completos), len(parciales), len(sin_datos),
    )

    _escribir_reporte_fundamentales(mercado, resultados, _CAMPOS_FUNDAMENTALES)

    return resultados


def _escribir_reporte_fundamentales(
    mercado: str,
    resultados: dict[str, dict],
    campos: tuple,
) -> None:
    """Escribe un reporte CSV por símbolo al terminar el refresh.

    Genera dos archivos en /tmp/fundamentals_reports/ (o ./reports/ si no existe /tmp):
      - fundamentals_{mercado}_{fecha}.csv   — todos los símbolos, fila por símbolo
      - fundamentals_{mercado}_{fecha}_sin_datos.txt — sólo los que fallaron

    Columnas CSV:
      symbol, estado, float_shares, shares_outstanding, market_cap,
      short_interest, short_ratio, days_until_earnings, campos_faltantes
    """
    import csv
    import os
    from datetime import datetime as _dt

    # Directorio de reportes (dentro del contenedor o local)
    for base in ("/tmp/fundamentals_reports", "./reports/fundamentals"):
        try:
            os.makedirs(base, exist_ok=True)
            reporte_dir = base
            break
        except OSError:
            continue
    else:
        logger.warning("No se pudo crear directorio de reportes, omitiendo reporte CSV")
        return

    fecha = _dt.now().strftime("%Y-%m-%d_%H%M")
    csv_path = os.path.join(reporte_dir, f"fundamentals_{mercado}_{fecha}.csv")
    sin_datos_path = os.path.join(reporte_dir, f"fundamentals_{mercado}_{fecha}_sin_datos.txt")

    try:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "symbol", "estado",
                *campos,
                "campos_faltantes",
            ])
            for sym in sorted(resultados.keys()):
                datos = resultados[sym]
                if not datos:
                    estado = "SIN_DATOS"
                    faltantes = ",".join(campos)
                else:
                    faltantes_list = [c for c in campos if datos.get(c) is None]
                    faltantes = ",".join(faltantes_list)
                    estado = "COMPLETO" if not faltantes_list else "PARCIAL"
                writer.writerow([
                    sym, estado,
                    *[datos.get(c, "") for c in campos],
                    faltantes,
                ])

        with open(sin_datos_path, "w", encoding="utf-8") as f:
            sin_datos = sorted(s for s, v in resultados.items() if not v)
            f.write(f"# Símbolos SIN datos fundamentales — {mercado} — {fecha}\n")
            f.write(f"# Total: {len(sin_datos)}\n\n")
            f.write("\n".join(sin_datos))

        logger.info(
            "Reporte fundamentales escrito: %s (%d filas)",
            csv_path, len(resultados),
        )
    except Exception as exc:
        logger.warning("No se pudo escribir reporte fundamentales: %s", exc)


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

    # Deduplicar símbolos
    simbolos_unicos = list(dict.fromkeys(simbolos))

    resultados: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="exthr") as pool:
        futures = {pool.submit(_fetch_volumen_extendido, sym): sym for sym in simbolos_unicos}
        for future in as_completed(futures):
            sym, data = future.result()
            resultados[sym] = data

    return resultados
