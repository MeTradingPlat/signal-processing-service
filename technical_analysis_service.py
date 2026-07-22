"""
Technical Analysis Service - Signal Processing Microservice

Calcula indicadores técnicos (RSI, EMA, SMA, ATR, Pivots) usando NumPy/Pandas.
Los cálculos se hacen en microsegundos, no bloqueando el Frontend.

Endpoints:
- GET /api/v1/analysis/{symbol} - Obtener indicadores técnicos
- GET /api/v1/analysis/health - Health check
"""

import pandas as pd
import numpy as np
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List, Optional
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Technical Analysis Service",
    description="Microservicio de Análisis Técnico para el Frontend",
    version="1.0.0"
)

# Permitir CORS para el Frontend Angular
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_credentials=True,
)


class TechnicalAnalysisEngine:
    """
    Motor de Análisis Técnico
    
    Calcula indicadores vectorizados usando NumPy/Pandas.
    Los cálculos se hacen en microsegundos, no bloqueando el Frontend.
    """

    @staticmethod
    def calculate_rsi(closes: np.ndarray, period: int = 14) -> float:
        """
        Calcula RSI (Índice de Fuerza Relativa)
        
        Fórmula: RSI = 100 - (100 / (1 + RS))
        donde RS = Ganancia Promedio / Pérdida Promedio
        
        Args:
            closes: Array de precios de cierre
            period: Período de cálculo (default: 14)
        
        Returns:
            Valor de RSI (0-100)
        """
        if len(closes) < period + 1:
            return 0.0

        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])

        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 0.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return float(rsi)

    @staticmethod
    def calculate_ema(closes: np.ndarray, period: int = 14) -> float:
        """
        Calcula EMA (Media Móvil Exponencial)
        
        Fórmula: EMA = (Precio * Multiplicador) + (EMA Anterior * (1 - Multiplicador))
        donde Multiplicador = 2 / (período + 1)
        
        Args:
            closes: Array de precios de cierre
            period: Período de cálculo (default: 14)
        
        Returns:
            Valor de EMA
        """
        if len(closes) < period:
            return 0.0

        multiplier = 2 / (period + 1)
        ema = np.mean(closes[:period])

        for price in closes[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))

        return float(ema)

    @staticmethod
    def calculate_sma(closes: np.ndarray, period: int = 14) -> float:
        """
        Calcula SMA (Media Móvil Simple)
        
        Fórmula: SMA = Suma de últimos N precios / N
        
        Args:
            closes: Array de precios de cierre
            period: Período de cálculo (default: 14)
        
        Returns:
            Valor de SMA
        """
        if len(closes) < period:
            return 0.0

        return float(np.mean(closes[-period:]))

    @staticmethod
    def calculate_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
        """
        Calcula ATR (Average True Range)
        
        Fórmula: ATR = Promedio del Rango Verdadero
        Rango Verdadero = max(High - Low, |High - Close Anterior|, |Low - Close Anterior|)
        
        Args:
            highs: Array de precios máximos
            lows: Array de precios mínimos
            closes: Array de precios de cierre
            period: Período de cálculo (default: 14)
        
        Returns:
            Valor de ATR
        """
        if len(highs) < period:
            return 0.0

        true_ranges = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1])
            )
            true_ranges.append(tr)

        return float(np.mean(true_ranges[-period:]))

    @staticmethod
    def calculate_pivots(high: float, low: float, close: float) -> Dict[str, float]:
        """
        Calcula Pivots (Puntos Pivote)
        
        Fórmula:
        - Pivot = (High + Low + Close) / 3
        - R1 = (2 * Pivot) - Low
        - S1 = (2 * Pivot) - High
        - R2 = Pivot + (High - Low)
        - S2 = Pivot - (High - Low)
        
        Args:
            high: Precio máximo del día
            low: Precio mínimo del día
            close: Precio de cierre del día anterior
        
        Returns:
            Dict con valores de Pivot, R1, S1, R2, S2
        """
        pivot = (high + low + close) / 3
        r1 = (2 * pivot) - low
        s1 = (2 * pivot) - high
        r2 = pivot + (high - low)
        s2 = pivot - (high - low)

        return {
            "pivot": float(pivot),
            "r1": float(r1),
            "s1": float(s1),
            "r2": float(r2),
            "s2": float(s2)
        }

    @staticmethod
    def calculate_all_indicators(candles: List[Dict]) -> Dict:
        """
        Calcula todos los indicadores a partir de un array de velas
        
        Entrada:
        [
          { "timestamp": 1234567890, "open": 150.0, "high": 151.0, "low": 149.0, "close": 150.5, "volume": 1000000 },
          ...
        ]
        
        Salida:
        {
          "rsi": 65.4,
          "ema": 150.25,
          "sma": 149.80,
          "atr": 1.25,
          "pivots": { "pivot": 150.0, "r1": 151.0, "s1": 149.0, "r2": 152.0, "s2": 148.0 },
          "latest_close": 150.5,
          "latest_volume": 1000000
        }
        """
        if not candles or len(candles) < 14:
            return {}

        closes = np.array([c["close"] for c in candles])
        highs = np.array([c["high"] for c in candles])
        lows = np.array([c["low"] for c in candles])

        return {
            "rsi": TechnicalAnalysisEngine.calculate_rsi(closes),
            "ema": TechnicalAnalysisEngine.calculate_ema(closes),
            "sma": TechnicalAnalysisEngine.calculate_sma(closes),
            "atr": TechnicalAnalysisEngine.calculate_atr(highs, lows, closes),
            "pivots": TechnicalAnalysisEngine.calculate_pivots(highs[-1], lows[-1], closes[-1]),
            "latest_close": float(closes[-1]),
            "latest_volume": int(candles[-1]["volume"])
        }


