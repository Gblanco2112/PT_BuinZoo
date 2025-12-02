import cv2
import time
import os
from datetime import datetime
import argparse

# =============== ARGUMENTOS CLI ===============
parser = argparse.ArgumentParser()

parser.add_argument(
    "--channel",
    type=int,
    default=1,
    help="Número de canal RTSP (ej: 1, 2, 3...)."
)

parser.add_argument(
    "--segment-minutes",
    type=float,
    default=5.0,
    help="Duración de cada archivo de video en minutos."
)

parser.add_argument(
    "--output-dir",
    type=str,
    default="videos_capturados",
    help="Carpeta donde se guardarán los videos."
)

args = parser.parse_args()

CHANNEL = args.channel
SEGMENT_MINUTES = args.segment_minutes
OUTPUT_DIR = args.output_dir
# =============================================


# =============== CONFIGURACIÓN RTSP ===============
rtsp_url = (
    f"rtsp://view:vieW.,star3250@190.8.125.219:554/"
    f"cam/realmonitor?channel=0&subtype=0"
)

os.makedirs(OUTPUT_DIR, exist_ok=True)

print(f"Usando canal RTSP: {CHANNEL}")
print(f"Duración por archivo: {SEGMENT_MINUTES} minutos")
print(f"Carpeta de salida: {OUTPUT_DIR}")
# ================================================


def open_capture():
    """Intenta abrir el RTSP, reintentando si falla."""
    while True:
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        if cap.isOpened():
            print("Stream RTSP abierto correctamente.")
            print("Ancho:", cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            print("Alto:", cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            return cap
        else:
            print("No se pudo abrir el stream RTSP. Reintentando en 5 segundos...")
            cap.release()
            time.sleep(5)


def create_writer(cap):
    """Crear un VideoWriter nuevo con nombre basado en timestamp."""
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps is None or fps <= 0:
        # Fallback si la cámara no reporta FPS
        fps = 25.0

    # Nombre: channelX_YYYYmmdd_HHMMSS.mp4
    now = datetime.now()
    ts_str = now.strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(
        OUTPUT_DIR,
        f"channel{CHANNEL}_{ts_str}.mp4"
    )

    # Codec: mp4v (suele ir bien con extensión .mp4)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(filename, fourcc, fps, (width, height))

    if not writer.isOpened():
        raise RuntimeError(f"No se pudo crear el archivo de video: {filename}")

    print(f"Grabando nuevo segmento: {filename}")
    return writer, filename


segment_duration_sec = SEGMENT_MINUTES * 60.0

cv2.namedWindow("Frame", cv2.WINDOW_NORMAL)

while True:  # bucle infinito hasta que cierres ventana o aprietes 'q'
    cap = open_capture()
    writer, current_filename = create_writer(cap)
    segment_start_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            print("No se pudo leer frame del stream. Cerrando y reintentando conexión...")
            writer.release()
            cap.release()
            break  # volvemos al while externo: se reabre el stream y se crea nuevo archivo

        # Escribimos frame en el video actual
        writer.write(frame)

        # Mostrar para monitorear
        cv2.imshow("Frame", frame)

        # Chequear si ya pasamos la duración del segmento
        elapsed = time.time() - segment_start_time
        if elapsed >= segment_duration_sec:
            print(f"Segmento completado ({SEGMENT_MINUTES} min): {current_filename}")
            writer.release()
            # Comenzar un nuevo archivo sin cortar el stream
            writer, current_filename = create_writer(cap)
            segment_start_time = time.time()

        # Cerrar ventana => salir del programa
        if cv2.getWindowProperty("Frame", cv2.WND_PROP_VISIBLE) < 1:
            print("Ventana cerrada. Saliendo del programa.")
            writer.release()
            cap.release()
            cv2.destroyAllWindows()
            raise SystemExit

        # 'q' para salir manualmente del programa
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("Tecla 'q' presionada. Saliendo del programa.")
            writer.release()
            cap.release()
            cv2.destroyAllWindows()
            raise SystemExit
