from app.models.enums import EnumCondicional
from app.models.valor import ValorCondicional


def evaluate_condition(cond: ValorCondicional | None, value: float) -> bool:
    if cond is None or cond.enumCondicional is None:
        return True
    v1 = cond.valor1 or 0.0
    v2 = cond.valor2 or 0.0
    if cond.enumCondicional == EnumCondicional.MAYOR_QUE:
        return value > v1
    if cond.enumCondicional == EnumCondicional.MENOR_QUE:
        return value < v1
    if cond.enumCondicional == EnumCondicional.ENTRE:
        return v1 <= value <= v2
    if cond.enumCondicional == EnumCondicional.FUERA:
        return value < v1 or value > v2
    if cond.enumCondicional == EnumCondicional.IGUAL_A:
        return value == v1
    return False
