# --- ANTES: from pydantic import BaseSettings ---
from pydantic_settings import BaseSettings  # <--- NUEVO IMPORT

class Settings(BaseSettings):
    # Sampling cadence for the vision pipeline (seconds)
    TS_SECONDS: int = 5

    class Config:
        env_file = ".env" 

settings = Settings()