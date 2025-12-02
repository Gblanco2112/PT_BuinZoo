import numpy as np
import os
import sys

class Reconstructor3D:
    def __init__(self, filename="calibracion_datos.npz", cam_key_1='cam_2', cam_key_2='cam_1'):
        """
        Inicializa el sistema de reconstrucción.
        Carga datos y pre-calcula las matrices de proyección (P) para eficiencia.
        
        Args:
            filename: Ruta al archivo .npz
            cam_key_1: Nombre de la clave en el npz para la cámara 1 (ej: 'cam_2' que es la IZQUIERDA en tu main)
            cam_key_2: Nombre de la clave en el npz para la cámara 2 (ej: 'cam_1' que es la DERECHA en tu main)
        """
        self.valid = False
        self.P1 = None
        self.P2 = None
        
        if not os.path.exists(filename):
            print(f"⚠️ ADVERTENCIA 3D: No se encontró '{filename}'. La reconstrucción 3D estará desactivada.")
            return

        try:
            data = np.load(filename)
            points_3d = data['points_3d']
            
            # Verificar que existan las claves de las cámaras
            if cam_key_1 not in data or cam_key_2 not in data:
                print(f"⚠️ ADVERTENCIA 3D: No se encontraron las claves '{cam_key_1}' o '{cam_key_2}' en el archivo.")
                print(f"   Claves disponibles: {list(data.files)}")
                return

            pts_2d_cam1 = data[cam_key_1]
            pts_2d_cam2 = data[cam_key_2]

            # Pre-calcular matrices P (Solo se hace una vez al inicio)
            self.P1 = self._calculate_projection_matrix(pts_2d_cam1, points_3d)
            self.P2 = self._calculate_projection_matrix(pts_2d_cam2, points_3d)
            self.valid = True
            print(f"✅ Sistema 3D Inicializado correctamente usando {cam_key_1} y {cam_key_2}.")
            
        except Exception as e:
            print(f"❌ ERROR 3D: Fallo al inicializar: {e}")

    def _calculate_projection_matrix(self, points_2d, points_3d):
        """Método interno DLT para calcular matriz P."""
        A = []
        for i in range(len(points_2d)):
            u, v = points_2d[i]
            X, Y, Z = points_3d[i]
            A.append([ -X, -Y, -Z, -1,  0,  0,  0,  0, u*X, u*Y, u*Z, u ])
            A.append([  0,  0,  0,  0, -X, -Y, -Z, -1, v*X, v*Y, v*Z, v ])
        
        A = np.array(A)
        U, S, Vt = np.linalg.svd(A)
        P = Vt[-1].reshape(3, 4)
        return P

    def _get_bbox_center(self, bbox):
        """Calcula centro (x, y) desde [x1, y1, x2, y2]."""
        # bbox puede venir como tensor o lista, aseguramos numpy
        if hasattr(bbox, 'cpu'): bbox = bbox.cpu().numpy()
        if hasattr(bbox, 'numpy'): bbox = bbox.numpy()
        
        x_min, y_min, x_max, y_max = bbox
        cx = (x_min + x_max) / 2.0
        cy = (y_min + y_max) / 2.0
        return np.array([cx, cy])

    def _triangulate_point(self, P1, P2, point1, point2):
        """Triangula la posición 3D."""
        u1, v1 = point1
        u2, v2 = point2
        A = np.array([
            u1 * P1[2] - P1[0],
            v1 * P1[2] - P1[1],
            u2 * P2[2] - P2[0],
            v2 * P2[2] - P2[1]
        ])
        U, S, Vt = np.linalg.svd(A)
        X_homogeneous = Vt[-1]
        return X_homogeneous[:3] / X_homogeneous[3]

    def obtener_coordenada_3d(self, bbox_cam1, bbox_cam2):
        """
        Recibe dos bounding boxes y retorna (X, Y, Z).
        Retorna None si el sistema no está calibrado o hay error.
        """
        if not self.valid:
            return None

        # 1. Obtener centros
        center_1 = self._get_bbox_center(bbox_cam1)
        center_2 = self._get_bbox_center(bbox_cam2)

        # 2. Triangular
        try:
            point_3d = self._triangulate_point(self.P1, self.P2, center_1, center_2)
            return point_3d # Array [X, Y, Z]
        except Exception as e:
            print(f"Error triangulando: {e}")
            return None