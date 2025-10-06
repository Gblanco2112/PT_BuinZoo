# schemas.py
from typing import List, Optional
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
