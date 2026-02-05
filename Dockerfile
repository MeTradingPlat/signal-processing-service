FROM python:3.11-slim

LABEL project="metradingplat"
LABEL service="signal-processing-service"

WORKDIR /app

RUN addgroup --system appuser && adduser --system --ingroup appuser appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

USER appuser:appuser

EXPOSE 8000

CMD ["python", "main.py"]
