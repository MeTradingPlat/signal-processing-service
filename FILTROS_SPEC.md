# Especificacion de Filtros - Signal Processing Service

> Los 41 filtros definidos en `scanner-management-service`.
> Cada filtro especifica que dato usa y por que segun la estrategia de trading.

---

## Notas Generales

- Todos los filtros heredan de `BaseFiltro` e implementan: `evaluar()`, `get_timeframe_requerido()`, `get_cantidad_velas_requeridas()`.
- El parametro **CONDICION** define un rango `min/max`. Un simbolo pasa si el valor cae dentro del rango.
- Logica **AND con cortocircuito**: si un filtro falla, se descarta el simbolo.
- **Todos los filtros trabajan con velas cerradas** salvo que se indique lo contrario.
- Un "close por encima de X" es una confirmacion. Un wick no lo es (puede ser fakeout).

### Tipos de dato que usa cada filtro

| Dato | Significado | Cuando se usa |
|------|-------------|---------------|
| `close` (vela cerrada) | Precio confirmado al cierre | Confirmaciones de cruces, rupturas, niveles |
| `high` (vela cerrada) | Maximo alcanzado en la vela | Deteccion de nuevos maximos, rangos |
| `low` (vela cerrada) | Minimo alcanzado en la vela | Deteccion de nuevos minimos, rangos |
| `open` (vela cerrada) | Apertura de la vela | Gaps, patrones de velas |
| `volume` (vela cerrada) | Volumen total de la vela | Analisis de volumen (solo tiene sentido completo) |
| `quote` (tiempo real) | Precio actual del mercado | Solo HALT (estado del mercado, no precio) |

---

## 1. VOLUMEN (6 filtros)

> El volumen de una vela en formacion esta incompleto. Evaluar volumen parcial genera falsos negativos.
> **Todos los filtros de volumen usan exclusivamente velas cerradas.**

### 1.1 VOLUME
- **Que hace**: Verifica que el volumen de la ultima vela cerrada este en el rango.
- **Dato que usa**: `candles[-1].volume` (vela cerrada).
- **Por que**: El volumen solo tiene sentido cuando la vela cerro. Volumen parcial es inutil.
- **Parametros**: `CONDICION` (min/max), `TIPO_VOLUMEN`, `TIMEFRAME_VOLUME`.
- **Velas necesarias**: 1.

### 1.2 AVERAGE_VOLUME
- **Que hace**: Promedio de volumen sobre N velas cerradas.
- **Dato que usa**: `volume` de las ultimas N velas cerradas.
- **Por que**: Promedio requiere velas completas para ser representativo.
- **Parametros**: `CONDICION` (min/max), `TIMEFRAME_AVERAGE_VOLUME`.
- **Velas necesarias**: ~20.

### 1.3 VOLUMEN_POST_PRE
- **Que hace**: Compara volumen de sesion extendida vs sesion regular.
- **Dato que usa**: `volume` de velas cerradas de sesiones pre/post market.
- **Por que**: Se comparan periodos completos, no parciales.
- **Parametros**: `CONDICION` (min/max).
- **Velas necesarias**: Velas de sesion extendida + regular.

### 1.4 RELATIVE_VOLUME
- **Que hace**: Ratio de volumen actual vs promedio historico.
- **Dato que usa**: `candles[-1].volume / promedio(volume historico)` — todo velas cerradas.
- **Por que**: Comparar volumen parcial contra promedios completos no tiene sentido.
- **Parametros**: `CONDICION` (min/max), `TIMEFRAME_RELATIVE_VOLUME_PERCENT`.
- **Velas necesarias**: ~20-50.

### 1.5 RELATIVE_VOLUME_SAME_TIME
- **Que hace**: Compara volumen vs promedio a la misma hora en dias anteriores.
- **Dato que usa**: `volume` de velas cerradas filtradas por misma franja horaria.
- **Por que**: Compara periodos equivalentes completos.
- **Parametros**: `CONDICION` (min/max).
- **Velas necesarias**: Velas de multiples dias a la misma hora.

