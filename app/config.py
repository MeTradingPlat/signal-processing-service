from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "SP_"}

    http_host: str = "0.0.0.0"
    http_port: int = 8000
    log_level: str = "INFO"

    marketdata_url: str = "https://api.metradingplat.net"
    marketdata_user: str = "admin"
    marketdata_password: str = "Coltes2025!"


settings = Settings()
