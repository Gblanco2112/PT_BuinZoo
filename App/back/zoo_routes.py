# zoo_routes.py
from datetime import datetime, date, time, timedelta
from typing import List, Optional, Dict
import json

from fastapi import APIRouter, Query, Depends, HTTPException
from pydantic import BaseModel
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

import schemas
import models
from database import get_db
from auth_routes import get_current_user

router = APIRouter(tags=["zoo"])

TZ = ZoneInfo("America/Santiago")

# ------------------ Static animals & behaviors ------------------

BASELINE_BEHAVIOR_PCT = {
    "default": {
        "Foraging": 8,
        "Resting": 68.0,
        "Locomotion": 12.0,
        "Social": 1.0,
        "Play": 1.0,
        "Stereotypy": 10.0,
    },
}

ANIMALS: List[schemas.Animal] = [
    schemas.Animal(
        animal_id="a-001",
        nombre="Fito",
        especie="Caracal",
        baseline_behavior_pct=BASELINE_BEHAVIOR_PCT["default"],
    ),
    # etc...
]


# Must match the labels your frontend expects
BEHAVIORS = ["Foraging", "Resting", "Locomotion", "Social", "Play", "Stereotypy"]


class AckBulkBody(BaseModel):
    ids: List[str]


# ------------------ Public API: animals ------------------


@router.get("/animals", response_model=List[schemas.Animal])
def list_animals(current=Depends(get_current_user)):
    """
    Static list of animals used by the frontend and the synthetic generator.
    """
    return ANIMALS


# ------------------ Public API: behavior ------------------


