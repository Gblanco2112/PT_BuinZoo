from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=False)
    scopes = Column(String, nullable=True)
    full_name = Column(String, nullable=True)


class WelfareReport(Base):
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
    One row per model output: "at ts, this animal is doing BEHAVIOR with CONFIDENCE".
    This is what your real pipeline will write to.
    """
    __tablename__ = "behavior_events"

    id = Column(Integer, primary_key=True, index=True)
    animal_id = Column(String, index=True)
    ts = Column(DateTime, index=True)           # timezone-aware datetime in practice
    behavior = Column(String, index=True)       # e.g. "Foraging", "Resting", ...
    confidence = Column(Float, nullable=True)


class Alert(Base):
    """
    Persistent alerts, instead of random ones in memory.
    Your rule engine (or synthetic script) creates these.
    """
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(String, unique=True, index=True)  # e.g. "a-001-20250301-00"
    animal_id = Column(String, index=True)
    tipo = Column(String)
    severidad = Column(String)
    resumen = Column(String)
    estado = Column(String, default="open")             # "open" | "closed"
    ts = Column(DateTime, index=True)
    details_json = Column(Text, nullable=True)