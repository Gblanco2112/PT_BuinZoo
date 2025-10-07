# zoo_routes.py
from datetime import datetime
from typing import List, Optional, Set, Dict, Iterable
import random
import hashlib

from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel
from zoneinfo import ZoneInfo

import schemas
from auth_routes import get_current_user

router = APIRouter(tags=["zoo"])

TZ = ZoneInfo("America/Santiago")

# =========================
# In-memory ACK state (mock)
# =========================
# NOTE: Resets if the process restarts (fine for a mock).
_ACKED: Set[str] = set()

# Mock data
ANIMALS: List[schemas.Animal] = [
    schemas.Animal(animal_id="a-001", nombre="Fito", especie="Caracal"),
    schemas.Animal(animal_id="a-002", nombre="Milo", especie="Giraffa camelopardalis"),
    schemas.Animal(animal_id="a-003", nombre="Uma",  especie="Panthera tigris"),
]

BEHAVIORS = ["Foraging", "Resting", "Locomotion", "Social", "Play", "Stereotypy"]

class AckBulkBody(BaseModel):
    ids: List[str]

# ------------------ Helpers (alerts) ------------------

def _seed_from(animal_id: str) -> int:
    # Stable per-animal seed so mocks are deterministic
    return int(hashlib.sha256(animal_id.encode("utf-8")).hexdigest(), 16) % (2**31)

def _mock_alerts_for(animal_id: str) -> List[Dict]:
    """
    Deterministic, small set of alerts per animal.
    IDs are namespaced with animal_id to avoid collisions (e.g., a-001-al-101).
    Alerts ACKed in-memory are returned as 'closed'.
    """
    now = datetime.now(TZ).isoformat()
    rnd = random.Random(_seed_from(animal_id))

    candidates = [
        ("Stereotypy spike", "medium", "Movimiento repetitivo"),
        ("Low activity",     "low",    "Actividad por debajo del umbral"),
        ("Social change",    "low",    "Variación en interacciones"),
        ("Agitation",        "high",   "Patrón de estrés detectado"),
        ("Feeding anomaly",  "medium", "Anomalía en forrajeo"),
    ]

    k = rnd.randint(1, 3)              # 1–3 alerts per animal
    picked = rnd.sample(candidates, k) # unique picks

    alerts: List[Dict] = []
    for idx, (tipo, severidad, resumen) in enumerate(picked, start=1):
        alert_id = f"{animal_id}-al-{100+idx}"  # unique per animal
        estado = "open" if (rnd.random() > 0.4) else "closed"  # ~60% open
        if alert_id in _ACKED:
            estado = "closed"
        alerts.append({
            "alert_id": alert_id,
            "animal_id": animal_id,
            "tipo": tipo,
            "severidad": severidad,
            "estado": estado,
            "ts": now,
            "resumen": resumen,
        })
    return alerts

def _all_alerts() -> Iterable[Dict]:
    for a in ANIMALS:
        yield from _mock_alerts_for(a.animal_id)

# ------------------ Public API ------------------

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

    if req_date > now_local.date():  # future date -> no data
        return []

    hours = range(0, now_local.hour) if req_date == now_local.date() else range(0, 24)

    # deterministic mock per animal+date+hour
    base_seed = sum(ord(c) for c in (animal_id + req_date.isoformat()))
    rows = []
    for h in range(hours.start, hours.stop):
        random.seed(base_seed + h)
        rows.append({"hour": h, "behavior": random.choice(BEHAVIORS)})
    return rows

@router.get("/metrics")
def metrics(current = Depends(get_current_user)):
    # Compute current open alerts across all animals
    open_count = sum(1 for a in _all_alerts() if a["estado"] == "open")
    return {
        "uptime_days": 12,
        "alerts_open": open_count,
        "animals": len(ANIMALS),
    }

@router.get("/alerts")
def alerts(animal_id: Optional[str] = None, current = Depends(get_current_user)):
    """
    Returns alerts.
    - If `animal_id` is provided: only that animal’s alerts.
    - Otherwise: all animals’ alerts (flattened).
    Alerts acknowledged via /alerts/ack are returned as 'closed' (frontend filters unread).
    """
    data = _mock_alerts_for(animal_id) if animal_id else list(_all_alerts())

    # OPTION A: return all (open + closed) and let the frontend filter unread
    return data

    # OPTION B: only return open alerts (uncomment if you prefer server-side filtering)
    # return [a for a in data if a["estado"] == "open"]

@router.post("/alerts/ack/{alert_id}")
def ack_alert(alert_id: str, current = Depends(get_current_user)):
    """
    Acknowledge a single alert. 'alert_id' must be the full per-animal ID
    (e.g., 'a-001-al-101').
    """
    _ACKED.add(alert_id)
    return {"status": "ok", "alert_id": alert_id}

@router.post("/alerts/ack/bulk")
def ack_bulk(body: AckBulkBody, current = Depends(get_current_user)):
    """
    Acknowledge many alerts at once.
    """
    _ACKED.update(body.ids)
    return {"status": "ok", "acked_count": len(body.ids)}