### 1.6 VOLUME_SPIKE
- **Que hace**: Detecta pico subito de volumen.
- **Dato que usa**: `candles[-1].volume / promedio(candles[-N-1:-1].volume)` — velas cerradas.
- **Por que**: Un spike solo se confirma cuando la vela cierra con volumen completo. Volumen parcial puede parecer spike y terminar siendo normal.
- **Parametros**: `CONDICION` (min/max), `NUMERO_VELAS_VOLUME_SPIKE`, `TIMEFRAME_VOLUME_SPIKE`, `PROPORCION_VOLUMEN_VOLUME_SPIKE`.
- **Velas necesarias**: N+1.

---

## 2. PRECIO Y MOVIMIENTO (9 filtros)

### 2.1 PRECIO
- **Que hace**: Verifica que el precio este dentro del rango.
- **Dato que usa**: `candles[-1].close` (vela cerrada).
- **Por que**: Es un filtro de estado ("quiero acciones entre $5 y $50"). El close confirmado es suficiente; la diferencia entre close y precio actual es irrelevante para este rango amplio.
- **Parametros**: `CONDICION` (min/max).
- **Velas necesarias**: 1.

### 2.2 CHANGE
- **Que hace**: Cambio de precio desde un punto de referencia.
- **Dato que usa**: `candles[-1].close - candles[-2].close` (o `.open`, `.high`, `.low` segun `PUNTO_REFERENCIA`).
- **Por que**: El cambio se mide entre puntos confirmados. Un close no confirmado puede revertir.
- **Parametros**: `CONDICION` (min/max), `PUNTO_REFERENCIA_CHANGE` (OPEN, CLOSE, HIGH, LOW), `TIPO_MEDIDA_CHANGE` (PRECIO o PORCENTAJE).
- **Velas necesarias**: 2+.

### 2.3 PERCENTAGE_CHANGE
- **Que hace**: Cambio porcentual del precio sobre un periodo.
- **Dato que usa**: `(candles[-1].close - candles[0].close) / candles[0].close * 100` — closes cerrados.
- **Por que**: % change se mide entre closes confirmados.
- **Parametros**: `CONDICION` (min/max), `TIMEFRAME_PERCENTAGE_CHANGE_PERCENT`.
- **Velas necesarias**: ~50 (D1).

### 2.4 GAP_FROM_CLOSE
- **Que hace**: Gap entre cierre anterior y apertura actual.
- **Dato que usa**: `candles[-1].open - candles[-2].close`.
- **Por que**: El gap es un dato fijo del dia — se calcula una vez con la apertura confirmada y el cierre del dia anterior. No cambia.
- **Parametros**: `CONDICION` (min/max), `FORMATO_GAP_FROM_CLOSE` (dolares o %).
- **Velas necesarias**: 2.

### 2.5 POSITION_IN_RANGE
- **Que hace**: Posicion porcentual del precio dentro del rango high-low del periodo.
- **Dato que usa**: `(candles[-1].close - low_periodo) / (high_periodo - low_periodo) * 100`.
- **Por que**: Posicion relativa se evalua con close confirmado. Un wick puede estar en 95% y cerrar en 60%.
- **Parametros**: `CONDICION` (min/max), `TIMEFRAME_POSITION_IN_RANGE`.
- **Velas necesarias**: Variable segun timeframe.

### 2.6 PERCENTAGE_RANGE
- **Que hace**: Rango porcentual entre high y low de la vela/periodo.
- **Dato que usa**: `(candles[-1].high - candles[-1].low) / candles[-1].low * 100` — vela cerrada.
- **Por que**: El rango real solo se conoce al cerrar la vela. Una vela en formacion puede expandir su rango.
- **Parametros**: `CONDICION` (min/max), `TIMEFRAME_PERCENTAGE_RANGE_PERCENT`.
- **Velas necesarias**: 1+.

### 2.7 RANGE_DOLLARS
- **Que hace**: Rango en dolares (high - low).
- **Dato que usa**: `candles[-1].high - candles[-1].low` — vela cerrada.
- **Por que**: Mismo razonamiento que PERCENTAGE_RANGE. El rango es definitivo al cierre.
- **Parametros**: `CONDICION` (min/max), `TIMEFRAME_RANGE_DOLLAR`.
- **Velas necesarias**: 1+.

