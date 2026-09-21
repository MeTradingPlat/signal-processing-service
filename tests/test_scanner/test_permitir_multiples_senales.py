from datetime import time

from app.models.enums import EnumEstadoEscaner, EnumFiltro, EnumTipoEjecucion
from app.models.escaner import Escaner, EstadoEscaner, TipoEjecucion
from app.models.filtro import Filtro
from app.scanner.symbols import SymbolPipeline


def _escaner(permitir_multiples_senales: bool) -> Escaner:
    return Escaner(
        idEscaner=1,
        nombre="test",
        horaInicio=time(9, 30, 0),
        horaFin=time(16, 0, 0),
        objEstado=EstadoEscaner(enumEstadoEscaner=EnumEstadoEscaner.INICIADO),
        objTipoEjecucion=TipoEjecucion(enumTipoEjecucion=EnumTipoEjecucion.DIARIA),
        filtros=[Filtro(enumFiltro=EnumFiltro.CHANGE)],
        permitirMultiplesSenales=permitir_multiples_senales,
    )


def test_excluye_simbolos_ya_senializados_por_defecto():
    pipeline = SymbolPipeline(_escaner(False))
    pipeline._filtrados = ["AAPL", "MSFT"]
    pipeline._log_client.get_signaled_today = lambda scanner_id: {"AAPL"}

    pipeline._excluir_ya_senializados_hoy()

    assert pipeline.filtrados == ["MSFT"]


def test_permitir_multiples_senales_salta_la_exclusion():
    # Con el flag activo, ni siquiera se consulta a log-service -- un
    # simbolo que ya se senializo hoy sigue pudiendo re-senializarse.
    pipeline = SymbolPipeline(_escaner(True))
    pipeline._filtrados = ["AAPL", "MSFT"]

    def _falla_si_se_llama(scanner_id):
        raise AssertionError("get_signaled_today no deberia llamarse con permitirMultiplesSenales=true")

    pipeline._log_client.get_signaled_today = _falla_si_se_llama

    pipeline._excluir_ya_senializados_hoy()

    assert pipeline.filtrados == ["AAPL", "MSFT"]


def test_tras_un_reinicio_no_republica_lo_que_ya_senalizo_y_sigue_calificando():
    pipeline = SymbolPipeline(_escaner(True))
    pipeline._log_client.get_signaled_today = lambda scanner_id: {"AAPL", "TSLA"}
    pipeline.cargar_baseline_de_senales()

    nuevos = pipeline.nuevos_symbols({"AAPL": [], "MSFT": []})

    assert nuevos == {"MSFT"}


def test_tras_el_reinicio_un_simbolo_que_deja_de_calificar_y_vuelve_si_cuenta_como_nuevo():
    pipeline = SymbolPipeline(_escaner(True))
    pipeline._log_client.get_signaled_today = lambda scanner_id: {"AAPL"}
    pipeline.cargar_baseline_de_senales()
    pipeline.nuevos_symbols({"AAPL": []})
    pipeline.nuevos_symbols({})

    nuevos = pipeline.nuevos_symbols({"AAPL": []})

    assert nuevos == {"AAPL"}


def test_un_simbolo_senalizado_hoy_que_no_calificaba_al_reiniciar_si_se_publica_cuando_califica():
    pipeline = SymbolPipeline(_escaner(True))
    pipeline._log_client.get_signaled_today = lambda scanner_id: {"AAPL"}
    pipeline.cargar_baseline_de_senales()
    pipeline.nuevos_symbols({"MSFT": []})

    nuevos = pipeline.nuevos_symbols({"MSFT": [], "AAPL": []})

    assert nuevos == {"AAPL"}


def test_sin_multiples_senales_el_baseline_no_consulta_log_service():
    pipeline = SymbolPipeline(_escaner(False))

    def _falla_si_se_llama(scanner_id):
        raise AssertionError("no deberia consultarse")

    pipeline._log_client.get_signaled_today = _falla_si_se_llama
    pipeline.cargar_baseline_de_senales()

    assert pipeline.nuevos_symbols({"AAPL": []}) == {"AAPL"}
