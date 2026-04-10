FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema necesarias
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Solo copiar requirements primero (mejor cache de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar solo los archivos necesarios para la app
COPY main.py .
COPY database.py .
COPY cv_parser.py .
COPY ai_evaluator.py .
COPY gmail_fetcher.py .

# Crear directorio para uploads
RUN mkdir -p /app/uploads

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
