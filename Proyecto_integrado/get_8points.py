# -*- coding: utf-8 -*-
import cv2
import numpy as np
import os
import time
import threading # Importante para no congelar la GUI

# --- Configuración ---
# Plantilla de URL RTSP. Se usa el parámetro 'channel' para elegir cámara.
RTSP_BASE_URL = "rtsp://view:vieW.,star3250@190.8.125.219:554/cam/realmonitor?channel={channel}&subtype=0"
CHANNELS = [1, 2, 3] 
NUM_POINTS = 8
WINDOW_NAME = "Asistente de Calibracion"

# Configuración Visual (tamaños y colores de elementos gráficos)
CIRCLE_RADIUS = 10       
CIRCLE_COLOR = (0, 0, 255)      # Rojo
CIRCLE_BORDER = (255, 255, 255) # Blanco
TEXT_COLOR = (255, 255, 255)
PANEL_WIDTH = 500
WINDOW_WIDTH = 1280 # Ancho total por defecto para pantallas de texto
WINDOW_HEIGHT = 720 # Alto total por defecto

# Colores de Ejes para el Cubo (BGR)
COLOR_X = (255, 255, 0)   # Cian (BGR)
COLOR_Y = (255, 0, 255)   # Magenta (BGR)
COLOR_Z = (0, 255, 255)   # Amarillo (BGR)
COLOR_DEFAULT = (100, 100, 100) # Gris

