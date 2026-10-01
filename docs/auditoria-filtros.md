# Auditoría de filtros de escáner vs. estándar profesional

Fecha: 2026-10-01. Alcance: todos los filtros de `signal-processing-service` excepto NOTICIAS y PIVOTS. Comparación contra cómo lo implementan plataformas de screening reales (TradingView, Trade Ideas, Finviz, Thinkorswim, Warrior Trading/Scanz).

## Prioridad (corregir primero)

1. **VWAP y "día actual" usan corte de medianoche UTC, no horario de mercado ET** — `app/indicators.py:114,131` (`calculate_vwap`, `todays_candles`). Medianoche UTC cae a las 7-8pm ET, en plena sesión post-market, no al abrir pre-market (4am ET). Contamina VWAP y todo lo que depende de él (DISTANCE_FROM_VWAP, CROSSING_ABOVE_BELOW, THROUGH_EMA_VWAP_ALERT, EMA_VWAP_SUPPORT_RESISTANCE) y el "primer candle del día" (FIRST_CANDLE, OPENING_RANGE_BREAKOUT/BREAKDOWN, HIGH_LOW_OF_DAY) cuando corren sin `data.day`. Fix: usar `ZoneInfo("America/New_York")`, igual que ya se hizo en `MinutosInMarketStrategy` (`app/strategies/patrones.py:234`).

2. **El default de período EMA = 2 está repetido en 4 filtros distintos de scanner-management-service**, no solo en uno — confirmado en la segunda pasada (ver abajo): `FiltroFactoryDistanceFromVwapEmaMa.java:154`, `FiltroFactoryCrossingAboveBelow.java:160`, `FiltroFactoryThroughEmaVwapAlert.java:122`, `FiltroFactoryEmaVwapSupportResistance.java:123` tienen todos default=2. `FiltroFactoryBackToEmaAlert.java:104` tiene default=14 (distinto, también inconsistente). El fallback correcto de Python es EMA9 en los 5 casos (`app/strategies/momentum.py:39,68,96,130`, `app/strategies/precio_movimiento.py:164`), pero nunca se activa porque Java siempre manda un valor explícito. Es un bug sistémico de copy-paste entre las 5 factories de la familia EMA/VWAP, no un caso aislado.

3. **RELATIVE_VOLUME no es RVOL de verdad** (compara contra el promedio del buffer, no contra la misma hora de días anteriores — es más un volume-spike disfrazado). El que SÍ calcula RVOL correctamente, **RELATIVE_VOLUME_SAME_TIME**, tiene el lookback fijo en código (`app/strategies/volumen/relative_volume_same_time.py:3`, `_DIAS_COMPARACION`) a 5 días, cuando la industria usa 10-20.

4. **AVERAGE_VOLUME y RELATIVE_VOLUME no exponen tamaño de ventana** — solo CONDICION+TIMEFRAME en `FiltroFactoryAverageVolume.java`/`FiltroFactoryRelativeVolume.java`. No se puede elegir "promedio de 20 días" vs "90 días" como en Finviz/TOS.

5. **Filtros fundamentales (FLOAT/SHORT_INTEREST/MARKET_CAP/etc.) sin presets ni guía** hacia los rangos que de verdad producen señales de momentum real (float <10-30M, short interest >5-6% + ratio >19 días, market cap <$2B, precio >$1).

6. **RELATIVE_RANGE tiene el período de ATR hardcodeado en 14** (`app/strategies/volatilidad.py:42`), sin parámetro — inconsistente con ATR/ATRP que sí lo exponen.

7. **GAP_FROM_CLOSE no exige volumen mínimo de confirmación** — en "Gap and Go" real nunca se usa el gap% aislado, siempre junto a volumen pre-market mínimo. No es un bug de cálculo, es una brecha de guía de producto.

## Detalle por categoría

### Volumen

