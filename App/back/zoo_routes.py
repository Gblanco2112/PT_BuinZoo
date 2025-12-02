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
TS = 300  

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
    ts: int = TS,  # NEW
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    """
    Distribución de comportamientos para un día específico.

    Devuelve:
      {
        "animal_id": "...",
        "date": "YYYY-MM-DD",
        "total_events": N,
        "behavior_counts": { "Foraging": 12, ... },
        "behavior_percentages": { "Foraging": 25.0, ... },                   # OBSERVADO
        "baseline_samples_per_day": float,                                   # NUEVO
        "behavior_percentages_vs_baseline": { "Foraging": 1.2, ... }         # NUEVO (sobre día completo)
      }
    """
    now_local = datetime.now(TZ)
    req_date = now_local.date() if not date else datetime.strptime(date, "%Y-%m-%d").date()

    # Rango del día en zona local
    day_start = datetime.combine(req_date, time.min, tzinfo=TZ)
    day_end = day_start + timedelta(days=1)

    # Para 'hoy', cortamos en ahora; para fechas pasadas, día completo
    if req_date == now_local.date():
        day_end = min(day_end, now_local)

    # Leer eventos de ese día
    events = (
        db.query(models.BehaviorEvent)
        .filter(
            models.BehaviorEvent.animal_id == animal_id,
            models.BehaviorEvent.ts >= day_start,
            models.BehaviorEvent.ts < day_end,
        )
        .all()
    )

    # Conteos observados
    behavior_counts: Dict[str, int] = {}
    for ev in events:
        behavior_counts[ev.behavior] = behavior_counts.get(ev.behavior, 0) + 1

    total_observed = sum(behavior_counts.values())

    # % observado (lo que tenías antes; mantenemos el campo)
    if total_observed == 0:
        observed_percentages = {b: 0.0 for b in BEHAVIORS}
    else:
        observed_percentages = {
            b: (behavior_counts.get(b, 0) / total_observed) * 100.0 for b in BEHAVIORS
        }

    # -------- NUEVO: % Vs Baseline del día completo ----------
    per_hour = 3600.0 / ts                 # muestras/​hora (puede ser float)
    baseline_day = 24.0 * per_hour         # muestras teóricas en 24h

    if baseline_day <= 0:
        vs_baseline = {b: 0.0 for b in BEHAVIORS}
    else:
        vs_baseline = {
            b: (behavior_counts.get(b, 0) / baseline_day) * 100.0 for b in BEHAVIORS
        }

    return {
        "animal_id": animal_id,
        "date": req_date.isoformat(),
        "total_events": total_observed,
        "behavior_counts": behavior_counts,
        "behavior_percentages": observed_percentages,                 # (observado)
        "baseline_samples_per_day": baseline_day,                     # (info)
        "behavior_percentages_vs_baseline": vs_baseline,              # (nuevo)
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


@router.post("/alerts/ack/bulk")
def ack_bulk(
    body: AckBulkBody,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """
    Bulk acknowledge alerts. Includes debug prints to verify ID matching.
    """
    if not body.ids:
        return {"status": "ok", "acked_count": 0}

    # Debug: Print what we received
    print(f"[ACK-BULK] Request to close {len(body.ids)} alerts.")
    
    # Perform the update
    updated_count = (
        db.query(models.Alert)
        .filter(models.Alert.alert_id.in_(body.ids))
        .update({"estado": "closed"}, synchronize_session=False)
    )
    
    db.commit()
    
    print(f"[ACK-BULK] Database updated {updated_count} rows.")
    
    return {"status": "ok", "acked_count": updated_count}


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
            "ts": row.ts.replace(tzinfo=timezone.utc).isoformat() if row.ts else None,
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
    Generates a PDF file with dynamic row heights for detailed alerts.
    """
    # 1. Fetch the report
    report = db.query(models.WelfareReport).filter(models.WelfareReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # 2. Parse details
    data = json.loads(report.details_json) if report.details_json else {}
    alerts = data.get("alerts", [])
    behavior_counts = data.get("behavior_daily_counts", {})
    
    # Resolve Animal Name
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
        sorted_behaviors = sorted(behavior_counts.items(), key=lambda item: item[1], reverse=True)
        
        for behavior, count in sorted_behaviors:
            pct = (count / total_events) * 100
            pdf.cell(80, 8, behavior, border=1)
            pdf.cell(40, 8, str(count), border=1)
            pdf.cell(40, 8, f"{pct:.1f}%", border=1, ln=True)
    else:
        pdf.chapter_body("No hay datos de comportamiento registrados para este día.")
    
    pdf.ln(10)

    # --- ALERTS SECTION (UPDATED FOR WRAPPING TEXT) ---
    pdf.chapter_title(f"Detalle de Alertas ({alert_count})")
    
    if alerts:
        # Define Column Widths (Total ~190mm)
        w_time = 25
        w_type = 50
        w_sev = 25
        w_desc = 90

        # Table Header
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(w_time, 8, "Hora", border=1, fill=True)
        pdf.cell(w_type, 8, "Tipo", border=1, fill=True)
        pdf.cell(w_sev, 8, "Severidad", border=1, fill=True)
        pdf.cell(w_desc, 8, "Detalle", border=1, fill=True, ln=True)
        
        pdf.set_font('Helvetica', '', 8) # Smaller font to fit more text
        
        for alert in alerts:
            # Parse timestamp
            ts_str = alert.get("ts", "")
            time_str = "N/A"
            if ts_str:
                try:
                    dt = datetime.fromisoformat(ts_str)
                    time_str = dt.strftime("%H:%M")
                except:
                    pass

            tipo = alert.get("tipo", "General")
            severity = alert.get("severidad", "media").upper()
            # NO TRUNCATION HERE: We take the full string
            summary = alert.get("resumen", "")

            # --- DYNAMIC ROW HEIGHT LOGIC ---
            # 1. Save current position
            x_start = pdf.get_x()
            y_start = pdf.get_y()

            # 2. Print the 'Detail' column using MultiCell first to see how tall it gets
            # We move the cursor to the right to print the last column
            pdf.set_xy(x_start + w_time + w_type + w_sev, y_start)
            pdf.multi_cell(w_desc, 8, summary, border=1, align='L')
            
            # 3. Calculate the height of the row based on where the cursor ended up
            y_end = pdf.get_y()
            row_height = y_end - y_start

            # 4. Go back and print the other columns with that calculated height
            pdf.set_xy(x_start, y_start)
            pdf.cell(w_time, row_height, time_str, border=1)
            pdf.cell(w_type, row_height, tipo, border=1)
            pdf.cell(w_sev, row_height, severity, border=1)

            # 5. Move cursor to the next line (y_end) for the next iteration
            pdf.set_xy(x_start, y_end)

            # Page break check (simple)
            if pdf.get_y() > 270: 
                pdf.add_page()

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



# =========================================================
# NEW: INTELLIGENT ALERT LOGIC
# =========================================================

def check_and_create_alerts(db: Session, animal_id: str, behavior: str, ts: datetime):
    """
    Calculates accumulated percentage based on TIME ELAPSED vs SAMPLING PERIOD.
    This ensures that if data is missing, it reflects in the stats.
    """
    
    # --- CONFIGURATION ---
    DEFAULT_TOLERANCE = 5.0
    SAMPLING_PERIOD_SECONDS = TS  # 5 Minutes (Must match your pipeline/simulation)
    MIN_HOURS_TO_ANALYZE = 1       # Don't alert in the first hour of the day

    # 1. Get Baseline
    baseline_map = BASELINE_BEHAVIOR_PCT["default"]
    baseline_val = baseline_map.get(behavior, 0.0)

    # 2. Calculate Theoretical Total Samples (Perfect Pipeline)
    # How many samples SHOULD we have received since midnight?
    today_midnight = datetime.combine(ts.date(), time.min, tzinfo=TZ)
    seconds_since_midnight = (ts - today_midnight).total_seconds()
    
    # Avoid division by zero at 00:00:00
    if seconds_since_midnight < (MIN_HOURS_TO_ANALYZE * 3600):
        return None

    theoretical_total_samples = seconds_since_midnight / SAMPLING_PERIOD_SECONDS

    # 3. Get Actual Count of Specific Behavior
    behavior_events_today = (
        db.query(models.BehaviorEvent)
        .filter(
            models.BehaviorEvent.animal_id == animal_id,
            models.BehaviorEvent.behavior == behavior,
            models.BehaviorEvent.ts >= today_midnight,
            models.BehaviorEvent.ts <= ts
        )
        .count()
    )

    # 4. Calculate Percentage against THEORETICAL Time
    # This represents: "What % of the elapsed time today was spent doing X?"
    current_pct = (behavior_events_today / theoretical_total_samples) * 100.0
    
    # Calculate Math Deviation
    deviation = current_pct - baseline_val
    dev_str = f"{deviation:+.1f}%"

    # 5. Analyze Deviation (With Logic Gates)
    alert_type = None
    severity = "media"
    resumen = ""
    
    hour = ts.hour

    # --- STEREOTYPY (Critical if high) ---
    if behavior == "Stereotypy":
        threshold = baseline_val + DEFAULT_TOLERANCE
        if current_pct > threshold:
            alert_type = "comportamiento_anormal"
            severity = "alta"
            resumen = (
                f"Estereotipia crítica ({current_pct:.1f}%). "
                f"Supera el baseline ({baseline_val}%) en {dev_str}."
            )

    # --- FORAGING (Critical if low) ---
    elif behavior == "Foraging":
        # Check only after 4 PM to allow time for feeding
        if hour >= 16:
            threshold = max(0, baseline_val - DEFAULT_TOLERANCE)
            if current_pct < threshold:
                alert_type = "poca_alimentacion"
                severity = "alta"
                resumen = (
                    f"Déficit alimentario. Acumulado: {current_pct:.1f}% "
                    f"(Meta: {baseline_val}%). Desviación: {dev_str}"
                )

    # --- RESTING (Check both High and Low) ---
    elif behavior == "Resting":
        upper_limit = baseline_val + 15.0
        lower_limit = max(0, baseline_val - 15.0)
        
        # Lethargy check (after noon)
        if current_pct > upper_limit and hour >= 12:
            alert_type = "baja_actividad"
            resumen = (
                f"Letargo/Inactividad. Descanso actual: {current_pct:.1f}% "
                f"(Normal: {baseline_val}%). Desviación: {dev_str}"
            )
        # Agitation check (after 10 AM)
        elif current_pct < lower_limit and hour >= 10:
            alert_type = "agitacion"
            resumen = (
                f"Falta de descanso. Actual: {current_pct:.1f}% "
                f"(Esperado: {baseline_val}%). Desviación: {dev_str}"
            )

    # --- LOCOMOTION (High is bad) ---
    elif behavior == "Locomotion":
        threshold = baseline_val + 10.0
        if current_pct > threshold:
            alert_type = "actividad_excesiva"
            resumen = f"Hiperactividad detectada ({current_pct:.1f}%). Desviación: {dev_str}"

    # --- SOCIAL (Low is bad) ---
    elif behavior == "Social" and baseline_val > 2.0:
        threshold = max(0, baseline_val - DEFAULT_TOLERANCE)
        if current_pct < threshold:
            alert_type = "aislamiento"
            resumen = f"Aislamiento social ({current_pct:.1f}% vs {baseline_val}%). Desviación: {dev_str}"

    # --- PLAY (Low is bad) ---
    elif behavior == "Play" and baseline_val > 2.0:
        threshold = max(0, baseline_val - DEFAULT_TOLERANCE)
        if current_pct < threshold:
            alert_type = "apatia"
            resumen = f"Apatía/Falta de juego ({current_pct:.1f}% vs {baseline_val}%). Desviación: {dev_str}"

    # 6. Save Alert (Anti-Spam)
    if alert_type:
        existing_alert = (
            db.query(models.Alert)
            .filter(
                models.Alert.animal_id == animal_id,
                models.Alert.tipo == alert_type,
                models.Alert.estado == "open",
                models.Alert.ts >= today_midnight
            )
            .first()
        )

        if existing_alert:
            return None 

        new_alert = models.Alert(
            alert_id=f"{animal_id}-{ts.strftime('%Y%m%d-%H%M%S')}",
            animal_id=animal_id,
            tipo=alert_type,
            severidad=severity,
            resumen=resumen,
            estado="open",
            ts=ts
        )
        db.add(new_alert)
        db.commit()
        return new_alert

    return None
# =========================================================
# NEW: INGESTION ENDPOINT (For the AI Pipeline)
# =========================================================

class EventIngest(BaseModel):
    animal_id: str
    behavior: str
    confidence: float
    ts: Optional[datetime] = None  # If null, use server time

@router.post("/events", status_code=201)
def ingest_event(
    body: EventIngest,
    db: Session = Depends(get_db),
    # Optional: Require auth so random people don't post fake data
    # current=Depends(get_current_user) 
):
    """
    This is where your Python AI Script sends data.
    JSON Body: { "animal_id": "a-001", "behavior": "Resting", "confidence": 0.95 }
    """
    # 1. Use provided timestamp or current server time
    event_ts = body.ts or datetime.now(TZ)
    
    # 2. Save the Raw Event
    event = models.BehaviorEvent(
        animal_id=body.animal_id,
        ts=event_ts,
        behavior=body.behavior,
        confidence=body.confidence
    )
    db.add(event)
    db.commit()

    # 3. Run the Intelligent Logic (The Brain)
    alert = check_and_create_alerts(db, body.animal_id, body.behavior, event_ts)

    return {
        "status": "stored", 
        "alert_generated": alert is not None,
        "alert_type": alert.tipo if alert else None
    }