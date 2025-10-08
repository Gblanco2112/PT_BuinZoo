# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import Base, engine
import models
from auth_routes import router as auth_router
from zoo_routes import router as zoo_router
import os
from database import SessionLocal
import models
from auth import hash_password


app = FastAPI(title="Zoo Behavior API", version="1.0.0")

@app.on_event("startup")
def seed_dev_user():
    db = SessionLocal()
    try:
        u = db.query(models.User).filter(models.User.username == "vicente.florez@uc.cl").first()
        if not u:
            u = models.User(
                username="vicente.florez@uc.cl",
                email="vicente.florez@uc.cl",
                hashed_password=hash_password("Vicente1234"),
                full_name="Keeper",
                scopes="keeper",
            )
            db.add(u); db.commit()
            print("[startup] Seeded keeper@zoo")
    finally:
        db.close()

# Create tables (SQLite dev)
Base.metadata.create_all(bind=engine)

# CORS (dev). In prod, restrict to your real frontend domain and keep allow_credentials=True
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "ok"}

# Routers
app.include_router(auth_router)
app.include_router(zoo_router, prefix="/api")
