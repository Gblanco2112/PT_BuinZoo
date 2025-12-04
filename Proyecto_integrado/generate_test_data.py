# generate_test_data.py
"""
generate_test_data.py  (history + reports + streaming + INTELLIGENT ALERTS)

Simula un "pipeline en tiempo real" generando:
- BehaviorEvent (comportamiento en el tiempo)
- Alert (generadas por el Backend usando lógica de negocio)
- WelfareReport (reportes diarios generados para los 7 días previos)

Comportamiento:
  1) Limpia tablas BehaviorEvent, Alert y WelfareReport.
  2) Genera historial sintético para 7 días previos.
  3) POR CADA DÍA PREVIO: Genera automáticamente el Reporte de Bienestar.
  4) Genera datos para HOY desde 00:00 hasta la última hora completa.
  5) Entra en un loop infinito para datos en tiempo real.
"""

from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import random
import time as pytime

from database import SessionLocal
import models
# IMPORTAMOS LA FUNCIÓN DE REPORTES Y LA DE ALERTAS INTELIGENTES
from zoo_routes import ANIMALS, BEHAVIORS, create_or_update_daily_report, check_and_create_alerts

from auth import hash_password # Make sure you have the dependencies installed locally

TZ = ZoneInfo("America/Santiago")

# === Parámetros de simulación ===
TS_SECONDS = 5 * 60             # periodo entre "ticks" en tiempo real
DAYS_HISTORY = 7                # 7 Días de historial
BACKFILL_EVENTS_PER_HOUR = 2    # cuántos eventos por hora al backfillear


def ensure_admin_user(db):
    """
    Crea un usuario administrador por defecto si no existe.
    Útil para entornos de desarrollo / pruebas.
    """
    user = db.query(models.User).filter(models.User.username == "vicente.florez@uc.cl").first()
    if not user:
        print("Creating Admin User...")
        user = models.User(
            username="vicente.florez@uc.cl",
            email="vicente.florez@uc.cl",
            hashed_password=hash_password("Vicente1234"),
            full_name="Keeper",
            scopes="keeper",
        )
        db.add(user)
        db.commit()
        print("Admin user created.")


# -------------------------------------------------------------------
# Helpers de comportamiento
# -------------------------------------------------------------------

def pick_behavior_for_hour(hour: int) -> str:
    """
    Selecciona un comportamiento probable según la hora del día.
    Se definen distribuciones de probabilidad (weights) para cada bloque horario.
    Además, se inyecta una pequeña probabilidad de 'Stereotypy' para testear alertas.
    """
    # Definición heurística de pesos por franja horaria
    if 0 <= hour < 6:
        weights = {"Resting": 0.7, "Locomotion": 0.1, "Foraging": 0.1, "Play": 0.05, "Social": 0.05, "Stereotypy": 0.0}
    elif 6 <= hour < 10:
        weights = {"Resting": 0.2, "Locomotion": 0.3, "Foraging": 0.4, "Play": 0.05, "Social": 0.05, "Stereotypy": 0.0}
    elif 10 <= hour < 18:
        weights = {"Resting": 0.2, "Locomotion": 0.4, "Foraging": 0.2, "Play": 0.1, "Social": 0.1, "Stereotypy": 0.0}
    elif 18 <= hour < 22:
        weights = {"Resting": 0.3, "Locomotion": 0.2, "Foraging": 0.3, "Play": 0.1, "Social": 0.1, "Stereotypy": 0.0}
    else:
        weights = {"Resting": 0.6, "Locomotion": 0.15, "Foraging": 0.1, "Play": 0.05, "Social": 0.1, "Stereotypy": 0.0}

    # Convertimos los pesos a un vector de probabilidades en el orden de BEHAVIORS
    probs = [weights.get(b, 0.01) for b in BEHAVIORS]
    total = sum(probs)
    probs = [p / total for p in probs]
    
    # PEQUEÑO TRUCO: Forzamos ocasionalmente comportamientos anómalos 
    # para probar que el sistema de alertas funciona.
    if random.random() < 0.02: # 2% chance de anomalía forzada
        return "Stereotypy"
        
    # Selección aleatoria según distribución de probabilidad
    return random.choices(BEHAVIORS, weights=probs, k=1)[0]


def emit_events_for_timestamp(ts: datetime, db, emit_alerts: bool = True):
    """
    Genera y almacena eventos de comportamiento para todos los animales
    en un timestamp específico. Opcionalmente dispara la lógica de alertas.
    
    ts: datetime que representa el instante de simulación.
    db: sesión de base de datos activa.
    emit_alerts: si es True, ejecuta check_and_create_alerts para cada evento.
    """
    hour = ts.hour
    for animal in ANIMALS:
        # 1. Seleccionar comportamiento según la hora
        behavior = pick_behavior_for_hour(hour)
        # 2. Simular un nivel de confianza (ruido entre 0.6 y 0.99)
        confidence = round(random.uniform(0.6, 0.99), 2)

        # 1. Crear Evento de comportamiento
        ev = models.BehaviorEvent(
            animal_id=animal.animal_id,
            ts=ts,
            behavior=behavior,
            confidence=confidence,
        )
        db.add(ev)
        
        # Guardar para que check_and_create_alerts pueda consultar el evento recién creado si fuera necesario
        # (Aunque en este caso pasamos los datos directamente)
        db.commit() 

        # 2. INTELIGENCIA: Llamar al Backend para verificar alertas
        # En vez de generar alertas random aquí, le preguntamos al backend si esto es una alerta.
        if emit_alerts:
            check_and_create_alerts(db, animal.animal_id, behavior, ts)


