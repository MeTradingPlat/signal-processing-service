from app.models.enums import EnumMercado


_MERCADO_TO_MIC: dict[str, str] = {
    EnumMercado.NASDAQ.value: "XNAS",
    EnumMercado.NYSE.value: "XNYS",
    EnumMercado.AMEX.value: "XASE",
    EnumMercado.ETF.value: "ARCX",
    # BATS (Cboe BZX) es una bolsa real y distinta de ARCX (NYSE Arca) --
    # ambas listan sobre todo ETFs, pero ETF aca solo mapeaba a ARCX,
    # dejando los ~1600 simbolos de Cboe BZX (incluido MSTU) invisibles
    # para cualquier escaner sin ninguna forma de seleccionarlos.
    EnumMercado.BATS.value: "BATS",
    EnumMercado.OTC.value: "OTC",
}


def mercado_to_mic(mercado_value: str) -> str:
    return _MERCADO_TO_MIC.get(mercado_value, mercado_value)


_TIMEFRAME_SCANNER_TO_MARKETDATA: dict[str, str] = {
    "_1M": "M1", "_2M": "M2", "_3M": "M3", "_5M": "M5",
    "_10M": "M10", "_15M": "M15", "_30M": "M30", "_45M": "M45",
    "_1H": "H1", "_2H": "H2", "_3H": "H3", "_4H": "H4", "_12H": "H12",
    "_1D": "D1", "_2D": "D2", "_3D": "D3", "_1W": "W1",
    "_1MO": "MO1", "_3MO": "MO3", "_6MO": "MO6", "_1Y": "Y1",
}


def timeframe_to_marketdata(scanner_timeframe: str) -> str:
    return _TIMEFRAME_SCANNER_TO_MARKETDATA.get(
        scanner_timeframe, scanner_timeframe.lstrip("_"),
    )
