import requests
import logging
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
