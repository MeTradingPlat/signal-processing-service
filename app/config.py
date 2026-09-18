from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    http_port: int = 8000
    scanner_management_url: str = "http://scanner-management-service:8081"
    marketdata_url: str = "http://marketdata-service:8082"
    notification_service_url: str = "http://notification-service:8085"
    servicio_origen: str = "signal-processing-service"
    log_service_url: str = "http://log-service:8084"
    log_level: str = "INFO"
    http_host: str = "0.0.0.0"

    class Config:
        env_prefix = "SP_"


settings = Settings()