| Filtro | Cómo lo calculan los profesionales | Cómo lo tenemos | Gap | Recomendación |
|---|---|---|---|---|
| VOLUME | Dato bruto, sin fórmula propia | `volumen/volume.py:5-20`, lee CIERRE/APERTURA | No soporta POST como opción (sí existe en VOLUMEN_POST_PRE) | Unificar con el mismo set de opciones que VOLUMEN_POST_PRE |
| AVERAGE_VOLUME | Promedio de volumen DIARIO sobre 10/20/50/90 sesiones (Finviz "Average Volume 3M", TOS) | `volumen/average_volume.py:10-14`, promedia velas intradía sobre toda la ventana fetcheada, sin parámetro de tamaño | Usuario no controla la ventana; no existe la variante estándar "N sesiones diarias" | Agregar `NUMERO_VELAS_AVERAGE_VOLUME` o modo "DIARIO N sesiones" |
| RELATIVE_VOLUME | RVOL real compara contra el promedio en la MISMA hora del día de sesiones anteriores | `volumen/relative_volume.py:13-23`, compara contra promedio de todo el buffer sin alinear por hora | No es RVOL en el sentido profesional, es un volume-spike de 1 vela | Renombrar/documentar qué es realmente; es redundante con VOLUME_SPIKE |
| RELATIVE_VOLUME_SAME_TIME | Igual que arriba, con 10-20 sesiones de lookback | `volumen/relative_volume_same_time.py`, `_DIAS_COMPARACION = 5` fijo en código | Lookback no configurable y corto vs estándar | Exponer como parámetro, default 10-20 |
| VOLUME_SPIKE | Vela actual vs promedio de N previas × proporción | `volumen/volume_spike.py:13-25` | Ya corregido, coincide con el estándar | Sin acción |
| VOLUMEN_POST_PRE | Sin análogo directo (específico de nuestro dominio) | Con fallback a `prevPostMarketVolume` | Sin gap | Sin acción |

### Precio y movimiento

Todos correctos en fórmula: CHANGE, PERCENTAGE_CHANGE, PRECIO, POSITION_IN_RANGE, PERCENTAGE_RANGE, RANGE_DOLLARS, CROSSING_ABOVE_BELOW (ya exige cruce real), HALT (estado binario, sin cálculo). GAP_FROM_CLOSE: fórmula correcta (gap% = (precio-cierre anterior)/cierre anterior, coincide con "Gap and Go" estándar 3-4%+), pero ver Prioridad #7.

### Volatilidad

ATR/ATRP (`volatilidad.py:6-29`, `indicators.py:24-58`): Wilder's RMA de 14 períodos, exactamente el estándar de la industria (TOS/TradingView default) — de los más fieles de todo el sistema. RELATIVE_RANGE: ver Prioridad #6.

### Momentum e indicadores técnicos

RSI (`momentum.py:6-13`, `indicators.py:61-94`): Wilder's RSI de 14, estándar exacto, sin gap. DISTANCE_FROM_VWAP/EMA/MA: ver Prioridad #1 y #2. BACK_TO_EMA_ALERT/THROUGH_EMA_VWAP_ALERT/EMA_VWAP_SUPPORT_RESISTANCE (`momentum.py:57-159`): ya exigen trayectoria real de 3 puntos, correctos salvo el problema compartido de VWAP.

### Tiempo y patrones de precio

BEARISH_BULLISH_ENGULFING, CONSECUTIVE_CANDLES: correctos, sin gap. FIRST_CANDLE/HIGH_LOW_OF_DAY/OPENING_RANGE_BREAKOUT/BREAKDOWN (`patrones.py:56-95,180-205`, `day_view.py:6-25`): ver Prioridad #1 (fallback a `todays_candles()` en UTC cuando no hay `data.day`). NEW_CANDLE_HIGH_LOW (`patrones.py:98-121`): N=20 default, coincide con el canal de Donchian estándar. PERCENTAGE_PULLBACK_HIGHS_LOWS/BREAK_OVER_RECENT_HIGHS_LOWS: N configurable (5 y 20), fórmulas estándar. MINUTOS_IN_MARKET (`patrones.py:226-237`): ya corregido el bug de zona horaria, correcto hoy.

