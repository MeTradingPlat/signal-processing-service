# Auditoría profunda: Volatilidad y Momentum/Indicadores Técnicos

Fecha: 2026-10-01. Segunda pasada, filtro por filtro, con fuentes dedicadas. Complementa `auditoria-filtros.md` (no repite lo ya documentado ahí: el bug sistémico de período EMA=2/14 en 5 factories Java — aquí se confirma el alcance exacto y se agrega un hallazgo nuevo del mismo tipo pero en el MODO de suavizado del ATR).

## ATR (Average True Range)

### Cómo lo hacen los profesionales

True Range = `max(high-low, |high-prevClose|, |low-prevClose|)`, suavizado con una media. TradingView usa **RMA (Relative Moving Average) como smoothing por defecto**, matemáticamente equivalente al suavizado de Wilder (una RMA de N es equivalente a una EMA de `2N-1`, ej. RMA-10 ≈ EMA-19) — el período por defecto es **14**. SMA/EMA/WMA existen como opciones alternativas, pero RMA/Wilder's es el estándar de facto.

Fuentes: [TradingView — Average True Range (ATR)](https://www.tradingview.com/support/solutions/43000501823-average-true-range-atr/), [TradingCode.net — ATR indicator coded for Pine](https://www.tradingcode.net/tradingview/average-true-range-indicator/)

### Cómo lo tenemos

`app/analysis/indicators.py:24-58` (`calculate_atr`) implementa correctamente los 4 modos: RMA (Wilder's, líneas 52-58, seed=SMA inicial + suavizado `(prior*(N-1)+TR)/N`), EMA, SMA, y un modo adicional **VMA (ponderado por volumen)** que no es estándar de ninguna plataforma de screening revisada — es una variante propia, no necesariamente mala, pero no tiene un análogo profesional con el que compararla.

`ATRStrategy` (`volatilidad.py:6-14`) lee `MODO_PROMEDIO_MOVIL_ATR` con fallback Python `"RMA"` — correcto como fallback.

**Pero el factory Java (`FiltroFactoryATR.java:130-132`) tiene el default en `EnumModoPromedioMovil.EMA`, no RMA.** Como Java SIEMPRE manda un valor explícito al crear el filtro (mismo patrón ya documentado para los períodos EMA=2), el fallback RMA de Python nunca se activa en la práctica: **cualquier ATR creado desde la UI sin que el usuario cambie manualmente el modo usa suavizado EMA, no Wilder's/RMA — el estándar real de TradingView/TOS.**

### Gaps encontrados

1. **Bug nuevo, mismo patrón que el de los períodos EMA**: default de modo = EMA en Java vs RMA esperado por Python/la industria (`FiltroFactoryATR.java:132`).
2. El condicional por defecto (`MAYOR_QUE 0.01`, línea 111) es casi siempre verdadero — cualquier ATR real en dólares supera 0.01 — no ayuda al usuario a entender qué umbral es razonable.
3. El modo VMA no tiene análogo profesional conocido; no es necesariamente incorrecto pero no se pudo validar contra ningún estándar de la industria.

### Recomendación concreta

Cambiar `FiltroFactoryATR.java:132` de `EnumModoPromedioMovil.EMA` a `EnumModoPromedioMovil.RMA` (o el nombre que corresponda a Wilder's en `EnumModoPromedioMovil`, confirmar que existe esa opción en el enum). Mismo fix aplica a ATRP (ver abajo).

## ATRP (ATR como % del precio)

### Cómo lo hacen los profesionales

Misma fórmula ATR, expresada como `(ATR/precio)×100` — usado para comparar volatilidad entre símbolos de precio muy distinto (un ATR de $2 es enorme para una acción de $5 pero trivial para una de $500). Mismo estándar RMA/14 que ATR.

### Cómo lo tenemos

`ATRPStrategy` (`volatilidad.py:17-29`): fórmula correcta, reutiliza `calculate_atr`. Mismo problema de modo: `FiltroFactoryATRP.java:151-153` también defaultea a `EnumModoPromedioMovil.EMA`, no RMA.

### Gaps encontrados

Idéntico al de ATR — el mismo bug de default de modo, copiado entre las dos factories.

### Recomendación concreta

Mismo fix que ATR, en `FiltroFactoryATRP.java:153`.

## RELATIVE_RANGE

### Cómo lo hacen los profesionales

No es un indicador estandarizado con nombre propio en ninguna plataforma revisada (TradingView/TOS/Trade Ideas) — es una construcción derivada (rango de la vela actual como % de un ATR de referencia) que varios traders arman manualmente combinando ATR + rango de vela, pero no existe como filtro con un nombre único reconocido.

### Cómo lo tenemos

`RelativeRangeStrategy` (`volatilidad.py:32-45`): `(rango_actual/ATR)×100`, con el período de ATR **hardcodeado en 14** (línea 42), sin parámetro — ya documentado en `auditoria-filtros.md` Prioridad #6, no se repite aquí el detalle.

### Gaps encontrados

Confirmado el ya conocido (período fijo). Sin hallazgo nuevo — al no tener análogo profesional de referencia, no hay más con qué comparar la fórmula en sí (que es razonable: rango/ATR es una normalización común aunque no tenga nombre de indicador propio).

### Recomendación concreta

La ya documentada: exponer el período de ATR como parámetro, o documentar que 14 es intencional.

## RSI (Relative Strength Index)

### Cómo lo hacen los profesionales

Fórmula de Wilder: `RSI = 100 - 100/(1+RS)`, `RS = promedio_ganancias/promedio_pérdidas` suavizados con RMA sobre un período por defecto de **14**. Umbrales estándar: **sobrecompra >70, sobreventa <30** (ajustables a 80/20 para reducir señales en mercados muy tendenciales) — estos son LOS umbrales que todo trader y toda plataforma usa como punto de partida.

Fuentes: [StockCharts — RSI](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/relative-strength-index-rsi), [Fidelity — What is RSI](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/RSI)

### Cómo lo tenemos

`calculate_rsi` (`indicators.py:61-94`): implementación de Wilder correcta y fiel — seed de las primeras `period` velas tomada de la MISMA ventana para ganancias y pérdidas (el bug de seeds desalineadas ya fue corregido, según el propio comentario del código), luego suavizado `(avg*(N-1)+g)/N`. Período default 14 en ambos lados (Python y `FiltroFactoryRSI.java:108`, `:119`) — coincide.

**Pero el condicional por defecto es `MAYOR_QUE` con valor1=14.0, valor2=21.0 (`FiltroFactoryRSI.java:108-109`).** Esos números (14, 21) son valores típicos de PERÍODO, no de UMBRAL de RSI — un "RSI mayor que 14" es casi siempre verdadero (RSI real rara vez baja de 14 salvo colapsos extremos) y no corresponde a ningún concepto real de sobrecompra/sobreventa. Parece un copy-paste del campo de período en vez de un default pensado para el condicional.

### Gaps encontrados

1. **Default del condicional sin sentido**: `MAYOR_QUE 14` no filtra nada útil — no se parece a los umbrales reales (70 sobrecompra, 30 sobreventa) que cualquier trader esperaría ver pre-cargados.

### Recomendación concreta

Cambiar el default del condicional en `FiltroFactoryRSI.java` a algo que refleje el uso real — por ejemplo `MAYOR_QUE 70` (sobrecompra) o `MENOR_QUE 30` (sobreventa) como punto de partida, documentando en la etiqueta cuál de los dos casos de uso es el default.

## DISTANCE_FROM_VWAP / DISTANCE_FROM_EMA / DISTANCE_FROM_MA

### Cómo lo hacen los profesionales

Distancia del precio a una línea de referencia (VWAP, EMA o SMA), en $ o en %. Para EMA/SMA de pullback intradía, los períodos que de verdad usa la comunidad de day trading son **9 EMA (línea de momentum/gatillo) y 20 EMA o 20 SMA (línea de tendencia intradía para operar pullbacks)** — confirmado como la combinación más vista en setups de día (5 minutos como timeframe típico).

Fuentes: [Snappchart — Best EMA Settings for Day Trading: 9, 20 & 200 EMA](https://www.snappchart.app/blog/technical-indicators/ema-day-trading-strategy), [Bulls on Wall Street — Trade Moving Average Pullbacks](https://www.bullsonwallstreet.com/post/trade-moving-average-pullbacks)

VWAP: ver sección dedicada abajo (comparte la fórmula base con estos tres filtros).

### Cómo lo tenemos

`DistanceFromVWAPStrategy` (`momentum.py:16-47`, unificada para las 3 variantes — ver docstring, `DISTANCE_FROM_EMA`/`DISTANCE_FROM_MA` son alias de la misma clase ya que scanner-management-service solo emite `DISTANCE_FROM_VWAP` con un selector `LINEA_REFERENCIA`). Defaults de período en Python: **9 para EMA, 20 para SMA** (línea 39) — coinciden EXACTAMENTE con el estándar de la industria confirmado arriba. Esto confirma que el default de Python está bien pensado; el problema es que nunca se usa.

**Ya documentado en `auditoria-filtros.md` Prioridad #2**: `FiltroFactoryDistanceFromVwapEmaMa.java:153` tiene el período fijo en **2**, no 9/20, y como Java siempre manda un valor, el 9/20 correcto de Python nunca se activa. Confirmo aquí con la fuente profesional que 9/20 es exactamente lo que debería estar en el default de Java — no es una suposición, es el estándar real que usan los day traders.

### Gaps encontrados

Confirmado el ya documentado, con evidencia de que el fallback de Python (9/20) SÍ es el valor correcto y el de Java (2) es el roto — no al revés.

### Recomendación concreta

En `FiltroFactoryDistanceFromVwapEmaMa.java:153`, el default no puede ser un único número fijo porque depende de qué línea se eligió (`LINEA_REFERENCIA_DISTANCE_FROM_VWAP_EMA_MA`): si es EMA el default debería ser 9, si es SMA/MA debería ser 20. Esto requiere que `crearParametroPeriodoLinea` reciba también la línea elegida para decidir el default — hoy no lo hace (ver código, línea 147: el método no recibe el parámetro de línea). Cambio estructural pequeño pero necesario para que el default sea correcto en ambos casos, no solo "mejor que 2".

## BACK_TO_EMA_ALERT

### Cómo lo hacen los profesionales

"EMA pullback": el precio se aleja de la EMA y luego vuelve a acercarse — exactamente la definición que implementa el código (comparar distancia actual vs distancia de la vela anterior, exigir que se esté acercando). No hay una "fórmula oficial" de plataforma de screening para esto específicamente (es un patrón de trading, no un indicador con nombre registrado), pero el concepto de pullback a la EMA 9 citado arriba es el contexto estándar en el que se usa.

### Cómo lo tenemos

`BackToEMAAlertStrategy` (`momentum.py:57-77`): lógica de "se está acercando" correcta (compara `abs(curr_distance)` vs `abs(prev_distance)`). Período default en Python: 9 (línea 68) — coincide con el estándar.

**`FiltroFactoryBackToEmaAlert.java:104` tiene el default en 14**, no 9 ni 2 como las otras 4 factories de la misma familia — es inconsistente incluso dentro del propio bug sistémico (las otras 4 copian "2", esta copia "14", ninguna de las dos es el 9 correcto).

### Gaps encontrados

Confirmado el ya documentado (parte de la Prioridad #2 de `auditoria-filtros.md`), con el detalle de que este es el único de los 5 con default=14 en vez de 2.

### Recomendación concreta

Cambiar a 9, igual que las otras 4, para consistencia con el estándar real.

## THROUGH_EMA_VWAP_ALERT

### Cómo lo hacen los profesionales

"Cruce real" de una línea de referencia: la vela anterior estaba de un lado, la actual cerró del otro — definición estándar de cruce (crossover), sin ambigüedad en la industria.

### Cómo lo tenemos

`ThroughEMAVWAPAlertStrategy` (`momentum.py:80-111`): exige cruce real (`prev_close <= ref < curr_close` o inverso), con dirección configurable (ABOVE/BELOW) — correcto, coincide con la definición estándar. Soporta EMA o VWAP como línea.

`FiltroFactoryThroughEmaVwapAlert.java:122`: default de período = 2 (parte del bug sistémico ya documentado).

### Gaps encontrados

Confirmado el ya documentado, sin hallazgo adicional — la lógica de detección de cruce en sí es correcta.

### Recomendación concreta

Cambiar el default a 9, mismo fix que el resto de la familia.

## EMA_VWAP_SUPPORT_RESISTANCE

### Cómo lo hacen los profesionales

"Rebote en soporte/resistencia dinámico": el precio se acerca a la línea, no la cruza, y se aleja de nuevo del mismo lado — requiere 3 puntos (lejos/cerca/lejos) para distinguir un rebote real de simplemente alejarse por primera vez. Es exactamente la definición que el código implementa (y el propio docstring documenta la corrección de un bug anterior que solo comparaba 2 puntos).

### Cómo lo tenemos

`EMAVWAPSupportResistanceStrategy` (`momentum.py:114-158`): lógica de 3 puntos correcta, con `TIPO_ROL` (SOPORTE/RESISTENCIA) respetado. Para VWAP usa una sola foto final repetida en los 3 puntos (razonado en el comentario: VWAP se mueve lento) — aproximación razonable. Para EMA calcula el valor real en cada uno de los 3 momentos (no reusa el final) — correcto, evita el error de comparar contra un valor que no existía en ese punto del tiempo.

`FiltroFactoryEmaVwapSupportResistance.java:123`: default de período = 2 (parte del bug sistémico).

### Gaps encontrados

Confirmado el ya documentado. La lógica de 3 puntos en sí es sólida y no tiene análogo exacto en ninguna plataforma de screening (es una construcción propia razonable, no una réplica de un indicador estándar).

### Recomendación concreta

Cambiar el default a 9, mismo fix que el resto de la familia.

## VWAP (función base — afecta a DISTANCE_FROM_VWAP, THROUGH_EMA_VWAP_ALERT, EMA_VWAP_SUPPORT_RESISTANCE)

### Cómo lo hacen los profesionales

VWAP = `Σ(precio típico × volumen) / Σ(volumen)`, acumulado SOLO desde el inicio de la sesión actual — **el reset estándar para acciones de EE.UU. es a las 9:30am ET (apertura de la sesión regular)**, no a medianoche. Es un indicador puramente intradía: arranca en cero cada mañana y nunca mezcla sesiones. (Existe una variante "Anchored VWAP" que arranca desde un punto elegido por el trader en vez de la apertura, pero esa es la excepción explícita, no el default.)

Fuentes: [TradingSim — VWAP Indicator Guide](https://www.tradingsim.com/blog/vwap-indicator-guide), [Metrotrade — Understanding VWAP](https://www.metrotrade.com/understanding-vwap-for-futures-trading/)

**Corrección a `auditoria-filtros.md` Prioridad #1**: esa auditoría dejó ambiguo si el reset debía ser a las 4am ET (apertura pre-market) o 9:30am ET (apertura regular). Con esta investigación dedicada, el estándar confirmado por múltiples fuentes de day trading es **9:30am ET, la apertura de la sesión regular** — no 4am. Un VWAP que incluyera pre-market mezclaría el "precio justo" institucional de la sesión regular (lo que mide VWAP) con actividad de pre-market de volumen mucho menor y spreads más anchos, distorsionando la lectura.

### Cómo lo tenemos

`calculate_vwap` (`indicators.py:97-121`): filtra velas por `c.timestamp.date() == datetime.now(timezone.utc).date()` — **usa el día calendario en UTC, no el día de trading en ET, y no excluye pre-market**. Esto es doblemente incorrecto respecto al estándar confirmado: (1) el corte de "día" debería ser por fecha ET, no UTC (el bug ya documentado en Prioridad #1), y (2) incluso corrigiendo la zona horaria, debería excluir las velas de pre-market (antes de 9:30am ET) y no solo cortar a medianoche.

### Gaps encontrados

1. Confirmado el bug de zona horaria ya documentado (UTC vs ET).
2. **Hallazgo más preciso que el original**: el reset correcto es a las 9:30am ET (apertura regular), no "en algún punto de la madrugada" — y además de la zona horaria, falta excluir explícitamente las velas de pre-market de la suma de VWAP.

### Recomendación concreta

En `calculate_vwap`, filtrar por `timestamp` convertido a `ZoneInfo("America/New_York")`, comparando contra el inicio de la SESIÓN REGULAR de ese día (9:30am ET), no la medianoche ET ni UTC. Esto reemplaza el filtro actual `c.timestamp.date() == today` por un corte de hora exacta, igual que ya se hizo correctamente en `MinutosInMarketStrategy` (que sí usa `ZoneInfo("America/New_York")`, aunque solo para contar minutos, no para filtrar velas).

## Resumen ejecutivo (3-5 cambios de mayor impacto)

1. **VWAP debe resetear a las 9:30am ET (apertura regular), no a medianoche UTC** — confirmado con fuentes dedicadas que 9:30 ET es el estándar, no 4am ni medianoche. Afecta `calculate_vwap` y en cascada a DISTANCE_FROM_VWAP, THROUGH_EMA_VWAP_ALERT, EMA_VWAP_SUPPORT_RESISTANCE.

2. **ATR/ATRP defaultean a suavizado EMA en vez de RMA/Wilder's** (`FiltroFactoryATR.java:132`, `FiltroFactoryATRP.java:153`) — hallazgo nuevo de esta pasada, mismo patrón del bug sistémico de períodos pero en el MODO de cálculo. TradingView confirma RMA como el estándar de facto. Cualquier ATR/ATRP creado desde la UI sin tocar ese campo usa una fórmula distinta a la que el propio sistema documenta como objetivo.

3. **El período EMA=2/14 en las 5 factories de la familia EMA/VWAP debe ser 9** — confirmado con fuente dedicada que 9 EMA es exactamente el estándar real de day trading (no una elección arbitraria de Python), reforzando que el fix es cambiar Java, no Python.

4. **El default del condicional de RSI (`MAYOR_QUE 14.0/21.0`) no tiene sentido** — son valores de magnitud de período, no de umbral de sobrecompra/sobreventa. El estándar real es 70/30. Candidato nuevo no documentado antes.

5. **`DistanceFromVwapEmaMa` necesita un default de período condicionado a la línea elegida** (9 si EMA, 20 si SMA/MA) en vez de un único número fijo — el fix de "cambiar 2 por 9" no alcanza si también se permite elegir SMA, donde el estándar real es 20, no 9.
