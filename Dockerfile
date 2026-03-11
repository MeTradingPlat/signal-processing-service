# ─── Stage 1: base con dependencias ──────────────────────────────────────────
FROM python:3.12-slim AS base

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─── Stage 2: tests ───────────────────────────────────────────────────────────
FROM base AS test

COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY app/ ./app/
COPY tests/ ./tests/

CMD ["pytest", "tests/", "-v", "--tb=short"]

# ─── Stage 3: producción ──────────────────────────────────────────────────────
FROM base AS production

LABEL project="metradingplat"
LABEL service="signal-processing-service"

COPY app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
