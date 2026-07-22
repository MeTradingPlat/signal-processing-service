from app.models.enums import EnumCondicional, EnumTipoValor
from app.models.valor import ValorCondicional
from app.strategies.condition import evaluate_condition


def test_mayor_que_true():
    cond = ValorCondicional(enumCondicional=EnumCondicional.MAYOR_QUE, enumTipoValor=EnumTipoValor.CONDICIONAL, valor1=10.0)
    assert evaluate_condition(cond, 15.0)


def test_mayor_que_false():
    cond = ValorCondicional(enumCondicional=EnumCondicional.MAYOR_QUE, enumTipoValor=EnumTipoValor.CONDICIONAL, valor1=10.0)
    assert not evaluate_condition(cond, 5.0)


def test_menor_que_true():
    cond = ValorCondicional(enumCondicional=EnumCondicional.MENOR_QUE, enumTipoValor=EnumTipoValor.CONDICIONAL, valor1=10.0)
    assert evaluate_condition(cond, 3.0)


def test_entre_true():
    cond = ValorCondicional(enumCondicional=EnumCondicional.ENTRE, enumTipoValor=EnumTipoValor.CONDICIONAL, valor1=5.0, valor2=15.0)
    assert evaluate_condition(cond, 10.0)


def test_entre_false():
    cond = ValorCondicional(enumCondicional=EnumCondicional.ENTRE, enumTipoValor=EnumTipoValor.CONDICIONAL, valor1=5.0, valor2=15.0)
    assert not evaluate_condition(cond, 20.0)


def test_fuera_true_below():
    cond = ValorCondicional(enumCondicional=EnumCondicional.FUERA, enumTipoValor=EnumTipoValor.CONDICIONAL, valor1=5.0, valor2=15.0)
    assert evaluate_condition(cond, 2.0)


def test_fuera_true_above():
    cond = ValorCondicional(enumCondicional=EnumCondicional.FUERA, enumTipoValor=EnumTipoValor.CONDICIONAL, valor1=5.0, valor2=15.0)
    assert evaluate_condition(cond, 20.0)


def test_fuera_false_inside():
    cond = ValorCondicional(enumCondicional=EnumCondicional.FUERA, enumTipoValor=EnumTipoValor.CONDICIONAL, valor1=5.0, valor2=15.0)
    assert not evaluate_condition(cond, 10.0)


def test_none_condition_returns_true():
    assert evaluate_condition(None, 999.0)
