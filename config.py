"""Configuracion del servicio."""

import os

# URLs de los microservicios (configurables via env vars para Docker/prod)
SCANNER_SERVICE_URL = os.getenv("SCANNER_SERVICE_URL", "http://localhost:8080/api")
MARKETDATA_SERVICE_URL = os.getenv("MARKETDATA_SERVICE_URL", "http://localhost:8080/api")

# Concurrencia
# MAX_WORKERS_ESCANERES eliminado: cada escaner corre en su propio proceso OS
MAX_WORKERS_SIMBOLOS = int(os.getenv("MAX_WORKERS_SIMBOLOS", "4"))  # threads por ScannerProcess

# HTTP
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))

# Procesos
SCANNER_PROCESS_JOIN_TIMEOUT = int(os.getenv("SCANNER_PROCESS_JOIN_TIMEOUT", "30"))

# Timing: margen de espera tras el cierre de vela antes de fetchear datos
# El proveedor de datos necesita unos segundos para publicar la vela cerrada
SIGNAL_MARGIN_SECONDS = int(os.getenv("SIGNAL_MARGIN_SECONDS", "2"))

# Kafka
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

# Event Loop (filtros de evento en tiempo real)
EVENT_POLLING_INTERVAL_SECONDS = float(os.getenv("EVENT_POLLING_INTERVAL_SECONDS", "1"))
MAX_SYMBOLS_REALTIME = int(os.getenv("MAX_SYMBOLS_REALTIME", "50"))
SIGNAL_COOLDOWN_SECONDS = int(os.getenv("SIGNAL_COOLDOWN_SECONDS", "300"))

# Pre-despertar (despertar antes de la ejecucion para recalcular sleep exacto)
PRE_DESPERTAR_UMBRAL_SEGUNDOS = int(os.getenv("PRE_DESPERTAR_UMBRAL_SEGUNDOS", "1800"))  # M30+
PRE_DESPERTAR_MINUTOS = int(os.getenv("PRE_DESPERTAR_MINUTOS", "5"))
PRE_DESPERTAR_MARGEN_SEGUNDOS = int(os.getenv("PRE_DESPERTAR_MARGEN_SEGUNDOS", "5"))

# Validacion de barras
VALIDACION_TOLERANCIA_SEGUNDOS = int(os.getenv("VALIDACION_TOLERANCIA_SEGUNDOS", "120"))
VALIDACION_MAX_REINTENTOS = int(os.getenv("VALIDACION_MAX_REINTENTOS", "3"))
VALIDACION_PAUSA_REINTENTO_SEGUNDOS = int(os.getenv("VALIDACION_PAUSA_REINTENTO_SEGUNDOS", "10"))
