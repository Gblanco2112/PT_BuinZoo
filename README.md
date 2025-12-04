# 🐾 Buin Zoo – Sistema de Monitoreo de Comportamiento

Este proyecto levanta un sistema completo para monitorear el comportamiento de animales en el Buin Zoo:

* **Backend** (FastAPI) – API REST + autenticación + reportes.
* **Frontend** (React + Vite) – dashboard web.
* **Visión computacional** (YOLO + RTSP) – pipeline que consume cámaras y envía eventos al backend.
* **Base de datos** (PostgreSQL 16).

Todo está orquestado con **Docker Compose**.
---

## 📁 Estructura de carpetas (esperada por `docker-compose.yml`)

A partir del `docker-compose.yml`:

* `back/`
  Backend FastAPI (código Python, `Dockerfile`, etc.).

* `front/my-app/`
  Frontend React/Vite con su propio `Dockerfile`.

* `vision/`
  Servicio de visión por computador:

  * `vision/Dockerfile`
  * `vision/yolo_model/` → carpeta montada como volumen con los pesos del modelo YOLO.

* `docker-compose.yml`
  Orquestación de todos los servicios.


---

## 🧱 Servicios definidos en `docker-compose.yml`

### 1. `db` – PostgreSQL 16

* Imagen: `postgres:16`
* Puerto expuesto: `5432:5432`
* Variables de entorno:

  * `POSTGRES_USER=buinzoo`
  * `POSTGRES_PASSWORD=buinzoo_password`
  * `POSTGRES_DB=buinzoo`
* Volumen de datos: `postgres_data:/var/lib/postgresql/data`
* Healthcheck con `pg_isready`.

### 2. `web` – Backend (FastAPI)

* `build.context: .`
* `build.dockerfile: back/Dockerfile`
* Contenedor: `zoo_backend`
* Puerto expuesto: `8000:8000`
* Variables de entorno:

  * `POSTGRES_HOST=db`
  * `POSTGRES_PORT=5432`
  * `POSTGRES_USER=buinzoo`
  * `POSTGRES_PASSWORD=buinzoo_password`
  * `POSTGRES_DB=buinzoo`
  * `SECRET_KEY=super_secret_dev_key_change_in_prod` 
* Depende de `db`.
* Conectado a la red `zoo_net`.

El backend expone, entre otros:

* API: `http://localhost:8000`
* Swagger: `http://localhost:8000/docs`

> En el startup del backend se crea automáticamente un usuario de pruebas:
>
> * **Usuario:** `vicente.florez@uc.cl`
> * **Contraseña:** `Vicente1234`
> * **Rol (scope):** `keeper`

### 3. `frontend` – Dashboard Web

* `build.context: ./front/my-app`
* `build.dockerfile: Dockerfile`
* `build.args`:

  * `VITE_API_BASE_URL: http://127.0.0.1:8000`
    (URL del backend que usará el frontend en build time)
* Contenedor: `zoo_frontend`
* Puerto expuesto: `80:80` → **dashboard en `http://localhost`**
* Depende de `web`.

### 4. `vision_caracal` – Pipeline de Visión

* `build.context: .`
* `build.dockerfile: vision/Dockerfile`
* Contenedor: `caracal_eyes`
* `deploy.resources.reservations.devices`:

  * Requiere **GPU NVIDIA** (`driver: nvidia`, `capabilities: [gpu]`).
* Variables de entorno:

  * `API_URL=http://web:8000/api/events` → endpoint del backend para ingesta de eventos.
  * `RTSP_LEFT=rtsp://...`
  * `RTSP_RIGHT=rtsp://...`

* Volúmenes:

  * `./vision/yolo_model:/app/yolo_model` → carpeta local con pesos del modelo.
* Depende de `web`.

### Redes y volúmenes

* Red: `zoo_net` (tipo `bridge`) – compartida por todos los servicios.
* Volumen: `postgres_data` – persiste la base de datos.

---

## ✅ Prerrequisitos

* [Docker](https://www.docker.com/) instalado.
* [Docker Compose](https://docs.docker.com/compose/) (en Docker Desktop ya viene).
* (CRITICO) **GPU NVIDIA** con drivers + runtime de Docker configurado para el servicio `vision_caracal`.

---

## 🚀 Cómo levantar todo con Docker Compose

1. Posicionarte en la raíz del proyecto (donde está `docker-compose.yml`):

   ```bash
   cd /ruta/a/tu/proyecto
   ```

2. (Opcional pero recomendado) revisar y ajustar el archivo `docker-compose.yml`:

   * Confirmar que las rutas de `build.context` y `dockerfile` existen:

     * `back/Dockerfile`
     * `front/my-app/Dockerfile`
     * `vision/Dockerfile`
   * Confirmar que existe la carpeta `vision/yolo_model` con los pesos de YOLO.

3. Construir las imágenes:

   ```bash
   docker compose build
   # o
   docker-compose build
   ```

4. Levantar los servicios:

   ```bash
   docker compose up -d
   # o
   docker-compose up -d
   ```

   Esto levantará:

   * `db` (Postgres)
   * `web` (backend FastAPI)
   * `frontend` (dashboard en Nginx/servidor web)
   * `vision_caracal` (si tienes GPU y las rutas correctas)

5. Ver los logs (opcional):

   ```bash
   docker compose logs -f
   # o
   docker-compose logs -f
   ```

---

## 🌐 Acceso a la aplicación

* **Dashboard (frontend)**
  👉 `http://127.0.0.1/`

* **API FastAPI**
  👉 `http://127.0.0.1:8000`

* **Swagger / documentación API**
  👉 `http://127.0.0.1:8000/docs`

---

## 🔐 Credenciales de ejemplo

En el boot del backend se seedéa un usuario de desarrollo:

* Usuario: `vicente.florez@uc.cl`
* Contraseña: `Vicente1234`

Puedes usarlo para iniciar sesión en el dashboard la primera vez.
Luego, desde la API o la base de datos, puedes crear más usuarios o cambiar la contraseña.

---

## 🧹 Apagar y limpiar

* Detener los contenedores (sin borrar datos):

  ```bash
  docker compose down
  # o
  docker-compose down
  ```

* Detener y borrar el volumen de la base de datos (⚠️ borra toda la BD):

  ```bash
  docker compose down -v
  # o
  docker-compose down -v
  ```

---

## 👩‍💻 Modo desarrollo (opcional, sin Docker completo)

Si en algún momento quieres trabajar “a mano”:

### Backend (FastAPI)

```bash
cd back
# crear y activar un entorno virtual, instalar requirements, etc.
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Solo asegúrate de que Postgres esté corriendo (puedes seguir usando el servicio `db` de Docker).

### Frontend (React + Vite)

```bash
cd front/my-app
npm install
npm run dev
# normalmente abre en http://localhost:5173
```

Y configura `VITE_API_BASE_URL` (en `.env` o en tu Dockerfile/env) apuntando al backend, por ejemplo:

```bash
VITE_API_BASE_URL=http://localhost:8000
```

---