# -------------------------------------------------------------------
# Backfill de historial
# -------------------------------------------------------------------

def backfill_full_day(day: date, db):
    """
    Genera un día completo de eventos históricos (24h) para todos los animales.
    Incluye también la generación de alertas durante ese día.
    """
    day_start = datetime.combine(day, time.min, tzinfo=TZ)
    print(f"[backfill] Generando eventos crudos para {day}...")

    # Permitimos alertas en el historial para que los PDFs tengan contenido interesante
    for h in range(24):
        for k in range(BACKFILL_EVENTS_PER_HOUR):
            # Se distribuyen BACKFILL_EVENTS_PER_HOUR eventos por cada hora
            minute = int(60 / BACKFILL_EVENTS_PER_HOUR * k)
            ts = day_start + timedelta(hours=h, minutes=minute)
            emit_events_for_timestamp(ts, db, emit_alerts=True) # Alertas ACTIVADAS en historial

    db.commit()


def backfill_today_until_last_hour(db):
    """
    Genera eventos históricos para el día actual desde las 00:00
    hasta la última hora completa (excluye la hora parcial en curso).
    """
    now_local = datetime.now(TZ)
    today = now_local.date()
    day_start = datetime.combine(today, time.min, tzinfo=TZ)

    current_hour = now_local.hour
    if current_hour == 0:
        # Si aún es la primera hora del día, no hay nada que backfillear
        return

    print(f"[backfill] Generando datos parciales para HOY ({today}) hasta la hora {current_hour - 1}...")

    for h in range(current_hour):
        for k in range(BACKFILL_EVENTS_PER_HOUR):
            minute = int(60 / BACKFILL_EVENTS_PER_HOUR * k)
            ts = day_start + timedelta(hours=h, minutes=minute)
            emit_events_for_timestamp(ts, db, emit_alerts=True) # Alertas ACTIVADAS

    db.commit()


# -------------------------------------------------------------------
# Loop de simulación en tiempo real
# -------------------------------------------------------------------

def step_once_realtime(db):
    """
    Ejecuta un solo paso del simulador en tiempo real:
    - Genera eventos para la hora/minuto actual.
    - Dispara la lógica de alertas.
    - Hace commit de la transacción.
    """
    now_local = datetime.now(TZ)
    emit_events_for_timestamp(now_local, db, emit_alerts=True)
    db.commit()
    print(f"[{now_local.isoformat()}] Generated realtime events + checked alerts")


def main():
    """
    Punto de entrada principal de la simulación.
    
    Flujo:
      1) Limpia tablas BehaviorEvent, Alert, WelfareReport.
      2) Genera historial de DAYS_HISTORY días previos + sus reportes.
      3) Backfill de eventos del día actual hasta la última hora completa.
      4) Entra en un bucle infinito generando datos en tiempo real.
    """
    random.seed()

    db = SessionLocal()
    try:
        # 1) Limpiar tablas (INCLUYENDO REPORTES)
        print("Clearing DB: BehaviorEvent, Alert, WelfareReport...")
        db.query(models.BehaviorEvent).delete()
        db.query(models.Alert).delete()
        db.query(models.WelfareReport).delete()
        db.commit()

        # 2) Historial de días completos previos (Ahora son 7)
        today = datetime.now(TZ).date()
        for i in range(1, DAYS_HISTORY + 1):
            day = today - timedelta(days=i)
            
            # A. Generar Eventos crudos + Alertas Inteligentes
            backfill_full_day(day, db)
            
            # B. Generar REPORTE (PDF Data) para ese día
            print(f"[reports] Generando WelfareReport para {day}...")
            for animal in ANIMALS:
                create_or_update_daily_report(
                    db=db,
                    animal_id=animal.animal_id,
                    report_date=day,
                    generated_by="system_sim"
                )
            print(f"[reports] Reportes listos para {day}.")

        # 3) Backfill de hoy (hasta la última hora completa)
        backfill_today_until_last_hour(db)

        # 4) Loop en tiempo real
        print(f"\nStarting realtime simulator with Ts = {TS_SECONDS} seconds.")
        print("Press Ctrl+C to stop.\n")

        while True:
            step_once_realtime(db)
            # Pausa entre ticks de simulación en tiempo real
            pytime.sleep(TS_SECONDS)

    except KeyboardInterrupt:
        print("\nSimulation stopped by user.")
    finally:
        # Aseguramos cierre limpio de la sesión
        db.close()


if __name__ == "__main__":
    main()