### 2.8 CROSSING_ABOVE_BELOW
- **Que hace**: Detecta si el precio cruzo por encima o debajo de un nivel (precio fijo, EMA, VWAP).
- **Dato que usa**: `candles[-2].close` vs `candles[-1].close` respecto al nivel — **ambos closes de velas cerradas**.
- **Por que**: En trading, un cruce se confirma con el **close**. Si el precio solo hace un wick por encima de la EMA pero cierra debajo, eso es un fakeout, no un cruce. La mayoria de estrategias de cruce de medias moviles requieren cierre por encima/debajo para confirmar.
- **Parametros**: `CONDICION` (min/max), `NIVEL_CRUCE_CROSSING_ABOVE_BELOW`, `PERIODO_EMA_CROSSING_ABOVE_BELOW`.
- **Velas necesarias**: 2+ (mas si necesita calcular EMA).

### 2.9 HALT
- **Que hace**: Detecta si el simbolo esta en halt (suspension de trading).
- **Dato que usa**: **Quote en tiempo real** — estado del mercado, no precio.
- **Por que**: Un halt es un evento externo del exchange. No aparece en velas. Requiere consultar el estado del simbolo via API de halts o quote.
- **Parametros**: `CONDICION`, `VALOR_HALT`.
- **Velas necesarias**: Ninguna. Necesita endpoint de halts/quote.
- **Estado actual**: NO IMPLEMENTADO (retorna `True` siempre).

---

## 3. VOLATILIDAD (3 filtros)

### 3.1 ATR (Average True Range)
- **Que hace**: Mide la volatilidad promedio.
- **Dato que usa**: `high`, `low`, `close` de N velas cerradas para calcular True Range, luego SMA o EMA.
- **Por que**: El True Range necesita high/low/close definitivos. Una vela en formacion subestima el TR.
- **Parametros**: `CONDICION` (min/max), `LONGITUD_ATR` (default 14), `MODO_PROMEDIO_MOVIL_ATR` (SMA/EMA), `TIMEFRAME_ATR`.
- **Velas necesarias**: ~30.

### 3.2 ATRP (ATR Percentage)
- **Que hace**: ATR como porcentaje del precio.
- **Dato que usa**: `ATR / candles[-1].close * 100` — todo velas cerradas.
- **Por que**: Deriva del ATR, misma logica.
- **Parametros**: `CONDICION` (min/max), `TIMEFRAME_ATRP`, `PERIODO_ATR_ATRP`, `TIPO_PROMEDIO_MOVIL_ATRP`, `VALOR_PROMEDIO_MOVIL_ATRP`.
- **Velas necesarias**: ~30.

### 3.3 RELATIVE_RANGE
- **Que hace**: Rango de la ultima vela vs promedio de rangos anteriores.
- **Dato que usa**: `(candles[-1].high - candles[-1].low) / promedio(rangos_anteriores)` — velas cerradas.
- **Por que**: El rango de la vela solo es definitivo al cierre.
- **Parametros**: `CONDICION` (min/max).
- **Velas necesarias**: N+1.

---

## 4. MOMENTUM E INDICADORES TECNICOS (7 filtros)

### 4.1 RSI (Relative Strength Index)
- **Que hace**: Mide sobrecompra/sobreventa.
- **Dato que usa**: `close` de N velas cerradas.
- **Por que**: El RSI se calcula sobre closes confirmados. Un close no confirmado cambiaria el RSI constantemente sin significado real.
- **Parametros**: `CONDICION` (min/max), `PERIODO_RSI` (default 14), `TIMEFRAME_RSI`.
- **Velas necesarias**: ~42 (periodo * 3 para estabilizar Wilder).

### 4.2 DISTANCE_FROM_VWAP
- **Que hace**: Distancia del precio al VWAP.
- **Dato que usa**: `candles[-1].close - VWAP` — close de vela cerrada, VWAP calculado con velas cerradas.
- **Por que**: La distancia al VWAP es un indicador de estado, no un evento. Se evalua sobre datos confirmados.
- **Parametros**: `CONDICION` (min/max), `LINEA_REFERENCIA` = VWAP, `MODO_DISTANCIA` ($ o %), `PERIODO_LINEA`.
- **Velas necesarias**: Todas las velas intradiarias (para VWAP).
- **Nota**: Comparte implementacion con DISTANCE_FROM_EMA y DISTANCE_FROM_MA en `filtro_distance_from_vwap_ema_ma.py`. Se diferencian por el parametro `LINEA_REFERENCIA`. El registry debe registrar 3 enums separados.

