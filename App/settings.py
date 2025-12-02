# settings.py
from pydantic import BaseSettings

class Settings(BaseSettings):
    # Sampling cadence for the vision pipeline (seconds)
    TS_SECONDS: int = 5

    # You can add more shared knobs here later:
    # API_URL: str = "http://127.0.0.1:8000"
    # TZ: str = "America/Santiago"

    class Config:
        env_file = ".env"   # optional, lets you override via a .env file

settings = Settings()
