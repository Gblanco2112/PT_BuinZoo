"""
generate_test_data.py  (history + streaming)

Simula un "pipeline en tiempo real" generando:
- BehaviorEvent (comportamiento en el tiempo)
- Alert (alertas ocasionales)

Comportamiento:
  1) (Opcional) Limpia tablas BehaviorEvent y Alert.
  2) Genera historial sintético para varios días previos (DAYS_HISTORY).
  3) Genera datos para HOY desde 00:00 hasta la última hora completa.
  4) Entra en un loop infinito y cada TS_SECONDS genera nuevos eventos
     con la hora actual.

Uso:
  - Asegúrate de que el backend (uvicorn) está corriendo.
  - En otra terminal, ejecuta:
        python generate_test_data.py
  - Detén la simulación con Ctrl+C.
"""

from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import random
import time as pytime  # para sleep

from database import SessionLocal
import models
from zoo_routes import ANIMALS, BEHAVIORS  # reutilizamos definiciones

TZ = ZoneInfo("America/Santiago")

# === Parámetros de simulación ===
TS_SECONDS = 5 * 60                 # periodo entre "ticks" en tiempo real
ALERT_PROB_PER_STEP = 0.03      # probabilidad de generar una alerta por animal y tick
DAYS_HISTORY = 3                # cantidad de días completos hacia atrás
BACKFILL_EVENTS_PER_HOUR = 2    # cuántos eventos por hora al backfillear


# -------------------------------------------------------------------
# Helpers de comportamiento / alertas
# -------------------------------------------------------------------

def pick_behavior_for_hour(hour: int) -> str:
  """
  Elige un comportamiento para una hora determinada del día,
  usando pesos distintos según franja horaria.
  """
  if 0 <= hour < 6:
      # noche: más descanso
      weights = {
          "Resting": 0.7,
          "Locomotion": 0.1,
          "Foraging": 0.1,
          "Play": 0.05,
          "Social": 0.05,
          "Stereotypy": 0.0,
      }
  elif 6 <= hour < 10:
      # mañana: alimentación + locomoción
      weights = {
          "Resting": 0.2,
          "Locomotion": 0.3,
          "Foraging": 0.4,
          "Play": 0.05,
          "Social": 0.05,
          "Stereotypy": 0.0,
      }
  elif 10 <= hour < 18:
      # día activo
      weights = {
          "Resting": 0.2,
          "Locomotion": 0.4,
          "Foraging": 0.2,
          "Play": 0.1,
          "Social": 0.1,
          "Stereotypy": 0.0,
      }
  elif 18 <= hour < 22:
      # tarde/noche: social + alimentación
      weights = {
          "Resting": 0.3,
          "Locomotion": 0.2,
          "Foraging": 0.3,
          "Play": 0.1,
          "Social": 0.1,
          "Stereotypy": 0.0,
      }
  else:
      # noche tardía: vuelve el descanso
      weights = {
          "Resting": 0.6,
          "Locomotion": 0.15,
          "Foraging": 0.1,
          "Play": 0.05,
          "Social": 0.1,
          "Stereotypy": 0.0,
      }

  probs = [weights.get(b, 0.01) for b in BEHAVIORS]
  total = sum(probs)
  probs = [p / total for p in probs]
  return random.choices(BEHAVIORS, weights=probs, k=1)[0]


def maybe_emit_alert(animal_id: str, ts: datetime, db):
  """
  Con una pequeña probabilidad, genera una alerta para este animal
  en el instante ts.
  """
  if random.random() >= ALERT_PROB_PER_STEP:
      return

  tipos = [
      "baja_actividad",
      "actividad_excesiva",
      "poca_alimentacion",
      "comportamiento_anormal",
  ]
  severidades = ["baja", "media", "alta"]

  tipo = random.choice(tipos)
  severidad = random.choice(severidades)

  resumen = {
      "baja_actividad": "Actividad menor a lo esperado para la especie.",
      "actividad_excesiva": "Actividad elevada por período prolongado.",
      "poca_alimentacion": "Pocos eventos de alimentación en la última jornada.",
      "comportamiento_anormal": "Patrones poco frecuentes detectados.",
  }[tipo]

  estado = "open" if random.random() < 0.6 else "closed"

  alert_id = f"{animal_id}-{ts.strftime('%Y%m%d-%H%M%S')}"

  alert = models.Alert(
      alert_id=alert_id,
      animal_id=animal_id,
      tipo=tipo,
      severidad=severidad,
      resumen=resumen,
      estado=estado,
      ts=ts,
  )
  db.add(alert)