### 4.3 DISTANCE_FROM_EMA
- **Que hace**: Distancia del precio a una EMA.
- **Dato que usa**: `candles[-1].close - EMA` — closes de velas cerradas.
- **Por que**: Mismo razonamiento — indicador de estado.
- **Parametros**: Mismos que DISTANCE_FROM_VWAP con `LINEA_REFERENCIA` = EMA.
- **Velas necesarias**: periodo * 2.

### 4.4 DISTANCE_FROM_MA
- **Que hace**: Distancia del precio a una SMA.
- **Dato que usa**: `candles[-1].close - SMA` — closes de velas cerradas.
- **Por que**: Mismo razonamiento.
- **Parametros**: Mismos que DISTANCE_FROM_VWAP con `LINEA_REFERENCIA` = MA.
- **Velas necesarias**: N (periodo de la SMA).

### 4.5 BACK_TO_EMA_ALERT
- **Que hace**: Detecta cuando el precio retorna a tocar la EMA.
- **Dato que usa**: `candles[-2].close` vs EMA y `candles[-1].close` vs EMA — closes de velas cerradas.
- **Por que**: Un "retorno a la EMA" se confirma con el close. Si solo hace un wick hasta la EMA pero cierra lejos, no es un retorno real — es ruido. Las estrategias de pullback a EMA esperan que el close confirme proximidad.
- **Parametros**: `CONDICION` (min/max), `PERIODO_EMA_BACK_TO_EMA`, `TIMEFRAME_BACK_TO_EMA`.
- **Velas necesarias**: periodo EMA + 2.

### 4.6 THROUGH_EMA_VWAP_ALERT
- **Que hace**: Detecta cuando el precio rompe/atraviesa una EMA, VWAP o MA.
- **Dato que usa**: `candles[-2].close` vs linea y `candles[-1].close` vs linea — **closes de velas cerradas**.
- **Por que**: Un rompimiento de EMA/VWAP se confirma con close. Si el precio atraviesa la EMA con un wick pero cierra del mismo lado, no hay rompimiento confirmado. Es la misma logica que CROSSING_ABOVE_BELOW.
- **Parametros**: `CONDICION` (min/max), `THROUGH_EMA_VWAP_LINEA_CRUCE` (EMA, VWAP, MA), `THROUGH_EMA_VWAP_PERIODO_EMA`, `THROUGH_EMA_VWAP_DIRECCION_ROMPIMIENTO`.
- **Velas necesarias**: periodo + 2.

### 4.7 EMA_VWAP_SUPPORT_RESISTANCE
- **Que hace**: Verifica si una EMA o VWAP actua como soporte o resistencia.
- **Dato que usa**: `close`, `low`, `high` de varias velas cerradas recientes.
- **Por que**: Soporte/resistencia se confirma con multiples toques y rebotes — necesitas velas cerradas para ver el patron. Un solo wick no confirma soporte.
  - SUPPORT: los `low` de las ultimas velas se mantienen sobre la linea y los `close` tambien.
  - RESISTANCE: los `high` de las ultimas velas se mantienen bajo la linea y los `close` tambien.
- **Parametros**: `CONDICION` (min/max), `LINEA_REFERENCIA_EMA_VWAP_SUPPORT`, `PERIODO_EMA_EMA_VWAP_SUPPORT`, `TIPO_ROL_EMA_VWAP_SUPPORT` (SUPPORT/RESISTANCE).
- **Velas necesarias**: periodo + varias para confirmar patron.

---

## 5. TIEMPO Y PATRONES DE PRECIO (11 filtros)

### 5.1 BEARISH_BULLISH_ENGULFING
- **Que hace**: Detecta patron de vela envolvente.
- **Dato que usa**: `open`, `close` de `candles[-2]` y `candles[-1]` — **velas cerradas obligatoriamente**.
- **Por que**: Un engulfing requiere que la segunda vela CIERRE envolviendo a la primera. Si la vela no ha cerrado, no sabes si va a envolver o no. No existe engulfing sin confirmacion de cierre.
  - Alcista: `candles[-2]` bajista + `candles[-1]` alcista + `close[-1] >= open[-2]` y `open[-1] <= close[-2]`
  - Bajista: inverso.
- **Parametros**: `CONDICION`, `TIMEFRAME_BEARISH_BULLISH_ENGULFING_CANDLE`, `TIPO_PATRON`.
- **Velas necesarias**: 2.

