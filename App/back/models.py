from sqlalchemy import Column, Integer, String
from database import Base


class User(Base):
    __tablename__ = "users"  # or whatever you currently use

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=False)
    scopes = Column(String, nullable=True)      # CSV: e.g. "keeper,vet"
    full_name = Column(String, nullable=True)   # <-- ADD THIS
