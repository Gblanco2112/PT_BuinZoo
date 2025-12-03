import asyncio
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import Base, engine, SessionLocal
import models
from auth_routes import router as auth_router
from zoo_routes import (
    router as zoo_router,
    ANIMALS,
    TZ,  # timezone compartida con zoo_routes
    create_or_update_daily_report,
)
from auth import hash_password


app = FastAPI(title="Zoo Behavior API", version="1.0.0")


async def reports_background_loop():
  """
  Bucle en background muy simple:
  - Cada cierto intervalo (1 hora) recalcula los reportes diarios del día actual.
  - Se ejecuta mientras la app esté levantada.
  """
  while True:
    await generate_reports_for_today()
    # dormir 1 hora; se puede cambiar a 24*3600 para una vez al día
    await asyncio.sleep(60 * 60)


async def generate_reports_for_today():
  """
  Genera/actualiza el reporte diario de bienestar para cada animal del listado ANIMALS
  correspondiente a la fecha actual en la zona horaria del zoo.
  Solo backend: el frontend no participa en este flujo.
  """
  db = SessionLocal()
  try:
    today = datetime.now(TZ).date()
    for animal in ANIMALS:
      create_or_update_daily_report(
        db=db,
        animal_id=animal.animal_id,
        report_date=today,
        generated_by="system",
      )
  finally:
    db.close()


@app.on_event("startup")
async def on_startup():
  """
  Hook de inicio de la aplicación:
    - Crea todas las tablas del modelo en la base de datos (Postgres)
    - Inserta un usuario de desarrollo si no existe (semilla)
    - Lanza la tarea en background que genera reportes diarios de bienestar
  """
  # 1) Asegura que las tablas existen en la base de datos destino
  Base.metadata.create_all(bind=engine)

  # 2) Seed usuario de desarrollo (keeper)
  db = SessionLocal()
  try:
    u = (
      db.query(models.User)
      .filter(models.User.username == "vicente.florez@uc.cl")
      .first()
    )
    if not u:
      u = models.User(
        username="vicente.florez@uc.cl",
        email="vicente.florez@uc.cl",
        hashed_password=hash_password("Vicente1234"),
        full_name="Keeper",
        scopes="keeper",
      )
      db.add(u)
      db.commit()
      print("[startup] Seeded keeper@zoo")
  finally:
    db.close()

  # 3) Inicia tarea en background para reportes diarios
  asyncio.create_task(reports_background_loop())


# main.py

# Orígenes permitidos para CORS (frontend local y en Docker)
origins = [
    "http://localhost:5173",    # Local Dev (npm run dev)
    "http://127.0.0.1:5173",    # Local Dev IP
    "http://localhost",         # Frontend en Docker (puerto 80)
    "http://127.0.0.1",         # Frontend en Docker IP
    # Si accedes desde otro PC, agrega también esa IP:
    # "http://192.168.1.50",
]

# Middleware CORS para permitir llamadas desde el frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
  """
  Endpoint simple de healthcheck.
  Permite verificar que el backend está levantado.
  """
  return {"status": "ok"}


# Routers (se montan módulos de rutas)
app.include_router(auth_router)
app.include_router(zoo_router, prefix="/api")