### 5.2 CONSECUTIVE_CANDLES
- **Que hace**: N velas consecutivas alcistas o bajistas.
- **Dato que usa**: `open` y `close` de las ultimas N velas — **velas cerradas obligatoriamente**.
- **Por que**: No puedes saber si una vela es alcista (`close > open`) hasta que cierra. Evaluar una vela en formacion como "alcista" es prematuro.
- **Parametros**: `CONDICION`, `NUMERO_VELAS_CONSECUTIVAS` (default 3), `TIMEFRAME_CONSECUTIVE_CANDLES`.
- **Velas necesarias**: N.

### 5.3 FIRST_CANDLE
- **Que hace**: Evalua si la primera vela del dia fue alcista o bajista.
- **Dato que usa**: `candles[0].open` y `candles[0].close` — **primera vela cerrada del dia**.
- **Por que**: Necesitas que la primera vela cierre para saber su tipo.
- **Parametros**: `TIPO_VELA_FIRTS_CANDLE` (ALCISTA/BAJISTA).
- **Velas necesarias**: 1 (primera del dia).

### 5.4 HIGH_LOW_OF_DAY
- **Que hace**: Detecta si la ultima vela cerrada marcó un nuevo high o low del dia.
- **Dato que usa**: `candles[-1].high` vs `max(candles[:-1].high)` — o `.low` vs `min(...)` — **velas cerradas**.
- **Por que**: El high/low de una vela cerrada es definitivo. Usar el high de una vela en formacion parece tentador, pero: (1) la vela puede seguir subiendo, generando multiples senales para el mismo evento, (2) el high/low de velas cerradas ya captura los extremos reales que el mercado alcanzo. Si el high de la vela M5 cerrada es un nuevo HOD, eso es un hecho confirmado.
- **Parametros**: `CONDICION`, `OPCION_EXTREMO_HIGH_LOW_DAY` (HIGH/LOW), `TIMEFRAME_HIGH_LOW_DAY`.
- **Velas necesarias**: Todas las velas del dia.

### 5.5 NEW_CANDLE_HIGH_LOW
- **Que hace**: Detecta si la ultima vela cerrada supero el high/low de la anterior.
- **Dato que usa**: `candles[-1].high > candles[-2].high` o `.low < .low` — **velas cerradas**.
- **Por que**: Comparas extremos definitivos entre dos velas completas.
- **Parametros**: `CONDICION`, `OPCION_EXTREMO_NEW_CANDLE`, `TIMEFRAME_NEW_CANDLE`.
- **Velas necesarias**: 2.

### 5.6 PERCENTAGE_PULLBACK_HIGHS_LOWS
- **Que hace**: Mide retroceso porcentual desde un high o low reciente.
- **Dato que usa**: `((max_high - candles[-1].close) / max_high) * 100` — close de vela cerrada vs extremo historico.
- **Por que**: El retroceso se mide desde un extremo confirmado hasta un close confirmado. Un close no confirmado puede revertir.
- **Parametros**: `CONDICION`, `PUNTO_REFERENCIA_PULLBACK`, `PORCENTAJE_RETROCESO_PULLBACK`.
- **Velas necesarias**: Suficientes para identificar el extremo reciente.

### 5.7 BREAK_OVER_RECENT_HIGHS_LOWS
- **Que hace**: Detecta si el precio rompe por encima de highs recientes o por debajo de lows recientes.
- **Dato que usa**: `candles[-1].close > max(candles[:-1].high)` — **close de vela cerrada**.
- **Por que**: Un breakout se confirma con **close por encima del nivel**. Si solo el high supera el nivel pero el close queda debajo, eso es un fakeout/trampa. Las estrategias de breakout serias esperan confirmacion de cierre.
- **Parametros**: `CONDICION`, `OPCION_EXTREMO_BREAK_OVER`, `TIMEFRAME_BREAK_OVER`.
- **Velas necesarias**: N+1.

### 5.8 OPENING_RANGE_BREAKOUT
- **Que hace**: El precio cierra por encima del high del rango de apertura.
- **Dato que usa**: `candles[-1].close > candles[0].high` — **close de vela cerrada**.
- **Por que**: La estrategia ORB clasica requiere **close por encima** del rango. Un wick por encima que cierra dentro del rango es fakeout.
- **Parametros**: `CONDICION`, `TIMEFRAME_OPENING_RANGE_BREAKOUT`.
- **Velas necesarias**: ~78 (M5, sesion completa).

