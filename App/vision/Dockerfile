FROM ultralytics/ultralytics:latest

WORKDIR /app

# Copiamos requirements desde la carpeta 'vision'
COPY vision/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- CAMBIO IMPORTANTE ---
# 1. Copiamos settings.py de la raíz
COPY settings.py .
# 2. Copiamos el código fuente de la carpeta vision
COPY vision/ .

CMD ["python", "-u", "main.py"]