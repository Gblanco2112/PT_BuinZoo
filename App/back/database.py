# database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# --------------------------------------------------------------------
# Postgres connection settings
# --------------------------------------------------------------------
# Match the settings you used in `docker run`:
#   - POSTGRES_USER=buinzoo
#   - POSTGRES_PASSWORD=buinzoo_password
#   - POSTGRES_DB=buinzoo
#   - host: localhost, port: 5432
#
# You can override these with environment variables later if you want.
# --------------------------------------------------------------------
POSTGRES_USER = os.getenv("POSTGRES_USER", "buinzoo")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "buinzoo_password")
POSTGRES_DB = os.getenv("POSTGRES_DB", "buinzoo")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

SQLALCHEMY_DATABASE_URL = (
    f"postgresql+psycopg2://"
    f"{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

# Create the SQLAlchemy engine and session factory
engine = create_engine(SQLALCHEMY_DATABASE_URL, echo=False, future=True)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Base class for your ORM models
Base = declarative_base()


# Dependency for FastAPI: inject a DB session per request
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
