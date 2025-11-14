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
    default=5.0,
    help="Periodo de muestreo en segundos."
)

args = parser.parse_args()

CHANNEL = args.channel
Ts = args.Ts
# =============================================

# =============== CONFIGURACIÓN ===============

# RTSP: usamos el canal pasado por parámetro
rtsp_url = (
    f"rtsp://view:vieW.,star3250@190.8.125.219:554/"
    f"cam/realmonitor?channel={CHANNEL}&subtype=0"
)

output_dir = "frames_capturados"
ext = "png"  # "png" o "jpg"

MAX_FRAMES_LOCAL = 10  # cuando haya N frames, se suben y se borran

DROPBOX_ACCESS_TOKEN = "sl.u.AGER-Cc6zGB1ZClBpsUUHIL_szHUzjhMFnng_Zq7DzIYB6vayv0yo_hkuiWFVqm5TuAJw6MiU5rWdMUlgdc5FK32TUASautyPaiSTRkRJKdxxhIF7uMaWGHTokki2Ah6_hmYCjOietF70OEwsAUKhHxdfqT03zN4aBrZileHymWcqU3IuyC48eTpPeegFryunzDXl9orLFZKdtPBfAGK0bv0iyck-Lq5eBUbTc4xFt3OrJlUK7-tPPPwbi0jHE3Qzj13PC-FpbYg4Mj1oMDp4brfzgmIkRVdsmFI1G1E7yPGdqcZc0_U3GEwEYHWrOhARFQ5Ov6zOLBO-VZKsPLdg9RYdrj2TrMWmNBUSdsQn0L3hWNl7SV_4hzzbR7d2EuU-7NGQ3K2I-ULKHs14-i3A2zTzeniX3TpHa0udIWcqPiUVvHs2laqqSbAnx8W3qSwVkN03XUjh9Na9coYPgBCgpDOGfk_HWvSRcXWH7G8vyllYODsrBlPhgEd7PdD0cTUSGDFsOjLTV8PXZzLLDPhsYsRsbe-SAYAeUA7Wa1fabxi76vtPcClLRfm8QsXBxfjmtLJr4qtFnMCPhD5NDKyN9QG8GsFC5plxrb1b3mW95JPlZtSYR3rUOfQjxubLnRzQkU6BUWDpxeM-BhCEoSSd04HQ0M1wI_Ge6XN_G7AjSWR48ryT2oeOaFNu_HMvxT4rSYMexMPyjjDBOgww09x71QRkUoWtKf6M6PQNhxYGJ8x4bcuBhGZk9hd0z0wO8QoBsDIOT07qqOrtmDe6taCiS0VkZUQdMBA5z9-SO4IFFHqZZFZOkMnlo_6pXz1geVQozU0_3soTl3ZgBe-uZjao4M2mbJtN9Lufj52f02pVQjaK4rdWF3UUWcx2npk6hZA8vbHpBU8vpCNBznNApU2-vmNrHXV9eSSQxEbgN51uPPyYVdC8PlwVzKNiNUg1XyWDtCa12t8FVYpWGvR0tGZbnCDNth9UVgBriEt4-v4_IuDjCuwYL3_eezE4GcTjRc6c3XaLG4QvqNP0uVavPnqonMV65pm6kn_3MSK4nGRyq9b2ESUpYOjFjStCeNVHhTQ1T7gPfWtiahoySntE56BFW6juraa5UrwMH5IE1h8AfamjwfvJ5W6m-NgdPsYOp7ceQfrVxXuR37ox_WWxKJlw8AvGQKfHOv1gCvubFo3w2D0y2F4tyRjlxQgtyCbW0_NUwZXQDyhzStLVOvCFocZiv-8df-82ZInWA3tKNJaOe3QNn08XKGyfBIK-IzDVpvUH7fUml19QzOdqVSln3HiaAuebGuvxpfOeoMHGkrtCXvglEZDpOGAjGsUBRCYi1yQJl3GvZ1yInq2LKXB5gC9Jt8arAqVwb9zSsxOzsxw3jKuZ7rklEouom9stEN_uCYb5q6XnW3x_-nYYC4FBesOnN8UogewUcnGvO1KRKQ5GKbzdw"

# Carpeta en Dropbox: si el usuario no pasa nada, usamos /Channel{CHANNEL}
if args.dropbox_folder is not None:
    DROPBOX_FOLDER = args.dropbox_folder
else:
    DROPBOX_FOLDER = f"/Channel{CHANNEL}"

print(f"Usando canal RTSP: {CHANNEL}")
print(f"Carpeta de Dropbox: {DROPBOX_FOLDER}")
print(f"Periodo de muestreo Ts: {Ts} s")

# =============================================

os.makedirs(output_dir, exist_ok=True)

dbx = dropbox.Dropbox(DROPBOX_ACCESS_TOKEN)


def upload_and_cleanup(local_dir, dropbox_folder):
    """
    Sube todos los archivos de local_dir a dropbox_folder
    y luego los borra localmente.
    """
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
        # Borrar archivo local después de subirlo
        os.remove(path)

    print("Subida completada y archivos locales eliminados.")


cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

print("Ancho:", cap.get(cv2.CAP_PROP_FRAME_WIDTH))
print("Alto:", cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

if not cap.isOpened():
    raise RuntimeError("No se pudo abrir el stream RTSP")

cv2.namedWindow("Frame", cv2.WINDOW_NORMAL)

last_save_time = 0.0
frame_counter = 0

while True:
    ret, frame = cap.read()
    if not ret:
        print("No se pudo leer frame del stream.")
        break

    now = time.time()

    # Guardar frame cada Ts segundos
    if now - last_save_time >= Ts:
        ts = datetime.fromtimestamp(now)
        ts_str = ts.strftime("%Y%m%d_%H%M%S_%f")[:-3]  # hasta milisegundos

        # channelX_timestamp.ext
        filename = os.path.join(
            output_dir,
            f"channel{CHANNEL}_{ts_str}.{ext}"
        )

        cv2.imwrite(filename, frame)
        print(f"Guardado: {filename}")

        last_save_time = now
        frame_counter += 1

        # ¿Llegamos al máximo permitido localmente?
        if frame_counter % MAX_FRAMES_LOCAL == 0:
            upload_and_cleanup(output_dir, DROPBOX_FOLDER)

    # Mostrar video
    cv2.imshow("Frame", frame)

    if cv2.getWindowProperty("Frame", cv2.WND_PROP_VISIBLE) < 1:
        break

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Al salir, subir lo que quede pendiente
upload_and_cleanup(output_dir, DROPBOX_FOLDER)

cap.release()
cv2.destroyAllWindows()
