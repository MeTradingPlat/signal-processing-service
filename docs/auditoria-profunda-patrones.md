# Auditoría profunda: filtros de Tiempo y Patrones de Precio

Investigación individual de 16 filtros (categoría TIEMPO_Y_PATRONES_DE_PRECIO, excluyendo PIVOTS) contra fuentes dedicadas por filtro: TradingView, LuxAlgo, Investopedia, screeners reales (Trade Ideas, TrendSpider, Finviz) y fuentes de ICT/Smart Money Concepts para los 6 filtros de ese origen. Complementa (no repite) `auditoria-filtros.md`.

Nota de categorización: `HIGH_LOW_OF_DAY`, `PERCENTAGE_PULLBACK_HIGHS_LOWS` y `BREAK_OVER_RECENT_HIGHS_LOWS` están registrados en el factory Java bajo `EnumCategoriaFiltro.PRECIO_Y_MOVIMIENTO`, no bajo `TIEMPO_Y_PATRONES_DE_PRECIO` — solo una diferencia de etiqueta de categoría, sin efecto funcional, se incluyen aquí de todas formas por ser parte del grupo de patrones de precio/tiempo del pedido original.

---

## BEARISH_BULLISH_ENGULFING

### Cómo lo hacen los profesionales
El patrón engulfing estándar (Investopedia, TradingView) exige que el cuerpo de la vela actual cubra completo el cuerpo de la anterior. Pero las implementaciones serias de screener van más allá: filtran por tamaño relativo a la volatilidad para evitar falsos positivos en velas microscópicas — el engulfing debe tener un cuerpo ≥1.5× ATR(14), con la vela previa siendo de cuerpo pequeño (<0.5× ATR), y frecuentemente se exige volumen ≥1.25× el promedio de 20 días como confirmación adicional ([Enhanced Candlestick Patterns v3](https://indie-script.github.io/indicators/Enhanced%20Candlestick%20Patterns%20v3/), [TradingView engulfing scripts](https://www.tradingview.com/scripts/engulfingcandle/)).

### Cómo lo tenemos
`patrones.py:7-38` (`BearishBullishEngulfingStrategy`): compara únicamente `curr.open <= prev.close` y `curr.close >= prev.open` — geometría pura del cuerpo, sin ningún filtro de tamaño mínimo relativo a ATR ni a volumen.

### Gaps encontrados
Un engulfing de 2 centavos en un warrant ilíquido pasa exactamente igual que un engulfing violento en un símbolo líquido — no hay forma de distinguir "ruido" de "señal real" por tamaño. Es el único filtro de patrón de vela donde la industria tiene un criterio de filtrado por volatilidad bien documentado que nosotros no aplicamos en absoluto (a diferencia de `LiquidityGrabCandleStrategy`, que sí exige una proporción mecha/cuerpo).

### Recomendación concreta
Agregar un parámetro opcional `PROPORCION_ATR_MINIMA_ENGULFING` (float, default sugerido 1.0-1.5× ATR(14) del cuerpo de la vela engulfing) en `FiltroFactoryBearishBullishEngulfingCandle.java` + `BearishBullishEngulfingStrategy.compute_value`, reutilizando `calculate_atr` que ya existe en `indicators.py`. No bloqueante, pero es el gap más claro y mejor documentado de todo el bloque de patrones de vela.

---

## CONSECUTIVE_CANDLES

### Cómo lo hacen los profesionales
Conteo directo de barras consecutivas en la misma dirección, configurable por N — exactamente el mecanismo que ofrecen TradingView ("Consecutive Candle Counter"), TrendSpider y el filtro nativo de Trade Ideas ("Consecutive Candles Analysis", 15min/diario) ([TrendSpider](https://trendspider.com/trading-tools-store/indicators/69effd-consecutive-candles/), [Trade Ideas](https://forums.trade-ideas.com/help/filter/Up/)).

### Cómo lo tenemos
`patrones.py:41-53`: cuenta N velas con `close > open` (alcista) o `close < open` (bajista) consecutivas, N configurable (`NUMERO_VELAS_CONSECUTIVAS`, default 3). Coincide exactamente con el mecanismo estándar.

### Gaps encontrados
Ninguno en la fórmula. (El condicional ya fue corregido en una pasada anterior — el Java factory ahora usa `IGUAL_A` con `alcistaBajistaNinguna`, reemplazando un default `MAYOR_QUE 3` que nunca podía ser verdadero contra el rango -1..1, documentado en el propio comentario del código.)

### Recomendación concreta
Ninguna — filtro correcto tal cual.

---

## FIRST_CANDLE

### Cómo lo hacen los profesionales
No existe una fuente dedicada ampliamente citada para "primera vela del día alcista/bajista" como patrón aislado — es un concepto que casi siempre aparece subsumido dentro de Opening Range Breakout (la primera vela SÍ importa, pero como insumo del rango de apertura, no como señal por sí misma). Se documenta explícitamente aquí la ausencia de una fuente profesional dedicada en vez de forzar una comparación.

### Cómo lo tenemos
`patrones.py:56-70`: compara `close`/`open` de la primera vela del día (`first_candle_of_day`), filtrando por `TIPO_VELA_FIRTS_CANDLE` (ALCISTA/BAJISTA). Condicional ya restringido a `IGUAL_A` con `deteccionConDireccionPropia` (correcto).

### Gaps encontrados
El único gap real es el compartido de la Prioridad #1 de `auditoria-filtros.md`: `first_candle_of_day` cae al fallback `todays_candles()` en UTC cuando `data.day` no está disponible (camino batch).

### Recomendación concreta
Ninguna específica de este filtro — se resuelve al arreglar la Prioridad #1 compartida.

---

## HIGH_LOW_OF_DAY

### Cómo lo hacen los profesionales
TradingView expone un "position screener" que ubica el precio en una escala 0-100 del rango del día, donde **0 = mínimo del día y 100 = máximo del día**, consistentemente sin importar qué extremo esté vigilando el usuario ([posición screener TradingView](https://it.tradingview.com/script/tPJrWXaf-BANKNIFTY-position-screener)).

### Cómo lo tenemos
`patrones.py:73-95`: con `OPCION_EXTREMO=LOW` devuelve `(price-low)/(high-low)*100` — coincide con la convención estándar (0=mínimo, 100=máximo). Pero con `OPCION_EXTREMO=HIGH` devuelve `(high-price)/(high-low)*100`, es decir, **invierte la escala** (0 = en el máximo, 100 = en el mínimo) respecto a la opción LOW.

### Gaps encontrados
No es un bug de cálculo (el propio docstring lo explica y el condicional de Java usa `MENOR_QUE` como default, consistente con "0 = en el extremo elegido"), pero diverge de la convención única 0-100 (0=low/100=high siempre) que usan los screeners profesionales. Un usuario que cambia de LOW a HIGH sin leer la documentación puede interpretar mal la escala.

### Recomendación concreta
Documentar explícitamente en la etiqueta del parámetro que la escala se invierte según `OPCION_EXTREMO`, o — más simple — estandarizar a la convención única (0=mínimo, 100=máximo siempre) y dejar que el usuario filtre con `MAYOR_QUE`/`MENOR_QUE` según qué extremo le interesa, sin necesitar la opción HIGH/LOW en absoluto. Esto simplificaría el filtro (un parámetro menos) y lo alinearía con el estándar de la industria.

---

## NEW_CANDLE_HIGH_LOW

### Cómo lo hacen los profesionales
Canal de Donchian: máximo/mínimo de las últimas N velas, estándar de la industria en N=20 (un mes de trading en diario), con 10-14 para intradía más sensible y 30-55 para swing/position trading ([LightningChart](https://lightningchart.com/blog/trader/donchian-channels/), [Deepvue](https://deepvue.com/indicators/donchian-channels-the-breakout-traders/)).

### Cómo lo tenemos
`patrones.py:98-121`: `NUMERO_VELAS_NEW_CANDLE` default 20, exactamente el estándar de Donchian. Ya corregido (antes comparaba contra todo el buffer, ahora contra exactamente N velas previas).

### Gaps encontrados
Ninguno — coincide con el estándar documentado punto por punto.

### Recomendación concreta
Ninguna.

---

## PERCENTAGE_PULLBACK_HIGHS_LOWS

### Cómo lo hacen los profesionales
No existe un único "filtro de pullback %" estandarizado con nombre propio en plataformas de screening — el concepto más cercano y ampliamente documentado es el retroceso de Fibonacci (23.6%, 38.2%, 50%, 61.8%, 78.6%), donde la "zona dorada" 38.2-61.8% es la más citada para entradas de continuación.

### Cómo lo tenemos
`patrones.py:124-152`: retroceso % simple desde el máximo/mínimo de una ventana de N velas (`NUMERO_VELAS_PULLBACK`, default 5), sin ninguna referencia a niveles de Fibonacci.

### Gaps encontrados
No es un error — un % de retroceso simple es una métrica válida y de hecho más simple/transparente que Fibonacci — pero pierde la oportunidad de alinearse con el lenguaje que usan los traders reales ("retrocedió a la zona dorada").

### Recomendación concreta
Opcional, no bloqueante: documentar en la UI que 38-62% es la "zona dorada" de referencia, como guía de configuración del condicional (ej. sugerir `ENTRE 38 62` en vez de dejar el campo completamente libre). No requiere cambio de código, solo de guía de producto — mismo tipo de mejora que la Prioridad #5 de fundamentales en `auditoria-filtros.md`.

---

## BREAK_OVER_RECENT_HIGHS_LOWS

### Cómo lo hacen los profesionales
Mismo concepto de ruptura de rango reciente que Donchian/canal de breakout — N configurable, sin una convención de N distinta a la ya revisada en NEW_CANDLE_HIGH_LOW.

### Cómo lo tenemos
`patrones.py:155-177`: N=20 default, coincide. Ya corregido para exigir N velas previas reales (evita series degeneradas de 1 vela).

### Gaps encontrados
Ninguno.

### Recomendación concreta
Ninguna.

---

## OPENING_RANGE_BREAKOUT / OPENING_RANGE_BREAKDOWN

### Cómo lo hacen los profesionales
El ORB de 15 minutos es el estándar más usado y recomendado para quien empieza — rango más ancho, menos señales falsas, mayor convicción. El ORB de 5 minutos es la variante agresiva de scalping: ~3x más señales por día, pero con tasa de falsos breakouts notablemente más alta ([orbsetups.com](https://orbsetups.com/research/5-minute-vs-15-minute-vs-30-minute-opening-range-which-timeframe-has-the-best-win-rate/), [grandalgo.com](https://grandalgo.com/blog/orb-5-minute-vs-15-minute-which-is-better)). Ninguna fuente exige confirmación de volumen adicional al cierre fuera del rango — un cierre fuera del rango de apertura ya es la señal completa.

### Cómo lo tenemos
`patrones.py:180-205`: compara el cierre actual contra el high/low de la primera vela del día en la temporalidad elegida. `FiltroFactoryOpeningRangeBreakout.java`/`FiltroFactoryOpeningRangeBreakdown.java`: **default = 5M** en ambos factories (`EnumTimeframe._5M`), con 1M/5M/15M/30M/1H como opciones soportadas.

### Gaps encontrados
El mecanismo es correcto y ya soporta configurar la temporalidad — pero el **default elegido (5M) es la variante agresiva/ruidosa, no la recomendada para la mayoría de traders (15M)**. Un usuario que no toca el parámetro obtiene el comportamiento de scalping de alta frecuencia y alta tasa de falsos positivos, no el comportamiento "de referencia" de la industria.

### Recomendación concreta
Cambiar el default a `EnumTimeframe._15M` en ambos factories (`FiltroFactoryOpeningRangeBreakout.java`, `FiltroFactoryOpeningRangeBreakdown.java`), o como mínimo documentar en la etiqueta del parámetro que 5M es la variante agresiva. Comparten además el bug de zona horaria de la Prioridad #1 (dependen de `first_candle_of_day`).

---

## MINUTOS_IN_MARKET

### Cómo lo hacen los profesionales
No es un indicador de mercado — es un temporizador de sesión, sin análogo de "cálculo profesional" (confirmado explícitamente, no se fuerza comparación).

### Cómo lo tenemos
`patrones.py:226-237`: minutos desde las 9:30 ET, ya corregido para usar `ZoneInfo("America/New_York")` correctamente. `FiltroFactoryMinutosInMarket.java` acota el condicional a 1-390 (la sesión regular completa, 6.5h = 390 min) — límites sensatos y correctos.

### Gaps encontrados
Ninguno.

### Recomendación concreta
Ninguna.

---

## ORDER_BLOCK_IMBALANCE

### Cómo lo hacen los profesionales (ICT/Smart Money Concepts)
Dos conceptos ICT relacionados pero DISTINTOS: un **Order Block** es la vela (o pequeño grupo) de origen de un movimiento impulsivo, marcada como zona de soporte/resistencia potencial; un **Fair Value Gap (FVG)** es una ineficiencia de 3 velas donde la mecha de la vela 1 y la vela 3 nunca se solapan. LuxAlgo documenta que un Order Block se "valida" cuando la vela que forma el FVG subsiguiente cierra lejos del OB — es decir, el FVG CONFIRMA el OB, pero la zona del OB en sí es el rango de la vela de origen, NO el hueco del FVG ([LuxAlgo Order Blocks](https://www.luxalgo.com/blog/ict-trader-concepts-order-blocks-unpacked/), [LuxAlgo FVG](https://www.luxalgo.com/library/concept/fair-value-gap/)).

### Cómo lo tenemos
`liquidity_inducement.py:9-44`: `has_fair_value_gap(recent[i-1], recent[i+1], alcista)` detecta el hueco de 3 velas (coincide exactamente con la definición ICT de FVG), pero la `zona` que produce el filtro (línea 39: `(recent[i-1].high, recent[i+1].low)`) ES el hueco del FVG, no el rango de la vela de origen del impulso.

### Gaps encontrados
Simplificación real respecto a la definición estricta de dos conceptos separados: usamos el FVG como proxy de la zona del Order Block en vez de distinguir ambos. Esto es una práctica común en implementaciones retail simplificadas (muchos scripts de TradingView hacen lo mismo), no es "incorrecto" per se, pero se aleja de la definición ICT estricta donde OB y FVG son zonas distintas que pueden no coincidir exactamente. Adicionalmente, ninguna fuente exige, y nosotros tampoco verificamos, que el movimiento que genera el FVG sea un candle de "desplazamiento" (displacement) — un movimiento inusualmente fuerte, que es parte de la definición ICT completa.

### Recomendación concreta
Documentar explícitamente (ya lo hace el docstring, pero vale reforzarlo en la etiqueta visible al usuario) que esta es una aproximación simplificada "FVG como proxy del Order Block", no la implementación estricta de dos conceptos separados — para que un usuario familiarizado con ICT no asuma que es idéntico a lo que ve en indicadores dedicados de LuxAlgo/TradingView. Opcional: agregar un filtro de tamaño mínimo del hueco (ya existe parcialmente vía `near_zone`/tolerancia, pero no un mínimo absoluto de desplazamiento).

---

## LIQUIDITY_GRAB_CANDLE

### Cómo lo hacen los profesionales (ICT)
Una barrida de liquidez (liquidity sweep/grab/stop hunt) es un movimiento breve más allá de un soporte/resistencia clave que activa stops, y luego revierte. La mecha es "la cacería" — el elemento crítico; el cuerpo DEBE cerrar de vuelta DENTRO del rango anterior (si cierra fuera, es un breakout real, no un sweep) ([SwapHunt](https://swaphunt.dev/articles/liquidity-sweeps-explained), [TradingStrategyGuides](https://tradingstrategyguides.com/the-1-candlestick-for-catching-institutional-stop-hunts-the-sweep-candle-explained/)).

### Cómo lo tenemos
`liquidity_inducement.py:47-84`: exige `curr.low < prev_low and curr.close > prev_low` (perfora el mínimo previo, pero cierra de vuelta por encima) — coincide EXACTAMENTE con la definición ICT ("wick hunts, body closes back inside"). Proporción mecha/cuerpo configurable, default 2.0x.

### Gaps encontrados
Ninguno en la lógica central. La proporción 2.0x no tiene un valor "oficial" único citado por ninguna fuente (los scripts de la comunidad varían entre 1.5x y 3x), por lo que 2.0x es un punto medio razonable, no arbitrario.

### Recomendación concreta
Ninguna — es de los filtros ICT más fielmente implementados del sistema.

---

## ACCELERATION_DECELERATION

### Cómo lo hacen los profesionales
Sin fuente profesional/ICT dedicada verificable tras la búsqueda — es un concepto propio del curso de trading analizado (explícitamente reconocido así en el propio docstring del código), no un patrón con nombre estándar en TradingView/LuxAlgo/literatura ICT ampliamente citada. Se documenta la ausencia de fuente en vez de forzar una comparación.

### Cómo lo tenemos
`liquidity_inducement.py:87-118`: caída del cuerpo promedio de N velas de "desaceleración" respecto al cuerpo promedio de M velas de "aceleración" previas, por debajo de una proporción configurable (default 0.4).

### Gaps encontrados
Ninguno verificable — es internamente consistente con la descripción del propio curso que dice implementar.

### Recomendación concreta
Ninguna.

---

## CONFIRMATION_CANDLE

### Cómo lo hacen los profesionales
El concepto de "vela de poder" (strong/power candle) está bien documentado: ratio cuerpo/rango ≥70-80% es el umbral más citado para considerar una vela "fuerte" (algunos scripts usan 90%, el rango típico citado es 70-90%) ([Strong Body Candle indicator](https://www.tradingview.com/script/PqqzxcZm-Strong-Body-Candle-80-of-Range/)). Para confirmación de ruptura de estructura (Break of Structure), ICT exige que el cierre sea decisivo más allá del punto de swing, con cuerpo significativo — una mecha sola no confirma.

### Cómo lo tenemos
`liquidity_inducement.py:225-253`: `PROPORCION_CUERPO_MINIMA_CONFIRMATION_CANDLE` default 0.7 (70%) — coincide exactamente con el extremo inferior del rango documentado (70-90%). Además exige un FVG respecto a la vela anterior (combinando "vela de poder" + "imbalance", definición compuesta propia del curso).

### Gaps encontrados
Ninguno — el default 0.7 está bien fundamentado contra fuentes reales, no es un número inventado.

### Recomendación concreta
Ninguna. Opcional: el rango documentado llega hasta 90%, así que si se quisiera una variante "más estricta" podría ofrecerse como preset, pero no es necesario.

---

## RANGE_EXTREME_PROXIMITY

### Cómo lo hacen los profesionales (ICT)
Estructura de swing con el "3-candle rule": un swing high/low se confirma cuando el precio retrocede al menos 1-2 velas sin superarlo — "la palabra clave es 'confirmado', que en la práctica significa esperar al menos una o dos velas de reversión clara antes de tratar un punto como swing confirmado" ([LiquidityScan](https://liquidityscan.io/blog/what-is-a-swing-high-and-swing-low-in-ict-the-3-candle-rule)).

### Cómo lo tenemos
`liquidity_inducement.py:121-160` + `indicators.py:208-251` (`swing_range`): `confirmacion_velas` default 2 — coincide EXACTAMENTE con el rango "1-2 velas" documentado como estándar ICT. El rango "se mueve" con cada confirmación en vez de ser una ventana fija, que es precisamente la diferencia entre estructura de swing real y un canal de Donchian simple.

### Gaps encontrados
Ninguno — es de los filtros mejor alineados con su fuente ICT citada de todo el sistema.

### Recomendación concreta
Ninguna.

---

## RANGE_CONFLUENCE_D1_H4_H1

### Cómo lo hacen los profesionales
La confluencia multi-timeframe (D1 tendencia + H4/H1 contexto + TF menor para entrada) es el "estándar de oro" documentado para swing trading — el "Triple Screen Approach" clásico. La interpretación más común de "confluencia" en la literatura es ALINEACIÓN DIRECCIONAL entre temporalidades (la tendencia de D1 coincide con la de H4/H1), no necesariamente solapamiento espacial de zonas de rango exactas.

### Cómo lo tenemos
`liquidity_inducement.py:163-222`: calcula el `swing_range` de D1, H4 y H1 por separado y verifica si al menos un par de esas zonas se SOLAPA espacialmente (`zonas_cercanas`), usando la intersección más angosta como zona final.

### Gaps encontrados
No es un error, es una interpretación específica y válida de "confluencia" (solapamiento geométrico de zonas) en vez de la más citada (alineación direccional de tendencia). Es consistente con cómo el propio curso describe el concepto ("cuando se mezclan esos máximos y mínimos"), así que es fiel a SU fuente, aunque diverge de la interpretación más común en la literatura general de multi-timeframe trading.

### Recomendación concreta
Ninguna obligatoria — documentar la distinción (solapamiento de zona vs. alineación de tendencia) para que un usuario que venga de otra escuela de trading entienda qué tipo de "confluencia" está pidiendo este filtro específicamente.

---

## Resumen ejecutivo

Los 5 cambios de mayor impacto, ordenados:

1. **BEARISH_BULLISH_ENGULFING sin filtro de tamaño mínimo relativo a ATR/volumen** — es el único patrón de vela donde la industria tiene un criterio de filtrado por volatilidad ampliamente documentado (body ≥1.0-1.5× ATR(14), volumen ≥1.25× promedio) que no implementamos en absoluto. Agregar `PROPORCION_ATR_MINIMA_ENGULFING` reutilizando `calculate_atr` ya existente.

2. **Default de OPENING_RANGE_BREAKOUT/BREAKDOWN en 5M (variante agresiva), no 15M (estándar recomendado)** — ambos factories Java deberían cambiar su default a `EnumTimeframe._15M`; el mecanismo de configuración ya es correcto, solo el valor de fábrica induce al usuario hacia la variante más ruidosa.

3. **HIGH_LOW_OF_DAY invierte la escala 0-100 según la opción elegida**, divergiendo de la convención única de la industria (0=mínimo, 100=máximo siempre) — considerar simplificar a una sola escala y dejar la dirección al condicional del usuario.

4. **ORDER_BLOCK_IMBALANCE usa el FVG como proxy de la zona del Order Block**, en vez de distinguir los dos conceptos ICT separados (Order Block = vela de origen, FVG = el hueco que lo confirma) — simplificación común en implementaciones retail, pero vale documentarla explícitamente para no generar expectativas de que coincide con indicadores ICT dedicados.

5. **PERCENTAGE_PULLBACK_HIGHS_LOWS sin referencia a niveles de Fibonacci** — no es un error, pero perder la "zona dorada" (38-62%) como guía de configuración es una oportunidad de producto, no de código, consistente con la misma brecha ya señalada para los filtros fundamentales en `auditoria-filtros.md`.

Los filtros mejor implementados de todo el bloque, fieles a su fuente citada: **RANGE_EXTREME_PROXIMITY** (swing structure ICT con confirmación de 1-2 velas, coincide exacto), **LIQUIDITY_GRAB_CANDLE** (sweep con cierre de vuelta dentro del rango, coincide exacto), **NEW_CANDLE_HIGH_LOW** (Donchian N=20, coincide exacto) y **CONFIRMATION_CANDLE** (umbral de vela de poder 70%, dentro del rango documentado 70-90%).
