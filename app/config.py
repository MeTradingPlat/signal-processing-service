from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    http_port: int = 8000
    scanner_management_url: str = "http://scanner-management-service:8081"
    marketdata_url: str = "http://gateway:8080"
    marketdata_user: str = "admin"
    marketdata_password: str = "Coltes2025!"
    kafka_bootstrap_servers: str = "kafka:29092"
    kafka_group_id: str = "signal-processing-group"
    max_barras_por_simbolo: int = 500
    max_simbolos_por_lote: int = 50
    margen_cierre_vela_seg: int = 5
    max_workers_pool: int = 2
    reintentos_rest: int = 3
    servicio_origen: str = "signal-processing-service"
    log_level: str = "INFO"
    http_host: str = "0.0.0.0"

    # Datos externos
    finnhub_api_key: str = ""
    fundamentals_max_workers: int = 10
    halt_monitor_intervalo_seg: int = 30

    class Config:
        env_prefix = "SP_"


settings = Settings()
