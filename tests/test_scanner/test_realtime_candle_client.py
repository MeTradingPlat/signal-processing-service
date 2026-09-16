from app.scanner.realtime_candle_client import _group_by_timeframe


def test_group_by_timeframe_agrupa_simbolos_del_mismo_timeframe():
    keys = {("AAPL", "M5"), ("MSFT", "M5"), ("AAPL", "D1")}

    grouped = _group_by_timeframe(keys)

    assert grouped.keys() == {"M5", "D1"}
    assert sorted(grouped["M5"]) == ["AAPL", "MSFT"]
    assert grouped["D1"] == ["AAPL"]


def test_group_by_timeframe_set_vacio_da_dict_vacio():
    assert _group_by_timeframe(set()) == {}
