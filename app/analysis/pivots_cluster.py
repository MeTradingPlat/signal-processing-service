from app.analysis.pivots_swing import PivotPoint


def merge_and_limit(
    levels: list[PivotPoint], current_price: float, slip_ratio: float, number_pivots: int,
) -> list[PivotPoint]:
    """Ordena por cercania al precio actual y descarta niveles a menos de
    slip_ratio de uno ya elegido (fusiona duplicados cercanos), hasta reunir
    number_pivots -- equivalente simplificado a _filtered_strong_pivots/
    _filtered_weak_pivots de PivotsAlpaca."""
    ordenados = sorted(levels, key=lambda punto: abs(punto[1] - current_price))
    elegidos: list[PivotPoint] = []
    for punto in ordenados:
        if len(elegidos) >= number_pivots:
            break
        if all(abs(punto[1] - elegido[1]) >= slip_ratio for elegido in elegidos):
            elegidos.append(punto)
    return elegidos