### 5.9 OPENING_RANGE_BREAKDOWN
- **Que hace**: El precio cierra por debajo del low del rango de apertura.
- **Dato que usa**: `candles[-1].close < candles[0].low` — **close de vela cerrada**.
- **Por que**: Misma logica que ORB pero invertida.
- **Parametros**: `CONDICION`, `TIMEFRAME_OPENING_RANGE_BREAKDOWN`.
- **Velas necesarias**: ~78 (M5).

### 5.10 PIVOTS
- **Que hace**: Verifica si el precio esta cerca de un nivel de pivot.
- **Dato que usa**: Pivot calculado con `(high_ayer + low_ayer + close_ayer) / 3` del dia anterior. Precio actual = `candles[-1].close`.
- **Por que**: Los pivots son niveles fijos calculados con datos del dia anterior. La posicion del precio respecto a ellos se evalua con close confirmado.
- **Parametros**: `CONDICION`, `TIMEFRAME_PIVOTS`.
- **Velas necesarias**: Velas del dia anterior + actual.

### 5.11 MINUTOS_IN_MARKET
- **Que hace**: Minutos transcurridos desde apertura del mercado.
- **Dato que usa**: `datetime.now()` — **reloj del sistema**.
- **Por que**: No depende de precio ni velas. Es puramente temporal.
- **Parametros**: `CONDICION` (min/max), `MINUTOS_TRANSCURRIDOS`.
- **Velas necesarias**: 0.

---

## 6. CARACTERISTICAS FUNDAMENTALES (7 filtros)

> Datos que cambian una vez al dia o menos. No requieren velas.
> Fuente: Yahoo Finance (`yahooquery`) y market-data-service.

### 6.1 FLOAT
- **Que hace**: Float shares dentro del rango.
- **Dato que usa**: `datos_fundamentales.float_shares` (Yahoo: `floatShares`).
- **Por que**: Dato fundamental, cambia trimestralmente.
- **Parametros**: `CONDICION` (min/max).
- **Comportamiento si no hay datos**: Retorna `True` (permisivo).

### 6.2 SHARES_OUTSTANDING
- **Que hace**: Acciones totales en circulacion dentro del rango.
- **Dato que usa**: `datos_fundamentales.shares_outstanding`.
- **Por que**: Dato fundamental estatico.
- **Parametros**: `CONDICION` (min/max).

### 6.3 MARKET_CAP
- **Que hace**: Capitalizacion de mercado dentro del rango.
- **Dato que usa**: `datos_fundamentales.market_cap` (calculado: `last_price * shares_outstanding`).
- **Por que**: Cambia con el precio pero el rango es amplio (small cap vs large cap). Close es suficiente.
- **Parametros**: `CONDICION` (min/max).

### 6.4 SHORT_INTEREST
- **Que hace**: Acciones en corto dentro del rango.
- **Dato que usa**: `datos_fundamentales.short_interest` (Yahoo: `sharesShort`).
- **Por que**: Se actualiza cada 2 semanas (reportes FINRA).
- **Parametros**: `CONDICION` (min/max).

### 6.5 SHORT_RATIO
- **Que hace**: Ratio short/float dentro del rango.
- **Dato que usa**: `datos_fundamentales.short_ratio` (Yahoo: `shortRatio`).
- **Por que**: Dato bisemanal.
- **Parametros**: `CONDICION` (min/max).

### 6.6 DAYS_UNTIL_EARNINGS
- **Que hace**: Dias hasta proximo reporte de earnings.
- **Dato que usa**: `datos_fundamentales.days_until_earnings` (market-data-service).
- **Por que**: Cambia una vez al dia.
- **Parametros**: `CONDICION` (min/max).

### 6.7 NOTICIAS
- **Que hace**: Filtra por estado de noticias del simbolo.
- **Dato que usa**: `datos_fundamentales.estado_noticia`.
- **Por que**: Estado discreto (hay noticia o no).
- **Parametros**: `ESTADO_NOTICIA` (NINGUNA, POSITIVA, NEGATIVA, PREVIA, DURANTE, DESPUES).

---

## Resumen de datos por filtro

### Todos usan velas cerradas excepto HALT

