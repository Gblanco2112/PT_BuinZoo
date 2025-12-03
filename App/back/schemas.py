from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, EmailStr, Field


# ------ Auth / usuarios ------
class UserCreate(BaseModel):
    """
    Esquema de entrada para registrar un nuevo usuario.
    """
    username: str = Field(min_length=3, max_length=64)
    email: Optional[EmailStr] = None
    password: str = Field(min_length=6, max_length=128)
    full_name: Optional[str] = None
    scopes: Optional[List[str]] = []


class UserResponse(BaseModel):
    """
    Representación pública de un usuario al responder al frontend.
    Nota: 'scopes' se almacena como CSV en el modelo ORM.
    """
    id: int
    username: str
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    scopes: Optional[str] = None  # almacenado como CSV en el modelo

    class Config:
        from_attributes = True  # pydantic v2 (reemplaza orm_mode)


class LoginBody(BaseModel):
    """
    Cuerpo del request de login.
    """
    username: str
    password: str


# ------ Zoo (modelos de dominio expuestos al frontend) ------
class Animal(BaseModel):
    """
    Esquema de un animal conocido por el sistema (catálogo estático).
    """
    animal_id: str
    nombre: str
    especie: str
    baseline_behavior_pct: Optional[Dict[str, float]] = None



class WelfareReportBase(BaseModel):
    """
    Base para reportes de bienestar (estructura interna de detalles).
    """
    animal_id: str
    period_type: str = "daily"
    period_start: datetime
    period_end: datetime

    welfare_score: Optional[float] = None
    rest_hours: Optional[float] = None
    feeding_events: Optional[int] = None
    social_interactions: Optional[int] = None
    alerts_count: Optional[int] = None

    details: Optional[Dict[str, Any]] = None


class WelfareReportResponse(BaseModel):
    """
    Respuesta de un reporte de bienestar lista para el frontend.
    Incluye metadatos del periodo y el bloque de 'details' ya parseado.
    """
    id: int
    animal_id: str
    period_type: str
    period_start: datetime
    period_end: datetime

    alerts_count: Optional[int] = None

    generated_at: datetime
    generated_by: Optional[str] = None

    # Contenido de details_json (alerts, behavior_hourly, etc.)
    details: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True  # pydantic v2
