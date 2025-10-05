import { useMemo, useState, useCallback, useEffect, useRef } from "react";
import "./styles.css";

/* =================================
   Ayudas de API
   ================================= */
const API_BASE = "http://127.0.0.1:8000"; // ajusta si es necesario

async function getJSON(path, params) {
  const url = new URL(API_BASE + path);
  if (params) Object.entries(params).forEach(([k, v]) => v != null && url.searchParams.set(k, v));
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
async function postJSON(path, body) {
  const res = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/* =================================
   Iconos / Notificaciones
   ================================= */
function BellIcon({ filled }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" width="22" height="22" focusable="false">
      <path
        d="M12 3a6 6 0 00-6 6v3.382l-.894 1.789A1 1 0 006 16h12a1 1 0 00.894-1.529L18 12.382V9a6 6 0 00-6-6z"
        fill={filled ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path d="M9 17a3 3 0 006 0" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function NotificationTray({ open, onClose, notifications, onMarkAllRead, anchorRef, onAck }) {
  const trayRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => {
      if (trayRef.current?.contains(e.target)) return;
      if (anchorRef.current?.contains(e.target)) return;
      onClose();
    };
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose, anchorRef]);

  if (!open) return null;

  return (
    <div ref={trayRef} className="notif-tray" role="dialog" aria-label="Alertas">
      <div className="notif-header">
        <span>Alertas</span>
        <button className="link-btn" onClick={onMarkAllRead}>Marcar todo como leído</button>
      </div>
      <div className="notif-list" role="list">
        {notifications.length === 0 ? (
          <div className="notif-empty">Sin alertas 🎉</div>
        ) : notifications.map(n => (
          <div key={n.id} className={`notif-item ${n.unread ? "unread" : ""}`} role="listitem" tabIndex={0}>
            <div className="notif-title">{n.title}</div>
            <div className="notif-body">{n.body}</div>
            <div className="notif-meta">{n.time}</div>
            {n.unread && (
              <div style={{ marginTop: 6 }}>
                <button className="secondary-btn" onClick={() => onAck(n.id)}>Reconocer</button>
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="notif-footer">
        <button className="secondary-btn" onClick={onClose}>Cerrar</button>
      </div>
    </div>
  );
}

/* =================================
   Mapeo de comportamientos (nombres tal como llegan del backend)
   ================================= */
const BEHAVIORS = ["Foraging","Resting","Locomotion","Social","Play","Stereotypy"];
const BEHAVIOR_COLORS = {
  Foraging:   "#60a5fa",
  Resting:    "#94a3b8",
  Locomotion: "#34d399",
  Social:     "#f59e0b",
  Play:       "#a78bfa",
  Stereotypy: "#ef4444",
};
const colorForBehavior = (b) => BEHAVIOR_COLORS[b] || "#64748b";

/* =================================
   Hooks: animales, alertas, comportamiento
   ================================= */
function useAnimals() {
  const [animals, setAnimals] = useState([]);
  useEffect(() => { getJSON("/api/animals").then(setAnimals).catch(console.error); }, []);
  return animals;
}

function useAlerts(selectedAnimalId) {
  const [notifications, setNotifications] = useState([]);
  const load = async () => {
    const rows = await getJSON("/api/alerts", selectedAnimalId ? { animal_id: selectedAnimalId } : undefined);
    const mapped = rows.map(r => ({
      id: r.alert_id,
      title: `${r.tipo} (${r.severidad})`,
      body: r.resumen || r.tipo,
      time: new Date(r.ts).toLocaleString(),
      unread: r.estado === "open",
    }));
    setNotifications(mapped);
  };
  useEffect(() => {
    load().catch(()=>{});
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, [selectedAnimalId]);
  return { notifications, setNotifications, reload: load };
}

function useCurrentBehavior(animalId) {
  const [cur, setCur] = useState(null);
  useEffect(() => {
    if (!animalId) return;
    let stop = false;
    async function load() {
      try {
        const row = await getJSON("/api/behavior/current", { animal_id: animalId });
        if (!stop) setCur(row);
      } catch (_) {}
    }
    load();
    const t = setInterval(load, 15000); // sondeo
    return () => { stop = true; clearInterval(t); };
  }, [animalId]);
  return cur; // {behavior, confidence, ts}
}

function useBehaviorTimeline(animalId, dateISO) {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    if (!animalId) return;
    getJSON("/api/behavior/timeline", { animal_id: animalId, date: dateISO })
      .then(setRows)
      .catch(() => setRows([]));
  }, [animalId, dateISO]);
  // respaldo si el backend devuelve vacío
  if (!rows.length) {
    const seed = (animalId || "seed").split("").reduce((a,c)=>a+c.charCodeAt(0),0);
    return Array.from({length:24}, (_,h) => ({
      hour: h,
      behavior: BEHAVIORS[(seed + h) % BEHAVIORS.length]
    }));
  }
  return rows; // [{hour, behavior}]
}

/* =================================
   Agregación y gráfico de % del día
   ================================= */
function useBehaviorPercentages(timeline) {
  return useMemo(() => {
    if (!timeline?.length) return [];
    const total = timeline.length; // 24 horas en el mock
    const counts = {};
    for (const { behavior } of timeline) counts[behavior] = (counts[behavior] || 0) + 1;
    return BEHAVIORS.map(b => ({ behavior: b, pct: ((counts[b] || 0) / total) * 100 }));
  }, [timeline]);
}

function BehaviorPercentBarChart({ data, height = 180, width = 560, padding = 18 }) {
  const maxPct = 100;
  const n = data.length || 1;
  const bw = (width - 2 * padding) / n;
  const sy = (v) => {
    const h = height - 2 * padding;
    return height - padding - (v / maxPct) * h;
  };
  return (
    <svg className="plot" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Porcentaje de comportamientos hoy">
      <rect x="0" y="0" width={width} height={height} className="plot-bg" />
      <g className="plot-axes">
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} />
        <line x1={padding} y1={padding} x2={padding} y2={height - padding} />
      </g>
      {data.map((d, i) => {
        const x = padding + i * bw + 6;
        const y = sy(d.pct);
        const h = Math.max(1, height - padding - y);
        const w = Math.max(8, bw - 12);
        return (
          <g key={d.behavior}>
            <rect x={x} y={y} width={w} height={h} fill={colorForBehavior(d.behavior)} rx="6" />
            <text x={x + w / 2} y={y - 6} textAnchor="middle" fontSize="10" fill="#cbd5e1">
              {Math.round(d.pct)}%
            </text>
            <text x={x + w / 2} y={height - padding + 12} textAnchor="middle" fontSize="10" fill="#9aa3b2">
              {d.behavior}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/* =================================
   Ayudas para “últimos 10 días”
   ================================= */
function dateISOdaysAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

function useDominantBehaviorLastDays(animalId, days = 10) {
  const [rows, setRows] = useState([]); // [{date, behavior}]
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!animalId) return;
    setLoading(true);
    const dates = Array.from({ length: days }, (_, i) => dateISOdaysAgo(days - 1 - i));
    Promise.all(
      dates.map(date =>
        getJSON("/api/behavior/timeline", { animal_id: animalId, date })
          .then((hourly) => {
            const counts = {};
            for (const h of hourly || []) counts[h.behavior] = (counts[h.behavior] || 0) + 1;
            if (!hourly?.length) {
              const seed = (animalId + date).split("").reduce((a,c)=>a+c.charCodeAt(0),0);
              const b = BEHAVIORS[(seed) % BEHAVIORS.length];
              return { date, behavior: b };
            }
            const behavior = Object.entries(counts).sort((a,b) => b[1]-a[1])[0][0];
            return { date, behavior };
          })
          .catch(() => {
            const seed = (animalId + date).split("").reduce((a,c)=>a+c.charCodeAt(0),0);
            return { date, behavior: BEHAVIORS[(seed) % BEHAVIORS.length] };
          })
      )
    ).then(setRows).finally(() => setLoading(false));
  }, [animalId, days]);
  return { rows, loading };
}

function LastDaysDominantStrip({ data }) {
  // data: [{date, behavior}] en orden del más antiguo → más reciente
  const cols = data.length || 1;
  const gridStyle = { gridTemplateColumns: `repeat(${cols}, 1fr)` };

  const fmt = (iso) =>
    new Date(iso).toLocaleDateString("es-CL", { day: "2-digit", month: "short" }).replace(".", "");

  return (
    <div>
      {/* fila de bloques coloreados */}
      <div className="ribbon" style={gridStyle} aria-label="Comportamiento dominante por día (últimos 10)">
        {data.map(({ date, behavior }) => (
          <div
            key={date}
            className="ribbon-cell"
            title={`${date} — ${behavior}`}
            style={{ background: colorForBehavior(behavior), height: 36, borderRadius: 8 }}
            aria-label={`${date}, ${behavior}`}
          />
        ))}
      </div>

      {/* fila de etiquetas de fecha, alineadas 1:1 */}
      <div className="ribbon-labels" style={gridStyle} aria-hidden="true">
        {data.map(({ date }) => (
          <div key={`d-${date}`} className="ribbon-time" title={new Date(date).toLocaleDateString("es-CL")}>
            {fmt(date)}
          </div>
        ))}
      </div>

      {/* leyenda opcional */}
      <div className="ribbon-legend" style={{ marginTop: 8 }}>
        <div className="legend-item">
          <span className="legend-swatch" style={{ background:'#2b3240' }} />
          <span className="legend-label">Del más antiguo al más reciente</span>
        </div>
      </div>
    </div>
  );
}


/* =================================
   Componentes de UI: chapa + cinta
   ================================= */
function BehaviorBadge({ behavior, confidence }) {
  if (!behavior) return (
    <div className="badge-pill" style={{ background: "#1e2430", color: "#cbd5e1" }}>—</div>
  );
  const bg = colorForBehavior(behavior);
  return (
    <div className="badge-pill" style={{ background: bg }}>
      {behavior}{Number.isFinite(confidence) ? ` · ${(confidence*100).toFixed(0)}%` : ""}
    </div>
  );
}

function BehaviorRibbon({ timeline }) {
  const cols = timeline.length || 1;
  const gridStyle = { gridTemplateColumns: `repeat(${cols}, 1fr)` };

  return (
    <div>
      {/* fila de cuadrados */}
      <div className="ribbon" style={gridStyle} aria-label="Comportamiento por hora">
        {timeline.map(({ hour, behavior }) => (
          <div
            key={hour}
            className="ribbon-cell"
            title={`Hora ${String(hour).padStart(2,"0")}:00 — ${behavior}`}
            style={{ background: colorForBehavior(behavior) }}
            aria-label={`Hora ${hour}, ${behavior}`}
          />
        ))}
      </div>

      {/* fila de etiquetas de hora */}
      <div className="ribbon-labels" style={gridStyle} aria-hidden="true">
        {timeline.map(({ hour }) => (
          <div key={`t-${hour}`} className="ribbon-time">
            {String(hour).padStart(2,"0")}:00
          </div>
        ))}
      </div>

      {/* leyenda */}
      <div className="ribbon-legend" style={{ marginTop: 8 }}>
        {BEHAVIORS.map(b => (
          <div key={b} className="legend-item">
            <span className="legend-swatch" style={{ background: colorForBehavior(b) }} />
            <span className="legend-label">{b}</span>
          </div>
        ))}
      </div>
    </div>
  );
}



/* =================================
   App
   ================================= */
export default function App() {
  // Animales y selección
  const animals = useAnimals();
  const [selectedId, setSelectedId] = useState(null);
  const selected = useMemo(() => animals.find(a => a.animal_id === selectedId), [animals, selectedId]);
  useEffect(() => { if (!selectedId && animals[0]) setSelectedId(animals[0].animal_id); }, [animals, selectedId]);

  // Alertas
  const { notifications, setNotifications, reload: reloadAlerts } = useAlerts(selectedId);
  const unreadCount = notifications.filter(n => n.unread).length;
  const [trayOpen, setTrayOpen] = useState(false);
  const bellRef = useRef(null);
  const markAllRead = () => setNotifications(prev => prev.map(n => ({ ...n, unread: false })));
  async function ackAlert(id) { try { await postJSON(`/api/alerts/ack/${id}`); await reloadAlerts(); } catch (e) { console.error(e); } }

  // Navegación por teclado en la barra lateral
  const listRef = useRef(null);
  const handleKeyDown = useCallback((e) => {
    const idx = Math.max(0, animals.findIndex(i => i.animal_id === selectedId));
    if (e.key === "ArrowDown") {
      e.preventDefault();
      const next = Math.min(idx + 1, animals.length - 1);
      setSelectedId(animals[next]?.animal_id);
      scrollItemIntoView(next);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const prev = Math.max(idx - 1, 0);
      setSelectedId(animals[prev]?.animal_id);
      scrollItemIntoView(prev);
    } else if (e.key === "Home") {
      e.preventDefault(); if (animals[0]) { setSelectedId(animals[0].animal_id); scrollItemIntoView(0); }
    } else if (e.key === "End") {
      e.preventDefault(); if (animals.length) { setSelectedId(animals[animals.length - 1].animal_id); scrollItemIntoView(animals.length - 1); }
    }
  }, [animals, selectedId]);
  const scrollItemIntoView = (index) => {
    const el = listRef.current?.querySelector(`[data-index="${index}"]`);
    el?.scrollIntoView({ block: "nearest" });
  };
  useEffect(() => { listRef.current?.focus(); }, [animals.length]);

  // Datos de comportamiento
  const todayISO = new Date().toISOString().slice(0,10);
  const currentBehavior = useCurrentBehavior(selectedId);
  const timeline = useBehaviorTimeline(selectedId, todayISO);
  const behaviorPercents = useBehaviorPercentages(timeline);

  // Panel conmutado: Hoy % vs Últimos 10 días
  const [distViewIndex, setDistViewIndex] = useState(0); // 0=hoy %, 1=últimos 10
  const distViews = ["today_pct", "last10_dom"];
  const nextDistView = () => setDistViewIndex(i => (i + 1) % distViews.length);
  const prevDistView = () => setDistViewIndex(i => (i - 1 + distViews.length) % distViews.length);
  const { rows: last10, loading: last10Loading } = useDominantBehaviorLastDays(selectedId, 10);

  return (
    <div className="layout">
      {/* Barra lateral */}
      <aside
        className="sidebar"
        role="listbox"
        aria-label="Animales"
        aria-activedescendant={selectedId ? `animal-${selectedId}` : undefined}
        tabIndex={0}
        onKeyDown={handleKeyDown}
        ref={listRef}
      >
        {animals.map((a, idx) => {
          const isSelected = a.animal_id === selectedId;
          return (
            <button
              key={a.animal_id}
              id={`animal-${a.animal_id}`}
              data-index={idx}
              role="option"
              aria-selected={isSelected}
              className={`row ${isSelected ? "selected" : ""}`}
              onClick={() => setSelectedId(a.animal_id)}
            >
              <div className="row-title">{a.nombre}</div>
              <div className="row-subtitle">{a.especie}</div>
            </button>
          );
        })}
      </aside>

      {/* Detalle */}
      <main className="detail">
        <header className="detail-header">
          <h1 className="detail-title">{selected?.nombre || "—"}</h1>
          <p className="detail-subtitle">{selected?.especie || ""}</p>

          <button
            className="icon-btn notif-bell"
            aria-label={`Abrir alertas${unreadCount ? `, ${unreadCount} sin leer` : ""}`}
            aria-haspopup="dialog"
            aria-expanded={trayOpen}
            onClick={() => setTrayOpen(v => !v)}
            ref={bellRef}
            title="Alertas"
          >
            <BellIcon filled={unreadCount > 0} />
            {unreadCount > 0 && <span className="badge" aria-hidden="true">{unreadCount}</span>}
          </button>
        </header>

        <NotificationTray
          open={trayOpen}
          onClose={() => setTrayOpen(false)}
          notifications={notifications}
          onMarkAllRead={markAllRead}
          anchorRef={bellRef}
          onAck={ackAlert}
        />

        <section className="detail-body">
          {/* Tarjetas de información */}
          <div className="detail-cards">
            <div className="card">
              <div className="card-label">ID del animal</div>
              <div className="card-value">{selected?.animal_id || "—"}</div>
            </div>
            <div className="card">
              <div className="card-label">Comportamiento actual</div>
              <div className="card-value">
                <BehaviorBadge behavior={currentBehavior?.behavior} confidence={currentBehavior?.confidence} />
              </div>
            </div>
            <div className="card">
              <div className="card-label">Actualizado</div>
              <div className="card-value">
                {currentBehavior?.ts ? new Date(currentBehavior.ts).toLocaleTimeString() : "—"}
              </div>
            </div>
          </div>

          {/* Cinta diaria de comportamiento */}
          <div className="plot-panel" style={{ marginTop: 16 }}>
            <div className="plot-header">
              <div>
                <div className="plot-title">Comportamiento de hoy</div>
                <div className="plot-subtitle">Comportamiento dominante por hora</div>
              </div>
            </div>
            <div className="p-4">
              <BehaviorRibbon timeline={timeline} />
            </div>
          </div>

          {/* Panel conmutado: Hoy % vs Últimos 10 días */}
          <div className="plot-panel" style={{ marginTop: 16 }}>
            <div className="plot-header">
              <div>
                <div className="plot-title">
                  {distViewIndex === 0
                    ? "% del día en cada comportamiento (hoy)"
                    : "Comportamiento dominante (últimos 10 días)"}
                </div>
                <div className="plot-subtitle">
                  {distViewIndex === 0
                    ? "Basado en el comportamiento dominante por hora"
                    : "Un bloque coloreado por día — del más antiguo al más reciente"}
                </div>
              </div>

              <div className="plot-switch">
                <button className="arrow-btn" aria-label="Vista anterior" title="Anterior (←)" onClick={prevDistView}>
                  <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
                    <path d="M15 19l-7-7 7-7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
                <div className="plot-switch-label">
                  {distViewIndex === 0 ? "Hoy %" : "Últimos 10 días"}
                </div>
                <button className="arrow-btn" aria-label="Siguiente vista" title="Siguiente (→)" onClick={nextDistView}>
                  <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
                    <path d="M9 5l7 7-7 7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
              </div>
            </div>

            <div className="p-4">
              {distViewIndex === 0 ? (
                <BehaviorPercentBarChart data={behaviorPercents} />
              ) : (
                last10Loading ? <div className="plot-subtitle">Cargando…</div> : <LastDaysDominantStrip data={last10} />
              )}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
