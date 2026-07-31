from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class CandleResponse(BaseModel):
    symbol: str
    timestamp: datetime
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None
    vwap: Optional[float] = None
    impVolatility: Optional[float] = None


class QuoteResponse(BaseModel):
    symbol: str
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    prevClose: Optional[float] = None
    volume: Optional[float] = None
    tradingHalted: Optional[bool] = None
    tradingHaltedReason: Optional[str] = None
    beta: Optional[float] = None


class EarningsResponse(BaseModel):
    symbol: str
    occurredDate: Optional[date] = None
    eps: Optional[float] = None
    daysUntilEarnings: Optional[int] = None


class SymbolResponse(BaseModel):
    symbol: str
    description: Optional[str] = None
    listedMarket: Optional[str] = None


class FundamentalResponse(BaseModel):
    symbol: str
    marketCap: Optional[float] = None
    sharesOutstanding: Optional[int] = None
    floatShares: Optional[int] = None
    shortInterest: Optional[float] = None
    shortRatio: Optional[float] = None
    dayVolume: Optional[int] = None
    daysUntilEarnings: Optional[int] = None
    preMarketVolume: Optional[int] = None
    postMarketVolume: Optional[int] = None
    preMarketClose: Optional[float] = None
    postMarketClose: Optional[float] = None
    eps: Optional[float] = None
    dividendAmount: Optional[float] = None
    dividendFrequency: Optional[str] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    prevClose: Optional[float] = None
    tradingStatus: Optional[str] = None
    statusReason: Optional[str] = None
    haltStartTime: Optional[int] = None
    haltEndTime: Optional[int] = None
    beta: Optional[float] = None
    impliedVolatilityIndex: Optional[float] = None
    impliedVolatilityRank: Optional[float] = None
    impliedVolatilityPercentile: Optional[float] = None
    liquidity: Optional[float] = None
    liquidityRating: Optional[int] = None
    isEtf: Optional[bool] = None
    securityType: Optional[str] = None