# ===== Endpoints =====

@app.get("/api/v1/analysis/{symbol}")
async def get_technical_indicators(symbol: str, limit: int = 100):
    """
    GET /api/v1/analysis/{symbol}
    
    Calcula indicadores técnicos para un símbolo.
    El Frontend llama a este endpoint para obtener RSI, EMA, SMA, ATR, Pivots.
    
    Path Parameters:
    - symbol: Símbolo del instrumento (ej: "SPY", "AAPL")
    
    Query Parameters:
    - limit: Cantidad de velas a usar para cálculo (default: 100)
    
    Respuesta:
    {
      "symbol": "SPY",
      "indicators": {
        "rsi": 65.4,
        "ema": 150.25,
        "sma": 149.80,
        "atr": 1.25,
        "pivots": { "pivot": 150.0, "r1": 151.0, "s1": 149.0, "r2": 152.0, "s2": 148.0 },
        "latest_close": 150.5,
        "latest_volume": 1000000
      },
      "calculated_at": 1234567890
    }
    """
    logger.info(f"[TECHNICAL-ANALYSIS] Solicitud de indicadores: symbol={symbol}, limit={limit}")
    
    try:
        # En Producción: Obtener velas de MarketData Service o caché local
        # Por ahora, simulamos con datos de prueba
        mock_candles = [
            {
                "timestamp": i,
                "open": 150.0 + i * 0.1,
                "high": 151.0 + i * 0.1,
                "low": 149.0 + i * 0.1,
                "close": 150.5 + i * 0.1,
                "volume": 1000000
            }
            for i in range(limit)
        ]
        
        indicators = TechnicalAnalysisEngine.calculate_all_indicators(mock_candles)
        
        logger.info(f"[TECHNICAL-ANALYSIS] Indicadores calculados para {symbol}: RSI={indicators.get('rsi', 0):.2f}")
        
        return {
            "symbol": symbol,
            "indicators": indicators,
            "calculated_at": datetime.now().timestamp()
        }
    except Exception as e:
        logger.error(f"[TECHNICAL-ANALYSIS] Error calculando indicadores: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/analysis/health")
async def health_check():
    """
    GET /api/v1/analysis/health
    
    Health check del servicio de análisis técnico
    
    Respuesta:
    {
      "status": "UP",
      "service": "technical-analysis",
      "timestamp": 1234567890
    }
    """
    return {
        "status": "UP",
        "service": "technical-analysis",
        "timestamp": datetime.now().timestamp()
    }


@app.get("/")
async def root():
    """Endpoint raíz - información del servicio"""
    return {
        "service": "Technical Analysis Service",
        "version": "1.0.0",
        "endpoints": {
            "analysis": "/api/v1/analysis/{symbol}",
            "health": "/api/v1/analysis/health",
            "docs": "/docs"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
