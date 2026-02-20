import requests
import logging
from datetime import datetime, timezone
from typing import Optional

from config import MARKETDATA_SERVICE_URL

class MarketDataAdapter:
    def __init__(self, base_url=None):
        self.base_url = base_url or f"{MARKETDATA_SERVICE_URL}/marketdata"
        self.logger = logging.getLogger(__name__)

    def obtener_velas_historicas(self, symbol: str, timeframe: str, bars: int = 100, end_date: Optional[str] = None):
        """
        Obtiene velas historicas desde el servicio de market data.
        """
        try:
            url = f"{self.base_url}/historical/{symbol}"
            params = {
                "timeframe": timeframe,
                "bars": bars
            }
            if end_date:
                params["endDate"] = end_date

            # self.logger.info(f"Consultando market data: {url} {params}")
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Error obteniendo market data para {symbol}: {e}")
            return []

    def obtener_barra_en_formacion(self, symbol: str, timeframe: str) -> dict:
        """GET /historical/{symbol}/current?timeframe=... — barra en formacion (periodo aun no cerrado)."""
        try:
            url = f"{self.base_url}/historical/{symbol}/current"
            params = {"timeframe": timeframe}
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Error obteniendo barra en formacion para {symbol}: {e}")
            return {}

    def obtener_ultima_barra_completa(self, symbol: str, timeframe: str) -> dict:
        """GET /historical/{symbol}/last?timeframe=... — ultima barra cerrada."""
        try:
            url = f"{self.base_url}/historical/{symbol}/last"
            params = {"timeframe": timeframe}
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Error obteniendo ultima barra para {symbol}: {e}")
            return {}

    def obtener_velas_historicas_batch(self, symbols: list[str], timeframe: str, bars: int = 100) -> dict:
        """
        POST /historical/batch - Obtiene candles para multiples simbolos en una sola peticion.
        Retorna: {symbol: [list of candles], ...}
        """
        try:
            url = f"{self.base_url}/historical/batch"
            payload = {
                "symbols": symbols,
                "timeframe": timeframe,
                "bars": bars
            }
            # Timeout escalado: base 30s + 0.05s por simbolo
            timeout = 30 + len(symbols) * 0.05

            self.logger.info(f"Batch request: {len(symbols)} symbols, tf={timeframe}, bars={bars}, timeout={timeout:.1f}s")
            response = requests.post(url, json=payload, timeout=timeout)
            response.raise_for_status()

            result = response.json()
            candles_por_simbolo = result.get("candlesPorSimbolo", {})

            # Detectar clock skew con serverTimestamp
            server_ts_str = result.get("serverTimestamp")
            if server_ts_str:
                try:
                    server_ts = datetime.fromisoformat(
                        server_ts_str.replace("Z", "+00:00")
                    )
                    ahora = datetime.now(timezone.utc)
                    skew = abs((ahora - server_ts).total_seconds())
                    if skew > 5:
                        self.logger.warning(
                            f"Clock skew detectado: {skew:.1f}s entre "
                            f"signal-processing y marketdata-service"
                        )
                except (ValueError, TypeError):
                    self.logger.debug(f"No se pudo parsear serverTimestamp: {server_ts_str}")

            self.logger.info(f"Batch response: {len(candles_por_simbolo)} symbols con datos")
            return candles_por_simbolo

        except Exception as e:
            self.logger.error(f"Error en batch request ({len(symbols)} symbols): {e}")
            return {}
    def obtener_ultima_barra_completa_batch(self, symbols: list[str], timeframe: str) -> dict:
        """
        POST /historical/batch/last - Obtiene la ultima barra cerrada para multiples simbolos.
        """
        try:
            url = f"{self.base_url}/historical/batch/last"
            payload = {"symbols": symbols, "timeframe": timeframe}
            timeout = 10 + len(symbols) * 0.02
            response = requests.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            return response.json().get("candlePorSimbolo", {})
        except Exception as e:
            self.logger.error(f"Error en batch last request ({len(symbols)} symbols): {e}")
            return {}

    def obtener_barra_en_formacion_batch(self, symbols: list[str], timeframe: str) -> dict:
        """
        POST /historical/batch/current - Obtiene la barra en formacion para multiples simbolos.
        """
        try:
            url = f"{self.base_url}/historical/batch/current"
            payload = {"symbols": symbols, "timeframe": timeframe}
            timeout = 10 + len(symbols) * 0.02
            response = requests.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            return response.json().get("candlePorSimbolo", {})
        except Exception as e:
            self.logger.error(f"Error en batch current request ({len(symbols)} symbols): {e}")
            return {}
