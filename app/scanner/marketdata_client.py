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

    def is_ready(self) -> bool:
        try:
            self.fetch_symbols(["NASDAQ"])
            return True
        except Exception:
            return False

    # OTC is deliberately excluded: thin/no fundamental coverage there is
    # normal even when marketdata's pipeline is fully healthy, so including
    # it would make this check fail on data sparsity, not actual readiness.
    _READY_SAMPLE_MERCADOS = ["NASDAQ", "NYSE", "AMEX", "ETF"]
    _READY_THRESHOLD = 0.8

    def fundamentals_ready(self, per_mercado_sample: int = 5) -> bool:
        try:
            sample: List[str] = []
            for mercado in self._READY_SAMPLE_MERCADOS:
                sample.extend(self.fetch_symbols([mercado])[:per_mercado_sample])
            if not sample:
                return False
            fundamentals = self.fetch_fundamentals(sample)
            populated = sum(
                1 for f in fundamentals.values() if f.marketCap is not None or f.prevClose is not None
            )
            return populated / len(sample) >= self._READY_THRESHOLD
        except Exception:
            return False

    def fetch_symbols(self, mercados: List[str]) -> List[str]:
        mics = [mercado_to_mic(m) for m in mercados]
        params = "&".join(f"markets={m}" for m in mics)
        data = self._request("GET", f"/marketdata/symbols?{params}", timeout=60)
        return [s["symbol"] for s in data]

    def fetch_fundamentals(self, symbols: List[str]) -> dict[str, FundamentalResponse]:
        data = self._request("POST", "/marketdata/fundamentals/realtime", body=symbols, timeout=90)
        return {k: FundamentalResponse(**v) for k, v in data.items()}

    # marketdata-service reliably serves up to 8 channels x 100 symbols/channel
    # (800) in a single pass (~15s); larger requests still work correctly there
    # via internal sequential waves, but each wave adds ~15s, so we chunk here
    # to keep every individual HTTP call fast and comfortably under our own
    # 90s timeout instead of relying on marketdata-service's waves for that.
    _CANDLE_CHUNK_SIZE = 800

    def fetch_candles(
        self, symbols: List[str], timeframe: str, bars: int
    ) -> dict[str, List[CandleResponse]]:
        tf = timeframe_to_marketdata(timeframe)
        result: dict[str, List[CandleResponse]] = {}
        for i in range(0, len(symbols), self._CANDLE_CHUNK_SIZE):
            chunk = symbols[i:i + self._CANDLE_CHUNK_SIZE]
            data = self._request("POST", "/marketdata/historical/batch",
                                 body={"symbols": chunk, "timeframe": tf, "bars": bars}, timeout=90)
            raw = data.get("candlesPorSimbolo", {})
            result.update({k: [CandleResponse(**c) for c in v] for k, v in raw.items()})
        return result

    def fetch_candles_current(
        self, symbols: List[str], timeframe: str
    ) -> dict[str, CandleResponse]:
        tf = timeframe_to_marketdata(timeframe)
        data = self._request("POST", "/marketdata/historical/batch/current",
                             body={"symbols": symbols, "timeframe": tf}, timeout=90)
        raw = data.get("candlePorSimbolo", {})
        return {k: CandleResponse(**v) for k, v in raw.items() if v}

    def fetch_quotes(self, symbols: List[str]) -> dict[str, float]:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        chunk_size = 100
        chunks = [symbols[i:i + chunk_size] for i in range(0, len(symbols), chunk_size)]

        result = {}
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(self._request, "POST", "/marketdata/quotes/rest", body=c, timeout=15): c for c in chunks}
            for future in as_completed(futures, timeout=30):
                try:
                    batch = future.result()
                    if batch:
                        result.update(batch)
                except Exception as e:
                    logger.warning(f"Quote chunk failed: {e}")
        return result
