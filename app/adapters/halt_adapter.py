"""Adaptador para obtener trading halts del NASDAQ en tiempo real.

Descarga el archivo oficial de NASDAQ Trader (pipe-delimited, actualizado
continuamente durante el horario de mercado) y retorna el set de símbolos
actualmente halteados.

URL oficial:
  https://www.nasdaqtrader.com/dynamic/symdir/nasdaqhaltedissues.txt

El archivo contiene todas las suspensiones del día. Un halt está "activo"
cuando tiene HaltTime pero no tiene ResumptionTradeTime aún.
"""
from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

_NASDAQ_HALT_URL = (
    "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqhaltedissues.txt"
)
_TIMEOUT_SEG = 10.0


def obtener_simbolos_halted() -> set[str] | None:
    """Descarga el archivo de halts de NASDAQ y retorna símbolos activos.

    Returns:
        Set de símbolos actualmente halteados (vacío si no hay halts activos).
        None si hubo un error de red o no se pudo obtener el archivo.
    """
    try:
        import httpx
        import pandas as pd
        import time

        max_reintentos = 3
        texto = ""
        for intento in range(max_reintentos):
            try:
                resp = httpx.get(_NASDAQ_HALT_URL, timeout=_TIMEOUT_SEG, follow_redirects=True)
                if resp.status_code == 200:
                    texto = resp.text
                    break
                logger.warning("NASDAQ halt file: HTTP %d (intento %d/%d)", resp.status_code, intento + 1, max_reintentos)
            except Exception as req_exc:
                logger.warning("NASDAQ halt file error de red: %s (intento %d/%d)", req_exc, intento + 1, max_reintentos)
            
            if intento < max_reintentos - 1:
                time.sleep(2 ** intento)  # 1s, 2s

        if not texto.strip():
            return set()

        df = pd.read_csv(
            io.StringIO(texto),
            sep="|",
            dtype=str,
            on_bad_lines="skip",
        )

        # Limpiar nombres de columnas (a veces tienen espacios)
        df.columns = df.columns.str.strip()

        if "Symbol" not in df.columns:
            logger.debug("NASDAQ halt file: sin columna 'Symbol' (normal fuera de horario)")
            return set()

        df["Symbol"] = df["Symbol"].str.strip()

        # Halt activo = tiene HaltTime pero ResumptionTradeTime está vacío
        col_resume = next(
            (c for c in df.columns if "ResumptionTrade" in c or "Resumption Trade" in c),
            None,
        )
        if col_resume:
            df[col_resume] = df[col_resume].str.strip()
            activos = df[df[col_resume].isna() | (df[col_resume] == "")]
        else:
            # Si no hay columna de reanudación, considerar todos como activos
            activos = df

        simbolos = {
            s for s in activos["Symbol"].dropna()
            if s and s.upper() != "SYMBOL"  # excluir cabecera duplicada
        }
        return simbolos

    except Exception as exc:
        logger.warning("Error obteniendo halts NASDAQ: %s", exc)
        return None
