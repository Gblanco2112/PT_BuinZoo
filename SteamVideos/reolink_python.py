import cv2

rtsp_url = "rtsp://view:vieW.,star3250@190.8.125.219:554/cam/realmonitor?channel=1&subtype=0"
cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

print("Ancho:", cap.get(cv2.CAP_PROP_FRAME_WIDTH))
print("Alto:", cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

if not cap.isOpened():
    raise RuntimeError("No se pudo abrir el stream RTSP")

cv2.namedWindow("Frame", cv2.WINDOW_NORMAL)

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    cv2.imshow("Frame", frame)
    
    # Detectar si se cerró la ventana
    if cv2.getWindowProperty("Frame", cv2.WND_PROP_VISIBLE) < 1:
        break
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()