import gzip
import json
import logging
import re
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
    # Calls marketdata-service directly over the Docker network instead of
    # through the gateway -- marketdata-service's own security only requires
    # X-Gateway-Passed for /marketdata/**, no JWT (confirmed in
    # SecurityConfiguration: that path falls under anyRequest().permitAll(),
    # and both its Jwt/ApiKey filters are no-ops when their header is
    # absent). Going direct removes the login/24h-token-refresh dance
    # entirely, along with the extra hop through the gateway.
    def __init__(self):
        self._base = settings.marketdata_url

    def _headers(self) -> dict:
        # /marketdata/historical/batch devuelve hasta ~9MB de JSON crudo por
        # lote de 700 simbolos (confirmado en vivo el 2026-08-19) --
        # Accept-Encoding le dice a marketdata-service que comprima (Echo
        # gzip middleware). urllib NO descomprime solo aunque el servidor
        # marque Content-Encoding: gzip (a diferencia de requests/httpx),
        # ver _request.
        return {"Content-Type": "application/json", "X-Gateway-Passed": "true", "Accept-Encoding": "gzip"}

    # Cuanto espera entre reintentos cuando marketdata esta en refill
    # (503 MAINTENANCE) -- el refill dura ~20-40 min, reintentar cada 60s
    # mantiene la espera sin martillar la API.
    _MAINTENANCE_RETRY_SECONDS = 60
    _MAINTENANCE_MAX_ATTEMPTS = 60

    def _request(self, method: str, path: str, body: Optional[dict] = None, timeout: int = 30) -> dict:
        import time

        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(f"{self._base}{path}", data=data, headers=self._headers(), method=method)
        for attempt in range(1, self._MAINTENANCE_MAX_ATTEMPTS + 1):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read()
                    if resp.headers.get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                    return json.loads(raw)
            except urllib.error.HTTPError as e:
                # El marketdata-service responde 503 con {"code": "MAINTENANCE",
                # "message": ...} durante el refill -- esperar con backoff
                # largo en vez de fallar o martillar.
                if e.code == 503:
                    try:
                        body_resp = json.loads(e.read().decode())
                        if body_resp.get("code") == "MAINTENANCE":
                            logger.warning(
                                "marketdata en mantenimiento (refill), reintento %d/%d en %ds",
                                attempt, self._MAINTENANCE_MAX_ATTEMPTS, self._MAINTENANCE_RETRY_SECONDS,
                            )
                            time.sleep(self._MAINTENANCE_RETRY_SECONDS)
                            continue
                    except json.JSONDecodeError:
                        pass
                raise
        raise RuntimeError(f"marketdata sigue en mantenimiento tras {self._MAINTENANCE_MAX_ATTEMPTS} intentos")

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

    # Warrants ("BWIV/WS") y preferentes ("PCGpA", "SNUSpI") no tienen
    # marketCap/prevClose de forma estructural (mismo motivo que los ETF sin
    # EPS -- no es que falten datos, es que no aplican). Los primeros N
    # simbolos de cada mercado (orden fijo, siempre los mismos en cada
    # arranque) caian a menudo por debajo del 80% de poblados solo por mala
    # suerte con el orden alfabetico -- confirmado en vivo: fundamentals_ready
    # nunca llegaba a True, 5 minutos perdidos en CADA arranque del servicio.
    _NOT_COMMON_STOCK_RE = re.compile(r"/|p[A-Z]{1,2}$")

    def fundamentals_ready(self, per_mercado_sample: int = 5) -> bool:
        try:
            sample: List[str] = []
            for mercado in self._READY_SAMPLE_MERCADOS:
                candidatos = [s for s in self.fetch_symbols([mercado]) if not self._NOT_COMMON_STOCK_RE.search(s)]
                sample.extend(candidatos[:per_mercado_sample])
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

    def fetch_current_prices(self, symbols: List[str]) -> dict[str, float]:
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
