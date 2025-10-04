from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta, timezone
import random
import os

app = FastAPI(title="Mini Zoo Welfare API")

# --- CORS: allow your React dev server (adjust ports if needed) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite default
        "http://127.0.0.1:5173",
        "http://localhost:3000",  # CRA
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== Mock data models ==========
class Animal(BaseModel):
    animal_id: str
    nombre: str
    especie: str

class MetricPoint(BaseModel):
    ts: str
    valor: float

class Alert(BaseModel):
    alert_id: str
    ts: str
    animal_id: str
    tipo: str
    severidad: str
    resumen: str
    estado: str = "open"

# In-memory data
ANIMALS: List[Animal] = [
    Animal(animal_id="a-001", nombre="Fito", especie="Caracal"),
    Animal(animal_id="a-002", nombre="Milo", especie="Giraffa camelopardalis"),
    Animal(animal_id="a-003", nombre="Uma",  especie="Panthera tigris"),
]
ALERTS: List[Alert] = [
    Alert(alert_id="al-001", ts=datetime.now(timezone.utc).isoformat(),
          animal_id="a-001", tipo="stereotypy_spike", severidad="high",
          resumen="Pacing elevado 15m", estado="open")
]

# ========== Animals ==========
@app.get("/api/animals", response_model=List[Animal])
def list_animals():
    return ANIMALS

# ========== Metrics (mock activity_level 0..1) ==========
@app.get("/api/metrics", response_model=List[MetricPoint])
def get_metrics(animal_id: str, kpi: Optional[str] = None, minutes: int = 60):
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=minutes)
    random.seed(hash(animal_id + (kpi or "")) & 0xFFFFFFFF)
    base = random.uniform(0.35, 0.7)
    out: List[MetricPoint] = []
    for i in range(minutes + 1):
        t = start + timedelta(minutes=i)
        jitter = random.uniform(-0.1, 0.1)
        val = max(0.0, min(1.0, base + jitter))
        out.append(MetricPoint(ts=t.isoformat(), valor=val))
    return out

# ========== Alerts ==========
@app.get("/api/alerts", response_model=List[Alert])
def list_alerts(animal_id: Optional[str] = None, estado: Optional[str] = None):
    data = ALERTS
    if animal_id:
        data = [a for a in data if a.animal_id == animal_id]
    if estado:
        data = [a for a in data if a.estado == estado]
    return data

@app.post("/api/alerts/ack/{alert_id}")
def ack_alert(alert_id: str):
    for a in ALERTS:
        if a.alert_id == alert_id:
            a.estado = "ack"
            return {"ok": True, "alert": a}
    raise HTTPException(status_code=404, detail="Alert not found")

# ========== Behaviors (your endpoints) ==========
BEHAVIORS = ["Foraging", "Resting", "Locomotion", "Social", "Play", "Stereotypy"]

@app.get("/api/behavior/current")
def behavior_current(animal_id: str = Query(...)):
    b = random.choice(BEHAVIORS)
    return {
        "animal_id": animal_id,
        "behavior": b,
        "confidence": round(random.uniform(0.6, 0.97), 2),
        "ts": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/behavior/timeline")
def behavior_timeline(animal_id: str = Query(...), date: str = Query(None)):
    # dominant behavior per hour (mock)
    seed = sum(ord(c) for c in animal_id + (date or ""))
    random.seed(seed)
    rows = [{"hour": h, "behavior": random.choice(BEHAVIORS)} for h in range(24)]
    return rows
