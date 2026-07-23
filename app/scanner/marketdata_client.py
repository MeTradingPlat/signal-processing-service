import json
import logging
import urllib.request
from typing import List, Optional

from app.config import settings
from app.scanner.marketdata_models import (
    CandleResponse,
    FundamentalResponse,
)
from app.scanner.mappings import mercado_to_mic, timeframe_to_marketdata

logger = logging.getLogger(__name__)


class MarketdataClient:
    def __init__(self):
        self._base = settings.marketdata_url
        self._token: Optional[str] = None

    def _auth(self):
        if self._token:
            return
        data = json.dumps({
            "username": settings.marketdata_user,
            "password": settings.marketdata_password,
        }).encode()
        req = urllib.request.Request(
            f"{self._base}/auth/login",
            data=data,
            headers={"Content-Type": "application/json", "X-Gateway-Passed": "true"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            self._token = json.loads(resp.read())["token"]
        logger.info("Marketdata auth OK via gateway")

    def _request(self, method: str, path: str, body: Optional[dict] = None, timeout: int = 30) -> dict:
        self._auth()
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(
            f"{self._base}{path}",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._token}",
                "X-Gateway-Passed": "true",
            },
            method=method,
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())

    def fetch_symbols(self, mercados: List[str]) -> List[str]:
        mics = [mercado_to_mic(m) for m in mercados]
        params = "&".join(f"markets={m}" for m in mics)
        data = self._request("GET", f"/marketdata/symbols?{params}", timeout=60)
        return [s["symbol"] for s in data]

    def fetch_fundamentals(self, symbols: List[str]) -> dict[str, FundamentalResponse]:
        data = self._request("POST", "/marketdata/fundamentals/realtime", body=symbols)
        return {k: FundamentalResponse(**v) for k, v in data.items()}

    def fetch_candles(
        self, symbols: List[str], timeframe: str, bars: int
    ) -> dict[str, List[CandleResponse]]:
        tf = timeframe_to_marketdata(timeframe)
        data = self._request("POST", "/marketdata/historical/batch",
                             body={"symbols": symbols, "timeframe": tf, "bars": bars}, timeout=90)
        raw = data.get("candlesPorSimbolo", {})
        return {k: [CandleResponse(**c) for c in v] for k, v in raw.items()}

    def fetch_candles_current(
        self, symbols: List[str], timeframe: str
    ) -> dict[str, CandleResponse]:
        tf = timeframe_to_marketdata(timeframe)
        data = self._request("POST", "/marketdata/historical/batch/current",
                             body={"symbols": symbols, "timeframe": tf}, timeout=90)
        raw = data.get("candlePorSimbolo", {})
        return {k: CandleResponse(**v) for k, v in raw.items() if v}

    def fetch_quotes(self, symbols: List[str]) -> dict[str, float]:
        result = {}
        chunk_size = 500
        for i in range(0, len(symbols), chunk_size):
            chunk = symbols[i:i + chunk_size]
            batch = self._request("POST", "/marketdata/quotes/rest", body=chunk)
            result.update(batch)
        return result
