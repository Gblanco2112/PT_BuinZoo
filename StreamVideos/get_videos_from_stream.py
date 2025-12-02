import cv2
import time
import os
import queue
import threading
from datetime import datetime
import argparse

# =============== ARGUMENTOS ===============
parser = argparse.ArgumentParser()
parser.add_argument("--channel", type=int, default=1, help="Canal RTSP")
parser.add_argument("--segment-minutes", type=float, default=5.0, help="Minutos por video")
parser.add_argument("--output-dir", type=str, default="videos_capturados", help="Carpeta salida")
args = parser.parse_args()

CHANNEL = args.channel
SEGMENT_MINUTES = args.segment_minutes
OUTPUT_DIR = args.output_dir

# Credenciales (Sanitizadas)
USER = "view"
PASS = "tupassword" # <--- CAMBIAR CONTRASEÑA REAL AQUÍ
IP = "190.8.125.219"
PORT = "554"

rtsp_url = f"rtsp://view:vieW.,star3250@190.8.125.219:554/cam/realmonitor?channel=1&subtype=0"
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp" # Mantenemos TCP por estabilidad

# =============== CLASE DE LECTURA EN HILO (LA SOLUCIÓN) ===============
class RTSPFrameGetter:
    """
    Lee frames en un hilo separado para que guardar el video 
    no bloquee la lectura del stream.
    """
    def __init__(self, src):
        self.cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG)
        self.q = queue.Queue()
        self.stop_signal = False
        self.connected = self.cap.isOpened()
        
        if self.connected:
            self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            # Usamos 25 FPS por defecto si la cámara falla al reportarlo
            self.fps = self.cap.get(cv2.CAP_PROP_FPS)
            if not self.fps or self.fps > 60 or self.fps < 1: 
                self.fps = 25.0
            
            # Iniciamos el hilo
            self.t = threading.Thread(target=self._reader_loop)
            self.t.daemon = True
            self.t.start()
    
    def _reader_loop(self):
        while not self.stop_signal:
            ret, frame = self.cap.read()
            if not ret:
                break
            # Ponemos el frame en la fila. Si la fila está muy llena, sacamos el viejo 
            # para no saturar la memoria RAM.
            if not self.q.empty():
                try:
                    self.q.get_nowait() # Descartar frame viejo si hay acumulación (opcional)
                except queue.Empty:
                    pass
            self.q.put(frame)
            
        self.cap.release()

    def read(self):
        return self.q.get() # Esto bloquea hasta que haya un frame disponible

    def running(self):
        return self.connected and not self.stop_signal

    def stop(self):
        self.stop_signal = True
        self.t.join()

# ======================================================================

os.makedirs(OUTPUT_DIR, exist_ok=True)

def create_writer(width, height, fps):
    now = datetime.now()
    ts_str = now.strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(OUTPUT_DIR, f"channel{CHANNEL}_{ts_str}.mp4")
    # 'mp4v' es compatible, pero si sigue lento prueba 'avc1' si tienes codecs instalados
    fourcc = cv2.VideoWriter_fourcc(*"mp4v") 
    writer = cv2.VideoWriter(filename, fourcc, fps, (width, height))
    print(f"Grabando: {filename}")
    return writer, filename

# =============== BLOQUE PRINCIPAL ===============

print("Conectando a cámara...")
stream_loader = RTSPFrameGetter(rtsp_url)

if not stream_loader.connected:
    print("Error crítico: No se pudo conectar a la cámara.")
    exit()

writer, current_filename = create_writer(stream_loader.width, stream_loader.height, stream_loader.fps)
segment_start_time = time.time()
segment_duration_sec = SEGMENT_MINUTES * 60.0

cv2.namedWindow("Grabacion", cv2.WINDOW_NORMAL)

try:
    while True:
        # Obtenemos frame del hilo (ya no directamente del socket)
        # Esto es muy rápido porque el frame ya está en memoria RAM
        try:
            frame = stream_loader.q.get(timeout=5) # esperar max 5 seg por un frame
        except queue.Empty:
            print("Timeout recibiendo frames. Reiniciando conexión...")
            break

        # Escritura en disco (esto es lo que causaba el lag, ahora no afecta la lectura)
        writer.write(frame)
        
        cv2.imshow("Grabacion", frame)

        # Control de tiempo de segmento
        if time.time() - segment_start_time >= segment_duration_sec:
            print("Segmento completado.")
            writer.release()
            writer, current_filename = create_writer(stream_loader.width, stream_loader.height, stream_loader.fps)
            segment_start_time = time.time()

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        
        if cv2.getWindowProperty("Grabacion", cv2.WND_PROP_VISIBLE) < 1:
            break

except KeyboardInterrupt:
    print("Interrupción de teclado.")

finally:
    print("Cerrando recursos...")
    stream_loader.stop()
    writer.release()
    cv2.destroyAllWindows()