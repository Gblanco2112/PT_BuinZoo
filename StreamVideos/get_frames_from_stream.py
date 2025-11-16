import cv2
import time
import os
import glob
import dropbox
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
    "--dropbox-folder",
    type=str,
    default=None,
    help="Carpeta en Dropbox (ej: /Channel1). Si no se indica, se usa /Channel{channel}."
)

parser.add_argument(
    "--Ts",
    type=float,
    default=10,
    help="Periodo de muestreo en segundos."
)

parser.add_argument(
    "--local-only",
    action="store_true",
    help="Si se pasa, solo guarda en disco local y NO sube a Dropbox."
)

args = parser.parse_args()

CHANNEL = args.channel
Ts = args.Ts
LOCAL_ONLY = args.local_only
# =============================================

# =============== CONFIGURACIÓN ===============

rtsp_url = (
    f"rtsp://view:vieW.,star3250@190.8.125.219:554/"
    f"cam/realmonitor?channel={CHANNEL}&subtype=0"
)

output_dir = "frames_capturados"
ext = "png"  # "png" o "jpg"

MAX_FRAMES_LOCAL = 10  # cuando haya N frames, se suben y se borran (si no es local-only)

# Token desde variable de entorno (recomendado)
DROPBOX_ACCESS_TOKEN = os.getenv("DROPBOX_ACCESS_TOKEN")

# Carpeta en Dropbox: si el usuario no pasa nada, usamos /Channel{CHANNEL}
if args.dropbox_folder is not None:
    DROPBOX_FOLDER = args.dropbox_folder
else:
    DROPBOX_FOLDER = f"/Channel{CHANNEL}"

print(f"Usando canal RTSP: {CHANNEL}")
print(f"Periodo de muestreo Ts: {Ts} s")
print(f"Solo local (sin Dropbox): {LOCAL_ONLY}")

if not LOCAL_ONLY:
    print(f"Carpeta de Dropbox: {DROPBOX_FOLDER}")
# =============================================

os.makedirs(output_dir, exist_ok=True)

# Solo inicializamos Dropbox si NO es solo local
dbx = None
if not LOCAL_ONLY:
    if not DROPBOX_ACCESS_TOKEN:
        raise RuntimeError(
            "No se encontró la variable DROPBOX_ACCESS_TOKEN "
            "y no estás usando --local-only."
        )
    dbx = dropbox.Dropbox(DROPBOX_ACCESS_TOKEN)


def upload_and_cleanup(local_dir, dropbox_folder):
    """
    Sube todos los archivos de local_dir a dropbox_folder
    y luego los borra localmente.

    Si LOCAL_ONLY es True, no hace nada.
    """
    if LOCAL_ONLY:
        return  # no subimos ni borramos nada

    pattern = os.path.join(local_dir, f"*.{ext}")
    files = glob.glob(pattern)

    if not files:
        return

    print(f"Subiendo {len(files)} archivos a Dropbox...")

    for path in files:
        name = os.path.basename(path)
        dropbox_path = f"{dropbox_folder}/{name}"

        with open(path, "rb") as f:
            dbx.files_upload(
                f.read(),
                dropbox_path,
                mode=dropbox.files.WriteMode("overwrite"),
            )
        os.remove(path)

    print("Subida completada y archivos locales eliminados.")


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


cv2.namedWindow("Frame", cv2.WINDOW_NORMAL)

frame_counter = 0
last_save_time = 0.0

while True:  # bucle infinito hasta que cierres ventana o aprietes 'q'
    cap = open_capture()

    while True:
        ret, frame = cap.read()

        if not ret:
            print("No se pudo leer frame del stream. Cerrando y reintentando conexión...")
            cap.release()
            break  # salimos del while interno y volvemos a open_capture()

        now = time.time()

        # Guardar frame cada Ts segundos
        if now - last_save_time >= Ts:
            ts = datetime.fromtimestamp(now)
            ts_str = ts.strftime("%Y%m%d_%H%M%S_%f")[:-3]

            filename = os.path.join(
                output_dir,
                f"channel{CHANNEL}_{ts_str}.{ext}"
            )

            cv2.imwrite(filename, frame)
            print(f"Guardado: {filename}")

            last_save_time = now
            frame_counter += 1

            # ¿Llegamos al máximo permitido localmente?
            # Solo sube/borra si NO es local-only
            if (frame_counter % MAX_FRAMES_LOCAL == 0) and (not LOCAL_ONLY):
                upload_and_cleanup(output_dir, DROPBOX_FOLDER)

        cv2.imshow("Frame", frame)

        # Cerrar ventana => salir del programa
        if cv2.getWindowProperty("Frame", cv2.WND_PROP_VISIBLE) < 1:
            print("Ventana cerrada. Saliendo del programa.")
            cap.release()
            cv2.destroyAllWindows()
            raise SystemExit

        # 'q' para salir manualmente del programa
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("Tecla 'q' presionada. Saliendo del programa.")
            cap.release()
            cv2.destroyAllWindows()
            raise SystemExit
