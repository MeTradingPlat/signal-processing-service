"""Interfaz base para todos los filtros."""

from abc import ABC, abstractmethod

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro


class BaseFiltro(ABC):

    @abstractmethod
    def evaluar(
        self,
        candles: list[Candle],
        filtro: Filtro,
        datos_fundamentales: DatosFundamentales | None = None,
    ) -> bool:
        """
        Evalua si la condicion del filtro se cumple.

        Args:
            candles: Lista de candles OHLCV ordenados por timestamp (mas antiguo primero)
            filtro: Filtro con sus parametros configurados
            datos_fundamentales: Datos fundamentales del simbolo (puede ser None)
        Returns:
            True si la condicion se cumple
        """
        pass

    @abstractmethod
    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        """Retorna el timeframe que necesita este filtro (ej: 'M5', 'D1')."""
        pass

    @abstractmethod
    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        """Cuantas velas historicas necesita como minimo."""
        pass

    def _obtener_valor_parametro(self, filtro: Filtro, enum_parametro: str):
        """Helper: obtiene el valor seleccionado de un parametro."""
        param = filtro.obtener_parametro(enum_parametro)
        if param:
            return param.obj_valor_seleccionado
        return None

    def _obtener_valor_condicional(self, filtro: Filtro, enum_parametro: str = "CONDICION"):
        """Helper: obtiene valor1 y valor2 de un parametro condicional, 
        ajustando los limites segun la operacion (Smart Range)."""
        valor = self._obtener_valor_parametro(filtro, enum_parametro)
        if isinstance(valor, ValorCondicional):
            op = valor.enum_condicional
            v1 = valor.valor1
            v2 = valor.valor2
            
            if op == "MAYOR_QUE":
                return v1, float('inf')
            elif op == "MENOR_QUE":
                return float('-inf'), v1
            elif op == "IGUAL_A":
                return v1, v1
            
            # Para ENTRE (o si no hay operacion definida), devolvemos el rango normal
            return v1, v2
            
        return None, None

    def _evaluar_condicion_completa(self, valor_a_testear: float, filtro: Filtro, enum_parametro: str = "CONDICION") -> bool:
        """
        Evalua un valor contra la condicion configurada, soportando todos los operadores.
        """
        valor_obj = self._obtener_valor_parametro(filtro, enum_parametro)
        if not isinstance(valor_obj, ValorCondicional):
            return False
            
        op = valor_obj.enum_condicional
        v1 = valor_obj.valor1
        v2 = valor_obj.valor2
        
        if op == "MAYOR_QUE":
            return valor_a_testear > v1
        elif op == "MENOR_QUE":
            return valor_a_testear < v1
        elif op == "IGUAL_A":
            return valor_a_testear == v1
        elif op == "FUERA":
            return valor_a_testear < v1 or valor_a_testear > v2
        else:
            # Por defecto: ENTRE
            return v1 <= valor_a_testear <= v2

    def _obtener_valor_string(self, filtro: Filtro, enum_parametro: str) -> str:
        """Helper: obtiene el string de un parametro."""
        valor = self._obtener_valor_parametro(filtro, enum_parametro)
        if valor and hasattr(valor, "valor"):
            return str(valor.valor)
        return ""

    def _obtener_valor_int(self, filtro: Filtro, enum_parametro: str) -> int:
        """Helper: obtiene el entero de un parametro."""
        valor = self._obtener_valor_parametro(filtro, enum_parametro)
        if valor and hasattr(valor, "valor"):
            return int(valor.valor)
        return 0

    def _obtener_valor_float(self, filtro: Filtro, enum_parametro: str) -> float:
        """Helper: obtiene el float de un parametro."""
        valor = self._obtener_valor_parametro(filtro, enum_parametro)
        if valor and hasattr(valor, "valor"):
            return float(valor.valor)
        return 0.0

    @staticmethod
    def _evaluar_condicion(valor: float, min_val: float, max_val: float) -> bool:
        """Evalua si un valor esta dentro del rango condicional (>= min, <= max)."""
        return min_val <= valor <= max_val

    @staticmethod
    def _calcular_ema(closes: list[float], periodo: int) -> list[float]:
        """Calcula EMA (Exponential Moving Average)."""
        if len(closes) < periodo:
            return []
        multiplier = 2 / (periodo + 1)
        ema = [sum(closes[:periodo]) / periodo]
        for price in closes[periodo:]:
            ema.append((price - ema[-1]) * multiplier + ema[-1])
        return ema

    @staticmethod
    def _calcular_sma(closes: list[float], periodo: int) -> list[float]:
        """Calcula SMA (Simple Moving Average)."""
        if len(closes) < periodo:
            return []
        sma = []
        for i in range(periodo - 1, len(closes)):
            sma.append(sum(closes[i - periodo + 1:i + 1]) / periodo)
        return sma

    @staticmethod
    def _calcular_true_range(candles: list[Candle]) -> list[float]:
        """Calcula True Range para cada candle (excepto el primero)."""
        if len(candles) < 2:
            return []
        tr_values = []
        for i in range(1, len(candles)):
            high = candles[i].high
            low = candles[i].low
            prev_close = candles[i - 1].close
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_values.append(tr)
        return tr_values

    @staticmethod
    def _calcular_vwap(candles: list[Candle]) -> float:
        """Calcula VWAP (Volume Weighted Average Price)."""
        total_vol = 0.0
        total_vwap = 0.0
        for c in candles:
            typical_price = (c.high + c.low + c.close) / 3
            total_vwap += typical_price * c.volume
            total_vol += c.volume
        if total_vol == 0:
            return 0.0
        return total_vwap / total_vol