ORDER_BLOCK_IMBALANCE/LIQUIDITY_GRAB_CANDLE/ACCELERATION_DECELERATION/CONFIRMATION_CANDLE/RANGE_EXTREME_PROXIMITY/RANGE_CONFLUENCE_D1_H4_H1 (`liquidity_inducement.py`): conceptos ICT (smart money concepts), sin una única "fórmula oficial" de plataforma de screening para comparar — internamente consistentes con la definición ICT que citan sus propios docstrings (FVG de 3 velas, swing confirmado por retroceso).

### Características fundamentales

FLOAT/SHARES_OUTSTANDING/MARKET_CAP/SHORT_INTEREST/SHORT_RATIO/DAYS_UNTIL_EARNINGS (`fundamentales.py`): lectura directa de dato, correctas tal cual. El gap no está en la fórmula sino en la falta de presets/guía hacia rangos probados en la práctica real — ver Prioridad #5.

## Auditoría de condicionales y parámetros (segunda pasada)

Alcance: para los 44 filtros, (A) ¿el condicional (CONDICION) tiene sentido para el tipo de valor que produce cada filtro?, (B) ¿los parámetros que lee la estrategia Python están todos expuestos en el factory Java correspondiente, con el nombre EnumParametro exacto?, (C) ¿los defaults de Java y Python coinciden?, (D) ¿el tipo de Valor (Integer/Float/String/Condicional) coincide entre ambos lados?

### A) Restricción de condicionales: mecanismo confirmado sólido

`CondicionalOpciones.java` (scanner-management-service) restringe correctamente el condicional a IGUAL_A con los valores discretos correctos para TODOS los filtros cuyo `compute_value()` en Python solo puede devolver un conjunto acotado (patrón detectado/no detectado): BEARISH_BULLISH_ENGULFING, FIRST_CANDLE (`deteccionConDireccionPropia`, ±1/0), CONSECUTIVE_CANDLES (`alcistaBajistaNinguna`), HALT, OPENING_RANGE_BREAKOUT/BREAKDOWN, NEW_CANDLE_HIGH_LOW, BREAK_OVER_RECENT_HIGHS_LOWS, CONFIRMATION_CANDLE, ACCELERATION_DECELERATION, LIQUIDITY_GRAB_CANDLE, ORDER_BLOCK_IMBALANCE, RANGE_EXTREME_PROXIMITY, RANGE_CONFLUENCE_D1_H4_H1, VOLUME_SPIKE (`siNo`) — los 15 filtros de valor discreto revisados usan el grupo correcto, ninguno encontrado exponiendo el condicional completo sin restringir cuando no debería. No encontramos ningún filtro discreto con este control faltante.

Para los 4 filtros "alerta" que devuelven 0.0 (sin evento) o una magnitud con signo (evento con dirección) — BACK_TO_EMA_ALERT, THROUGH_EMA_VWAP_ALERT, EMA_VWAP_SUPPORT_RESISTANCE, CROSSING_ABOVE_BELOW — el factory SÍ expone el condicional completo (`EnumCondicional.values()`) a propósito, y el default es `FUERA` de una banda casi-cero (ej. `FUERA(-0.001, 0.001)` en CrossingAboveBelow) — esto es correcto y deliberado: "FUERA de casi-cero" = "hubo evento en cualquier dirección", y el usuario puede además pedir `MAYOR_QUE 2` para exigir que el cruce tenga al menos 2% de follow-through. Diseño correcto, no es un gap.

### B) Parámetros completos: sin huecos nuevos encontrados

Se verificó cada `self._param_int/_param_float/_param_str(EnumParametro.X, ...)` de las ~20 estrategias contra el `new Parametro(EnumParametro.X, ...)` correspondiente en su factory Java. Los 44 filtros tienen el EnumParametro exacto expuesto en ambos lados — no se encontró ningún parámetro que Python lea y Java nunca exponga (más allá de los 2 ya documentados en la Prioridad: ventana de AVERAGE_VOLUME/RELATIVE_VOLUME y período de ATR en RELATIVE_RANGE, que no son un desalineamiento Java/Python sino que el propio Python nunca definió un EnumParametro para ese valor). Tampoco se encontró ningún parámetro "fantasma" que Java exponga pero Python nunca lea.