# --- Lógica 3D ---
# Orden lógico de los 8 puntos del cubo en coordenadas normalizadas
# (0 o 1) antes de escalar por las dimensiones reales.
CORRESPONDENCIA_3D_ORDEN = [
    (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
    (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)
]

# --- Variables Globales ---
selected_points = []         # Lista de puntos 2D seleccionados por el usuario
current_video_width = 0      # Ancho del frame de la cámara actual

# ==========================================
# UTILIDADES GRÁFICAS
# ==========================================

def create_blank_screen(message_lines, subtext=None, color=(0,0,0)):
    """Crea una imagen de fondo (color sólido) con texto centrado en pantalla."""
    img = np.zeros((WINDOW_HEIGHT, WINDOW_WIDTH, 3), dtype=np.uint8)
    img[:] = color
    
    font = cv2.FONT_HERSHEY_SIMPLEX
    center_x = WINDOW_WIDTH // 2
    
    total_text_height = len(message_lines) * 60
    start_y = (WINDOW_HEIGHT - total_text_height) // 2
    
    # Escribe cada línea de mensaje centrada
    for i, line in enumerate(message_lines):
        text_size = cv2.getTextSize(line, font, 1.3, 3)[0]
        text_x = center_x - (text_size[0] // 2)
        cv2.putText(img, line, (text_x, start_y + (i * 70)), font, 1.3, (255, 255, 255), 3, cv2.LINE_AA)

    # Subtexto opcional en la parte inferior (por ejemplo, instrucciones)
    if subtext:
        text_size = cv2.getTextSize(subtext, font, 0.8, 1)[0]
        text_x = center_x - (text_size[0] // 2)
        cv2.putText(img, subtext, (text_x, WINDOW_HEIGHT - 100), font, 0.8, (200, 200, 200), 1, cv2.LINE_AA)
        
    return img

def show_temporary_message(lines, duration_ms=1):
    """
    Muestra un mensaje en pantalla por un tiempo determinado (en ms).
    Si duration_ms=1, se usa principalmente para refrescar la UI.
    """
    img = create_blank_screen(lines)
    cv2.imshow(WINDOW_NAME, img)
    cv2.waitKey(duration_ms)

def draw_invalid_key_alert(img):
    """Dibuja una alerta roja de 'Tecla No Válida' sobre la imagen dada."""
    h, w = img.shape[:2]
    # Dimensiones y posición del rectángulo de alerta
    box_w, box_h = 600, 100
    top_left = (w//2 - box_w//2, h//2 - box_h//2)
    bottom_right = (w//2 + box_w//2, h//2 + box_h//2)
    
    # Dibujar fondo rojo y borde blanco
    cv2.rectangle(img, top_left, bottom_right, (0, 0, 255), -1) # Fondo Rojo
    cv2.rectangle(img, top_left, bottom_right, (255, 255, 255), 4) # Borde Blanco
    
    # Texto de la alerta centrado
    text = "TECLA NO VALIDA"
    font = cv2.FONT_HERSHEY_SIMPLEX
    text_size = cv2.getTextSize(text, font, 2.0, 5)[0]
    text_x = w//2 - text_size[0]//2
    text_y = h//2 + text_size[1]//2
    
    cv2.putText(img, text, (text_x, text_y), font, 2.0, (255, 255, 255), 5, cv2.LINE_AA)

# ==========================================
# DIBUJO DEL CUBO
# ==========================================

def draw_enhanced_cube(img, center_x, center_y, size, highlight_axis=None):
    """
    Dibuja un cubo isométrico con aristas coloreadas según eje (X, Y, Z).
    highlight_axis: 'X', 'Y' o 'Z' para resaltar ese eje, o None para todos iguales.
    """
    # Proyección Isométrica Simple: definimos largo, profundidad y alto
    L, W, H = size, int(size/2), size
    sx, sy = center_x - int(size/2), center_y + int(size/2)

    # Vértices (1-8) del cubo en 2D para dibujar
    pts = {}
    pts[1] = (sx, sy)
    pts[2] = (sx + L, sy)
    pts[3] = (sx + L + W, sy - W)
    pts[4] = (sx + W, sy - W)
    pts[5] = (sx, sy - H)
    pts[6] = (sx + L, sy - H)
    pts[7] = (sx + L + W, sy - W - H)
    pts[8] = (sx + W, sy - W - H)

    # Definición de Aristas con info de a qué eje pertenecen
    edges_info = [
        (1, 2, 'X'), (2, 3, 'Y'), (3, 4, 'X'), (4, 1, 'Y'), # Base
        (5, 6, 'X'), (6, 7, 'Y'), (7, 8, 'X'), (8, 5, 'Y'), # Tapa
        (1, 5, 'Z'), (2, 6, 'Z'), (3, 7, 'Z'), (4, 8, 'Z')  # Verticales
    ]

    base_thickness = 2
    
    # Dibujo de aristas (cambiar color y grosor si están resaltadas)
    for s, e, axis in edges_info:
        color = COLOR_DEFAULT
        thickness = base_thickness
        if highlight_axis == axis:
            thickness = 6
            if axis == 'X': color = COLOR_X
            elif axis == 'Y': color = COLOR_Y
            elif axis == 'Z': color = COLOR_Z
            
        cv2.line(img, pts[s], pts[e], color, thickness, cv2.LINE_AA)

    # Dibujar vértices numerados del cubo
    for i in range(1, 9):
        cv2.circle(img, pts[i], 20, (30, 30, 30), -1, cv2.LINE_AA)
        cv2.circle(img, pts[i], 20, (200, 200, 200), 2, cv2.LINE_AA)
        txt_x = pts[i][0] - 10
        txt_y = pts[i][1] + 10
        num_color = (0, 0, 255)
        cv2.putText(img, str(i), (txt_x, txt_y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, num_color, 2, cv2.LINE_AA)

# ==========================================
# PANELES E INTERFAZ
# ==========================================

def create_side_panel(height, points_count):
    """
    Crea el panel lateral derecho con el estado de la calibración,
    instrucciones y representación del cubo de referencia.
    """
    panel = np.zeros((height, PANEL_WIDTH, 3), dtype=np.uint8)
    
    cv2.putText(panel, "CALIBRACION 3D", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3, cv2.LINE_AA)
    cv2.line(panel, (20, 65), (PANEL_WIDTH-20, 65), (100, 100, 100), 2)

    next_pt = points_count + 1
    if points_count < NUM_POINTS:
        msg = f"PUNTO ACTUAL: {next_pt}"
        clr = (0, 255, 255)
    else:
        msg = "LISTO PARA GUARDAR"
        clr = (0, 255, 0)
    
    cv2.putText(panel, msg, (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.2, clr, 3, cv2.LINE_AA)
    draw_enhanced_cube(panel, int(PANEL_WIDTH/2), 350, 120, highlight_axis=None)

    # Texto de ayuda para interacción con el mouse/teclado
    start_y = 550
    msgs = ["Clic IZQ: Marcar", "Clic DER: Borrar", "'r': Reiniciar", "ESPACIO: Confirmar"]
    for i, m in enumerate(msgs):
        cv2.putText(panel, m, (20, start_y + i*50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (200, 200, 200), 2, cv2.LINE_AA)

    return panel

def mouse_callback(event, x, y, flags, param):
    """
    Callback de eventos del mouse sobre la ventana principal.
    Permite agregar o borrar puntos 2D en la imagen de la cámara.
    """
    global selected_points
    # Ignorar clicks en el área del panel lateral (solo imagen de la cámara)
    if x >= current_video_width: return

    if event == cv2.EVENT_LBUTTONDOWN:
        # Click izquierdo: agregar punto (si aún hay cupo)
        if len(selected_points) < NUM_POINTS:
            selected_points.append((x, y))
    elif event == cv2.EVENT_RBUTTONDOWN:
        # Click derecho: eliminar último punto agregado
        if len(selected_points) > 0:
            selected_points.pop()

# ==========================================
# LÓGICA DE FLUJO
# ==========================================

def run_calibration_step(channel):
    """
    Ejecuta la secuencia de calibración para una cámara específica:
      - Conecta a la cámara RTSP.
      - Muestra el primer frame.
      - Permite seleccionar 8 puntos 2D sobre la imagen.
      - Devuelve un array de puntos o None si hay error/abort.
    """
    global selected_points, current_video_width
    selected_points = []
    
    rtsp_url = RTSP_BASE_URL.format(channel=channel)
    cap_holder = {"cap": None}
    
    # Usamos un hilo para no bloquear la interfaz mientras conecta a la cámara
    def connect_worker():
        temp_cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        if temp_cap.isOpened():
            cap_holder["cap"] = temp_cap
    
    t = threading.Thread(target=connect_worker)
    t.start()
    
    start_time = time.time()
    
    # Mostrar pantalla de "conectando..." mientras el hilo sigue vivo
    while t.is_alive():
        elapsed_seconds = int(time.time() - start_time)
        lines = [
            f"Conectando a CAMARA {channel}...",
            "Espere, este proceso puede demorar.",
            f"(Tiempo en espera: {elapsed_seconds} segundos...)"
        ]
        screen = create_blank_screen(lines, subtext="No cierre la ventana, intentando conectar...", color=(20, 20, 20))
        cv2.imshow(WINDOW_NAME, screen)
        cv2.waitKey(100)
    
    t.join()
    cap = cap_holder["cap"]
    
    # Si no se logró abrir la cámara, avisamos y salimos
    if cap is None or not cap.isOpened():
        show_temporary_message([f"ERROR: Camara {channel}", "No se pudo conectar", "o tiempo de espera agotado"], 3000)
        return None, False

    ret, frame = cap.read()
    cap.release()
    
    if not ret:
        # Conexión lograda pero sin imagen válida
        show_temporary_message([f"ERROR: Camara {channel}", "Conectado pero sin imagen"], 3000)
        return None, False

    # Guardamos ancho para discriminar zona de panel lateral
    current_video_width = frame.shape[1]
    cv2.setMouseCallback(WINDOW_NAME, mouse_callback)

    # Variable para controlar el tiempo de visualización de la alerta
    invalid_key_timer = 0

    while True:
        disp_frame = frame.copy()
        # Dibujo de puntos elegidos sobre la imagen
        for i, pt in enumerate(selected_points):
            cv2.circle(disp_frame, pt, CIRCLE_RADIUS, CIRCLE_COLOR, -1, cv2.LINE_AA)
            cv2.putText(disp_frame, str(i+1), (pt[0]+10, pt[1]-10), cv2.FONT_HERSHEY_SIMPLEX, 2, CIRCLE_COLOR, 4, cv2.LINE_AA)
        
        panel = create_side_panel(frame.shape[0], len(selected_points))
        combined = np.hstack((disp_frame, panel))
        
        # Si el temporizador de error está activo, dibujamos la alerta
        if time.time() < invalid_key_timer:
            draw_invalid_key_alert(combined)

        cv2.imshow(WINDOW_NAME, combined)
        
        k = cv2.waitKey(10) & 0xFF
        
        if k != 255: # Si se presionó una tecla
            # Si presionamos CUALQUIER tecla, apagamos la alerta actual (y evaluamos si la nueva es válida)
            invalid_key_timer = 0
            
            is_valid = False
            
            if k == ord('q'):
                # Salir de la herramienta
                return None, True # Salir
                
            elif k == ord('z'):
                # Deshacer último punto
                if selected_points: selected_points.pop()
                is_valid = True # 'z' es válido
                
            elif k == ord('r'):
                # Reiniciar selección de puntos
                selected_points = []
                is_valid = True # 'r' es válido
                
            elif k == 32: # Espacio
                # Confirmar solo si ya están los 8 puntos
                if len(selected_points) == NUM_POINTS:
                    return np.array(selected_points, dtype=np.float32), False
                else:
                    # Espacio con < 8 puntos es inválido
                    is_valid = False
            
            else:
                is_valid = False # Cualquier otra tecla

            if not is_valid:
                # Activar alerta por 2 segundos (antes 5)
                invalid_key_timer = time.time() + 2

def get_dimension_input(axis_name, edge_name, color_hint):
    """
    Pide al usuario que ingrese la longitud de una arista en metros
    para un eje específico (X, Y o Z). El input se hace en pantalla
    usando el teclado numérico.
    """
    input_str = ""
    invalid_key_timer = 0
    
    while True:
        img = np.zeros((WINDOW_HEIGHT, WINDOW_WIDTH, 3), dtype=np.uint8)
        
        cv2.putText(img, f"INGRESE MEDIDA EN METROS EJE {axis_name}", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.5, color_hint, 4, cv2.LINE_AA)
        cv2.putText(img, f"(Arista {edge_name})", (50, 140), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (200,200,200), 2, cv2.LINE_AA)
        
        draw_enhanced_cube(img, WINDOW_WIDTH - 300, WINDOW_HEIGHT//2 + 50, 200, highlight_axis=axis_name)
        
        # Cuadro de texto donde se muestra lo digitado
        cv2.rectangle(img, (50, 250), (600, 350), (50, 50, 50), -1)
        cv2.rectangle(img, (50, 250), (600, 350), color_hint, 2)
        
        display_txt = input_str + "_"
        cv2.putText(img, display_txt, (70, 320), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (255, 255, 255), 3, cv2.LINE_AA)
        
        cv2.putText(img, "Escriba con el teclado numerico.", (50, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (150,150,150), 1, cv2.LINE_AA)
        cv2.putText(img, "Presione ENTER para confirmar.", (50, 490), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (150,150,150), 1, cv2.LINE_AA)

        # Dibujar alerta si está activa
        if time.time() < invalid_key_timer:
            draw_invalid_key_alert(img)

        cv2.imshow(WINDOW_NAME, img)
        
        # Cambiamos waitKey(0) por waitKey(10) en bucle para manejar el tiempo de la alerta
        k = cv2.waitKey(10) & 0xFF
        
        if k != 255:
            # Apagar alerta anterior al presionar tecla nueva
            invalid_key_timer = 0
            is_valid = False
            
            if k == 13: # Enter
                # Intentar parsear el input a float > 0
                try:
                    val = float(input_str)
                    if val > 0: return val
                except:
                    # Si no se puede parsear, se limpia el input pero no se considera tecla inválida
                    input_str = "" # Reset si inválido pero no error de tecla
                is_valid = True
                
            elif k == 8: # Backspace
                # Borrar último carácter
                input_str = input_str[:-1]
                is_valid = True
                
            elif 48 <= k <= 57: # Números 0-9
                # Agregar dígito
                input_str += chr(k)
                is_valid = True
                
            elif k == 46: # Punto .
                # Permitir solo un punto decimal
                if '.' not in input_str: input_str += '.'
                is_valid = True
                
            elif k == ord('q'):
                # Cerrar programa desde este punto
                exit()
            
            if not is_valid:
                # Activar alerta por 2 segundos (antes 5)
                invalid_key_timer = time.time() + 2

# ==========================================
# MAIN
# ==========================================

def main():
    """
    Flujo principal del asistente de calibración:
      1) Muestra pantalla de bienvenida.
      2) Para cada canal en CHANNELS, ejecuta la selección de 8 puntos 2D.
      3) Pide dimensiones reales del cubo (X, Y, Z).
      4) Calcula los 8 puntos 3D y guarda todo en 'calibracion_datos.npz'.
    """
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, WINDOW_WIDTH, WINDOW_HEIGHT)
    
    screen = create_blank_screen(
        ["BIENVENIDO AL ASISTENTE", "DE CALIBRACION"], 
        "Presione ESPACIO para comenzar"
    )
    
    # Bucle inicial con manejo de error (opcional si quieren validar el espacio estrictamente)
    invalid_start_timer = 0
    while True:
        display_screen = screen.copy()
        if time.time() < invalid_start_timer:
            draw_invalid_key_alert(display_screen)
            
        cv2.imshow(WINDOW_NAME, display_screen)
        k = cv2.waitKey(10) & 0xFF
        
        if k != 255:
            if k == 32: # Espacio
                break
            elif k == ord('q'):
                return
            else:
                # Activar alerta por 2 segundos (antes 5)
                invalid_start_timer = time.time() + 2

    all_2d = {}

    # Recorremos canales de cámara y recogemos sus 8 puntos 2D
    for ch in CHANNELS:
        pts, abort = run_calibration_step(ch)
        if abort: 
            print("Abortado por usuario.")
            return
        if pts is not None:
            all_2d[f'cam_{ch}'] = pts

    # Se requiere al menos 2 cámaras para triangulación 3D
    if len(all_2d) < 2:
        show_temporary_message(["ERROR FATAL", "No hay suficientes camaras", "para calibrar."], 4000)
        return

    # Desactivamos el callback del mouse, ya no hace falta
    cv2.setMouseCallback(WINDOW_NAME, lambda *args: None)
    
    # Pedimos dimensiones reales del recinto / cubo
    Lx = get_dimension_input('X', '1-2', COLOR_X)
    Ly = get_dimension_input('Y', '1-4', COLOR_Y)
    Lz = get_dimension_input('Z', '1-5', COLOR_Z)

    show_temporary_message(["Guardando datos..."])
    
    # Escalamos las coordenadas normalizadas del cubo (0/1) a metros reales
    points_3d = []
    for rc in CORRESPONDENCIA_3D_ORDEN:
        points_3d.append([rc[0]*Lx, rc[1]*Ly, rc[2]*Lz])
    
    save_data = all_2d
    save_data['points_3d'] = np.array(points_3d, dtype=np.float32)
    np.savez("calibracion_datos.npz", **save_data)
    
    show_temporary_message(["PROCESO FINALIZADO", "Archivo guardado exitosamente"], 3000)
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
