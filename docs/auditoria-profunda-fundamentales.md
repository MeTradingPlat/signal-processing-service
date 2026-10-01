# Auditoría profunda: filtros fundamentales (CARACTERISTICAS_FUNDAMENTALES)

Fecha: 2026-10-01. Profundización de la sección "Características fundamentales" de `auditoria-filtros.md`, filtro por filtro, con fuentes dedicadas y rangos numéricos exactos de scanners profesionales reales (Warrior Trading/Ross Cameron, Scanz, fuentes de short-interest).

Hallazgo transversal clave: en los 6 filtros, el factory Java fija `CONDICION` por defecto en **MAYOR_QUE**, y `valor1`/`valor2` vienen prellenados como si fueran para un **ENTRE** (un piso y un techo razonables). Como MAYOR_QUE solo usa `valor1`, el `valor2` configurado queda invisible/ignorado por defecto — el usuario tiene que saber cambiar manualmente la condición a ENTRE para que el techo tenga efecto. Esto explica por qué varios defaults "parecen" razonables en el código pero no filtran nada útil en la práctica.

## FLOAT

### Cómo lo hacen los profesionales
Ross Cameron (Warrior Trading) busca float **≤20M acciones como ideal**, acepta hasta 50M en el pre-market scan, y considera "bajo" cualquier cosa por debajo de 100M pero prioriza fuertemente los de 20M o menos — a menor float, mayor volatilidad por movimiento de volumen. Su scan de pre-market combina float <50M con precio $2-$20 y gap ≥5% con volumen >100K.

### Cómo lo tenemos
`app/strategies/fundamentales.py:4-8` (`FloatStrategy`): lectura directa de `data.fundamental.floatShares`, sin cálculo. `FiltroFactoryFloat.java:87-106`: CONDICION default **MAYOR_QUE 1,000** (mil acciones), con `valor2=50,000,000` definido pero ignorado bajo MAYOR_QUE. Validación permite 1,000 a 10 billones.

### Gaps encontrados
El default efectivo es "float > 1,000 acciones" — prácticamente CUALQUIER acción cotizada cumple esto, el filtro no filtra nada si el usuario lo agrega sin tocarlo. El valor que sí tiene sentido (50M, ya en el código como `valor2`) está invisible por el CONDICION por defecto.

### Recomendación concreta
Cambiar el default a CONDICION=**MENOR_QUE** con `valor1=20,000,000` (el ideal de Ross Cameron), o si se prefiere mantener MAYOR_QUE como condición neutra por consistencia con los otros filtros, al menos cambiar `valor1` a algo que refleje "float bajo" como techo via MENOR_QUE, no piso via MAYOR_QUE — la semántica de "float" para momentum SIEMPRE es "menor que", nunca "mayor que".

## SHARES_OUTSTANDING

### Cómo lo hacen los profesionales
Ninguna fuente de day trading cita "shares outstanding" como criterio de scanner independiente — es un insumo para calcular Float% (float/shares outstanding) y Market Cap (shares outstanding × precio), no un filtro que se use solo. Donde aparece explícito es para distinguir "low float" real de una empresa que simplemente tiene pocas acciones outstanding en total (sin ser necesariamente de baja capitalización).

### Cómo lo tenemos
`fundamentales.py:11-15` (`SharesOutstandingStrategy`): lectura directa. `FiltroFactorySharesOutstanding.java:87-106`: MAYOR_QUE 10,000,000 por defecto, `valor2=1,000,000,000` ignorado.

### Gaps encontrados
Mismo patrón del default "MAYOR_QUE un piso bajo" sin filtrar nada útil. Además, es el filtro con MENOR justificación de existir como standalone en los scanners profesionales — su valor real es como insumo de Float%, que el sistema no calcula (ver recomendación).

### Recomendación concreta
Mantenerlo como filtro secundario/raramente usado (no es prioritario corregir su default), pero considerar agregar un filtro derivado **FLOAT_PERCENT = floatShares/sharesOutstanding** en una iteración futura — es una métrica real que usan plataformas como Scanz/Fintel ("float % of shares outstanding") que hoy no existe en el sistema ni como FLOAT ni como SHARES_OUTSTANDING por separado.

## MARKET_CAP

