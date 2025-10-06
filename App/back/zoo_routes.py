# zoo_routes.py
from datetime import datetime
from typing import List, Optional
import random

from fastapi import APIRouter, Query, Depends
from zoneinfo import ZoneInfo

import schemas
from auth_routes import get_current_user

router = APIRouter(tags=["zoo"])

TZ = ZoneInfo("America/Santiago")

# Mock data
ANIMALS: List[schemas.Animal] = [
    schemas.Animal(animal_id="a-001", nombre="Fito", especie="Caracal"),
    schemas.Animal(animal_id="a-002", nombre="Milo", especie="Giraffa camelopardalis"),
    schemas.Animal(animal_id="a-003", nombre="Uma",  especie="Panthera tigris"),
]

BEHAVIORS = ["Foraging", "Resting", "Locomotion", "Social", "Play", "Stereotypy"]

@router.get("/animals", response_model=List[schemas.Animal])
def list_animals(current = Depends(get_current_user)):
    return ANIMALS

@router.get("/behavior/current")
def behavior_current(
    animal_id: str = Query(...),
    current = Depends(get_current_user),
):
    b = random.choice(BEHAVIORS)
    return {
        "animal_id": animal_id,
        "behavior": b,
        "confidence": round(random.uniform(0.6, 0.97), 2),
        "ts": datetime.now(TZ).isoformat()
    }

@router.get("/behavior/timeline")
def behavior_timeline(
    animal_id: str = Query(...),
    date: Optional[str] = Query(None, description="YYYY-MM-DD (local)"),
    current = Depends(get_current_user),
):
    now_local = datetime.now(TZ)
    req_date = now_local.date() if not date else datetime.strptime(date, "%Y-%m-%d").date()

    # future date -> no data
    if req_date > now_local.date():
        return []

    # hours to output
    if req_date == now_local.date():
        hours = range(0, now_local.hour)  # include current hour
    else:
        hours = range(0, 24)                  # full day for past dates

    # deterministic mock per animal+date+hour
    base_seed = sum(ord(c) for c in (animal_id + req_date.isoformat()))
    rows = []
    for h in hours:
        random.seed(base_seed + h)
        rows.append({"hour": h, "behavior": random.choice(BEHAVIORS)})
    return rows

@router.get("/metrics")
def metrics(current = Depends(get_current_user)):
    # example KPI mock
    return {
        "uptime_days": 12,
        "alerts_open": 2,
        "animals": len(ANIMALS),
    }

@router.get("/alerts")
def alerts(animal_id: Optional[str] = None, current = Depends(get_current_user)):
    now = datetime.now(TZ).isoformat()
    data = [
        {"alert_id": "al-101", "tipo": "Stereotypy spike", "severidad": "medium", "estado": "open", "ts": now, "resumen": "Movimiento repetitivo"},
        {"alert_id": "al-102", "tipo": "Low activity",      "severidad": "low",    "estado": "closed", "ts": now, "resumen": "Actividad por debajo del umbral"},
    ]
    if animal_id:
        # in a real system, filter by animal_id
        pass
    return data
