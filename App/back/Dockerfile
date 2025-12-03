FROM python:3.13-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiamos requirements desde la carpeta 'back'
COPY back/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# --- CAMBIO IMPORTANTE ---
# 1. Copiamos el archivo settings.py de la raíz
COPY settings.py .
# 2. Copiamos el código fuente de la carpeta back
COPY back/ .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]