### Cómo lo hacen los profesionales
El rango de small-cap estándar es **$300M-$2B** (algunas fuentes usan $250M-$2B); por debajo de $300M es micro-cap, donde la liquidez se vuelve poco confiable y el riesgo de manipulación es mayor. Para momentum/day trading de small-caps, un preset típico es market cap ≤$2B combinado con cambio ≥+5% y volumen ≥500K.

### Cómo lo tenemos
`fundamentales.py:18-22` (`MarketCapStrategy`): lectura directa. `FiltroFactoryMarketCap.java:87-100`: MAYOR_QUE 1,000,000 ($1M) por defecto, `valor2=2,000,000,000` ($2B, que SÍ coincide con el techo profesional estándar) ignorado bajo MAYOR_QUE.

### Gaps encontrados
El valor2 por defecto ($2B) es exactamente correcto como techo de small-cap, pero queda inactivo. El valor1 ($1M) es tan bajo que incluye literalmente cualquier empresa cotizada, incluyendo shells sin negocio real.

### Recomendación concreta
Cambiar CONDICION default a **ENTRE** con `valor1=300,000,000` (piso de small-cap, excluye micro-cap de alto riesgo de manipulación) y `valor1`=$2B ya correcto como techo. Esto activa el rango que el propio código ya tenía definido pero nunca usaba.

## SHORT_INTEREST

### Cómo lo hacen los profesionales
Short interest como % del float: **>10% es candidato de squeeze**, **>20% señala posicionamiento bajista de alta convicción**, **>30% es zona de squeeze potencial**. Un checklist de squeeze completo pide además días-a-cubrir en aumento y costo de préstamo subiendo junto con el short interest.

### Cómo lo tenemos
`fundamentales.py:25-29` (`ShortInterestStrategy`): lectura directa de `data.fundamental.shortInterest` (ya expresado como %, confirmado contra `marketdata-service/internal/core/domain/fundamentals.go`). `FiltroFactoryShortInterest.java:87-99`: MAYOR_QUE **5.0** por defecto, `valor2=50.0` ignorado. Validación permite 0-100.

### Gaps encontrados
El default de 5% está por DEBAJO del piso real de "candidato de squeeze" (10%) citado por las fuentes — un usuario que use el default sin ajustar obtiene resultados mucho más ruidosos/menos selectivos que un scanner profesional de squeeze.

### Limitación estructural real (no es un bug)
FINRA (la fuente de este dato, confirmado en `marketdata-service/internal/adapters/outgoing/external/finra/`) solo reporta short interest **dos veces al mes** (el 15 y el último día hábil del mes), y los publica **7 días hábiles después** de la fecha de liquidación — el dato puede tener hasta ~2-3 semanas de antigüedad en cualquier momento dado. Esto es una limitación de la industria completa (ningún scanner, ni siquiera los de pago, tiene short interest intradía real), no algo que corregir en el código. Ya está correctamente tratado como pre-filtro ESTÁTICO (no dinámico) en el sistema, que es la decisión arquitectónica correcta dado este hecho.

### Recomendación concreta
Subir el default a MAYOR_QUE **10.0** (piso real de squeeze candidate). Documentar en la UI/tooltip la limitación de frecuencia FINRA para que el usuario no espere que este filtro reaccione el mismo día a un evento de corto.

## SHORT_RATIO (days to cover)

### Cómo lo hacen los profesionales
Days to cover = acciones en corto / volumen promedio diario. **>5 días se considera elevado**, **>8 días es una señal de advertencia genuina** de short squeeze (fuentes citan también 8+ como "alta probabilidad de squeeze").

### Cómo lo tenemos
`fundamentales.py:32-36` (`ShortRatioStrategy`): lectura directa. `FiltroFactoryShortRatio.java:87-99`: MAYOR_QUE **1.0** por defecto, `valor2=15.0` ignorado. Validación permite 0-30.

### Gaps encontrados
El default de 1.0 día es trivialmente cierto para casi cualquier acción — no filtra nada. El valor2 (15) ya configurado es razonable como techo (por encima de 15 días es un extremo, útil para ENTRE), pero inactivo.

### Recomendación concreta
Cambiar el default a MAYOR_QUE **5.0** (piso de "elevado" según las fuentes), o ENTRE 5-15 usando el valor2 ya existente en el código. Misma limitación estructural de frecuencia FINRA que SHORT_INTEREST, mismo tratamiento correcto como estático.