| # | Filtro | Dato principal | Fuente |
|---|--------|---------------|--------|
| 1 | VOLUME | `volume` vela cerrada | Candles |
| 2 | AVERAGE_VOLUME | `volume` N velas cerradas | Candles |
| 3 | VOLUMEN_POST_PRE | `volume` sesiones extendidas | Candles |
| 4 | RELATIVE_VOLUME | `volume` ratio | Candles |
| 5 | RELATIVE_VOLUME_SAME_TIME | `volume` misma hora | Candles |
| 6 | VOLUME_SPIKE | `volume` ratio spike | Candles |
| 7 | PRECIO | `close` vela cerrada | Candles |
| 8 | CHANGE | `close` (o OHLC segun config) | Candles |
| 9 | PERCENTAGE_CHANGE | `close` periodo | Candles |
| 10 | GAP_FROM_CLOSE | `open` actual, `close` anterior | Candles |
| 11 | POSITION_IN_RANGE | `close`, `high`, `low` periodo | Candles |
| 12 | PERCENTAGE_RANGE | `high`, `low` vela cerrada | Candles |
| 13 | RANGE_DOLLARS | `high`, `low` vela cerrada | Candles |
| 14 | CROSSING_ABOVE_BELOW | `close` 2 velas cerradas | Candles |
| 15 | HALT | Estado del mercado | **Quote/API tiempo real** |
| 16 | ATR | `high`, `low`, `close` N velas | Candles |
| 17 | ATRP | ATR / `close` | Candles |
| 18 | RELATIVE_RANGE | `high`, `low` velas cerradas | Candles |
| 19 | RSI | `close` N velas cerradas | Candles |
| 20 | DISTANCE_FROM_VWAP | `close`, VWAP | Candles |
| 21 | DISTANCE_FROM_EMA | `close`, EMA | Candles |
| 22 | DISTANCE_FROM_MA | `close`, SMA | Candles |
| 23 | BACK_TO_EMA_ALERT | `close` 2 velas vs EMA | Candles |
| 24 | THROUGH_EMA_VWAP_ALERT | `close` 2 velas vs linea | Candles |
| 25 | EMA_VWAP_SUPPORT_RESISTANCE | `close`, `high`, `low` N velas | Candles |
| 26 | BEARISH_BULLISH_ENGULFING | `open`, `close` 2 velas cerradas | Candles |
| 27 | CONSECUTIVE_CANDLES | `open`, `close` N velas cerradas | Candles |
| 28 | FIRST_CANDLE | `open`, `close` primera vela | Candles |
| 29 | HIGH_LOW_OF_DAY | `high` o `low` velas cerradas | Candles |
| 30 | NEW_CANDLE_HIGH_LOW | `high` o `low` 2 velas cerradas | Candles |
| 31 | PERCENTAGE_PULLBACK_HIGHS_LOWS | `close` vs extremo historico | Candles |
| 32 | BREAK_OVER_RECENT_HIGHS_LOWS | `close` vs `high`/`low` historico | Candles |
| 33 | OPENING_RANGE_BREAKOUT | `close` vs `high` primera vela | Candles |
| 34 | OPENING_RANGE_BREAKDOWN | `close` vs `low` primera vela | Candles |
| 35 | PIVOTS | `close` vs niveles pivot | Candles |
| 36 | MINUTOS_IN_MARKET | `datetime.now()` | Reloj sistema |
| 37 | FLOAT | `float_shares` | Yahoo Finance |
| 38 | SHARES_OUTSTANDING | `shares_outstanding` | Yahoo Finance |
| 39 | MARKET_CAP | `market_cap` | Yahoo + Candles |
| 40 | SHORT_INTEREST | `short_interest` | Yahoo Finance |
| 41 | SHORT_RATIO | `short_ratio` | Yahoo Finance |
| 42 | DAYS_UNTIL_EARNINGS | `days_until_earnings` | Market Data Service |
| 43 | NOTICIAS | `estado_noticia` | Datos fundamentales |

### Filtros con implementacion combinada en signal-processing-service

`DISTANCE_FROM_VWAP`, `DISTANCE_FROM_EMA` y `DISTANCE_FROM_MA` estan en un solo archivo (`filtro_distance_from_vwap_ema_ma.py`). El `filtro_registry.py` debe registrar los 3 enums apuntando a la misma clase, diferenciando por parametro `LINEA_REFERENCIA`.

### Filtro NO IMPLEMENTADO

- **HALT**: Retorna `True` siempre. Requiere integracion con endpoint de halts/quotes en tiempo real.
