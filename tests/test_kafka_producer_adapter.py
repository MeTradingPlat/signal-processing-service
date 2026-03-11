"""Tests for KafkaProducerAdapter."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.output.kafka_producer_adapter import (
    KafkaProducerAdapter,
    TOPIC_SIGNALS,
    TOPIC_LOGS,
    TOPIC_SCANNER_STATE,
)


@pytest.fixture
def producer():
    """KafkaProducerAdapter con AIOKafkaProducer mockeado."""
    with patch("app.infrastructure.output.kafka_producer_adapter.AIOKafkaProducer") as mock_cls:
        mock_instance = AsyncMock()
        mock_cls.return_value = mock_instance
        adapter = KafkaProducerAdapter(bootstrap_servers="localhost:9092")
        adapter._producer = mock_instance
        yield adapter, mock_instance


@pytest.mark.asyncio
class TestKafkaProducerAdapterCicloVida:
    async def test_iniciar_llama_start(self, producer):
        adapter, mock_p = producer
        await adapter.iniciar()
        mock_p.start.assert_awaited_once()

    async def test_detener_llama_stop(self, producer):
        adapter, mock_p = producer
        await adapter.detener()
        mock_p.stop.assert_awaited_once()


@pytest.mark.asyncio
class TestPublicarSenal:
    async def test_envia_al_topic_signals(self, producer):
        adapter, mock_p = producer
        senal = {
            "idEscaner": 1,
            "nombreEscaner": "Momentum",
            "symbol": "AAPL",
            "tipoSenal": "COMPRA",
        }
        await adapter.publicar_senal(senal)
        mock_p.send_and_wait.assert_awaited_once_with(TOPIC_SIGNALS, value=senal)

    async def test_no_lanza_excepcion_si_kafka_falla(self, producer):
        adapter, mock_p = producer
        mock_p.send_and_wait.side_effect = Exception("connection refused")
        # Debe capturar la excepción internamente sin propagar
        await adapter.publicar_senal({"symbol": "X"})

    async def test_envia_dict_exacto(self, producer):
        adapter, mock_p = producer
        senal = {"symbol": "TSLA", "tipoSenal": "VENTA", "precioDeteccion": 200.0}
        await adapter.publicar_senal(senal)
        call_args = mock_p.send_and_wait.call_args
        assert call_args.kwargs["value"] == senal


@pytest.mark.asyncio
class TestPublicarLog:
    async def test_envia_al_topic_logs(self, producer):
        adapter, mock_p = producer
        await adapter.publicar_log(id_escaner=5, nivel="INFO", mensaje="Escaner iniciado")
        mock_p.send_and_wait.assert_awaited_once()
        topic = mock_p.send_and_wait.call_args.args[0]
        assert topic == TOPIC_LOGS

    async def test_payload_contiene_campos_requeridos(self, producer):
        adapter, mock_p = producer
        await adapter.publicar_log(id_escaner=3, nivel="ERROR", mensaje="Fallo en barras", categoria="BARRAS")
        payload = mock_p.send_and_wait.call_args.kwargs["value"]
        assert payload["idEscaner"] == 3
        assert payload["nivel"] == "ERROR"
        assert payload["mensaje"] == "Fallo en barras"
        assert payload["categoria"] == "BARRAS"
        assert payload["servicioOrigen"] == "signal-processing-service"
        assert "timestamp" in payload

    async def test_valores_por_defecto_categoria_y_tipo(self, producer):
        adapter, mock_p = producer
        await adapter.publicar_log(id_escaner=1, nivel="INFO", mensaje="ok")
        payload = mock_p.send_and_wait.call_args.kwargs["value"]
        assert payload["categoria"] == "SCANNER"
        assert payload["tipo"] == "SCANNER_STATE"

    async def test_no_lanza_excepcion_si_kafka_falla(self, producer):
        adapter, mock_p = producer
        mock_p.send_and_wait.side_effect = Exception("timeout")
        await adapter.publicar_log(1, "WARN", "msg")


@pytest.mark.asyncio
class TestPublicarCambioEstado:
    async def test_envia_al_topic_scanner_state(self, producer):
        adapter, mock_p = producer
        await adapter.publicar_cambio_estado(
            id_escaner=2,
            nombre_escaner="Scanner A",
            estado_anterior="INICIADO",
            estado_nuevo="DETENIDO",
            razon="Hora fin alcanzada",
        )
        topic = mock_p.send_and_wait.call_args.args[0]
        assert topic == TOPIC_SCANNER_STATE

    async def test_payload_contiene_campos_correctos(self, producer):
        adapter, mock_p = producer
        await adapter.publicar_cambio_estado(
            id_escaner=7,
            nombre_escaner="Mi Escaner",
            estado_anterior="DETENIDO",
            estado_nuevo="INICIADO",
            razon="Comando manual",
        )
        payload = mock_p.send_and_wait.call_args.kwargs["value"]
        assert payload["idEscaner"] == 7
        assert payload["nombreEscaner"] == "Mi Escaner"
        assert payload["estadoAnterior"] == "DETENIDO"
        assert payload["estadoNuevo"] == "INICIADO"
        assert payload["razon"] == "Comando manual"
        assert payload["servicioOrigen"] == "signal-processing-service"
        assert "timestamp" in payload

    async def test_no_lanza_excepcion_si_kafka_falla(self, producer):
        adapter, mock_p = producer
        mock_p.send_and_wait.side_effect = Exception("broker unavailable")
        await adapter.publicar_cambio_estado(1, "sc", "A", "B", "error")
