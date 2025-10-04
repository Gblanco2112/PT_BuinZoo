import { useMemo, useState, useCallback, useEffect, useRef } from "react";
import "./styles.css";

/* =================================
   API helpers
   ================================= */
// const API_BASE =
//   typeof window !== "undefined" && window.location.origin.includes(":")
//     ? window.location.origin
//     : "http://localhost:8000";

const API_BASE = "http://127.0.0.1:8000";


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
   Icons / Notifications
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
    <div ref={trayRef} className="notif-tray" role="dialog" aria-label="Alerts">
      <div className="notif-header">
        <span>Alerts</span>
        <button className="link-btn" onClick={onMarkAllRead}>Mark all read</button>
      </div>
      <div className="notif-list" role="list">
        {notifications.length === 0 ? (
          <div className="notif-empty">No alerts 🎉</div>
        ) : notifications.map(n => (
          <div key={n.id} className={`notif-item ${n.unread ? "unread" : ""}`} role="listitem" tabIndex={0}>
            <div className="notif-title">{n.title}</div>
            <div className="notif-body">{n.body}</div>
            <div className="notif-meta">{n.time}</div>
            {n.unread && (
              <div style={{ marginTop: 6 }}>
                <button className="secondary-btn" onClick={() => onAck(n.id)}>Ack</button>
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="notif-footer">
        <button className="secondary-btn" onClick={onClose}>Close</button>
      </div>
    </div>
  );
}

/* =================================
   Behavior mapping
   ================================= */
const BEHAVIORS = ["Foraging","Resting","Locomotion","Social","Play","Stereotypy"];
const BEHAVIOR_COLORS = {
  Foraging:   "#60a5fa", // blue
  Resting:    "#94a3b8", // slate
  Locomotion: "#34d399", // green
  Social:     "#f59e0b", // amber
  Play:       "#a78bfa", // violet
  Stereotypy: "#ef4444", // red
};
const colorForBehavior = (b) => BEHAVIOR_COLORS[b] || "#64748b";

/* =================================
   Hooks: animals, alerts, behavior
   ================================= */
function useAnimals() {
  const [animals, setAnimals] = useState([]);
  useEffect(() => {
    getJSON("/api/animals")
      .then(setAnimals)
      .catch((e) => console.error(e));
  }, []);
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
  return { notifications, reload: load };
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
    const t = setInterval(load, 15000); // poll
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
  // fallback if backend returns empty
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
   UI widgets
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
  return (
    <div>
      <div className="ribbon" aria-label="Behavior by hour">
        {timeline.map(({hour, behavior}) => (
          <div
            key={hour}
            className="ribbon-cell"
            title={`${String(hour).padStart(2,"0")}:00 — ${behavior}`}
            style={{ background: colorForBehavior(behavior) }}
            aria-label={`Hour ${hour}, ${behavior}`}
          />
        ))}
      </div>
      <div className="ribbon-legend">
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
   App (Zoo behaviors focus)
   ================================= */
export default function App() {
  // Animals & selection
  const animals = useAnimals();
  const [selectedId, setSelectedId] = useState(null);
  const selected = useMemo(() => animals.find(a => a.animal_id === selectedId), [animals, selectedId]);
  useEffect(() => {
    if (!selectedId && animals[0]) setSelectedId(animals[0].animal_id);
  }, [animals, selectedId]);

  // Alerts as notifications
  const { notifications, reload: reloadAlerts } = useAlerts(selectedId);
  const unreadCount = notifications.filter(n => n.unread).length;
  const [trayOpen, setTrayOpen] = useState(false);
  const bellRef = useRef(null);

  const markAllRead = () => {
    // local only; you can wire a backend endpoint if you want to persist
    // Here we just hide unread badges.
    notifications.forEach(n => n.unread = false);
    // force rerender
    reloadAlerts();
  };

  async function ackAlert(id) {
    try {
      await postJSON(`/api/alerts/ack/${id}`);
      await reloadAlerts();
    } catch (e) { console.error(e); }
  }

  // Sidebar keyboard navigation
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

  // Behavior data
  const todayISO = new Date().toISOString().slice(0,10);
  const currentBehavior = useCurrentBehavior(selectedId);
  const timeline = useBehaviorTimeline(selectedId, todayISO);

  return (
    <div className="layout">
      {/* Sidebar */}
      <aside
        className="sidebar"
        role="listbox"
        aria-label="Animals"
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

      {/* Details */}
      <main className="detail">
        <header className="detail-header">
          <h1 className="detail-title">{selected?.nombre || "—"}</h1>
          <p className="detail-subtitle">{selected?.especie || ""}</p>

          <button
            className="icon-btn notif-bell"
            aria-label={`Open notifications${unreadCount ? `, ${unreadCount} unread` : ""}`}
            aria-haspopup="dialog"
            aria-expanded={trayOpen}
            onClick={() => setTrayOpen(v => !v)}
            ref={bellRef}
            title="Alerts"
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
          {/* Info cards */}
          <div className="detail-cards">
            <div className="card">
              <div className="card-label">Animal ID</div>
              <div className="card-value">{selected?.animal_id || "—"}</div>
            </div>
            <div className="card">
              <div className="card-label">Current behavior</div>
              <div className="card-value">
                <BehaviorBadge behavior={currentBehavior?.behavior} confidence={currentBehavior?.confidence} />
              </div>
            </div>
            <div className="card">
              <div className="card-label">Updated</div>
              <div className="card-value">
                {currentBehavior?.ts ? new Date(currentBehavior.ts).toLocaleTimeString() : "—"}
              </div>
            </div>
          </div>

          {/* Daily behavior ribbon */}
          <div className="plot-panel" style={{ marginTop: 16 }}>
            <div className="plot-header">
              <div>
                <div className="plot-title">Behavior today</div>
                <div className="plot-subtitle">Dominant behavior per hour</div>
              </div>
            </div>
            <div className="p-4">
              <BehaviorRibbon timeline={timeline} />
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
