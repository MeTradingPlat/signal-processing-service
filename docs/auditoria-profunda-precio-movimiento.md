# Auditoría profunda — Precio y Movimiento (9 filtros, uno por uno)

Fecha: 2026-10-01. Complementa `auditoria-filtros.md` (que cubrió los 44 filtros de forma agrupada) con una investigación individual y fuentes citadas para cada uno de los 9 filtros de esta categoría. Código: `app/strategies/precio_movimiento.py` (Python) + `FiltroFactory*.java` (scanner-management-service).

**Hallazgo de contexto, válido para toda la categoría**: el `EnumCategoriaFiltro` que la UI muestra NO siempre coincide con la categoría de la carpeta Python. `PERCENTAGE_CHANGE` y `CROSSING_ABOVE_BELOW` están deliberadamente reasignados a `MOMENTUM_E_INDICADORES_TECNICOS` en sus factories Java (con comentario explícito: "signal-processing-service solo pasa velas reales a filtros de esa categoría, PRECIO_Y_MOVIMIENTO nunca provee candles"), y `PERCENTAGE_RANGE`/`RANGE_DOLLARS` están en `VOLATILIDAD` (categorización correcta, son medidas de volatilidad). Son arreglos ya hechos, no un gap — pero significa que la lista de "9 filtros de precio y movimiento" del enum no es la misma lista de 9 que el usuario ve agrupados en la UI bajo esa etiqueta.

---

## CHANGE