def emit_events_for_timestamp(ts: datetime, db, emit_alerts: bool = True):
  """
  Genera un BehaviorEvent por animal para el instante ts.
  Opcionalmente también puede generar alertas.
  """
  hour = ts.hour
  for animal in ANIMALS:
      behavior = pick_behavior_for_hour(hour)
      confidence = round(random.uniform(0.6, 0.99), 2)

      ev = models.BehaviorEvent(
          animal_id=animal.animal_id,
          ts=ts,
          behavior=behavior,
          confidence=confidence,
      )
      db.add(ev)

      if emit_alerts:
          maybe_emit_alert(animal.animal_id, ts, db)


# -------------------------------------------------------------------
# Backfill de historial
# -------------------------------------------------------------------

def backfill_full_day(day: date, db):
  """
  Genera datos sintéticos para un día COMPLETO (00:00–23:59),
  espaciando BACKFILL_EVENTS_PER_HOUR eventos en cada hora.
  """
  day_start = datetime.combine(day, time.min, tzinfo=TZ)
  print(f"[backfill] Generando datos completos para {day}...")

  for h in range(24):
      for k in range(BACKFILL_EVENTS_PER_HOUR):
          minute = int(60 / BACKFILL_EVENTS_PER_HOUR * k)
          ts = day_start + timedelta(hours=h, minutes=minute)
          emit_events_for_timestamp(ts, db, emit_alerts=False)

  db.commit()
  print(f"[backfill] Día {day} listo.")


def backfill_today_until_last_hour(db):
  """
  Genera datos para HOY desde 00:00 hasta la ÚLTIMA HORA COMPLETA.
  Ejemplo: si ahora son las 10:34, se generan horas 00..09.
  Esto asegura que el timeline muestre datos hasta esa hora.
  """
  now_local = datetime.now(TZ)
  today = now_local.date()
  day_start = datetime.combine(today, time.min, tzinfo=TZ)

  current_hour = now_local.hour  # 10 si son las 10:34
  if current_hour == 0:
      print("[backfill] Aún no hay horas completas hoy, no se genera nada.")
      return

  print(
      f"[backfill] Generando datos para hoy ({today}) "
      f"desde 00:00 hasta la hora {current_hour - 1:02d}:00..."
  )

  for h in range(current_hour):
      for k in range(BACKFILL_EVENTS_PER_HOUR):
          minute = int(60 / BACKFILL_EVENTS_PER_HOUR * k)
          ts = day_start + timedelta(hours=h, minutes=minute)
          emit_events_for_timestamp(ts, db, emit_alerts=False)

  db.commit()
  print("[backfill] Hoy (hasta última hora completa) listo.")


# -------------------------------------------------------------------
# Loop de simulación en tiempo real
# -------------------------------------------------------------------

def step_once_realtime(db):
  """
  Un 'tick' de simulación en tiempo real:
  - genera un BehaviorEvent para cada animal en el instante actual
  - opcionalmente genera alguna alerta
  """
  now_local = datetime.now(TZ)
  emit_events_for_timestamp(now_local, db, emit_alerts=True)
  db.commit()
  print(f"[{now_local.isoformat()}] Generated events for {len(ANIMALS)} animals")


def main():
  random.seed()  # semilla distinta cada ejecución

  db = SessionLocal()
  try:
      # 1) (Opcional) limpiar tablas
      print("Clearing previous BehaviorEvent and Alert data...")
      db.query(models.BehaviorEvent).delete()
      db.query(models.Alert).delete()
      db.commit()

      # 2) Historial de días completos previos
      today = datetime.now(TZ).date()
      for i in range(1, DAYS_HISTORY + 1):
          day = today - timedelta(days=i)
          backfill_full_day(day, db)

      # 3) Backfill de hoy hasta la última hora completa
      backfill_today_until_last_hour(db)

      # 4) Loop en tiempo real
      print(f"\nStarting realtime simulator with Ts = {TS_SECONDS} seconds.")
      print("Press Ctrl+C to stop.\n")

      while True:
          step_once_realtime(db)
          pytime.sleep(TS_SECONDS)

  except KeyboardInterrupt:
      print("\nSimulation stopped by user.")
  finally:
      db.close()


if __name__ == "__main__":
  main()
