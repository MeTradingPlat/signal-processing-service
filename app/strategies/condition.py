from app.models.enums import EnumCondicional
from app.models.valor import ValorCondicional


def evaluate_condition(cond: ValorCondicional | None, value: float) -> bool:
    if cond is None or cond.enumCondicional is None:
        return True
    v1, v2 = cond.valor1, cond.valor2
    if cond.enumCondicional == EnumCondicional.MAYOR_QUE:
        return v1 is not None and value > v1
    if cond.enumCondicional == EnumCondicional.MENOR_QUE:
        return v1 is not None and value < v1
    if cond.enumCondicional == EnumCondicional.ENTRE:
        return v1 is not None and v2 is not None and v1 <= value <= v2
    if cond.enumCondicional == EnumCondicional.FUERA:
        return v1 is not None and v2 is not None and (value < v1 or value > v2)
    if cond.enumCondicional == EnumCondicional.IGUAL_A:
        return v1 is not None and value == v1
    return False
