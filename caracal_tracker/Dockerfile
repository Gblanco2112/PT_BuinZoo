# -------------------------------
# Dockerfile - Caracal Tracker CPU (Optimizado)
# -------------------------------

FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsm6 libxext6 git wget && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias (esta capa se cachea mientras requirements.txt no cambie)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar solo lo necesario (el resto se monta como volumen)
COPY . .

RUN mkdir -p /app/outputs

CMD ["python", "run_caracal_proxy.py"]
