# Usamos la imagen oficial de Ultralytics que ya trae PyTorch, CUDA y YOLO
FROM ultralytics/ultralytics:latest

WORKDIR /app

# Instalamos dependencias extra (requests)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el código
COPY . .

# Ejecutamos el script de visión (con -u para ver logs en tiempo real)
CMD ["python", "-u", "main.py"]