`EnumParametro.VALOR_HALT` existe en el enum pero no lo usa ni `FiltroFactoryHalt.java` (solo expone CONDICION) ni `HaltStrategy` (lee el estado directo de `snapshot.tradingHalted`/`fundamental.tradingStatus`, sin parámetros) — es un enum muerto en ambos lados, no un desalineamiento, pero vale la pena limpiarlo.

### C) Defaults inconsistentes: el bug sistémico de período EMA=2

Ya corregido arriba en Prioridad #2 — se confirmó que el problema de "Java manda un default que Python nunca pensó usar" no es un caso aislado de DISTANCE_FROM_VWAP/EMA/MA, sino que se repite en:

| Filtro | Default en Java | Default en Python | Archivo Java |
|---|---|---|---|
| DISTANCE_FROM_VWAP/EMA/MA | 2 | 9 (EMA) / 20 (SMA) | `FiltroFactoryDistanceFromVwapEmaMa.java:154` |
| CROSSING_ABOVE_BELOW | 2 | 9 | `FiltroFactoryCrossingAboveBelow.java:160` |
| THROUGH_EMA_VWAP_ALERT | 2 | 9 | `FiltroFactoryThroughEmaVwapAlert.java:122` |
| EMA_VWAP_SUPPORT_RESISTANCE | 2 | 9 | `FiltroFactoryEmaVwapSupportResistance.java:123` |
| BACK_TO_EMA_ALERT | 14 | 9 | `FiltroFactoryBackToEmaAlert.java:104` |

Las 5 factories claramente se copiaron una de otra (mismo patrón `ValorInteger valor = new ValorInteger("etiqueta.vacia", enumTipoValor, valorUsuario != null ? valorUsuario.getValor() : N)`), y el valor de relleno nunca se alineó con el default real que Python documenta como el estándar de la industria (EMA9). Cualquier escáner que use cualquiera de estos 5 filtros sin que el usuario cambie manualmente el período está usando una EMA de 2 (ruido puro) o 14 (no es incorrecto per se, pero inconsistente con los otros 4).

No se encontraron otros casos de default inconsistente entre los parámetros numéricos restantes (NUMERO_VELAS_CONSECUTIVAS=3, NUMERO_VELAS_NEW_CANDLE=20, NUMERO_VELAS_PULLBACK=5, NUMERO_VELAS_BREAK_OVER=20, PERIODO_RSI=14, LONGITUD_ATR=14, PERIODO_ATR_ATRP=14 coinciden en ambos lados).

### D) Tipo de Valor: sin mismatches encontrados

Se verificó que los parámetros numéricos usan `EnumTipoValor.INTEGER`/`ValorInteger` en Java cuando Python los lee con `_param_int` (ej. `PERIODO_EMA_CROSSING_ABOVE_BELOW`), y `EnumTipoValor.FLOAT`/`ValorFloat` cuando Python usa `_param_float` (ej. `PROPORCION_VOLUMEN_VOLUME_SPIKE`, `PROPORCION_MECHA_CUERPO_LIQUIDITY_GRAB_CANDLE`). No se encontró ningún caso de tipo desalineado que haría fallar el `isinstance()` de Python en silencio.

### Prioridad (segunda pasada)

1. **Bug sistémico de default EMA=2/14 en 5 filtros** (ver tabla arriba) — mismo impacto que el ya documentado en Prioridad #2, pero 4x más extendido de lo que se había detectado. Corregir las 5 factories a default=9 en una sola pasada, ya que comparten el mismo patrón de código.
2. **`EnumParametro.VALOR_HALT` es un enum muerto** en ambos lados (Java y Python) — candidato a limpieza, no a corrección funcional.
3. El resto del contrato de parámetros (completitud, tipos, restricción de condicionales) está **sólido** — no se encontraron bugs silenciosos nuevos de "parámetro que nunca llega" más allá de los 5 defaults de EMA y los 2 ya documentados en la primera pasada (ventana de AVERAGE_VOLUME/RELATIVE_VOLUME, período fijo de RELATIVE_RANGE).