@router.get("/behavior/current")
def behavior_current(
    animal_id: str = Query(...),
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """
    Current behavior for an animal.

    Reads the latest BehaviorEvent from the DB. This is exactly how the backend
    behaves whether the data comes from the synthetic script or a real pipeline.
    """
    ev = (
        db.query(models.BehaviorEvent)
        .filter(models.BehaviorEvent.animal_id == animal_id)
        .order_by(models.BehaviorEvent.ts.desc())
        .first()
    )

    if not ev:
        # Frontend already handles empty/error cases gracefully.
        raise HTTPException(status_code=404, detail="No behavior data for this animal")

    return {
        "animal_id": animal_id,
        "behavior": ev.behavior,
        "confidence": round(ev.confidence or 0.0, 2),
        "ts": ev.ts.isoformat(),
    }


@router.get("/behavior/timeline")
def behavior_timeline(
    animal_id: str,
    date: Optional[str] = None,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """
    For a given animal and date, return the dominant behavior per hour.

    For past days: returns up to 24 hours.
    For today: ONLY returns completed hours (each hour is finalized once the next
    hour starts), so the strip updates at most once per hour.
    """
    now_local = datetime.now(TZ)

    # If no date is given, assume "today" in zoo local time
    req_date = now_local.date() if not date else datetime.strptime(date, "%Y-%m-%d").date()

    # Future day -> no data
    if req_date > now_local.date():
        return []

    day_start = datetime.combine(req_date, time.min, tzinfo=TZ)
    day_end = day_start + timedelta(days=1)

    # For querying events:
    #  - Past days: full day
    #  - Today: up to "now" (we'll still only *use* completed hours)
    query_end = min(day_end, now_local) if req_date == now_local.date() else day_end

    events = (
        db.query(models.BehaviorEvent)
        .filter(
            models.BehaviorEvent.animal_id == animal_id,
            models.BehaviorEvent.ts >= day_start,
            models.BehaviorEvent.ts < query_end,
        )
        .all()
    )

    if not events:
        # Frontend has a deterministic fallback if this is empty
        return []

    # Bucket events per hour
    buckets: Dict[int, List[str]] = {}
    for ev in events:
        h = ev.ts.astimezone(TZ).hour
        buckets.setdefault(h, []).append(ev.behavior)

    # Decide up to which hour we expose data
    if req_date == now_local.date():
        # Only show COMPLETED hours for today
        # e.g. at 13:35 -> last_completed_hour = 12 (we show 0..12)
        last_completed_hour = now_local.hour - 1
        if last_completed_hour < 0:
            # Day just started, no completed hours yet
            return []
        end_hour = last_completed_hour + 1  # range() end is exclusive
    else:
        # Past days -> full 24h
        end_hour = 24

    rows = []
    for h in range(0, end_hour):
        if h not in buckets:
            continue
        behaviors = buckets[h]
        # Dominant behavior in that hour
        dominant = max(set(behaviors), key=behaviors.count)
        rows.append({"hour": h, "behavior": dominant})

    return rows


@router.get("/behavior/day_distribution")
def behavior_day_distribution(
    animal_id: str,
    date: Optional[str] = None,
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    """
    Distribución de comportamientos para un día específico,
    basada en *todos* los BehaviorEvent de ese día.

    Devuelve:
      {
        "animal_id": "...",
        "date": "YYYY-MM-DD",
        "total_events": N,
        "behavior_counts": { "Foraging": 12, ... },
        "behavior_percentages": { "Foraging": 25.0, ... }
      }
    """
    now_local = datetime.now(TZ)
    req_date = now_local.date() if not date else datetime.strptime(date, "%Y-%m-%d").date()

    # No datos en el futuro
    if req_date > now_local.date():
        return {
            "animal_id": animal_id,
            "date": req_date.isoformat(),
            "total_events": 0,
            "behavior_counts": {},
            "behavior_percentages": {b: 0.0 for b in BEHAVIORS},
        }

    day_start = datetime.combine(req_date, time.min, tzinfo=TZ)
    day_end = day_start + timedelta(days=1)
    if req_date == now_local.date():
        day_end = min(day_end, now_local)

    events = (
        db.query(models.BehaviorEvent)
        .filter(
            models.BehaviorEvent.animal_id == animal_id,
            models.BehaviorEvent.ts >= day_start,
            models.BehaviorEvent.ts < day_end,
        )
        .all()
    )

    behavior_counts: Dict[str, int] = {}
    for ev in events:
        behavior_counts[ev.behavior] = behavior_counts.get(ev.behavior, 0) + 1

    total = sum(behavior_counts.values())

    if total == 0:
        behavior_percentages = {b: 0.0 for b in BEHAVIORS}
    else:
        behavior_percentages = {
            b: (behavior_counts.get(b, 0) / total) * 100.0 for b in BEHAVIORS
        }

    return {
        "animal_id": animal_id,
        "date": req_date.isoformat(),
        "total_events": total,
        "behavior_counts": behavior_counts,
        "behavior_percentages": behavior_percentages,
    }



@router.get("/behavior/summary_last_days")
def behavior_summary_last_days(
    animal_id: str = Query(..., description="ID del animal"),
    days: int = Query(10, ge=1, le=365, description="Número de días hacia atrás"),
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """
    Resumen de comportamientos para los últimos N días (por defecto 10).

    Devuelve:
      - total_events
      - behavior_counts: { comportamiento: cantidad }
      - behavior_percentages: { comportamiento: porcentaje (0-100) }
    """
    now_local = datetime.now(TZ)
    # día más antiguo incluido (por ejemplo, si days=10: hoy-9)
    start_date = now_local.date() - timedelta(days=days - 1)
    start_dt = datetime.combine(start_date, time.min, tzinfo=TZ)
    end_dt = now_local  # hasta ahora mismo

    events = (
        db.query(models.BehaviorEvent)
        .filter(
            models.BehaviorEvent.animal_id == animal_id,
            models.BehaviorEvent.ts >= start_dt,
            models.BehaviorEvent.ts < end_dt,
        )
        .all()
    )

    if not events:
        # Sin datos: devolvemos estructura vacía
        return {
            "animal_id": animal_id,
            "days": days,
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "total_events": 0,
            "behavior_counts": {},
            "behavior_percentages": {},
        }

    behavior_counts: Dict[str, int] = {}
    for ev in events:
        behavior_counts[ev.behavior] = behavior_counts.get(ev.behavior, 0) + 1

    total = sum(behavior_counts.values())
    behavior_percentages = {
        b: (count / total) * 100.0 for b, count in behavior_counts.items()
    }

    return {
        "animal_id": animal_id,
        "days": days,
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
        "total_events": total,
        "behavior_counts": behavior_counts,
        "behavior_percentages": behavior_percentages,
    }


# ------------------ Public API: metrics & alerts ------------------


@router.get("/metrics")
def metrics(
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """
    Simple metrics used by the dashboard.
    Alerts are read from the Alert table (open = estado == 'open').
    """
    open_count = (
        db.query(models.Alert)
        .filter(models.Alert.estado == "open")
        .count()
    )
    return {
        "uptime_days": 12,  # still mock; you can make this real later
        "alerts_open": open_count,
        "animals": len(ANIMALS),
    }


@router.get("/alerts")
def list_alerts(
    animal_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """
    List alerts from the DB. Shape matches the previous mock-based alerts.
    """
    q = db.query(models.Alert)
    if animal_id:
        q = q.filter(models.Alert.animal_id == animal_id)

    rows = q.order_by(models.Alert.ts.desc()).all()
    return [
        {
            "alert_id": row.alert_id,
            "animal_id": row.animal_id,
            "tipo": row.tipo,
            "severidad": row.severidad,
            "resumen": row.resumen,
            "estado": row.estado,
            "ts": row.ts.isoformat(),
        }
        for row in rows
    ]


@router.post("/alerts/ack/{alert_id}")
def ack_one(
    alert_id: str,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """
    Acknowledge a single alert by setting estado='closed' in the DB.
    """
    alert = db.query(models.Alert).filter(models.Alert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.estado = "closed"
    db.commit()
    return {"status": "ok", "alert_id": alert_id}


@router.post("/alerts/ack/bulk")
def ack_bulk(
    body: AckBulkBody,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """
    Bulk acknowledge alerts, used by the frontend to clear all notifications.
    """
    if not body.ids:
        return {"status": "ok", "acked_count": 0}

    (
        db.query(models.Alert)
        .filter(models.Alert.alert_id.in_(body.ids))
        .update({"estado": "closed"}, synchronize_session=False)
    )
    db.commit()
    return {"status": "ok", "acked_count": len(body.ids)}


# ------------------ Welfare reports (backend-only generation) ------------------


def create_or_update_daily_report(
    db: Session,
    animal_id: str,
    report_date: date,
    generated_by: str = "system",
) -> models.WelfareReport:
    """
    Create or update a daily welfare report for one animal on a given date.
    Uses real alerts from the DB and stores behavior per hour in details_json.
    """
    # 1) Period for that day in local time
    period_start = datetime.combine(report_date, time.min, tzinfo=TZ)
    period_end = period_start + timedelta(days=1)

    # 2) Alerts for that animal and day, from the DB
    alert_rows = (
        db.query(models.Alert)
        .filter(
            models.Alert.animal_id == animal_id,
            models.Alert.ts >= period_start,
            models.Alert.ts < period_end,
        )
        .all()
    )

    alerts: List[Dict] = []
    for a in alert_rows:
        alerts.append(
            {
                "alert_id": a.alert_id,
                "animal_id": a.animal_id,
                "tipo": a.tipo,
                "severidad": a.severidad,
                "estado": a.estado,
                "ts": a.ts.isoformat() if a.ts else None,
                "resumen": a.resumen,
            }
        )

    open_alerts = [a for a in alert_rows if a.estado == "open"]
    alerts_count = len(open_alerts)

    # 3) Behavior events for that day, per hour
    events = (
        db.query(models.BehaviorEvent)
        .filter(
            models.BehaviorEvent.animal_id == animal_id,
            models.BehaviorEvent.ts >= period_start,
            models.BehaviorEvent.ts < period_end,
        )
        .all()
    )

    # bucket events per hour: {hour -> [behavior, ...]}
    hour_buckets: Dict[int, List[str]] = {h: [] for h in range(24)}
    for ev in events:
        h = ev.ts.astimezone(TZ).hour
        hour_buckets[h].append(ev.behavior)

    # build per-hour summary and simple daily counts
    behavior_hourly: List[Dict] = []
    total_counts: Dict[str, int] = {}

    for h in range(24):
        behaviors = hour_buckets[h]
        if not behaviors:
            behavior_hourly.append(
                {
                    "hour": h,
                    "total_events": 0,
                    "dominant": None,
                    "counts": {},
                }
            )
            continue

        counts_hour: Dict[str, int] = {}
        for b in behaviors:
            counts_hour[b] = counts_hour.get(b, 0) + 1
            total_counts[b] = total_counts.get(b, 0) + 1

        dominant = max(counts_hour, key=counts_hour.get)

        behavior_hourly.append(
            {
                "hour": h,
                "total_events": len(behaviors),
                "dominant": dominant,
                "counts": counts_hour,
            }
        )

    # 4) Build details_json payload
    details = {
        "alerts": alerts,
        "open_alerts_count": alerts_count,
        "behavior_hourly": behavior_hourly,
        "behavior_daily_counts": total_counts,
    }

    # 5) Insert or update report row
    existing = (
        db.query(models.WelfareReport)
        .filter(
            models.WelfareReport.animal_id == animal_id,
            models.WelfareReport.period_type == "daily",
            models.WelfareReport.period_start == period_start,
            models.WelfareReport.period_end == period_end,
        )
        .first()
    )

    if existing:
        report = existing
        report.alerts_count = alerts_count
        report.details_json = json.dumps(details)
        report.generated_by = generated_by
    else:
        report = models.WelfareReport(
            animal_id=animal_id,
            period_type="daily",
            period_start=period_start,
            period_end=period_end,
            alerts_count=alerts_count,
            details_json=json.dumps(details),
            generated_by=generated_by,
        )
        db.add(report)

    db.commit()
    db.refresh(report)
    return report


@router.get("/reports", response_model=List[schemas.WelfareReportResponse])
def list_reports(
    animal_id: Optional[str] = Query(
        None,
        description="Filtrar por ID de animal (opcional)",
    ),
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """
    Lista de reportes de bienestar (los últimos primero).
    Solo lectura para el frontend.
    """
    q = db.query(models.WelfareReport)
    if animal_id:
        q = q.filter(models.WelfareReport.animal_id == animal_id)

    q = q.order_by(models.WelfareReport.period_start.desc())
    reports = q.limit(50).all()

    results: List[schemas.WelfareReportResponse] = []
    for r in reports:
        details = json.loads(r.details_json) if r.details_json else None
        results.append(
            schemas.WelfareReportResponse(
                id=r.id,
                animal_id=r.animal_id,
                period_type=r.period_type,
                period_start=r.period_start,
                period_end=r.period_end,
                alerts_count=r.alerts_count,
                generated_at=r.generated_at,
                generated_by=r.generated_by,
                details=details,
            )
        )
    return results
