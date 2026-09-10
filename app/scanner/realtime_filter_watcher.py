import logging
from datetime import datetime, timezone
from typing import Callable

from app.models.escaner import Escaner
from app.models.filtro import Filtro
from app.models.signal_match import SignalMatch
from app.scanner.marketdata_models import CandleResponse
from app.scanner.realtime_candle_client import RealtimeCandleClient
from app.scanner.timeframe import extraer_timeframe_minutos, minutos_to_label
from app.strategies.base import MarketData
from app.strategies.registry import get_strategy

logger = logging.getLogger(__name__)

_MAX_BUFFERED_BARS = 200


def _to_candle(symbol: str, bar: dict) -> CandleResponse:
    return CandleResponse(
        symbol=symbol,
        timestamp=datetime.fromtimestamp(bar["time"], tz=timezone.utc),
        open=bar.get("open"), high=bar.get("high"), low=bar.get("low"),
        close=bar.get("close"), volume=bar.get("volume"),
    )


class RealtimeFilterWatcher:
    """Reevalua, apenas cierra una vela en /ws/candles de marketdata-service,
    los filtros de un escaner marcados con revisionTiempoReal=true -- sin
    esperar el ciclo normal de ~60s (ver runner.py). Se actualiza en cada
    ciclo con `SymbolPipeline.candidatos_previos_a_grupo`: los simbolos que
    ya sobrevivieron todo el resto del embudo y solo les falta este filtro."""

    def __init__(self, escaner: Escaner, ws_url: str, publish_signal: Callable[[Escaner, str, SignalMatch], None],
                 client_factory=RealtimeCandleClient):
        self._escaner = escaner
        self._publish_signal = publish_signal
        self._filtros_por_timeframe: dict[str, list[Filtro]] = {}
        self._candles: dict[tuple[str, str], list[CandleResponse]] = {}
        self._client = client_factory(ws_url, self._on_history, self._on_bar)

    def actualizar(self, filtros_realtime: list[Filtro], candidatos_previos_a_grupo: dict[int, set]) -> None:
        self._filtros_por_timeframe = {}
        keys: set[tuple[str, str]] = set()
        for filtro in filtros_realtime:
            minutos = extraer_timeframe_minutos(filtro)
            tf_label = minutos_to_label(minutos)
            self._filtros_por_timeframe.setdefault(tf_label, []).append(filtro)
            for symbol in candidatos_previos_a_grupo.get(minutos, set()):
                keys.add((symbol, tf_label))
        self._client.update_subscriptions(keys)

    def stop(self) -> None:
        self._client.stop()

    def _on_history(self, symbol: str, timeframe: str, bars: list[dict]) -> None:
        self._candles[(symbol, timeframe)] = [_to_candle(symbol, b) for b in bars if b.get("closed")]

    def _on_bar(self, symbol: str, timeframe: str, bar: dict) -> None:
        key = (symbol, timeframe)
        candles = self._candles.setdefault(key, [])
        candles.append(_to_candle(symbol, bar))
        del candles[:-_MAX_BUFFERED_BARS]

        data = MarketData(symbol=symbol, candles=candles)
        for filtro in self._filtros_por_timeframe.get(timeframe, []):
            if not get_strategy(filtro).evaluate(data):
                continue
            logger.info("RealtimeFilterWatcher: match en vivo symbol=%s filtro=%s escaner=%d",
                        symbol, filtro.enumFiltro.name, self._escaner.idEscaner)
            match = SignalMatch(filtro=filtro, vela_timestamp=candles[-1].timestamp, precio=candles[-1].close)
            self._publish_signal(self._escaner, symbol, match)
