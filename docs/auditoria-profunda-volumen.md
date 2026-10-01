# Auditoría profunda — Categoría VOLUMEN (investigación individual por filtro)

Complementa `auditoria-filtros.md`. Esta vez cada filtro tiene su propia investigación dedicada con fuentes citadas, no una comparación agrupada.

Nota de categorización: en scanner-management-service, AVERAGE_VOLUME, RELATIVE_VOLUME y VOLUME_SPIKE están archivados bajo `EnumCategoriaFiltro.MOMENTUM_E_INDICADORES_TECNICOS`, no `VOLUMEN` (comentario explícito en el código: "ver FiltroFactoryPercentageChange"). Es deliberado, no un bug, pero vale la pena saberlo: un usuario buscando "relative volume" en la categoría Volumen de la UI no lo va a encontrar ahí.

---

## 1. VOLUME

### Cómo lo hacen los profesionales
Es un umbral de liquidez básico, no un indicador calculado. Finviz y Warrior Trading lo usan como filtro de piso mínimo, casi siempre combinado con precio/float — Warrior Trading exige **≥500,000 acciones en pre-market** como criterio de entrada a su watchlist, y escaneos generales de day trading piden **≥100K acciones** en el período reciente como mínimo de liquidez negociable. No existe una "fórmula profesional" más allá de leer el dato.

### Cómo lo tenemos
`app/strategies/volumen/volume.py:5-20` (`VolumeStrategy`). `TIPO_VOLUMEN=CIERRE` lee `snapshot.volume` (con fallback a la última vela), `TIPO_VOLUMEN=APERTURA` lee `fundamental.preMarketVolume`. Java (`FiltroFactoryVolume.java:96-116`): condición default `MAYOR_QUE 100,000 / 5,000,000`, timeframe default 5M, validación 0-1,000,000,000.

### Gaps encontrados
- No soporta `POST` como tercera opción de `TIPO_VOLUMEN` (sí existe en VOLUMEN_POST_PRE) — inconsistencia entre dos filtros que leen el mismo tipo de dato con opciones distintas.
- `crearParametroCondicion` (línea 105-109) pasa `isInteger` default **`false`** para un valor que siempre es un conteo de acciones (nunca fraccionario) — un comentario en el propio código dice "isInteger = true (volumen de acciones)" pero el código real evalúa a `false` cuando no hay valor previo del usuario. Es cosmético (afecta solo el formato de display en la UI, no el cálculo), pero contradice su propio comentario.
- Default de 100K-5M coincide razonablemente con el piso de 100K-500K citado por fuentes reales — sin gap de fondo aquí.

### Recomendación concreta
1. Agregar `POST` a `EnumTipoVolumen` y el branch correspondiente en `VolumeStrategy.compute_value` (leer `fundamental.postMarketVolume`), igual patrón que `VolumenPostPreStrategy`.
2. Corregir `FiltroFactoryVolume.java:105-109`: el default de `isInteger` debería ser `true`, no `false`, para que coincida con el propio comentario del código.

---

## 2. AVERAGE_VOLUME

