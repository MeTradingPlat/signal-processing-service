from unittest.mock import MagicMock

from app.scanner.runner import _reintentar_carga_si_vacia


def test_retries_cargar_todos_when_symbol_list_is_empty():
    pipeline = MagicMock()
    pipeline.todos = []

    _reintentar_carga_si_vacia(pipeline)

    pipeline.cargar_todos.assert_called_once()


def test_does_not_retry_when_symbols_already_loaded():
    pipeline = MagicMock()
    pipeline.todos = ["AAPL", "MSFT"]

    _reintentar_carga_si_vacia(pipeline)

    pipeline.cargar_todos.assert_not_called()
