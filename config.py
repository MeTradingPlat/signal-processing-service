"""Configuracion del servicio."""

import os

# URLs de los microservicios (configurables via env vars para Docker/prod)
SCANNER_SERVICE_URL = os.getenv("SCANNER_SERVICE_URL", "http://localhost:8080/api")
MARKETDATA_SERVICE_URL = os.getenv("MARKETDATA_SERVICE_URL", "http://localhost:8080/api")

# Concurrencia
MAX_WORKERS_ESCANERES = int(os.getenv("MAX_WORKERS_ESCANERES", "10"))
MAX_WORKERS_SIMBOLOS = int(os.getenv("MAX_WORKERS_SIMBOLOS", "20"))

# HTTP
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))

# Scheduler
POLLING_INTERVAL_SECONDS = int(os.getenv("POLLING_INTERVAL_SECONDS", "60"))
SCHEDULER_TIMEZONE = os.getenv("SCHEDULER_TIMEZONE", "UTC")

# Kafka
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

# Event Loop (filtros de evento en tiempo real)
EVENT_POLLING_INTERVAL_SECONDS = float(os.getenv("EVENT_POLLING_INTERVAL_SECONDS", "0.1"))
MAX_SYMBOLS_REALTIME = int(os.getenv("MAX_SYMBOLS_REALTIME", "50"))
SIGNAL_COOLDOWN_SECONDS = int(os.getenv("SIGNAL_COOLDOWN_SECONDS", "300"))
