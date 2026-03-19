"""Tests de integración para worker_filtros con datos OHLCV reales.

Datos obtenidos de: https://metradingplat.com/api/marketdata/historical/{symbol}?timeframe={TF}&bars=60
- AAPL D1: 60 velas diarias (2025-12-10 a 2026-03-09)
- MSFT D1: 60 velas diarias (2025-12-10 a 2026-03-09)
- AAPL M5: 60 velas de 5 minutos (2026-03-09)

A diferencia de test_worker_filtros.py, estos tests NO usan mock de pandas_ta.
Calculan los indicadores reales y verifican que la lógica del filtro sea correcta.
"""

import pandas as pd
import pytest

# Saltar módulo completo si pandas_ta no puede cargarse (falta numba).
# pandas_ta==0.4.71b0 requiere numba, que no soporta Python 3.14+.
# Estos tests corren en Docker donde el entorno tiene las dependencias completas.
pytest.importorskip(
    "pandas_ta",
    reason="pandas_ta requiere numba; no disponible en Python 3.14+. Correr en Docker.",
)

from app.core.worker_filtros import evaluar_simbolos

# ──────────────────────────────────────────────────────────────────────────────
# Datos reales AAPL D1 (60 velas diarias)
# ──────────────────────────────────────────────────────────────────────────────