## DAYS_UNTIL_EARNINGS

### Cómo lo hacen los profesionales
El pre-earnings runup (anticipación de resultados) se concentra típicamente en una ventana de **7-14 días antes del reporte** (algunas estrategias usan 3-5 días para movimientos más cortos, otras hasta 20 días de retorno acumulado terminando 2 días antes del anuncio). No hay un número único "oficial", pero 7-14 días es el rango más citado para capturar momentum pre-earnings real sin capturar ruido de mucho antes.

### Cómo lo tenemos
`fundamentales.py:39-43` (`DaysUntilEarningsStrategy`): lectura directa. `FiltroFactoryDaysUntilEarnings.java:87-103`: MAYOR_QUE **0** por defecto, `valor2=30` ignorado. Validación permite 0-365.

### Gaps encontrados
El default "MAYOR_QUE 0" es verdadero para prácticamente cualquier día del año excepto el día mismo del earnings — no aísla la ventana de anticipación en absoluto. Es, de los 6, el default MENOS útil tal cual está.

### Recomendación concreta
Cambiar el default a **ENTRE 0-14** (ventana estándar de pre-earnings runup), usando un valor2 más ajustado que el 30 actual (30 días es demasiado amplio según las fuentes, que convergen en 7-14).

---

## Resumen ejecutivo

**Los 3-5 cambios de mayor impacto:**

1. **Los 6 filtros tienen el mismo patrón de diseño roto**: CONDICION default = MAYOR_QUE usando solo `valor1` (casi siempre demasiado permisivo), con un `valor2` ya razonable en el código pero invisible. Es un arreglo de UNA sola clase de bug repetido 6 veces — más barato de corregir junto que uno por uno.
2. **SHORT_INTEREST y SHORT_RATIO tienen pisos muy por debajo del estándar real** (5% vs 10% real; 1 día vs 5 días real) — un usuario que confíe en el default obtiene resultados mucho menos selectivos que lo que la industria considera "candidato de squeeze".
3. **DAYS_UNTIL_EARNINGS es el default menos funcional de los 6** — "mayor que 0" no aísla ninguna ventana real.
4. **MARKET_CAP ya tiene el techo correcto ($2B) en el código**, solo falta activar el piso (300M) y cambiar a ENTRE.
5. **La limitación de frecuencia de FINRA en SHORT_INTEREST/SHORT_RATIO es estructural, no corregible** — ya está bien manejada arquitectónicamente (pre-filtro estático), solo falta documentarla para el usuario final.

### Preset sugerido: "Low Float Momentum" (estilo Ross Cameron/Warrior Trading)

| Filtro | Condición sugerida |
|---|---|
| FLOAT | MENOR_QUE 20,000,000 |
| MARKET_CAP | ENTRE 50,000,000 y 2,000,000,000 |
| SHARES_OUTSTANDING | sin filtro (no es criterio primario) |

(Complementar con PRECIO ENTRE 2-20, RELATIVE_VOLUME_SAME_TIME ≥5, CHANGE/GAP_FROM_CLOSE ≥10% — fuera del alcance de esta categoría pero son el resto del setup real citado por las fuentes.)

### Preset sugerido: "Short Squeeze Candidate"

| Filtro | Condición sugerida |
|---|---|
| SHORT_INTEREST | MAYOR_QUE 10 (candidato) o 20 (alta convicción) |
| SHORT_RATIO | MAYOR_QUE 5 (elevado) o 8 (señal fuerte) |
| FLOAT | MENOR_QUE 50,000,000 (float bajo amplifica el efecto de squeeze) |
| MARKET_CAP | MENOR_QUE 2,000,000,000 (small/micro-cap, donde los squeezes son más violentos) |

Fuentes citadas inline por sección; principales: Warrior Trading (warriortrading.com/scanners, support.warriortrading.com), BananaFarmer (bananafarmer.app/learn/small-cap-momentum-scanner), LiberatedStockTrader/Scanz/PowerCycleTrading (short interest/days to cover), FINRA Rule 4560 (finra.org/rules-guidance/notices/21-19), Quantpedia/TrendSpider (pre-earnings runup timing).
