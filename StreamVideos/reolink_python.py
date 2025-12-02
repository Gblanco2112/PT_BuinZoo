import cv2

# Replace with your actual RTSP URLs
rtsp_urls = {
    '1': "rtsp://view:vieW.,star3250@190.8.125.219:554/cam/realmonitor?channel=1&subtype=0",
    '2': "rtsp://view:vieW.,star3250@190.8.125.219:554/cam/realmonitor?channel=2&subtype=0"  # <-- fill with your second camera URL
}

def open_camera(key):
    url = rtsp_urls[key]
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        cap.release()
        return None
    return cap

current = '1'
cap = open_camera(current)
if cap is None:
    raise RuntimeError(f"No se pudo abrir el stream RTSP para la cámara {current}")

cv2.namedWindow("Frame", cv2.WINDOW_NORMAL)

while True:
    ret, frame = cap.read()
    if not ret:
        # intentar reabrir la misma cámara si falla la lectura
        cap.release()
        cap = open_camera(current)
        if cap is None:
            print(f"Fallo al leer/cerrar la cámara {current}. Presione 1 o 2 para cambiar, q para salir.")
            # esperar key para permitir cambiar cámara o salir
            key = cv2.waitKey(0) & 0xFF
            if key == ord('q'):
                break
            if chr(key) in rtsp_urls:
                target = chr(key)
                if target != current:
                    new_cap = open_camera(target)
                    if new_cap:
                        cap = new_cap
                        current = target
                    else:
                        print(f"No se pudo abrir la cámara {target}")
            continue

    cv2.imshow("Frame", frame)

    # Detectar si se cerró la ventana
    if cv2.getWindowProperty("Frame", cv2.WND_PROP_VISIBLE) < 1:
        break

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    if chr(key) in rtsp_urls:
        target = chr(key)
        if target != current:
            # try to open new camera before releasing current
            new_cap = open_camera(target)
            if new_cap:
                cap.release()
                cap = new_cap
                current = target
                print(f"Cambiado a cámara {current}")
            else:
                print(f"No se pudo abrir la cámara {target}. Manteniendo cámara {current}")

cap.release()
cv2.destroyAllWindows()