AAPL_D1 = [
    {"symbol":"AAPL","timestamp":"2025-12-10T00:00:00Z","open":277.75,"high":279.75,"low":276.44,"close":278.78,"volume":33043922.0},
    {"symbol":"AAPL","timestamp":"2025-12-11T00:00:00Z","open":279.095,"high":279.59,"low":273.81,"close":278.03,"volume":33253925.0},
    {"symbol":"AAPL","timestamp":"2025-12-12T00:00:00Z","open":277.9,"high":279.22,"low":276.82,"close":278.28,"volume":39533801.0},
    {"symbol":"AAPL","timestamp":"2025-12-15T00:00:00Z","open":280.15,"high":280.15,"low":272.84,"close":274.11,"volume":50410957.0},
    {"symbol":"AAPL","timestamp":"2025-12-16T00:00:00Z","open":272.82,"high":275.5,"low":271.79,"close":274.61,"volume":37651032.0},
    {"symbol":"AAPL","timestamp":"2025-12-17T00:00:00Z","open":275.01,"high":276.16,"low":271.64,"close":271.84,"volume":50142064.0},
    {"symbol":"AAPL","timestamp":"2025-12-18T00:00:00Z","open":273.605,"high":273.63,"low":266.95,"close":272.19,"volume":51633686.0},
    {"symbol":"AAPL","timestamp":"2025-12-19T00:00:00Z","open":272.145,"high":274.6,"low":269.9,"close":273.67,"volume":144635553.0},
    {"symbol":"AAPL","timestamp":"2025-12-22T00:00:00Z","open":272.86,"high":273.88,"low":270.505,"close":270.97,"volume":36576024.0},
    {"symbol":"AAPL","timestamp":"2025-12-23T00:00:00Z","open":270.84,"high":272.5,"low":269.56,"close":272.36,"volume":29642935.0},
    {"symbol":"AAPL","timestamp":"2025-12-24T00:00:00Z","open":272.34,"high":275.43,"low":272.195,"close":273.81,"volume":17911712.0},
    {"symbol":"AAPL","timestamp":"2025-12-26T00:00:00Z","open":274.16,"high":275.37,"low":272.86,"close":273.4,"volume":21524065.0},
    {"symbol":"AAPL","timestamp":"2025-12-29T00:00:00Z","open":272.69,"high":274.36,"low":272.35,"close":273.76,"volume":23718087.0},
    {"symbol":"AAPL","timestamp":"2025-12-30T00:00:00Z","open":272.81,"high":274.08,"low":272.28,"close":273.08,"volume":22140461.0},
    {"symbol":"AAPL","timestamp":"2025-12-31T00:00:00Z","open":273.06,"high":273.68,"low":271.75,"close":271.86,"volume":27295497.0},
    {"symbol":"AAPL","timestamp":"2026-01-02T00:00:00Z","open":272.255,"high":277.84,"low":269.0,"close":271.01,"volume":37840554.0},
    {"symbol":"AAPL","timestamp":"2026-01-05T00:00:00Z","open":270.64,"high":271.51,"low":266.14,"close":267.26,"volume":45650866.0},
    {"symbol":"AAPL","timestamp":"2026-01-06T00:00:00Z","open":267.0,"high":267.55,"low":262.12,"close":262.36,"volume":52352852.0},
    {"symbol":"AAPL","timestamp":"2026-01-07T00:00:00Z","open":263.2,"high":263.68,"low":259.81,"close":260.33,"volume":48311533.0},
    {"symbol":"AAPL","timestamp":"2026-01-08T00:00:00Z","open":257.02,"high":259.29,"low":255.7,"close":259.04,"volume":50421740.0},
    {"symbol":"AAPL","timestamp":"2026-01-09T00:00:00Z","open":259.075,"high":260.21,"low":256.22,"close":259.37,"volume":39998542.0},
    {"symbol":"AAPL","timestamp":"2026-01-12T00:00:00Z","open":259.16,"high":261.3,"low":256.8,"close":260.25,"volume":45268836.0},
    {"symbol":"AAPL","timestamp":"2026-01-13T00:00:00Z","open":258.72,"high":261.81,"low":258.39,"close":261.05,"volume":45731820.0},
    {"symbol":"AAPL","timestamp":"2026-01-14T00:00:00Z","open":259.49,"high":261.82,"low":256.71,"close":259.96,"volume":40022555.0},
    {"symbol":"AAPL","timestamp":"2026-01-15T00:00:00Z","open":260.65,"high":261.04,"low":257.05,"close":258.21,"volume":39392526.0},
    {"symbol":"AAPL","timestamp":"2026-01-16T00:00:00Z","open":257.9,"high":258.9,"low":254.93,"close":255.53,"volume":72147286.0},
    {"symbol":"AAPL","timestamp":"2026-01-20T00:00:00Z","open":252.73,"high":254.79,"low":243.42,"close":246.7,"volume":80295860.0},
    {"symbol":"AAPL","timestamp":"2026-01-21T00:00:00Z","open":248.7,"high":251.56,"low":245.18,"close":247.65,"volume":54659273.0},
    {"symbol":"AAPL","timestamp":"2026-01-22T00:00:00Z","open":249.2,"high":251.0,"low":248.15,"close":248.35,"volume":39727765.0},
    {"symbol":"AAPL","timestamp":"2026-01-23T00:00:00Z","open":247.32,"high":249.41,"low":244.68,"close":248.04,"volume":41698726.0},
    {"symbol":"AAPL","timestamp":"2026-01-26T00:00:00Z","open":251.48,"high":256.56,"low":249.8,"close":255.41,"volume":55991405.0},
    {"symbol":"AAPL","timestamp":"2026-01-27T00:00:00Z","open":259.17,"high":261.95,"low":258.21,"close":258.27,"volume":49663337.0},
    {"symbol":"AAPL","timestamp":"2026-01-28T00:00:00Z","open":257.65,"high":258.855,"low":254.51,"close":256.44,"volume":41305155.0},
    {"symbol":"AAPL","timestamp":"2026-01-29T00:00:00Z","open":258.0,"high":259.65,"low":254.41,"close":258.28,"volume":67271461.0},
    {"symbol":"AAPL","timestamp":"2026-01-30T00:00:00Z","open":255.165,"high":261.8999,"low":252.18,"close":259.48,"volume":92488374.0},
    {"symbol":"AAPL","timestamp":"2026-02-02T00:00:00Z","open":260.03,"high":270.49,"low":259.205,"close":270.01,"volume":73950826.0},
    {"symbol":"AAPL","timestamp":"2026-02-03T00:00:00Z","open":269.2,"high":271.875,"low":267.61,"close":269.48,"volume":64407816.0},
    {"symbol":"AAPL","timestamp":"2026-02-04T00:00:00Z","open":272.285,"high":278.95,"low":272.285,"close":276.49,"volume":90562873.0},
    {"symbol":"AAPL","timestamp":"2026-02-05T00:00:00Z","open":278.13,"high":279.5,"low":273.23,"close":275.91,"volume":53002604.0},
    {"symbol":"AAPL","timestamp":"2026-02-06T00:00:00Z","open":277.12,"high":280.905,"low":276.925,"close":277.86,"volume":50478038.0},
    {"symbol":"AAPL","timestamp":"2026-02-09T00:00:00Z","open":277.905,"high":278.2,"low":271.7,"close":274.62,"volume":44633054.0},
    {"symbol":"AAPL","timestamp":"2026-02-10T00:00:00Z","open":274.885,"high":275.37,"low":272.94,"close":273.68,"volume":34381656.0},
    {"symbol":"AAPL","timestamp":"2026-02-11T00:00:00Z","open":274.695,"high":280.18,"low":274.45,"close":275.5,"volume":51939191.0},
    {"symbol":"AAPL","timestamp":"2026-02-12T00:00:00Z","open":275.59,"high":275.72,"low":260.18,"close":261.73,"volume":81087422.0},
    {"symbol":"AAPL","timestamp":"2026-02-13T00:00:00Z","open":262.01,"high":262.23,"low":255.45,"close":255.78,"volume":56312978.0},
    {"symbol":"AAPL","timestamp":"2026-02-17T00:00:00Z","open":258.05,"high":266.29,"low":255.54,"close":263.88,"volume":58491031.0},
    {"symbol":"AAPL","timestamp":"2026-02-18T00:00:00Z","open":263.6,"high":266.82,"low":262.45,"close":264.35,"volume":34212108.0},
    {"symbol":"AAPL","timestamp":"2026-02-19T00:00:00Z","open":262.6,"high":264.48,"low":260.05,"close":260.58,"volume":30851550.0},
    {"symbol":"AAPL","timestamp":"2026-02-20T00:00:00Z","open":258.97,"high":264.75,"low":258.16,"close":264.58,"volume":42076050.0},
    {"symbol":"AAPL","timestamp":"2026-02-23T00:00:00Z","open":263.49,"high":269.43,"low":263.381,"close":266.18,"volume":37317624.0},
    {"symbol":"AAPL","timestamp":"2026-02-24T00:00:00Z","open":267.86,"high":274.89,"low":267.71,"close":272.14,"volume":47024020.0},
    {"symbol":"AAPL","timestamp":"2026-02-25T00:00:00Z","open":271.78,"high":274.94,"low":271.05,"close":274.23,"volume":33707832.0},
    {"symbol":"AAPL","timestamp":"2026-02-26T00:00:00Z","open":274.945,"high":276.11,"low":270.795,"close":272.95,"volume":32351904.0},
    {"symbol":"AAPL","timestamp":"2026-02-27T00:00:00Z","open":272.81,"high":272.81,"low":262.89,"close":264.18,"volume":72370522.0},
    {"symbol":"AAPL","timestamp":"2026-03-02T00:00:00Z","open":262.41,"high":266.53,"low":260.2,"close":264.72,"volume":41854037.0},
    {"symbol":"AAPL","timestamp":"2026-03-03T00:00:00Z","open":263.48,"high":265.56,"low":260.13,"close":263.75,"volume":38584043.0},
    {"symbol":"AAPL","timestamp":"2026-03-04T00:00:00Z","open":264.65,"high":266.15,"low":261.42,"close":262.52,"volume":39817530.0},
    {"symbol":"AAPL","timestamp":"2026-03-05T00:00:00Z","open":260.79,"high":261.555,"low":257.25,"close":260.29,"volume":49671284.0},
    {"symbol":"AAPL","timestamp":"2026-03-06T00:00:00Z","open":258.63,"high":258.77,"low":254.37,"close":257.46,"volume":41129568.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T00:00:00Z","open":255.69,"high":261.15,"low":253.6805,"close":259.88,"volume":38242048.0},
]

# ──────────────────────────────────────────────────────────────────────────────
# Datos reales MSFT D1 (60 velas diarias)
# ──────────────────────────────────────────────────────────────────────────────

MSFT_D1 = [
    {"symbol":"MSFT","timestamp":"2025-12-10T00:00:00Z","open":484.03,"high":484.25,"low":475.08,"close":478.56,"volume":35759655.0},
    {"symbol":"MSFT","timestamp":"2025-12-11T00:00:00Z","open":476.63,"high":486.03,"low":475.86,"close":483.47,"volume":24674471.0},
    {"symbol":"MSFT","timestamp":"2025-12-12T00:00:00Z","open":479.82,"high":482.45,"low":476.34,"close":478.53,"volume":21248365.0},
    {"symbol":"MSFT","timestamp":"2025-12-15T00:00:00Z","open":480.1,"high":480.7205,"low":472.52,"close":474.82,"volume":23729204.0},
    {"symbol":"MSFT","timestamp":"2025-12-16T00:00:00Z","open":471.905,"high":477.89,"low":470.88,"close":476.39,"volume":20707051.0},
    {"symbol":"MSFT","timestamp":"2025-12-17T00:00:00Z","open":476.905,"high":480.0,"low":475.0,"close":476.12,"volume":24528275.0},
    {"symbol":"MSFT","timestamp":"2025-12-18T00:00:00Z","open":478.19,"high":489.6,"low":477.89,"close":483.98,"volume":28574461.0},
    {"symbol":"MSFT","timestamp":"2025-12-19T00:00:00Z","open":487.36,"high":487.85,"low":482.49,"close":485.92,"volume":70838173.0},
    {"symbol":"MSFT","timestamp":"2025-12-22T00:00:00Z","open":486.12,"high":488.73,"low":482.69,"close":484.92,"volume":16965222.0},
    {"symbol":"MSFT","timestamp":"2025-12-23T00:00:00Z","open":484.98,"high":487.83,"low":484.74,"close":486.85,"volume":14684074.0},
    {"symbol":"MSFT","timestamp":"2025-12-24T00:00:00Z","open":485.68,"high":489.1625,"low":484.83,"close":488.02,"volume":5856304.0},
    {"symbol":"MSFT","timestamp":"2025-12-26T00:00:00Z","open":486.705,"high":488.12,"low":485.96,"close":487.71,"volume":8842979.0},
    {"symbol":"MSFT","timestamp":"2025-12-29T00:00:00Z","open":484.855,"high":488.35,"low":484.18,"close":487.1,"volume":10894675.0},
    {"symbol":"MSFT","timestamp":"2025-12-30T00:00:00Z","open":485.93,"high":489.68,"low":485.5,"close":487.48,"volume":13944969.0},
    {"symbol":"MSFT","timestamp":"2025-12-31T00:00:00Z","open":487.84,"high":488.14,"low":483.3,"close":483.62,"volume":15602577.0},
    {"symbol":"MSFT","timestamp":"2026-01-02T00:00:00Z","open":484.385,"high":484.66,"low":470.16,"close":472.94,"volume":25573261.0},
    {"symbol":"MSFT","timestamp":"2026-01-05T00:00:00Z","open":474.055,"high":476.07,"low":469.5,"close":472.85,"volume":25252430.0},
    {"symbol":"MSFT","timestamp":"2026-01-06T00:00:00Z","open":473.8,"high":478.7367,"low":469.75,"close":478.51,"volume":23038016.0},
    {"symbol":"MSFT","timestamp":"2026-01-07T00:00:00Z","open":479.755,"high":489.7,"low":477.95,"close":483.47,"volume":25565649.0},
    {"symbol":"MSFT","timestamp":"2026-01-08T00:00:00Z","open":481.24,"high":482.66,"low":475.86,"close":478.11,"volume":18163898.0},
    {"symbol":"MSFT","timestamp":"2026-01-09T00:00:00Z","open":474.06,"high":479.82,"low":472.2001,"close":479.28,"volume":18491591.0},
    {"symbol":"MSFT","timestamp":"2026-01-12T00:00:00Z","open":476.67,"high":480.99,"low":475.6803,"close":477.18,"volume":23522471.0},
    {"symbol":"MSFT","timestamp":"2026-01-13T00:00:00Z","open":474.675,"high":475.7799,"low":465.95,"close":470.67,"volume":28546685.0},
    {"symbol":"MSFT","timestamp":"2026-01-14T00:00:00Z","open":466.46,"high":468.2,"low":457.1701,"close":459.38,"volume":28185750.0},
    {"symbol":"MSFT","timestamp":"2026-01-15T00:00:00Z","open":464.12,"high":464.25,"low":455.9,"close":456.66,"volume":23229881.0},
    {"symbol":"MSFT","timestamp":"2026-01-16T00:00:00Z","open":457.83,"high":463.19,"low":456.48,"close":459.86,"volume":34248644.0},
    {"symbol":"MSFT","timestamp":"2026-01-20T00:00:00Z","open":451.215,"high":456.8,"low":449.28,"close":454.52,"volume":26136999.0},
    {"symbol":"MSFT","timestamp":"2026-01-21T00:00:00Z","open":452.595,"high":452.69,"low":438.68,"close":444.11,"volume":37982782.0},
    {"symbol":"MSFT","timestamp":"2026-01-22T00:00:00Z","open":447.62,"high":452.84,"low":444.7,"close":451.14,"volume":25359826.0},
    {"symbol":"MSFT","timestamp":"2026-01-23T00:00:00Z","open":451.87,"high":471.1,"low":450.53,"close":465.95,"volume":38008795.0},
    {"symbol":"MSFT","timestamp":"2026-01-26T00:00:00Z","open":465.305,"high":474.25,"low":462.0,"close":470.28,"volume":29307958.0},
    {"symbol":"MSFT","timestamp":"2026-01-27T00:00:00Z","open":473.7,"high":482.87,"low":473.16,"close":480.58,"volume":29219318.0},
    {"symbol":"MSFT","timestamp":"2026-01-28T00:00:00Z","open":483.21,"high":483.74,"low":478.0,"close":481.63,"volume":36885583.0},
    {"symbol":"MSFT","timestamp":"2026-01-29T00:00:00Z","open":439.99,"high":442.5,"low":421.02,"close":433.5,"volume":128890289.0},
    {"symbol":"MSFT","timestamp":"2026-01-30T00:00:00Z","open":439.17,"high":439.6,"low":426.45,"close":430.29,"volume":58598312.0},
    {"symbol":"MSFT","timestamp":"2026-02-02T00:00:00Z","open":430.235,"high":430.736,"low":422.25,"close":423.37,"volume":42245300.0},
    {"symbol":"MSFT","timestamp":"2026-02-03T00:00:00Z","open":422.01,"high":422.05,"low":408.56,"close":411.21,"volume":61439843.0},
    {"symbol":"MSFT","timestamp":"2026-02-04T00:00:00Z","open":411.0,"high":419.8,"low":409.24,"close":414.19,"volume":45031200.0},
    {"symbol":"MSFT","timestamp":"2026-02-05T00:00:00Z","open":407.44,"high":408.3,"low":392.32,"close":393.67,"volume":66317102.0},
    {"symbol":"MSFT","timestamp":"2026-02-06T00:00:00Z","open":399.165,"high":401.79,"low":392.92,"close":401.14,"volume":53545458.0},
    {"symbol":"MSFT","timestamp":"2026-02-09T00:00:00Z","open":404.85,"high":414.89,"low":400.87,"close":413.6,"volume":45509945.0},
    {"symbol":"MSFT","timestamp":"2026-02-10T00:00:00Z","open":419.62,"high":423.68,"low":412.7,"close":413.27,"volume":44870432.0},
    {"symbol":"MSFT","timestamp":"2026-02-11T00:00:00Z","open":416.175,"high":416.46,"low":401.01,"close":404.37,"volume":42503340.0},
    {"symbol":"MSFT","timestamp":"2026-02-12T00:00:00Z","open":405.0,"high":406.2,"low":398.01,"close":401.84,"volume":40822021.0},
    {"symbol":"MSFT","timestamp":"2026-02-13T00:00:00Z","open":404.45,"high":405.54,"low":398.05,"close":401.32,"volume":34108474.0},
    {"symbol":"MSFT","timestamp":"2026-02-17T00:00:00Z","open":399.22,"high":400.52,"low":394.525,"close":396.86,"volume":32095678.0},
    {"symbol":"MSFT","timestamp":"2026-02-18T00:00:00Z","open":398.13,"high":402.56,"low":396.32,"close":398.69,"volume":23232808.0},
    {"symbol":"MSFT","timestamp":"2026-02-19T00:00:00Z","open":400.69,"high":404.43,"low":396.67,"close":398.46,"volume":28244826.0},
    {"symbol":"MSFT","timestamp":"2026-02-20T00:00:00Z","open":396.11,"high":400.1159,"low":395.16,"close":397.23,"volume":34024613.0},
    {"symbol":"MSFT","timestamp":"2026-02-23T00:00:00Z","open":395.0,"high":395.36,"low":383.1,"close":384.47,"volume":43252119.0},
    {"symbol":"MSFT","timestamp":"2026-02-24T00:00:00Z","open":384.14,"high":389.36,"low":381.71,"close":389.0,"volume":33902997.0},
    {"symbol":"MSFT","timestamp":"2026-02-25T00:00:00Z","open":390.525,"high":401.47,"low":390.16,"close":400.6,"volume":43605889.0},
    {"symbol":"MSFT","timestamp":"2026-02-26T00:00:00Z","open":404.71,"high":407.49,"low":398.74,"close":401.72,"volume":34416840.0},
    {"symbol":"MSFT","timestamp":"2026-02-27T00:00:00Z","open":390.88,"high":396.82,"low":389.88,"close":392.74,"volume":51377192.0},
    {"symbol":"MSFT","timestamp":"2026-03-02T00:00:00Z","open":392.855,"high":401.19,"low":390.63,"close":398.55,"volume":35507600.0},
    {"symbol":"MSFT","timestamp":"2026-03-03T00:00:00Z","open":393.14,"high":406.7,"low":392.67,"close":403.93,"volume":38216188.0},
    {"symbol":"MSFT","timestamp":"2026-03-04T00:00:00Z","open":401.265,"high":411.0326,"low":400.31,"close":405.2,"volume":35821256.0},
    {"symbol":"MSFT","timestamp":"2026-03-05T00:00:00Z","open":404.42,"high":411.61,"low":404.4,"close":410.68,"volume":39012934.0},
    {"symbol":"MSFT","timestamp":"2026-03-06T00:00:00Z","open":409.2,"high":413.05,"low":408.5101,"close":408.96,"volume":31133515.0},
    {"symbol":"MSFT","timestamp":"2026-03-09T00:00:00Z","open":404.915,"high":410.21,"low":403.5,"close":409.41,"volume":30165000.0},
]

# ──────────────────────────────────────────────────────────────────────────────
# Datos reales AAPL M5 (60 velas de 5 minutos — sesión extendida 2026-03-09/10)
# ──────────────────────────────────────────────────────────────────────────────

AAPL_M5 = [
    {"symbol":"AAPL","timestamp":"2026-03-09T21:35:00Z","open":259.6,"high":259.6,"low":259.58,"close":259.6,"volume":3769.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T21:40:00Z","open":259.51,"high":259.51,"low":259.51,"close":259.51,"volume":137.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T21:45:00Z","open":259.57,"high":259.57,"low":259.3221,"close":259.3221,"volume":800.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T21:50:00Z","open":259.3,"high":259.47,"low":259.3,"close":259.31,"volume":3297.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T21:55:00Z","open":259.31,"high":259.4,"low":259.31,"close":259.4,"volume":240.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T22:00:00Z","open":259.47,"high":259.47,"low":258.91,"close":259.0,"volume":6378.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T22:05:00Z","open":259.02,"high":259.7,"low":259.0,"close":259.2391,"volume":1283.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T22:10:00Z","open":259.12,"high":259.12,"low":258.88,"close":259.1,"volume":2317.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T22:15:00Z","open":258.91,"high":258.91,"low":258.88,"close":258.88,"volume":563.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T22:20:00Z","open":258.89,"high":258.89,"low":258.68,"close":258.7198,"volume":4176.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T22:25:00Z","open":258.71,"high":259.48,"low":258.71,"close":259.48,"volume":605.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T22:30:00Z","open":259.88,"high":259.88,"low":258.8,"close":258.8,"volume":4048.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T22:35:00Z","open":258.9132,"high":258.9132,"low":258.9132,"close":258.9132,"volume":109.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T22:40:00Z","open":259.14,"high":259.14,"low":259.14,"close":259.14,"volume":100.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T22:45:00Z","open":259.4,"high":259.4,"low":259.4,"close":259.4,"volume":100.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T22:50:00Z","open":259.021,"high":259.07,"low":259.021,"close":259.07,"volume":200.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T23:00:00Z","open":259.0,"high":259.06,"low":259.0,"close":259.06,"volume":500.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T23:05:00Z","open":259.15,"high":259.15,"low":259.15,"close":259.15,"volume":230.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T23:10:00Z","open":259.27,"high":259.43,"low":259.27,"close":259.43,"volume":200.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T23:15:00Z","open":259.06,"high":259.06,"low":259.06,"close":259.06,"volume":388.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T23:20:00Z","open":259.2262,"high":259.2262,"low":259.0,"close":259.0,"volume":593.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T23:25:00Z","open":259.11,"high":259.11,"low":259.0201,"close":259.0201,"volume":300.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T23:30:00Z","open":259.14,"high":259.15,"low":259.0215,"close":259.15,"volume":1300.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T23:35:00Z","open":259.15,"high":259.19,"low":259.0,"close":259.15,"volume":7318.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T23:40:00Z","open":259.0,"high":259.0001,"low":259.0,"close":259.0,"volume":414.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T23:45:00Z","open":258.98,"high":259.05,"low":258.98,"close":259.0,"volume":711.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T23:50:00Z","open":258.75,"high":258.75,"low":258.7241,"close":258.7241,"volume":13047.0},
    {"symbol":"AAPL","timestamp":"2026-03-09T23:55:00Z","open":259.19,"high":259.19,"low":258.99,"close":259.0,"volume":2483.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T00:00:00Z","open":258.25,"high":259.08,"low":258.23,"close":258.91,"volume":103.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T00:05:00Z","open":258.86,"high":258.86,"low":258.68,"close":258.68,"volume":25.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T00:10:00Z","open":258.78,"high":258.78,"low":258.54,"close":258.6,"volume":59.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T00:15:00Z","open":258.52,"high":258.78,"low":258.52,"close":258.78,"volume":53.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T00:20:00Z","open":258.71,"high":258.95,"low":258.71,"close":258.84,"volume":85.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T00:25:00Z","open":259.15,"high":259.15,"low":259.15,"close":259.15,"volume":9.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T00:30:00Z","open":259.15,"high":259.25,"low":259.06,"close":259.08,"volume":32.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T00:35:00Z","open":259.25,"high":259.7,"low":259.21,"close":259.7,"volume":257.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T00:40:00Z","open":259.61,"high":259.84,"low":259.46,"close":259.7,"volume":673.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T00:45:00Z","open":259.6,"high":259.89,"low":259.41,"close":259.41,"volume":321.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T00:50:00Z","open":259.41,"high":259.5,"low":259.35,"close":259.35,"volume":83.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T00:55:00Z","open":259.28,"high":259.35,"low":259.2,"close":259.3,"volume":174.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T01:00:00Z","open":259.36,"high":259.77,"low":259.23,"close":259.38,"volume":211.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T01:05:00Z","open":259.5,"high":259.54,"low":259.44,"close":259.51,"volume":52.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T01:10:00Z","open":259.55,"high":259.76,"low":259.55,"close":259.64,"volume":70.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T01:15:00Z","open":259.8,"high":259.83,"low":259.62,"close":259.62,"volume":52.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T01:20:00Z","open":259.62,"high":259.68,"low":259.62,"close":259.68,"volume":12.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T01:25:00Z","open":259.51,"high":259.56,"low":259.51,"close":259.56,"volume":11.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T01:30:00Z","open":259.52,"high":259.52,"low":259.52,"close":259.52,"volume":13.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T01:35:00Z","open":259.52,"high":259.66,"low":259.38,"close":259.38,"volume":166.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T01:40:00Z","open":259.63,"high":259.64,"low":259.39,"close":259.58,"volume":99.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T01:45:00Z","open":259.58,"high":259.65,"low":259.52,"close":259.65,"volume":130.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T01:55:00Z","open":259.68,"high":259.84,"low":259.63,"close":259.84,"volume":274.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T02:00:00Z","open":259.66,"high":259.82,"low":259.66,"close":259.81,"volume":21.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T02:05:00Z","open":259.82,"high":259.82,"low":259.56,"close":259.56,"volume":69.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T02:15:00Z","open":259.53,"high":259.53,"low":259.53,"close":259.53,"volume":1.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T02:20:00Z","open":259.48,"high":259.51,"low":259.48,"close":259.51,"volume":32.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T02:25:00Z","open":259.6,"high":259.6,"low":259.55,"close":259.6,"volume":28.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T02:30:00Z","open":259.6,"high":259.6,"low":259.31,"close":259.31,"volume":122.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T02:35:00Z","open":259.31,"high":259.42,"low":259.31,"close":259.42,"volume":3.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T02:40:00Z","open":259.43,"high":259.43,"low":259.34,"close":259.34,"volume":63.0},
    {"symbol":"AAPL","timestamp":"2026-03-10T02:45:00Z","open":259.34,"high":259.35,"low":259.23,"close":259.35,"volume":30.0},
]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _df(candles: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(candles)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _ctx(candles: list[dict], symbol: str) -> dict:
    df = _df(candles)
    return {
        symbol: {
            "symbol": symbol,
            "barras_por_tf": {"M5": df.to_dict(orient="list")},
            "fundamentales": {},
            "halteado": False,
        }
    }


def _filtro(enum_filtro: str, condicional: str, v1: float, v2: float | None = None,
            periodo: int | None = None) -> dict:
    parametros = []
    if periodo is not None:
        parametros.append({
            "enum_parametro": "PERIODO",
            "obj_valor_seleccionado": {"enumTipoValor": "INTEGER", "valor": periodo},
        })
    parametros.append({
        "enum_parametro": "CONDICION",
        "obj_valor_seleccionado": {
            "enumTipoValor": "CONDICIONAL",
            "enumCondicional": condicional,
            "valor1": v1,
            "valor2": v2,
        },
    })
    return {"enum_filtro": enum_filtro, "parametros": parametros}


# ──────────────────────────────────────────────────────────────────────────────
# Tests RSI — datos reales AAPL D1
# ──────────────────────────────────────────────────────────────────────────────

class TestRSIIntegracionReal:
    """RSI(14) calculado con pandas_ta real sobre 60 velas diarias de AAPL."""

    def test_rsi_valor_entre_0_y_100(self):
        """El RSI siempre debe estar en rango válido."""
        import pandas_ta as ta
        df = _df(AAPL_D1)
        rsi = ta.rsi(df["close"], length=14)
        rsi_val = float(rsi.dropna().iloc[-1])
        assert 0.0 <= rsi_val <= 100.0

    def test_rsi_genera_senal_cuando_umbral_por_encima_del_valor_real(self):
        """Si el umbral (MENOR_QUE) es mayor que el RSI real → debe generar señal."""
        import pandas_ta as ta
        df = _df(AAPL_D1)
        rsi_real = float(ta.rsi(df["close"], length=14).dropna().iloc[-1])

        ctx = _ctx(AAPL_D1, "AAPL")
        # RSI < (rsi_real + 5) → siempre verdadero → señal
        filtro = _filtro("RSI", "MENOR_QUE", rsi_real + 5.0, periodo=14)
        senales = evaluar_simbolos(ctx, [filtro], 1, "Test RSI")
        assert len(senales) == 1, f"RSI real={rsi_real:.2f}, umbral={rsi_real + 5:.2f}"

    def test_rsi_no_genera_senal_cuando_umbral_por_debajo_del_valor_real(self):
        """Si el umbral (MAYOR_QUE) está 5 pts por encima del RSI real → no señal."""
        import pandas_ta as ta
        df = _df(AAPL_D1)
        rsi_real = float(ta.rsi(df["close"], length=14).dropna().iloc[-1])

        ctx = _ctx(AAPL_D1, "AAPL")
        # RSI > (rsi_real + 5) → siempre falso → sin señal
        filtro = _filtro("RSI", "MAYOR_QUE", rsi_real + 5.0, periodo=14)
        senales = evaluar_simbolos(ctx, [filtro], 1, "Test RSI")
        assert len(senales) == 0, f"RSI real={rsi_real:.2f}, umbral={rsi_real + 5:.2f}"

    def test_rsi_entre_con_rango_centrado_en_valor_real(self):
        """Rango [rsi-10, rsi+10] centrado en el valor real → debe generar señal."""
        import pandas_ta as ta
        df = _df(AAPL_D1)
        rsi_real = float(ta.rsi(df["close"], length=14).dropna().iloc[-1])

        ctx = _ctx(AAPL_D1, "AAPL")
        filtro = _filtro("RSI", "ENTRE", rsi_real - 10.0, rsi_real + 10.0, periodo=14)
        senales = evaluar_simbolos(ctx, [filtro], 1, "Test RSI")
        assert len(senales) == 1

    def test_rsi_fuera_con_rango_lejos_del_valor_real(self):
        """FUERA de rango [5, 10] → RSI real (~30-70) está fuera → genera señal."""
        import pandas_ta as ta
        df = _df(AAPL_D1)
        rsi_real = float(ta.rsi(df["close"], length=14).dropna().iloc[-1])

        ctx = _ctx(AAPL_D1, "AAPL")
        # RSI real está entre 0 y 100, así que si está fuera del rango [5, 10]
        # depende del valor. Usamos un rango que definitivamente no contenga el RSI real.
        if rsi_real > 15.0:
            filtro = _filtro("RSI", "FUERA", 0.0, 10.0, periodo=14)
        else:
            filtro = _filtro("RSI", "FUERA", 90.0, 100.0, periodo=14)
        senales = evaluar_simbolos(ctx, [filtro], 1, "Test RSI")
        assert len(senales) == 1


# ──────────────────────────────────────────────────────────────────────────────
# Tests ATR — datos reales AAPL D1
# ──────────────────────────────────────────────────────────────────────────────

class TestATRIntegracionReal:
    """ATR(14) calculado con pandas_ta real sobre 60 velas diarias de AAPL."""

    def test_atr_valor_positivo(self):
        """El ATR siempre debe ser positivo."""
        import pandas_ta as ta
        df = _df(AAPL_D1)
        atr = ta.atr(df["high"], df["low"], df["close"], length=14)
        atr_val = float(atr.dropna().iloc[-1])
        assert atr_val > 0.0

    def test_atr_genera_senal_con_umbral_cero(self):
        """ATR > 0 siempre → MAYOR_QUE 0 debe generar señal con datos reales."""
        ctx = _ctx(AAPL_D1, "AAPL")
        filtro = _filtro("ATR", "MAYOR_QUE", 0.0, periodo=14)
        senales = evaluar_simbolos(ctx, [filtro], 1, "Test ATR")
        assert len(senales) == 1

    def test_atr_no_genera_senal_con_umbral_imposible(self):
        """ATR de AAPL (~$3-8) no puede superar $1000 → MAYOR_QUE 1000 → sin señal."""
        ctx = _ctx(AAPL_D1, "AAPL")
        filtro = _filtro("ATR", "MAYOR_QUE", 1000.0, periodo=14)
        senales = evaluar_simbolos(ctx, [filtro], 1, "Test ATR")
        assert len(senales) == 0

    def test_atr_rango_razonable_para_aapl(self):
        """El ATR diario de AAPL a ~$260 debe estar entre $1 y $30."""
        import pandas_ta as ta
        df = _df(AAPL_D1)
        atr_val = float(ta.atr(df["high"], df["low"], df["close"], length=14).dropna().iloc[-1])
        assert 1.0 <= atr_val <= 30.0, f"ATR AAPL fuera de rango razonable: {atr_val:.2f}"

    def test_atr_msft_tambien_positivo(self):
        """ATR de MSFT también debe ser positivo."""
        import pandas_ta as ta
        df = _df(MSFT_D1)
        atr_val = float(ta.atr(df["high"], df["low"], df["close"], length=14).dropna().iloc[-1])
        assert atr_val > 0.0

    def test_atr_genera_senal_con_umbral_centrado(self):
        """Umbral exactamente en el valor real → MENOR_QUE (val + 1) genera señal."""
        import pandas_ta as ta
        df = _df(AAPL_D1)
        atr_real = float(ta.atr(df["high"], df["low"], df["close"], length=14).dropna().iloc[-1])

        ctx = _ctx(AAPL_D1, "AAPL")
        filtro = _filtro("ATR", "MENOR_QUE", atr_real + 1.0, periodo=14)
        senales = evaluar_simbolos(ctx, [filtro], 1, "Test ATR")
        assert len(senales) == 1, f"ATR real={atr_real:.4f}"


# ──────────────────────────────────────────────────────────────────────────────
# Tests DISTANCE_FROM_EMA — datos reales AAPL D1
# ──────────────────────────────────────────────────────────────────────────────

class TestDistanceEMAIntegracionReal:
    """EMA(20) y distancia % calculada con pandas_ta real."""

    def test_distancia_ema_calculada_correctamente(self):
        """Verifica que la distancia % sea coherente: (close - EMA) / EMA * 100."""
        import pandas_ta as ta
        df = _df(AAPL_D1)
        ema = ta.ema(df["close"], length=20)
        ema_val = float(ema.dropna().iloc[-1])
        close_val = float(df["close"].iloc[-1])
        distancia_esperada = ((close_val - ema_val) / ema_val) * 100

        # La distancia debe ser pequeña (EMA cercana al precio actual)
        assert abs(distancia_esperada) < 15.0, f"Distancia EMA {distancia_esperada:.2f}% parece excesiva"

    def test_ema_genera_senal_umbral_muy_negativo(self):
        """DISTANCE_FROM_EMA > -50% → siempre verdadero para AAPL → señal."""
        ctx = _ctx(AAPL_D1, "AAPL")
        filtro = _filtro("DISTANCE_FROM_EMA", "MAYOR_QUE", -50.0, periodo=20)
        senales = evaluar_simbolos(ctx, [filtro], 1, "Test EMA")
        assert len(senales) == 1

    def test_ema_no_genera_senal_umbral_imposible(self):
        """DISTANCE_FROM_EMA > +50% imposible para AAPL D1 → sin señal."""
        ctx = _ctx(AAPL_D1, "AAPL")
        filtro = _filtro("DISTANCE_FROM_EMA", "MAYOR_QUE", 50.0, periodo=20)
        senales = evaluar_simbolos(ctx, [filtro], 1, "Test EMA")
        assert len(senales) == 0

    def test_ema_umbral_dinamico_centrado_en_valor_real(self):
        """Umbral centrado en distancia real → ENTRE (dist-5, dist+5) → señal."""
        import pandas_ta as ta
        df = _df(AAPL_D1)
        ema_val = float(ta.ema(df["close"], length=20).dropna().iloc[-1])
        close_val = float(df["close"].iloc[-1])
        dist_real = ((close_val - ema_val) / ema_val) * 100

        ctx = _ctx(AAPL_D1, "AAPL")
        filtro = _filtro("DISTANCE_FROM_EMA", "ENTRE", dist_real - 5.0, dist_real + 5.0, periodo=20)
        senales = evaluar_simbolos(ctx, [filtro], 1, "Test EMA")
        assert len(senales) == 1, f"Distancia real={dist_real:.4f}%"

    def test_ema_periodo_50_con_60_barras(self):
        """EMA(50) con 60 barras → suficientes datos → indicador se calcula."""
        import pandas_ta as ta
        df = _df(AAPL_D1)
        ema = ta.ema(df["close"], length=50)
        assert ema is not None
        assert not ema.dropna().empty

        ctx = _ctx(AAPL_D1, "AAPL")
        filtro = _filtro("DISTANCE_FROM_EMA", "MAYOR_QUE", -50.0, periodo=50)
        senales = evaluar_simbolos(ctx, [filtro], 1, "Test EMA50")
        assert len(senales) == 1


# ──────────────────────────────────────────────────────────────────────────────
# Tests DISTANCE_FROM_VWAP — datos reales AAPL M5
# ──────────────────────────────────────────────────────────────────────────────

class TestDistanceVWAPIntegracionReal:
    """VWAP calculado con pandas_ta real sobre 60 velas de 5 minutos."""

    def test_vwap_genera_senal_umbral_muy_negativo(self):
        """DISTANCE_FROM_VWAP > -50% → siempre verdadero → señal."""
        ctx = _ctx(AAPL_M5, "AAPL")
        filtro = _filtro("DISTANCE_FROM_VWAP", "MAYOR_QUE", -50.0)
        senales = evaluar_simbolos(ctx, [filtro], 1, "Test VWAP")
        assert len(senales) == 1

    def test_vwap_requiere_datetime_index_para_calcular(self):
        """pandas_ta.vwap necesita DatetimeIndex para agrupar por sesión.
        Sin él retorna None → el filtro es permisivo (True) → siempre genera señal.
        Este test documenta ese comportamiento: el filtro nunca rechaza cuando
        VWAP no puede computarse.
        """
        import pandas_ta as ta
        df = _df(AAPL_M5)
        # Sin DatetimeIndex, vwap retorna None o serie vacía
        vwap = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
        vwap_computable = vwap is not None and not vwap.dropna().empty

        ctx = _ctx(AAPL_M5, "AAPL")
        # Con umbral imposible (+50%): si VWAP no computa → señal igualmente (permisivo)
        filtro = _filtro("DISTANCE_FROM_VWAP", "MAYOR_QUE", 50.0)
        senales = evaluar_simbolos(ctx, [filtro], 1, "Test VWAP")
        if vwap_computable:
            # Si VWAP sí computa, distancia ~$259 no puede ser > 50% → sin señal
            assert len(senales) == 0
        else:
            # VWAP no computa → filtro pasa (permisivo) → señal generada
            assert len(senales) == 1

    def test_vwap_con_datetime_index_calcula_distancia(self):
        """Con DatetimeIndex correcto, VWAP computa y la distancia es pequeña (~$259)."""
        import pandas_ta as ta
        df = _df(AAPL_M5)
        df.index = pd.to_datetime(df["timestamp"])
        vwap = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
        if vwap is not None and not vwap.dropna().empty:
            vwap_val = float(vwap.dropna().iloc[-1])
            close_val = float(df["close"].iloc[-1])
            distancia = abs(((close_val - vwap_val) / vwap_val) * 100)
            assert distancia < 10.0, f"Distancia VWAP {distancia:.2f}% fuera de rango esperado"


# ──────────────────────────────────────────────────────────────────────────────
# Tests multi-símbolo con datos reales
# ──────────────────────────────────────────────────────────────────────────────

class TestMultiSimboloIntegracionReal:
    """AAPL y MSFT evaluados simultáneamente con filtros reales."""

    def test_dos_simbolos_mismo_filtro_atr_positivo(self):
        """ATR > 0 → ambos símbolos generan señal."""
        ctx = {}
        ctx.update(_ctx(AAPL_D1, "AAPL"))
        ctx.update(_ctx(MSFT_D1, "MSFT"))
        filtro = _filtro("ATR", "MAYOR_QUE", 0.0, periodo=14)
        senales = evaluar_simbolos(ctx, [filtro], 1, "Test Multi")
        symbols = {s["symbol"] for s in senales}
        assert "AAPL" in symbols
        assert "MSFT" in symbols

    def test_dos_simbolos_filtro_imposible_ninguno_genera_senal(self):
        """ATR > 1000 → ningún símbolo genera señal."""
        ctx = {}
        ctx.update(_ctx(AAPL_D1, "AAPL"))
        ctx.update(_ctx(MSFT_D1, "MSFT"))
        filtro = _filtro("ATR", "MAYOR_QUE", 1000.0, periodo=14)
        senales = evaluar_simbolos(ctx, [filtro], 1, "Test Multi")
        assert len(senales) == 0

    def test_senal_contiene_precio_real_de_ultima_vela(self):
        """El precio de detección debe coincidir con el close real de la última vela."""
        ctx = _ctx(AAPL_D1, "AAPL")
        filtro = _filtro("ATR", "MAYOR_QUE", 0.0, periodo=14)
        senales = evaluar_simbolos(ctx, [filtro], 99, "Scanner Real")
        assert len(senales) == 1
        close_ultima = AAPL_D1[-1]["close"]  # 259.88
        assert senales[0]["precioDeteccion"] == pytest.approx(close_ultima)

    def test_senal_contiene_volumen_real_de_ultima_vela(self):
        """El volumen de detección debe coincidir con el volume real de la última vela."""
        ctx = _ctx(AAPL_D1, "AAPL")
        filtro = _filtro("ATR", "MAYOR_QUE", 0.0, periodo=14)
        senales = evaluar_simbolos(ctx, [filtro], 99, "Scanner Real")
        volumen_ultima = AAPL_D1[-1]["volume"]  # 38242048.0
        assert senales[0]["volumenDeteccion"] == pytest.approx(volumen_ultima)


# ──────────────────────────────────────────────────────────────────────────────
# Tests combinación RSI + ATR con datos reales
# ──────────────────────────────────────────────────────────────────────────────

class TestCombinacionFiltrosReal:
    """RSI y ATR evaluados juntos (AND) sobre datos reales."""

    def test_rsi_y_atr_ambos_con_umbrales_alcanzables(self):
        """RSI < 100 AND ATR > 0 → siempre verdadero → señal."""
        ctx = _ctx(AAPL_D1, "AAPL")
        filtros = [
            _filtro("RSI", "MENOR_QUE", 100.0, periodo=14),
            _filtro("ATR", "MAYOR_QUE", 0.0, periodo=14),
        ]
        senales = evaluar_simbolos(ctx, filtros, 1, "Test Combo")
        assert len(senales) == 1

    def test_rsi_y_atr_primer_filtro_imposible_no_genera_senal(self):
        """RSI > 999 (imposible) AND ATR > 0 → cortocircuito → sin señal."""
        ctx = _ctx(AAPL_D1, "AAPL")
        filtros = [
            _filtro("RSI", "MAYOR_QUE", 999.0, periodo=14),
            _filtro("ATR", "MAYOR_QUE", 0.0, periodo=14),
        ]
        senales = evaluar_simbolos(ctx, filtros, 1, "Test Combo")
        assert len(senales) == 0

    def test_rsi_y_atr_segundo_filtro_imposible_no_genera_senal(self):
        """RSI < 100 (siempre) AND ATR > 1000 (imposible) → sin señal."""
        ctx = _ctx(AAPL_D1, "AAPL")
        filtros = [
            _filtro("RSI", "MENOR_QUE", 100.0, periodo=14),
            _filtro("ATR", "MAYOR_QUE", 1000.0, periodo=14),
        ]
        senales = evaluar_simbolos(ctx, filtros, 1, "Test Combo")
        assert len(senales) == 0

    def test_tres_filtros_rsi_atr_ema_todos_alcanzables(self):
        """RSI < 100 AND ATR > 0 AND EMA_dist > -50% → todos verdaderos → señal."""
        ctx = _ctx(AAPL_D1, "AAPL")
        filtros = [
            _filtro("RSI", "MENOR_QUE", 100.0, periodo=14),
            _filtro("ATR", "MAYOR_QUE", 0.0, periodo=14),
            _filtro("DISTANCE_FROM_EMA", "MAYOR_QUE", -50.0, periodo=20),
        ]
        senales = evaluar_simbolos(ctx, filtros, 1, "Test Combo 3")
        assert len(senales) == 1
        filtros_aplicados = senales[0]["filtrosAplicados"].split(",")
        assert "RSI" in filtros_aplicados
        assert "ATR" in filtros_aplicados
        assert "DISTANCE_FROM_EMA" in filtros_aplicados