### Cómo lo hacen los profesionales
Finviz separa esto en dos filtros rígidos y predefinidos: **"Change"** = % entre cierre actual y cierre anterior, y **"Change from Open"** = % entre cierre actual y apertura de hoy — cada uno es un filtro distinto, no configurable más allá de eso. [Finviz Screener Help](https://finviz.com/help/screener), confirmado por [TradingView: how Change filters are calculated](https://in.tradingview.com/support/solutions/43000635852-how-are-the-most-popular-filters-connected-with-change-calculated/).

### Cómo lo tenemos
`precio_movimiento.py:18-52` (`ChangeStrategy`). Un solo filtro unificado con `PUNTO_REFERENCIA_CHANGE` (OPEN/CLOSE/CLOSE_PRE_MARKET/CLOSE_POST_MARKET) y `TIPO_MEDIDA_CHANGE` (PRECIO en puntos/PORCENTAJE). Las dos opciones pre/post-market se habilitaron recientemente vía `FundamentalResponse.preMarketClose/postMarketClose` (antes devolvían `None` siempre, excluyendo el símbolo sin aviso).

### Gaps encontrados
Ninguno en la fórmula — de hecho nuestro diseño es **más flexible** que el estándar de la industria (un filtro con selector de referencia, en vez de dos filtros fijos separados como Finviz). Único detalle menor: los límites de validación en Java (`validarCondicional(..., -1000.0F, 1000.0F)`) son extremadamente laxos — en modo PORCENTAJE un cambio de "-1000% a 1000%" no tiene sentido físico (un precio no puede caer más de -100%), aunque en modo PRECIO (puntos) sí puede justificarse para acciones de precio muy alto.

### Recomendación concreta
Sin cambios funcionales. Opcional: acotar el rango de validación en modo PORCENTAJE a algo como -100/+500 para detectar configuraciones claramente erróneas en la UI.

---

## PERCENTAGE_CHANGE

### Cómo lo hacen los profesionales
Trade Ideas y TOS ofrecen variantes de "% change" sobre ventanas de tiempo configurables (no solo día-sobre-día), útil para momentum intradía de corto plazo.

### Cómo lo tenemos
`precio_movimiento.py:55-65` (`PercentageChangeStrategy`): `((last_close - first_open) / first_open) * 100` sobre la ventana de velas fetcheada, con `TIMEFRAME_PERCENTAGE_CHANGE_PERCENT` configurable (M1 a 1H). Correcto y coincide con la definición estándar.

### Gaps encontrados
Ninguno nuevo. Ya se corrigió la categorización (ver nota de contexto arriba) — antes de ese fix, cualquier escáner que usara este filtro quedaba en 0 permanentemente porque la etapa de "precio y movimiento" nunca le pasaba velas.

### Recomendación concreta
Sin cambios.

---

## PRECIO

### Cómo lo hacen los profesionales
La SEC define oficialmente "penny stock" como cualquier acción con precio **menor a $5.00** por acción (no $1, un error común) — [SECLaw.com glosario](https://seclaw.com/glossary/what-is-a-penny-stock/), [Study.com SEC Penny Stock Rules](https://study.com/academy/lesson/sec-rules-related-to-penny-stocks.html). Day traders de momentum en low-float suelen filtrar por encima de $1 (para evitar el Rule 15g-9 y la iliquidez extrema de OTC) y por debajo de $10-20 (para mantener volatilidad porcentual alta).

### Cómo lo tenemos
`precio_movimiento.py:7-15` (`PrecioStrategy`): lectura directa de `snapshot.last` con fallback a `fundamental.open`. Trivial y correcto.

### Gaps encontrados
El default de Java (`FiltroFactoryPrecio.java:97-98`) usa `valor1=0.0002`, `valor2=10.0` como límites por defecto del condicional — `0.0002` no corresponde a ningún umbral reconocido de la industria (ni el $1 "low-priced" ni el $5 SEC). Parece un valor de relleno arbitrario, no un default pensado.

### Recomendación concreta
Cambiar el default a algo con sentido documentado: `MAYOR_QUE 1.0` (evita penny stocks sub-$1 de iliquidez extrema) como default razonable, y mencionar el umbral SEC de $5 en la etiqueta/tooltip del filtro para que el usuario sepa qué significa cruzar ese número regulatoriamente.

---

## GAP_FROM_CLOSE

### Cómo lo hacen los profesionales
Gap% = (precio actual − cierre anterior) / cierre anterior × 100 — confirmado exacto. El "sweet spot" de gaps con buen follow-through está entre **3-5% (moderado) y 4-12% (óptimo)**; large-caps pueden valer con 1-2%. Volumen de confirmación es "no negociable": mínimo 100K en pre-market, o RVOL ≥2x, o 3-5x el volumen promedio de pre-market. Fuentes: [Scanz — Gap and Go Strategy](https://scanz.com/gap-and-go-strategy/), [TradeAlgo — Best Scanners for Pre-Market Movers 2026](https://www.tradealgo.com/trading-guides/tools/best-stock-scanners-for-pre-market-movers-in-2026-the-complete-guide), [ORB Setups — Gap and Go](https://orbsetups.com/research/gap-and-go-trading-strategy-how-to-combine-pre-market-gaps-with-opening-range-breakouts/).

### Cómo lo tenemos
`precio_movimiento.py:68-92` (`GapFromCloseStrategy`). Fórmula correcta, con el fallback de apertura pre-market ya corregido (antes calculaba contra un "open" fantasma de $0 antes de las 9:30 ET).

### Gaps encontrados
**Nuevo, más concreto que el ya documentado**: el default de Java (`FiltroFactoryGapFromClose.java:104`) es `valor1=0.10` (gap > 0.10%) — un umbral **30-50x más chico** que el mínimo real que usan los traders (3-4%+). Un escáner con el default de fábrica sin que el usuario lo ajuste dispara con cualquier ruido intradía, no con gaps reales. Esto es además de la falta de exigencia de volumen mínimo ya documentada en `auditoria-filtros.md` Prioridad #7.

### Recomendación concreta
Subir el default a `MAYOR_QUE 3.0` (3%, el piso del rango real de "Gap and Go"). Documentar en la UI que se recomienda combinar siempre con `VOLUMEN_POST_PRE` o `AVERAGE_VOLUME` en el mismo escáner.

---

## POSITION_IN_RANGE

### Cómo lo hacen los profesionales
TradingView tiene el concepto exacto bajo el nombre "Daily Closing Range %" (DCR): dónde cierra el precio relativo al rango de la sesión, 0-100%. Un DCR >80% indica compradores agresivos sosteniendo cerca del máximo — [LuxAlgo — Daily/Weekly Closing Range Screener](https://my.tradingview.com/script/CIOuyeNL-Daily-Weekly-Closing-Range-Screener-Compatible).

### Cómo lo tenemos
`precio_movimiento.py:95-107` (`PositionInRangeStrategy`): `((price - low) / (high - low)) * 100`, fórmula idéntica al estándar.

### Gaps encontrados
**Inconsistencia real encontrada**: cuando `high <= low` (rango degenerado — típicamente los primeros segundos/minutos del día, antes de que exista un rango real), esta estrategia devuelve **50.0** (línea 103), un valor "neutral" inventado. Esto es exactamente el mismo tipo de bug que ya se corrigió explícitamente en `HighLowOfDayStrategy` (`patrones.py:86-91`, comentario: *"un solo candle del dia no tiene rango... devolver 0.0 pasaba cualquier condicion MENOR_QUE"*), donde la solución fue devolver `None` (excluir el símbolo) en vez de un valor inventado. Aquí NO se aplicó la misma corrección: un escáner con `POSITION_IN_RANGE ENTRE 40-60` (un caso de uso real y común, "buscando consolidación a mitad de rango") puede señalar falsos positivos en los primeros minutos del día para cualquier símbolo sin rango real todavía, por la misma causa raíz ya identificada y arreglada en otro filtro.

### Recomendación concreta
Cambiar `return 50.0` por `return None` en `PositionInRangeStrategy.compute_value` cuando `q.high <= q.low`, igual que `HighLowOfDayStrategy`. Default de Java (`ENTRE 20-80`) es razonable, sin cambios ahí.

---

## PERCENTAGE_RANGE

### Cómo lo hacen los profesionales
Es distinto de `RELATIVE_RANGE` (que compara contra la propia historia del símbolo vía ATR) — este es el equivalente a cómo ATRP normaliza el ATR por precio: rango del día como % del precio, para poder comparar un stock de $5 contra uno de $500 en igualdad de condiciones. Confirmado como concepto separado y válido: [TradingView ATRP](https://www.tradingview.com/script/jFQB7ENC-Average-True-Range-Percentage-ATRP/), [Trade Ideas TRangeP](https://www.trade-ideas.com/help/filter/TRangeP/) (nota: Trade-Ideas' propio "TRangeP" en realidad compara contra el rango PROMEDIO del símbolo, un concepto más cercano a nuestro `RELATIVE_RANGE` — confirma que ambos filtros nuestros cubren partes reales y distintas del espacio de "rango como volatilidad", no están duplicados).

### Cómo lo tenemos
`precio_movimiento.py:110-120` (`PercentageRangeStrategy`): `((high-low) / mid) * 100`, usando el punto medio del rango como denominador (en vez de close). Elección razonable — evita que el valor salte con cada vela nueva como pasaría si el denominador fuera el close.

### Gaps encontrados
Ninguno. Categoría Java `VOLATILIDAD` es correcta (es una medida de volatilidad, no de dirección de precio). Default `ENTRE 2-15` razonable.

### Recomendación concreta
Sin cambios.

---

## RANGE_DOLLARS

### Cómo lo hacen los profesionales
Trade Ideas y otras plataformas ofrecen ATR/rango tanto en $ absolutos como en % — el valor en $ es útil para traders que piensan en riesgo fijo por acción, no en %. [Trade Ideas — ATR filter](https://www.trade-ideas.com/help/filter/ATR/).

### Cómo lo tenemos
`precio_movimiento.py:123-130` (`RangeDollarsStrategy`): `high - low`, trivial y correcto.

### Gaps encontrados
Ninguno de cálculo. El default `ENTRE 0.1-20.0` en dólares es razonable para acciones de precio bajo/medio, pero por diseño (es una medida NO normalizada por precio) nunca va a servir igual para una acción de $500+ — exactamente la razón por la que `PERCENTAGE_RANGE` existe en paralelo. No es un bug, es la limitación inherente y esperada de una medida en $ absolutos.

### Recomendación concreta
Sin cambios de cálculo. Documentar en la UI que este filtro es más útil para acciones de precio bajo/medio, y recomendar `PERCENTAGE_RANGE` para comparar across price tiers.

---

## CROSSING_ABOVE_BELOW

### Cómo lo hacen los profesionales
La práctica recomendada es exigir confirmación al CIERRE de la vela, no un toque intravela — "a live-bar signal can appear and disappear before the candle closes"; "wait for the candle to close and confirm the move as a crossover" — [LuxAlgo/Medium — EMA Crossover Confirmation](https://medium.com/@redsword_23261/advanced-trend-capturing-ema-crossover-multi-indicator-confirmation-trading-strategy-f390d4febe3b), confirmado en múltiples fuentes de estrategia EMA. Confirmación adicional recomendada: combinar con RSI/MACD — pero eso es composición de MÚLTIPLES filtros en el mismo escáner, no algo que este filtro individual deba hacer.

### Cómo lo tenemos
`precio_movimiento.py:133-178` (`CrossingAboveBelowStrategy`): ya exige `prev_close` a un lado y `curr_close` al otro del nivel de referencia (OPEN/CLOSE/VWAP/EMA) — coincide exactamente con la práctica recomendada de "confirmar al cierre". Ya corregido respecto a una versión anterior que solo medía distancia actual sin exigir cruce real (ver comentario en el código).

### Gaps encontrados
1. **Ya documentado en `auditoria-filtros.md` Prioridad #2**: `PERIODO_EMA_CROSSING_ABOVE_BELOW` tiene default=2 en Java (`FiltroFactoryCrossingAboveBelow.java:160`), cuando Python espera 9 como estándar de la industria.
2. **Heredado, no propio**: cuando `NIVEL_CRUCE=VWAP` o `OPEN`, el cálculo depende de `calculate_vwap`/`todays_candles` — ambos afectados por el bug de corte-de-día en UTC ya documentado como Prioridad #1. `NIVEL_CRUCE=CLOSE` (usa `fundamental.prevClose`) no está afectado.
3. **Edge case teórico, no accionable**: `compute_value` devuelve `0.0` tanto para "no hubo cruce" como, en el caso límite exacto de `ref == curr_close` tras un cruce real, para "cruce con 0% de follow-through". El default `FUERA(-0.001, 0.001)` podría en teoría no distinguir ambos casos — probabilidad prácticamente nula con floats reales, no amerita cambio.

### Recomendación concreta
Cubierto por las correcciones ya priorizadas (#1 y #2 de la primera auditoría). Sin acción nueva aquí más allá de esas dos.

---

## HALT

### Cómo lo hacen los profesionales
El estado de halt es un **dato de estado que llega de un feed regulatorio** (FINRA/exchange), no algo que se calcule — el mecanismo real es LULD (Limit Up-Limit Down): pausas de 5 minutos cuando el precio toca su banda permitida (±5% Tier 1 S&P500/Russell1000, ±10% Tier 2 resto). Fuentes: [Warrior Trading — T1/T2/T12/LULD explicado](https://www.warriortrading.com/circuit-breaker-halts/), [EdgeTick — LULD Explained](https://edgetick.com/trading-halts-explained-luld-t12/).

### Cómo lo tenemos
`precio_movimiento.py:181-191` (`HaltStrategy`): lee directamente `snapshot.tradingHalted` o `fundamental.tradingStatus != "ACTIVE"` — exactamente el patrón correcto ("halt es un flag que se recibe, no se calcula"). Ya restringido en Java a `IGUAL_A` con `CondicionalOpciones.siNo()`.

### Gaps encontrados
Ninguno en esta estrategia. La corrección/precisión depende enteramente de que marketdata-service reciba y traduzca bien el estado de halt de TastyTrade/el exchange — fuera del alcance de este filtro.

### Recomendación concreta
Sin cambios. Si se quisiera profundizar, el punto de inversión sería verificar en marketdata-service qué tan fielmente se traduce el campo de estado de TastyTrade a `tradingHalted`/`tradingStatus` — no es parte de esta auditoría de signal-processing-service.

---

## Resumen ejecutivo (cambios de mayor impacto, esta categoría)

1. **GAP_FROM_CLOSE: default de 0.10% es 30-50x menor que el umbral real de "Gap and Go" (3-4%+)** — subir a `MAYOR_QUE 3.0` como default de fábrica. Es el hallazgo nuevo de mayor impacto práctico de esta pasada: un usuario que no toque el default hoy obtiene ruido, no gaps reales.
2. **POSITION_IN_RANGE devuelve 50.0 en rango degenerado en vez de `None`** — mismo bug ya corregido en `HighLowOfDayStrategy` pero no replicado aquí; causa falsos positivos tempranos en el día para escáneres tipo "ENTRE 40-60".
3. **PRECIO: default `0.0002` sin ningún sentido reconocido** — reemplazar por `MAYOR_QUE 1.0` y documentar el umbral SEC de $5 para penny stocks en la etiqueta del filtro.
4. Confirmado (no es gap nuevo, pero vale la pena como hallazgo positivo): el diseño de `CHANGE` con selector de punto de referencia es más flexible que el estándar rígido de dos-filtros-separados de Finviz.
5. Confirmado: `PERCENTAGE_RANGE` y `RELATIVE_RANGE`/`RANGE_DOLLARS` NO son redundantes entre sí — cada uno normaliza un eje distinto (precio vs. historia propia vs. absoluto en $), coincide con cómo Trade Ideas/TradingView separan estos conceptos.
