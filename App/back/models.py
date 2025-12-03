from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from database import Base


class User(Base):
    """
    Modelo de usuario del sistema.
    Almacena credenciales y metadatos básicos.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=False)
    scopes = Column(String, nullable=True)  # CSV de scopes/roles (ej: "keeper,admin")
    full_name = Column(String, nullable=True)


class WelfareReport(Base):
    """
    Reporte de bienestar animal (agregado diario u otro período).
    Contiene:
      - rango de tiempo (period_start, period_end)
      - conteo de alertas
      - detalles en formato JSON (behavior_hourly, alerts, etc.)
    """
    __tablename__ = "welfare_reports"

    id = Column(Integer, primary_key=True, index=True)

    animal_id = Column(String, index=True)
    period_type = Column(String, default="daily")

    period_start = Column(DateTime, index=True)
    period_end = Column(DateTime, index=True)

    alerts_count = Column(Integer, nullable=True)

    details_json = Column(Text, nullable=True)

    generated_at = Column(DateTime, default=datetime.utcnow)
    generated_by = Column(String, nullable=True)



from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from datetime import datetime

class BehaviorEvent(Base):
    """
    Evento de comportamiento (dato crudo de la IA).
    Cada fila representa:
      - un animal
      - un timestamp (ts)
      - un tipo de comportamiento detectado
      - la confianza del modelo
    """
    __tablename__ = "behavior_events"

    id = Column(Integer, primary_key=True, index=True)
    animal_id = Column(String, index=True)
    ts = Column(DateTime, index=True)           # En práctica debería ser timezone-aware
    behavior = Column(String, index=True)       # Ej: "Foraging", "Resting", ...
    confidence = Column(Float, nullable=True)


class Alert(Base):
    """
    Alerta persistente generada por la lógica de negocio.
    Guarda:
      - tipo de alerta (comportamiento_anormal, poca_alimentacion, etc.)
      - severidad (baja/media/alta)
      - resumen descriptivo
      - estado (open/closed)
    """
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(String, unique=True, index=True)  # Ej: "a-001-20250301-00"
    animal_id = Column(String, index=True)
    tipo = Column(String)
    severidad = Column(String)
    resumen = Column(String)
    estado = Column(String, default="open")             # "open" | "closed"
    ts = Column(DateTime, index=True)
    details_json = Column(Text, nullable=True)
