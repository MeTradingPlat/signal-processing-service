"""Tests for EstadoEscanerKafkaListener."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.input.kafka_listener import EstadoEscanerKafkaListener


@pytest.fixture
def listener():
    with patch("app.infrastructure.input.kafka_listener.AIOKafkaConsumer") as mock_cls:
        mock_consumer = AsyncMock()
        mock_cls.return_value = mock_consumer

        mock_gestor = AsyncMock()
        mock_gestor.detener_escaner = AsyncMock()
        mock_gestor.iniciar_escaner = AsyncMock()

        mock_escaner_rest = AsyncMock()
        mock_escaner_rest.obtener_escaner_por_id = AsyncMock()
        mock_escaner_rest.obtener_filtros_escaner = AsyncMock(return_value=[])

        inst = EstadoEscanerKafkaListener(
            bootstrap_servers="localhost:9092",
            group_id="test-group",
            gestor=mock_gestor,
            escaner_rest=mock_escaner_rest,
        )
        inst._consumer = mock_consumer
        yield inst, mock_gestor, mock_escaner_rest


@pytest.mark.asyncio
class TestProcesarEvento:
    async def test_ignora_eventos_propios(self, listener):
        """Eventos con servicioOrigen == 'signal-processing-service' se ignoran."""
        inst, mock_gestor, mock_escaner_rest = listener
        evento = {
            "servicioOrigen": "signal-processing-service",
            "idEscaner": 1,
            "estadoNuevo": "INICIADO",
        }
        await inst._procesar_evento(evento)
        mock_gestor.iniciar_escaner.assert_not_called()
        mock_gestor.detener_escaner.assert_not_called()

    async def test_ignora_evento_sin_id_escaner(self, listener):
        inst, mock_gestor, _ = listener
        evento = {"servicioOrigen": "other-service", "estadoNuevo": "INICIADO"}
        await inst._procesar_evento(evento)
        mock_gestor.iniciar_escaner.assert_not_called()

    async def test_estado_iniciado_inicia_escaner(self, listener):
        inst, mock_gestor, mock_escaner_rest = listener
        escaner_data = {
            "idEscaner": 3,
            "nombre": "Test Scanner",
            "horaInicio": "09:30:00",
            "horaFin": "16:00:00",
            "objTipoEjecucion": {"enumTipoEjecucion": "DIARIA"},
            "mercados": [{"enumMercado": "NYSE"}],
        }
        mock_escaner_rest.obtener_escaner_por_id = AsyncMock(return_value=escaner_data)
        mock_escaner_rest.obtener_filtros_escaner = AsyncMock(return_value=[])

        evento = {
            "servicioOrigen": "scanner-management-service",
            "idEscaner": 3,
            "estadoNuevo": "INICIADO",
            "nombreEscaner": "Test Scanner",
        }
        await inst._procesar_evento(evento)
        mock_gestor.iniciar_escaner.assert_awaited_once()

    async def test_estado_detenido_detiene_escaner(self, listener):
        inst, mock_gestor, _ = listener
        evento = {
            "servicioOrigen": "scanner-management-service",
            "idEscaner": 5,
            "estadoNuevo": "DETENIDO",
            "razon": "Usuario detuvo el escaner",
        }
        await inst._procesar_evento(evento)
        mock_gestor.detener_escaner.assert_awaited_once_with(5, razon="Usuario detuvo el escaner")

    async def test_estado_archivado_detiene_escaner(self, listener):
        inst, mock_gestor, _ = listener
        evento = {
            "servicioOrigen": "scanner-management-service",
            "idEscaner": 7,
            "estadoNuevo": "ARCHIVADO",
        }
        await inst._procesar_evento(evento)
        mock_gestor.detener_escaner.assert_awaited_once_with(7, razon="Estado cambiado a ARCHIVADO")

    async def test_estado_desconocido_no_hace_nada(self, listener):
        inst, mock_gestor, _ = listener
        evento = {
            "servicioOrigen": "other-service",
            "idEscaner": 1,
            "estadoNuevo": "PAUSADO",
        }
        await inst._procesar_evento(evento)
        mock_gestor.iniciar_escaner.assert_not_called()
        mock_gestor.detener_escaner.assert_not_called()

    async def test_iniciado_no_inicia_si_escaner_rest_falla(self, listener):
        """Si obtener_escaner_por_id retorna None, no se llama a iniciar_escaner."""
        inst, mock_gestor, mock_escaner_rest = listener
        mock_escaner_rest.obtener_escaner_por_id = AsyncMock(return_value=None)

        evento = {
            "servicioOrigen": "scanner-management-service",
            "idEscaner": 99,
            "estadoNuevo": "INICIADO",
        }
        await inst._procesar_evento(evento)
        mock_gestor.iniciar_escaner.assert_not_called()

    async def test_razon_por_defecto_si_no_en_evento(self, listener):
        inst, mock_gestor, _ = listener
        evento = {
            "servicioOrigen": "other-service",
            "idEscaner": 2,
            "estadoNuevo": "DETENIDO",
            # sin campo "razon"
        }
        await inst._procesar_evento(evento)
        call_kwargs = mock_gestor.detener_escaner.call_args.kwargs
        assert "razon" in call_kwargs
        assert "DETENIDO" in call_kwargs["razon"]

    async def test_iniciado_obtiene_filtros_del_escaner(self, listener):
        """Al iniciar un escaner también consulta sus filtros."""
        inst, mock_gestor, mock_escaner_rest = listener
        escaner_data = {
            "idEscaner": 4,
            "nombre": "Scanner RSI",
            "horaInicio": "09:30:00",
            "horaFin": "16:00:00",
            "objTipoEjecucion": {"enumTipoEjecucion": "UNA_VEZ"},
            "mercados": [],
        }
        filtros_data = [{"enumFiltro": "RSI", "parametros": []}]
        mock_escaner_rest.obtener_escaner_por_id = AsyncMock(return_value=escaner_data)
        mock_escaner_rest.obtener_filtros_escaner = AsyncMock(return_value=filtros_data)

        evento = {
            "servicioOrigen": "scanner-management-service",
            "idEscaner": 4,
            "estadoNuevo": "INICIADO",
        }
        await inst._procesar_evento(evento)
        mock_escaner_rest.obtener_filtros_escaner.assert_awaited_once_with(4)
        mock_gestor.iniciar_escaner.assert_awaited_once()
