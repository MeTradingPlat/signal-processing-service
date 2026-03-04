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

# Timezone: forzar UTC en el contenedor independientemente del host
# Critico para que todos los datetime.now() sin timezone retornen UTC
# y para que los logs muestren timestamps correctos
ENV TZ=UTC
ENV PYTHONUNBUFFERED=1

# Deshabilitar optimizaciones SIMD que requieren AVX
# Esto es necesario para CPUs antiguos como AMD E-350
ENV NPY_DISABLE_SVML=1
ENV OPENBLAS_NUM_THREADS=1
ENV NPY_DISABLE_CPU_FEATURES="AVX AVX2 AVX512F"

# Usar versiones compatibles con CPUs sin AVX (numpy<2, pandas<3)
# Las versiones 2.x/3.x requieren AVX incluso compilando desde source
RUN pip install --no-cache-dir "numpy<2" "pandas<3"

# Instalar el resto de dependencias
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

USER appuser:appuser

EXPOSE 8000

CMD ["python", "main.py"]
