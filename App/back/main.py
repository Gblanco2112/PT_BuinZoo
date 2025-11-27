# main.py
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import Base, engine, SessionLocal
import models
from auth_routes import router as auth_router
from zoo_routes import router as zoo_router, ANIMALS, TZ, create_or_update_daily_report
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



TZ = ZoneInfo("America/Santiago")  # if you don't already have this in main.py


async def generate_reports_for_today():
    """
    Generate/update today's daily report for every animal.
    Backend-only: no frontend involvement.
    """
    db = SessionLocal()
    try:
        today = datetime.now(TZ).date()
        for animal in ANIMALS:
            create_or_update_daily_report(
                db=db,
                animal_id=animal.animal_id,
                report_date=today,
                generated_by="system",
            )
    finally:
        db.close()


async def reports_background_loop():
    """
    Very simple scheduler: every hour, recompute today's reports.
    """
    while True:
        await generate_reports_for_today()
        # sleep for 1 hour; you can change to 24*3600 for once per day
        await asyncio.sleep(60 * 60)


@app.on_event("startup")
async def startup_event():
    # you probably already have seeding logic; keep that
    # and also start the background task:
    asyncio.create_task(reports_background_loop())
