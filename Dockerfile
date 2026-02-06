FROM python:3.11-slim

LABEL project="metradingplat"
LABEL service="signal-processing-service"

WORKDIR /app

# Instalar dependencias de compilacion para numpy/pandas
# Esto permite compilar desde source sin instrucciones AVX
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system appuser && adduser --system --ingroup appuser appuser

COPY requirements.txt .

# Deshabilitar optimizaciones SIMD que requieren AVX
# Esto es necesario para CPUs antiguos como AMD E-350
ENV NPY_DISABLE_SVML=1
ENV OPENBLAS_NUM_THREADS=1

# Instalar numpy primero desde source (sin wheels pre-compilados con AVX)
RUN pip install --no-cache-dir --no-binary numpy numpy

# Instalar el resto de dependencias
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

USER appuser:appuser

EXPOSE 8000

CMD ["python", "main.py"]
