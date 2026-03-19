from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    puerto: int = 8000
    scanner_management_url: str = "http://scanner-management-service:8081"
    marketdata_url: str = "http://marketdata-service:8082"
    kafka_bootstrap_servers: str = "kafka:29092"
    kafka_group_id: str = "signal-processing-group"
    max_barras_por_simbolo: int = 500
    max_simbolos_por_lote: int = 50
    margen_cierre_vela_seg: int = 5
    max_workers_pool: int = 2
    reintentos_rest: int = 3
    servicio_origen: str = "signal-processing-service"

    # Datos externos
    finnhub_api_key: str = ""          # Registrarse gratis en finnhub.io
    fundamentals_max_workers: int = 10  # Threads para fetches paralelos de yfinance
    halt_monitor_intervalo_seg: int = 30  # Frecuencia de polling NASDAQ halt file

    class Config:
        env_prefix = "SP_"

settings = Settings()
