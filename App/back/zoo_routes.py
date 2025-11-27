# zoo_routes.py
from datetime import datetime, date, time, timedelta
from typing import List, Optional, Dict
import json

from fastapi import APIRouter, Query, Depends, HTTPException
from pydantic import BaseModel
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

from fastapi.responses import StreamingResponse
from fpdf import FPDF
import io

import schemas
import models
from database import get_db
from auth_routes import get_current_user

from datetime import timezone

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




# =========================================================
# PDF HELPER CLASS
# =========================================================
class WelfarePDF(FPDF):
    def header(self):
        # Logo or Title
        self.set_font('Helvetica', 'B', 16)
        self.cell(0, 10, 'Reporte Diario de Bienestar - Buin Zoo', border=False, align='C')
        self.ln(15)

    def chapter_title(self, label):
        self.set_font('Helvetica', 'B', 12)
        self.set_fill_color(200, 220, 255)  # Light blue
        self.cell(0, 10, label, border=0, fill=True, align='L')
        self.ln(10)

    def chapter_body(self, text):
        self.set_font('Helvetica', '', 10)
        self.multi_cell(0, 8, text)
        self.ln()


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
        "ts": ev.ts.replace(tzinfo=timezone.utc).isoformat(),
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




# =========================================================
# NEW ENDPOINT
# =========================================================
@router.get("/reports/{report_id}/pdf")
def download_report_pdf(
    report_id: int,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """
    Generates a PDF file for a specific welfare report and triggers a download.
    """
    # 1. Fetch the report
    report = db.query(models.WelfareReport).filter(models.WelfareReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # 2. Parse details
    data = json.loads(report.details_json) if report.details_json else {}
    alerts = data.get("alerts", [])
    behavior_counts = data.get("behavior_daily_counts", {})
    
    # Resolve Animal Name (using your ANIMALS constant list)
    animal_name = "Desconocido"
    species = "Desconocido"
    for a in ANIMALS:
        if a.animal_id == report.animal_id:
            animal_name = a.nombre
            species = a.especie
            break

    # 3. Create PDF
    pdf = WelfarePDF()
    pdf.add_page()

    # --- INFO SECTION ---
    pdf.set_font('Helvetica', '', 11)
    pdf.cell(0, 8, f"ID Reporte: #{report.id}   |   Generado el: {report.generated_at.strftime('%Y-%m-%d %H:%M')}", ln=True)
    pdf.cell(0, 8, f"Animal: {animal_name} ({species})", ln=True)
    pdf.cell(0, 8, f"Fecha del Reporte: {report.period_start.strftime('%Y-%m-%d')}", ln=True)
    pdf.ln(10)

    # --- SUMMARY SECTION ---
    pdf.chapter_title(f"Resumen General")
    total_events = sum(behavior_counts.values())
    alert_count = len(alerts)
    
    summary_text = (
        f"Durante este periodo se registraron un total de {total_events} eventos de comportamiento. "
        f"El sistema detectó {alert_count} alertas que requieren atención."
    )
    pdf.chapter_body(summary_text)

    # --- BEHAVIOR STATS ---
    pdf.chapter_title("Distribución de Comportamiento (Top Actividades)")
    if total_events > 0:
        pdf.set_font('Helvetica', 'B', 10)
        # Table Header
        pdf.cell(80, 8, "Comportamiento", border=1)
        pdf.cell(40, 8, "Eventos", border=1)
        pdf.cell(40, 8, "Porcentaje", border=1, ln=True)
        
        pdf.set_font('Helvetica', '', 10)
        # Sort behaviors by frequency
        sorted_behaviors = sorted(behavior_counts.items(), key=lambda item: item[1], reverse=True)
        
        for behavior, count in sorted_behaviors:
            pct = (count / total_events) * 100
            pdf.cell(80, 8, behavior, border=1)
            pdf.cell(40, 8, str(count), border=1)
            pdf.cell(40, 8, f"{pct:.1f}%", border=1, ln=True)
    else:
        pdf.chapter_body("No hay datos de comportamiento registrados para este día.")
    
    pdf.ln(10)

    # --- ALERTS SECTION ---
    pdf.chapter_title(f"Detalle de Alertas ({alert_count})")
    
    if alerts:
        # Table Header
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(40, 8, "Hora", border=1, fill=True)
        pdf.cell(40, 8, "Tipo", border=1, fill=True)
        pdf.cell(30, 8, "Severidad", border=1, fill=True)
        pdf.cell(80, 8, "Detalle", border=1, fill=True, ln=True)
        
        pdf.set_font('Helvetica', '', 8)
        for alert in alerts:
            # Parse timestamp if exists
            ts_str = alert.get("ts", "")
            time_str = "N/A"
            if ts_str:
                try:
                    # Simple slice to get HH:MM from ISO string
                    dt = datetime.fromisoformat(ts_str)
                    time_str = dt.strftime("%H:%M")
                except:
                    pass

            pdf.cell(40, 8, time_str, border=1)
            pdf.cell(40, 8, alert.get("tipo", "General"), border=1)
            
            # Color code severity slightly?
            severity = alert.get("severidad", "media")
            pdf.cell(30, 8, severity.upper(), border=1)
            
            # Truncate summary if too long for the cell
            summary = alert.get("resumen", "")[:50]
            pdf.cell(80, 8, summary, border=1, ln=True)
    else:
        pdf.chapter_body("No se detectaron alertas durante este periodo. El animal se encuentra estable.")

    # 4. Return as a stream
    pdf_bytes = pdf.output()
    buffer = io.BytesIO(pdf_bytes)
    
    filename = f"Reporte_{animal_name}_{report.period_start.strftime('%Y%m%d')}.pdf"
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )