# schemas.py
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, EmailStr, Field


# ------ Auth / users ------
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: Optional[EmailStr] = None
    password: str = Field(min_length=6, max_length=128)
    full_name: Optional[str] = None
    scopes: Optional[List[str]] = []

class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    scopes: Optional[str] = None  # stored as CSV in the model

    class Config:
        from_attributes = True  # pydantic v2 (orm_mode replacement)

class LoginBody(BaseModel):
    username: str
    password: str

# ------ Zoo (examples) ------
class Animal(BaseModel):
    animal_id: str
    nombre: str
    especie: str
    baseline_behavior_pct: Optional[Dict[str, float]] = None



class WelfareReportBase(BaseModel):
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
    id: int
    animal_id: str
    period_type: str
    period_start: datetime
    period_end: datetime

    alerts_count: Optional[int] = None

    generated_at: datetime
    generated_by: Optional[str] = None

    # contents of details_json (alerts, behavior_hourly, etc.)
    details: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True  # pydantic v2