### Cómo lo hacen los profesionales
Finviz define "Average Volume" explícitamente como **el promedio de acciones negociadas por día durante los últimos 3 meses** (~63 sesiones), con variantes de 10/20/50/90 días en screeners similares. Es SIEMPRE un promedio de volumen **diario** (un número por día, sumado/promediado sobre N días), no un promedio de velas intradía. ([Finviz Help - Technical Analysis Volume](https://finviz.com/help/technical-analysis/volume), [Mastering Finviz Screener Settings](https://medium.com/@teamme/mastering-finviz-screener-settings-unlock-profitable-stock-opportunities-342ddfe79af4))

### Cómo lo tenemos
`app/strategies/volumen/average_volume.py:10-14`. Promedia `volumes_or_zero(data.candles)` sobre TODAS las velas del rango que el pipeline haya fetcheado para ese grupo/timeframe — es un promedio de **velas intradía** (M1-1H), no de sesiones diarias completas, y el tamaño de la ventana no es un parámetro propio: depende de cuántas velas pidió el grupo de filtros compartido. Java (`FiltroFactoryAverageVolume.java`): solo expone CONDICION (default `MAYOR_QUE 500,000/10,000,000`) y TIMEFRAME — ningún parámetro de "cuántas velas/sesiones".

### Gaps encontrados
- Es conceptualmente un filtro DISTINTO al "Average Volume" de Finviz/TOS: el nuestro es "promedio de volumen por vela en la ventana que trajo el grupo", el profesional es "promedio de volumen DIARIO en N sesiones". Ambos son útiles, pero no son el mismo filtro y hoy solo existe el nuestro.
- Sin ningún parámetro de tamaño de ventana — dos escáneres con el mismo filtro AVERAGE_VOLUME pueden dar resultados distintos solo porque otro filtro del mismo grupo pidió más o menos velas (acoplamiento no intencional entre filtros del mismo grupo).
- Default de condición (500K-10M) razonable comparado con los pisos de liquidez citados (100K-500K), coherente con la práctica real.

### Recomendación concreta
1. Agregar `EnumParametro.NUMERO_VELAS_AVERAGE_VOLUME` (Java + Python), default **20** (el más citado tanto en Finviz como en moving-average de volumen general), para desacoplar la ventana de este filtro de la de los demás del grupo.
2. Evaluar agregar un modo `DIARIO` separado que promedie `day_volumes`/velas D1 en vez de velas intradía, para ofrecer el equivalente real al "Average Volume 3M" de Finviz cuando el usuario lo necesite (no reemplazar el modo actual, que sigue siendo útil para "promedio reciente de M1/M5").

---

## 3. VOLUMEN_POST_PRE

### Cómo lo hacen los profesionales
Trade Ideas tiene un filtro dedicado, "**Postmarket Volume in Shares**", definido explícitamente como activo **de 16:00 a 20:00 ET** — exactamente la ventana `PhasePostMarket` que ya usa marketdata-service. ([Trade Ideas - Post Market Volume Analysis](https://www.trade-ideas.com/help/filter/PMVol/)) El pre-market se trata como su propio filtro independiente, con Warrior Trading exigiendo **≥500,000 acciones pre-market** como criterio primario de su watchlist. ([Warrior Trading - Stock Selection](https://cdn.warriortrading.com/warriortrading.com/assets/Warrior%20Trading%20-%20Stock%20Selection.pdf)) Scanz/ChartMill también separan pre-market y after-hours como screeners distintos, nunca sumados por defecto. ([Scanz - After Hours Screeners](https://scanz.com/after-hours-stock-screeners/))

### Cómo lo tenemos
`app/strategies/volumen/volumen_post_pre.py`. `TIPO_VOLUMEN` con tres modos: `PRE` (solo `preMarketVolume`), `POST` (solo `postMarketVolume`), `AMBOS` (suma, con fallback inteligente a `prevPostMarketVolume` cuando corre en pre-market y el post de hoy genuinamente aún no existe). Java (`FiltroFactoryVolumenPostPre.java`): tres opciones expuestas correctamente, default `MAYOR_QUE 10,000/1,000,000`.

### Gaps encontrados
Ninguno de fondo. Esta es la implementación **mejor alineada con el estándar profesional** de toda la categoría: la ventana 16:00-20:00 ET coincide EXACTAMENTE con la definición de Trade Ideas, y separar PRE/POST/AMBOS como opciones explícitas coincide con cómo lo hacen Scanz/ChartMill/Warrior Trading (nunca sumar por defecto sin que el usuario lo pida). El manejo del caso borde (pre-market, post de hoy aún no existe) es más cuidadoso que lo que documentan la mayoría de plataformas, que simplemente muestran "0" sin explicar la diferencia entre "cero genuino" y "dato ausente".

### Recomendación concreta
Ninguna — dejar como está. Es un buen ejemplo a seguir para otros filtros de la categoría.

---

## 4. RELATIVE_VOLUME

### Cómo lo hacen los profesionales
Aquí hay un matiz importante que la auditoría anterior simplificó de más: TradingView tiene DOS indicadores de volumen relativo distintos y ambos son legítimos:
- **"Relative Volume" (simple)**: `volume / SMA(volume, N)` con N típicamente 10-50-100 barras, **sin alinear por hora del día** — exactamente lo que hace nuestro filtro hoy. Script de referencia: `AvgVol = ta.sma(volume,10); plot(volume/AvgVol)`. ([TrendSpider - Introduction to Relative Volume](https://trendspider.com/learning-center/introduction-to-relative-volume-indicator/), [TradingView - Relative Volume by ocmodak](https://www.tradingview.com/script/pcbrfv3D-Relative-Volume/))
- **"Relative Volume at Time"**: compara contra el promedio en la MISMA hora de días previos — esta es la versión "RVOL real" que day traders usan para filtrar por sesión. ([TradingView - Relative Volume at Time](https://www.tradingview.com/support/solutions/43000705489-relative-volume-at-time/))

Es decir: nuestro RELATIVE_VOLUME **sí es un "Relative Volume" legítimo** en el sentido de la versión simple de TradingView — el error de la primera auditoría fue decir que "no es RVOL de verdad" sin reconocer que existe esa variante simple como concepto propio y usado. El gap real es otro: TradingView expone el lookback N como parámetro configurable (10/50/100), nosotros no.

### Cómo lo tenemos
`app/strategies/volumen/relative_volume.py:13-23`. Promedia TODAS las velas previas del buffer (`data.candles[:-1]`), sin límite N, y divide la vela actual contra ese promedio × 100. Java (`FiltroFactoryRelativeVolume.java`): CONDICION default `MAYOR_QUE 150.0/500.0` (en base 100 = porcentaje, 150% = 1.5x), TIMEFRAME, sin parámetro de ventana.

### Gaps encontrados
- Sin lookback configurable — usa "todas las velas que haya en el buffer", a diferencia de TradingView que expone N (10/50/100) como parámetro explícito del usuario.
- El nombre y el comportamiento SÍ coinciden con el "Relative Volume" simple de TradingView — no es necesario renombrarlo, pero si se agrega la ventana configurable, documentar que es la variante "simple" (no alineada por hora) para que el usuario elija conscientemente entre este y RELATIVE_VOLUME_SAME_TIME.
- Default 150%/500% (1.5x/5x) es razonable frente al umbral de referencia (RVOL≥2 citado como "participación al doble de lo normal", RVOL≥5 citado por Warrior Trading como criterio de entrada).

### Recomendación concreta
1. Agregar `EnumParametro.NUMERO_VELAS_RELATIVE_VOLUME` (Java+Python), default **20** (punto medio del rango 10-50-100 citado, y consistente con el Donchian/ATR/RSI que ya usan 14-20 en este sistema).
2. Documentación/etiqueta en la UI: aclarar que este filtro NO alinea por hora del día (a diferencia de RELATIVE_VOLUME_SAME_TIME), para que el usuario sepa cuál usar según su caso.

---

## 5. RELATIVE_VOLUME_SAME_TIME

### Cómo lo hacen los profesionales
Esta es la variante "real"/alineada por hora. Dos referencias con defaults distintos pero mismo concepto:
- **TradingView "Relative Volume at Time"**: promedia **10 días** por defecto, tomando la barra con el mismo offset horario de cada uno de esos 10 días anteriores. ([TradingView Help](https://www.tradingview.com/support/solutions/43000635874-how-do-we-calculate-relative-volume-and-relative-volume-at-time/))
- **Trade Ideas**: analiza un período de **30 días**, partiendo cada día en buckets de 15 minutos, y compara contra el promedio acumulado de ese bucket horario. ([Trade Ideas - Relative Volume Scanner Strategies](https://www.trade-ideas.com/learning-center/stock-scanning/relative-volume-scanner-strategies/))

El rango real de la industria es **10-30 días**, no un número único — pero ambas referencias están muy por encima de los 5 días que usamos hoy.

### Cómo lo tenemos
`app/strategies/volumen/relative_volume_same_time.py`. Tiene DOS caminos de cálculo, algo que la auditoría anterior no distinguió:
- `_from_profile` (líneas 21-32): cuando corre vía `RealtimeFilterWatcher` (con `data.day`/`data.volume_profile` disponibles), usa el **volumen acumulado del día hasta ahora** contra el promedio acumulado a esa misma hora en sesiones anteriores (vía `/marketdata/volume-profile` de marketdata-service) — esto es conceptualmente **más sofisticado** que comparar una sola vela, y se acerca más al método de "buckets acumulados" de Trade Ideas que a una comparación de barra única. Es una fortaleza real, no mencionada en la auditoría anterior.
- `_from_candles` (líneas 34-62, el camino batch/fallback): compara la vela actual contra el promedio de las velas con el mismo HH:MM en los `_DIAS_COMPARACION = 5` días previos — el número está hardcodeado, sin `EnumParametro` en ningún lado (ni Java ni Python lo exponen, no es un desalineamiento entre los dos lados, es que nunca se creó el parámetro).

Java (`FiltroFactoryRelativeVolumeSameTime.java`): CONDICION default `MAYOR_QUE 200.0/800.0`, TIMEFRAME — mismo patrón que RELATIVE_VOLUME, sin parámetro de días de comparación.

### Gaps encontrados
- `_DIAS_COMPARACION=5` está por debajo de ambas referencias citadas (10 y 30 días) — a mitad de camino del mínimo de la industria.
- Sin parámetro expuesto en ningún lado para ajustarlo.
- El camino `_from_profile` (el bueno, acumulado) solo corre en el camino realtime/event-driven — el camino batch (`_from_candles`) es estructuralmente más simple y nunca se beneficia de la mejora.

### Recomendación concreta
1. Agregar `EnumParametro.NUMERO_DIAS_RELATIVE_VOLUME_SAME_TIME` (Java+Python), default **10** (el más citado, defecto oficial de TradingView), reemplazando el `_DIAS_COMPARACION=5` hardcodeado en `relative_volume_same_time.py:3`.
2. Documentar explícitamente en el código (y opcionalmente en la UI) que el camino realtime usa el perfil acumulado (más preciso) y el batch usa comparación de barra única — no es necesario unificarlos ahora, pero sí dejar constancia de que existe esa diferencia de fidelidad entre los dos caminos.

---

## 6. VOLUME_SPIKE

### Cómo lo hacen los profesionales
Dos escuelas de umbral conviven en la práctica real:
- **Múltiplo del promedio**: el más común — "volumen actual > N × promedio de las últimas M velas", con N típico de **2x** sobre una ventana M de **20 barras**. ([TradingView Volume Spikes indicator examples](https://www.tradingview.com/script/f8PrQXhg-Volume-Spikes-Daily-VWAP-SD-Bands/))
- **Desviaciones estándar (Z-score)**: un enfoque más estadístico — Z-score >2 para spikes moderados, 4+ para extremos/raros, hasta 10 para outliers extremos en algunas herramientas. ([GitHub - UnusualVolumeDetector](https://github.com/SamPom100/UnusualVolumeDetector), [TheTrading.Tools - Unusual Volume Scanner](https://www.thetrading.tools/unusual-volume))

Ambos son legítimos; el "múltiplo del promedio" es el más simple de configurar y el que usan la mayoría de scanners retail (TOS, TradingView community scripts).

### Cómo lo tenemos
`app/strategies/volumen/volume_spike.py:13-25`. `current >= proporcion × avg(N velas previas)` — coincide EXACTAMENTE con el enfoque de "múltiplo del promedio", el más común en la práctica. Defaults: `N=5`, `proporcion=1.5`. Java (`FiltroFactoryVolumeSpike.java`): CONDICION correctamente restringida a `IGUAL_A`/`siNo` (es un gate booleano, diseño correcto confirmado en la auditoría anterior), `NUMERO_VELAS_VOLUME_SPIKE` default=5 (validación 5-50), `PROPORCION_VOLUMEN_VOLUME_SPIKE` default=1.5 (validación 1.0-20.0).

### Gaps encontrados
- Fórmula y mecanismo de condicional: sin gap, coinciden con el estándar.
- Defaults son más "sensibles" (detectan más seguido) que lo típico citado: N=5 vela es una ventana corta comparada con las 20 barras citadas como estándar, y proporción 1.5x es más bajo que el 2x citado como el umbral más común. No es incorrecto — ambos parámetros YA son configurables por el usuario — pero el valor que ve alguien que no toca el formulario es más laxo que la convención más citada.

### Recomendación concreta
Ajustar los defaults en `FiltroFactoryVolumeSpike.java:124,155` de `N=5`→**20** y `proporcion=1.5`→**2.0**, para que el comportamiento "out of the box" (sin que el usuario cambie nada) coincida con el umbral más citado en la práctica real (2x sobre 20 barras), en vez de ser más sensible de lo típico. El rango de validación actual (N: 5-50, proporción: 1.0-20.0) ya permite ambos valores, solo cambia el relleno por defecto.

---

## Resumen ejecutivo (mayor impacto primero)

1. **AVERAGE_VOLUME no es un promedio diario de N sesiones (el "Average Volume" real de Finviz/TOS), es un promedio de velas intradía sin ventana configurable.** Es la brecha conceptual más grande de la categoría — el usuario que espera el filtro clásico de liquidez de 3 meses no lo tiene disponible. Agregar `NUMERO_VELAS_AVERAGE_VOLUME` (default 20) y evaluar un modo diario aparte.

2. **RELATIVE_VOLUME_SAME_TIME usa 5 días de comparación, por debajo de las dos referencias citadas (TradingView 10, Trade Ideas 30).** Subir el default a 10 y exponerlo como parámetro — hoy no existe en ningún lado del contrato Java/Python.

3. **RELATIVE_VOLUME no tiene ventana configurable** (usa todo el buffer disponible) — aunque el cálculo en sí es un "Relative Volume" simple legítimo (coincide con la versión básica de TradingView), falta el parámetro de lookback que la plataforma de referencia sí expone.

4. **VOLUME_SPIKE tiene defaults más laxos que la convención más citada** (N=5/1.5x vs. el estándar de 20/2x) — fácil de corregir, ya es configurable, solo cambia el relleno.

5. **VOLUMEN_POST_PRE es el mejor implementado de la categoría** — la ventana 16:00-20:00 ET coincide exactamente con la definición de Trade Ideas, sin cambios necesarios. Vale la pena usarlo como plantilla de diseño para los demás.
