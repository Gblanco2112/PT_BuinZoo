import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# --------------------------------------------------------------------
# Configuración de conexión a Postgres
# --------------------------------------------------------------------
# Debe coincidir con los parámetros usados en `docker run`:
#   - POSTGRES_USER=buinzoo
#   - POSTGRES_PASSWORD=buinzoo_password
#   - POSTGRES_DB=buinzoo
#   - host: localhost, port: 5432
#
# Se puede sobrescribir usando variables de entorno.
# --------------------------------------------------------------------
POSTGRES_USER = os.getenv("POSTGRES_USER", "buinzoo")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "buinzoo_password")
POSTGRES_DB = os.getenv("POSTGRES_DB", "buinzoo")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

# URL de conexión SQLAlchemy a Postgres
SQLALCHEMY_DATABASE_URL = (
    f"postgresql+psycopg2://"
    f"{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

# Engine principal de SQLAlchemy (sin echo para no llenar logs)
engine = create_engine(SQLALCHEMY_DATABASE_URL, echo=False, future=True)

# Factoría de sesiones (una por request en FastAPI)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Clase base para los modelos ORM
Base = declarative_base()


# Dependency para FastAPI: inyecta una sesión de DB por request
def get_db():
    """
    Generador que entrega una sesión de base de datos y se asegura de cerrarla
    al finalizar el request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
