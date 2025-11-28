import { useMemo, useState, useCallback, useEffect, useRef } from "react";
import { useAuth } from "./AuthContext.jsx";
import "./styles.css";

/* =================================
   Ayudas de API
   ================================= */
const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const tz = "America/Santiago";
const todayISO = new Intl.DateTimeFormat("en-CA", { timeZone: tz }).format(
  new Date()
); // YYYY-MM-DD


// Add this near the top of App.jsx, after labelFromISO function

function downloadPDF(reportId) {
  // Opens the PDF download endpoint in a new tab
  // The browser automatically attaches the cookies for authentication
  window.open(`${API_BASE}/api/reports/${reportId}/pdf`, '_blank');
}

async function getJSON(path, params) {
  const url = new URL(API_BASE + path);
  if (params)
    Object.entries(params).forEach(
      ([k, v]) => v != null && url.searchParams.set(k, v)
    );

  let res = await fetch(url, { credentials: "include" });
  if (res.status === 401) {
    await fetch(API_BASE + "/auth/refresh", {
      method: "POST",
      credentials: "include",
    }).catch(() => {});
    res = await fetch(url, { credentials: "include" });
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function postJSON(path, body) {
  let res = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) {
    await fetch(API_BASE + "/auth/refresh", {
      method: "POST",
      credentials: "include",
    }).catch(() => {});
    res = await fetch(API_BASE + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: body ? JSON.stringify(body) : undefined,
    });
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function labelFromISO(dateISO) {
  if (!dateISO) return "";
  const [y, m, d] = dateISO.split("-").map(Number);
  const localDate = new Date(y, m - 1, d); // local midnight
  return localDate.toLocaleDateString("es-CL", {
    day: "2-digit",
    month: "short",
  });
}

/* =================================
   Iconos / Notificaciones
   ================================= */
function BellIcon({ filled }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      width="22"
      height="22"
      focusable="false"
    >
      <path
        d="M12 3a6 6 0 00-6 6v3.382l-.894 1.789A1 1 0 006 16h12a1 1 0 00.894-1.529L18 12.382V9a6 6 0 00-6-6z"
        fill={filled ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path
        d="M9 17a3 3 0 0 0 6 0"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function LogoutIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      width="22"
      height="22"
      focusable="false"
    >
      <path
        d="M10 17v1a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-6a2 2 0 0 0-2 2v1"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M15 12H3m0 0 3-3m-3 3 3 3"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function NotificationTray({
  open,
  onClose,
  notifications,
  onMarkAllRead,
  anchorRef,
  onAck,
  scope,
  onToggleScope,
}) {
  const trayRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => {
      if (trayRef.current?.contains(e.target)) return;
      if (anchorRef.current?.contains(e.target)) return;
      onClose();
    };
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose, anchorRef]);

  if (!open) return null;

  const items = notifications.filter((n) => n.unread);

  return (
    <div ref={trayRef} className="notif-tray" role="dialog" aria-label="Alertas">
      <div className="notif-header">
        <span>Alertas</span>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <button className="link-btn" onClick={onToggleScope}>
            {scope === "selected" ? "Ver todas" : "Ver solo este animal"}
          </button>
          <button className="link-btn" onClick={onMarkAllRead}>
            Marcar todo como leído
          </button>
        </div>
      </div>

      <div className="notif-list" role="list">
        {items.length === 0 ? (
          <div className="notif-empty">Sin alertas 🎉</div>
        ) : (
          items.map((n) => (
            <div
              key={n.id}
              className={`notif-item ${n.unread ? "unread" : ""}`}
              role="listitem"
              tabIndex={0}
            >
              <div className="notif-title">{n.title}</div>
              <div className="notif-body">{n.body}</div>
              <div className="notif-meta">
                {n.time}
                {scope === "all" && n.animal_id && (
                  <span className="notif-tag" style={{ marginLeft: 8 }}>
                    Animal: {n.animal_id}
                  </span>
                )}
              </div>
              {n.unread && (
                <div style={{ marginTop: 6 }}>
                  <button
                    className="secondary-btn"
                    onClick={() => onAck(String(n.id))}
                  >
                    Reconocer
                  </button>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      <div className="notif-footer">
        <button className="secondary-btn" onClick={onClose}>
          Cerrar
        </button>
      </div>
    </div>
  );
}

/* =================================
   Mapeo de comportamientos
   ================================= */
const BEHAVIORS = [
  "Foraging",
  "Resting",
  "Locomotion",
  "Social",
  "Play",
  "Stereotypy",
];
const BEHAVIOR_COLORS = {
  Foraging: "#60a5fa",
  Resting: "#94a3b8",
  Locomotion: "#34d399",
  Social: "#f59e0b",
  Play: "#a78bfa",
  Stereotypy: "#ef4444",
};
const colorForBehavior = (b) => BEHAVIOR_COLORS[b] || "#64748b";

/* =================================
   Hooks
   ================================= */
function useAnimals() {
  const [animals, setAnimals] = useState([]);
  useEffect(() => {
    getJSON("/api/animals").then(setAnimals).catch(console.error);
  }, []);
  return animals;
}

function useAlerts(animalIdOrNull) {
  const [notifications, setNotifications] = useState([]);
  const load = async () => {
    const params = animalIdOrNull ? { animal_id: animalIdOrNull } : undefined;
    const rows = await getJSON("/api/alerts", params);
    const mapped = rows.map((r) => ({
      id: String(r.alert_id),
      animal_id: r.animal_id ?? null,
      title: `${r.tipo} (${r.severidad})`,
      body: r.resumen || r.tipo,
      time: new Date(r.ts).toLocaleString(),
      unread: r.estado === "open",
    }));
    setNotifications(mapped);
  };
  useEffect(() => {
    load().catch(() => {});
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, [animalIdOrNull]);
  return { notifications, setNotifications, reload: load };
}

function useCurrentBehavior(animalId) {
  const [cur, setCur] = useState(null);
  useEffect(() => {
    if (!animalId) return;
    let stop = false;
    async function load() {
      try {
        const row = await getJSON("/api/behavior/current", {
          animal_id: animalId,
        });
        if (!stop) setCur(row);
      } catch (_) {}
    }
    load();
    const t = setInterval(load, 15000);
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, [animalId]);
  return cur;
}

function useBehaviorTimeline(animalId, dateISO) {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    if (!animalId) {
      setRows([]);
      return;
    }
    let stop = false;
    async function load() {
      try {
        const data = await getJSON("/api/behavior/timeline", {
          animal_id: animalId,
          date: dateISO,
        });
        if (!stop) setRows(data);
      } catch {
        if (!stop) setRows([]);
      }
    }
    load();
    let t = null;
    if (dateISO === todayISO) {
      t = setInterval(load, 15000);
    }
    return () => {
      stop = true;
      if (t) clearInterval(t);
    };
  }, [animalId, dateISO]);

  if (!rows.length) {
    const seed = (animalId || "seed")
      .split("")
      .reduce((a, c) => a + c.charCodeAt(0), 0);
    return Array.from({ length: 24 }, (_, h) => ({
      hour: h,
      behavior: BEHAVIORS[(seed + h) % BEHAVIORS.length],
    }));
  }
  return rows;
}

function useBehaviorDayDistribution(animalId, dateISO) {
  const [dist, setDist] = useState(null);
  useEffect(() => {
    if (!animalId) {
      setDist(null);
      return;
    }
    let stop = false;
    async function load() {
      try {
        const data = await getJSON("/api/behavior/day_distribution", {
          animal_id: animalId,
          date: dateISO,
        });
        if (!stop) setDist(data);
      } catch {
        if (!stop) setDist(null);
      }
    }
    load();
    let t = null;
    if (dateISO === todayISO) {
      t = setInterval(load, 15000);
    }
    return () => {
      stop = true;
      if (t) clearInterval(t);
    };
  }, [animalId, dateISO]);
  return dist;
}

function useDeviationHistory(animalId, baselinePctMap) {
  const [history, setHistory] = useState([]);
  
  // Create a stable string key for the baseline object to use in dependencies
  const baselineKey = JSON.stringify(baselinePctMap);

  useEffect(() => {
    if (!animalId) return;
    
    // Generar últimos 7 días
    const dates = Array.from({ length: 7 }, (_, i) => {
      const d = new Date();
      d.setDate(d.getDate() - (6 - i));
      return {
        iso: new Intl.DateTimeFormat("en-CA", { timeZone: tz }).format(d),
        label: d.toLocaleDateString("es-CL", { weekday: "short", day: "numeric" }),
      };
    });

    async function loadAll() {
      try {
        const promises = dates.map((d) =>
          getJSON("/api/behavior/day_distribution", {
            animal_id: animalId,
            date: d.iso,
          }).catch(() => null)
        );
        
        const results = await Promise.all(promises);
        
        const processed = dates.map((d, i) => {
          const dayData = results[i]?.behavior_percentages || {};
          const dayDeviation = {};
          BEHAVIORS.forEach((b) => {
            const actual = dayData[b] || 0;
            const base = baselinePctMap[b] || 0;
            dayDeviation[b] = actual - base;
          });
          return { date: d.label, values: dayDeviation };
        });
        
        setHistory(processed);
      } catch (e) {
        console.error("History load failed", e);
      }
    }
    
    loadAll();
    
    // Polling cada 15 segundos para mantener el "hoy" actualizado
    const t = setInterval(loadAll, 15000);
    
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [animalId, baselineKey]); // Use the stringified key to avoid loop

  return history;
}

/* =================================
   Gráfico % día (Mejorado con Legend Izquierda)
   ================================= */
function BehaviorPercentBarChart({
  data,
  baseline,
  height = 180,
  width = 480, // Reduced from 560 to accommodate side legend
  padding = 18,
}) {
  const maxPct = 100;
  const topBuffer = 25;
  const plotHeight = height - 2 * padding - topBuffer;

  const n = data.length || 1;
  const bw = (width - 2 * padding) / n;

  const sy = (v) => (height - padding) - (v / maxPct) * plotHeight;

  const baselineMap = useMemo(() => {
    if (!baseline) return {};
    const m = {};
    baseline.forEach((b) => (m[b.behavior] = b.pct));
    return m;
  }, [baseline]);

  const hasAnyBaseline =
    baseline && baseline.some((b) => typeof b.pct === "number" && b.pct > 0);

  return (
    <div style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 24, justifyContent: 'center' }}>
      
      {/* 1. Left Side Legend (Baselines) */}
      <div style={{ minWidth: 110 }}>
        <div style={{ 
          fontSize: '10px', 
          textTransform: 'uppercase', 
          color: '#64748b', 
          fontWeight: 'bold', 
          marginBottom: 12,
          letterSpacing: '0.05em'
        }}>
          Baseline (Meta)
        </div>
        
        <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', rowGap: 8, columnGap: 12 }}>
          {baseline && baseline.map((b) => (
            <div key={b.behavior} style={{ display: 'contents' }}>
              <div style={{ display: 'flex', alignItems: 'center', fontSize: '11px', color: '#94a3b8' }}>
                <span style={{ 
                  width: 6, 
                  height: 6, 
                  borderRadius: '50%', 
                  backgroundColor: colorForBehavior(b.behavior), 
                  marginRight: 8 
                }} />
                {b.behavior}
              </div>
              <div style={{ fontSize: '11px', fontWeight: '600', color: '#e2e8f0', textAlign: 'right' }}>
                {b.pct}%
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 2. The Chart */}
      <div>
        <svg className="plot" viewBox={`0 0 ${width} ${height}`} role="img" style={{ display: "block" }}>
          <rect x="0" y="0" width={width} height={height} className="plot-bg" />
          <g className="plot-axes">
            <line
              x1={padding} y1={height - padding}
              x2={width - padding} y2={height - padding}
            />
            <line x1={padding} y1={padding} x2={padding} y2={height - padding} />
          </g>
          {data.map((d, i) => {
            const x = padding + i * bw + 6;
            const y = sy(d.pct);
            const h = Math.max(1, height - padding - y);
            const w = Math.max(8, bw - 12);
            const basePct = baselineMap[d.behavior];
            const hasBaseline = typeof basePct === "number" && basePct > 0;
            const by = hasBaseline ? sy(basePct) : null;
            const isTall = h > 25;
            const textY = isTall ? y + 16 : y - 6;
            const textColor = isTall ? "#ffffff" : "#cbd5e1";
            const fontWeight = isTall ? "bold" : "normal";

            return (
              <g key={d.behavior}>
                <rect
                  x={x} y={y} width={w} height={h}
                  fill={colorForBehavior(d.behavior)}
                  rx="6"
                />
                {hasBaseline && (
                  <line
                    x1={x} x2={x + w} y1={by} y2={by}
                    stroke="rgba(255,255,255,0.7)"
                    strokeWidth="2" strokeDasharray="4 3"
                  />
                )}
                <text
                  x={x + w / 2} y={textY}
                  textAnchor="middle" fontSize="10"
                  fontWeight={fontWeight} fill={textColor}
                  style={{ pointerEvents: "none", textShadow: isTall ? "0px 1px 2px rgba(0,0,0,0.4)" : "none" }}
                >
                  {Math.round(d.pct)}%
                </text>
                <text
                  x={x + w / 2} y={height - padding + 12}
                  textAnchor="middle" fontSize="10" fill="#9aa3b2"
                >
                  {d.behavior}
                </text>
              </g>
            );
          })}
        </svg>
        
        {/* Simple legend below to explain dashed line */}
        {hasAnyBaseline && (
          <div className="ribbon-legend" style={{ marginTop: 8, justifyContent: 'flex-end', opacity: 0.7 }}>
            <div className="legend-item">
              <span
                className="legend-swatch"
                style={{ borderTop: "2px dashed #94a3b8", width: 24, marginRight: 6 }}
              />
              <span className="legend-label">Target en gráfico</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* =================================
   Gráfico Historial (Single Behavior)
   ================================= */
function BehaviorHistoryChart({
  data, // [{ date: "Lun 25", values: { Foraging: 10... } }]
  selectedBehavior,
  height = 240,
  width = 560,
  padding = 30,
}) {
  const [hoverIndex, setHoverIndex] = useState(null);

  if (!data || data.length === 0 || !selectedBehavior) return null;

  // Extraer valores solo del comportamiento seleccionado
  const values = data.map((d) => d.values[selectedBehavior] || 0);

  // Escala dinámica pero con un mínimo de +/- 5%
  const maxAbsData = Math.max(...values.map(Math.abs));
  const maxAbs = Math.max(5, maxAbsData * 1.2);

  const plotW = width - 2 * padding;
  const plotH = height - 2 * padding;

  const sx = (i) => padding + (i * plotW) / (data.length - 1);
  const sy = (v) => height - padding - ((v + maxAbs) / (2 * maxAbs)) * plotH;
  const zeroY = sy(0);

  const color = colorForBehavior(selectedBehavior);

  // Generate path points
  const points = data
    .map((d, i) => `${sx(i)},${sy(d.values[selectedBehavior] || 0)}`)
    .join(" ");

  // Generate Area path (for fill effect)
  const areaPoints = [
    `${sx(0)},${zeroY}`,
    points,
    `${sx(data.length - 1)},${zeroY}`,
  ].join(" ");

  return (
    <div style={{ position: "relative" }}>
      <svg
        className="plot"
        viewBox={`0 0 ${width} ${height}`}
        aria-label={`Tendencia de ${selectedBehavior}`}
      >
        <rect x="0" y="0" width={width} height={height} className="plot-bg" />

        {/* --- Grid & Axes --- */}
        <line
          x1={padding}
          y1={zeroY}
          x2={width - padding}
          y2={zeroY}
          stroke="#475569"
          strokeWidth="1"
        />
        <line
          x1={padding}
          y1={padding}
          x2={padding}
          y2={height - padding}
          stroke="#334155"
        />

        {/* Y Axis Labels */}
        <text
          x={padding - 6}
          y={padding + 4}
          fill="#64748b"
          fontSize="9"
          textAnchor="end"
        >
          +{Math.round(maxAbs)}%
        </text>
        <text
          x={padding - 6}
          y={height - padding}
          fill="#64748b"
          fontSize="9"
          textAnchor="end"
        >
          -{Math.round(maxAbs)}%
        </text>
        <text
          x={padding - 6}
          y={zeroY + 3}
          fill="#94a3b8"
          fontSize="9"
          textAnchor="end"
        >
          0%
        </text>

        {/* X Axis Labels */}
        {data.map((d, i) => (
          <text
            key={i}
            x={sx(i)}
            y={height - padding + 15}
            fill="#94a3b8"
            fontSize="10"
            textAnchor="middle"
          >
            {d.date}
          </text>
        ))}

        {/* --- Data Visualization --- */}

        {/* Area Gradient Fill */}
        <defs>
          <linearGradient
            id={`grad-${selectedBehavior}`}
            x1="0"
            y1="0"
            x2="0"
            y2="1"
          >
            <stop offset="0%" stopColor={color} stopOpacity="0.2" />
            <stop offset="100%" stopColor={color} stopOpacity="0.05" />
          </linearGradient>
        </defs>
        <polygon points={areaPoints} fill={`url(#grad-${selectedBehavior})`} />

        {/* The Line */}
        <polyline
          points={points}
          fill="none"
          stroke={color}
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* The Dots & Interaction */}
        {data.map((d, i) => {
          const val = d.values[selectedBehavior] || 0;
          const cx = sx(i);
          const cy = sy(val);
          const isHovered = hoverIndex === i;

          return (
            <g key={i}>
              <circle
                cx={cx}
                cy={cy}
                r={isHovered ? 6 : 4}
                fill="#1e293b"
                stroke={color}
                strokeWidth="2"
                style={{ transition: "r 0.2s" }}
              />
              {/* Invisible Hit Target */}
              <circle
                cx={cx}
                cy={cy}
                r={12}
                fill="transparent"
                onMouseEnter={() => setHoverIndex(i)}
                onMouseLeave={() => setHoverIndex(null)}
                onClick={() => setHoverIndex(i)}
                style={{ cursor: "pointer" }}
              />
              {/* Tooltip */}
              {isHovered && (
                <g
                  transform={`translate(${cx}, ${cy - 12})`}
                  style={{ pointerEvents: "none" }}
                >
                  <rect
                    x="-20"
                    y="-22"
                    width="40"
                    height="18"
                    rx="4"
                    fill="#0f172a"
                    stroke={color}
                    strokeWidth="1"
                  />
                  <text
                    x="0"
                    y="-10"
                    textAnchor="middle"
                    fill="#fff"
                    fontSize="10"
                    fontWeight="bold"
                    dominantBaseline="middle"
                  >
                    {val > 0 ? `+${Math.round(val)}%` : `${Math.round(val)}%`}
                  </text>
                </g>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/* =================================
   UI Helpers
   ================================= */
function BehaviorBadge({ behavior, confidence }) {
  if (!behavior)
    return (
      <div className="badge-pill" style={{ background: "#1e2430", color: "#cbd5e1" }}>
        —
      </div>
    );
  const bg = colorForBehavior(behavior);
  return (
    <div className="badge-pill" style={{ background: bg }}>
      {behavior}
      {Number.isFinite(confidence) ? ` · ${(confidence * 100).toFixed(0)}%` : ""}
    </div>
  );
}

function BehaviorRibbon({ timeline }) {
  const cols = timeline.length || 1;
  const gridStyle = { gridTemplateColumns: `repeat(${cols}, 1fr)` };
  return (
    <div>
      <div className="ribbon" style={gridStyle} aria-label="Comportamiento por hora">
        {timeline.map(({ hour, behavior }) => (
          <div
            key={hour}
            className="ribbon-cell"
            title={`Hora ${String(hour).padStart(2, "0")}:00 — ${behavior}`}
            style={{ background: colorForBehavior(behavior) }}
          />
        ))}
      </div>
      <div className="ribbon-labels" style={gridStyle}>
        {timeline.map(({ hour }) => (
          <div key={`t-${hour}`} className="ribbon-time">
            {String(hour).padStart(2, "0")}:00
          </div>
        ))}
      </div>
      <div className="ribbon-legend" style={{ marginTop: 8 }}>
        {BEHAVIORS.map((b) => (
          <div key={b} className="legend-item">
            <span
              className="legend-swatch"
              style={{ background: colorForBehavior(b) }}
            />
            <span className="legend-label">{b}</span>
          </div>
        ))}
      </div>
    </div>
  );
}



/* =================================
   Panel de Reportes (Default: Hoy)
   ================================= */
function ReportsPanel({ animalId }) {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(false);
  
  // CHANGE 1: Initialize with Today's date instead of ""
  // 'en-CA' is a trick to get YYYY-MM-DD format using the local timezone
  const [filterDate, setFilterDate] = useState(
    new Date().toLocaleDateString('en-CA')
  );

  // Load ALL history when animal changes
  useEffect(() => {
    if (!animalId) return;
    setLoading(true);
    getJSON("/api/reports", { animal_id: animalId })
      .then(setReports)
      .catch((err) => console.error("Error loading reports:", err))
      .finally(() => setLoading(false));
  }, [animalId]);

  // Filter logic
  const displayedReports = useMemo(() => {
    if (!filterDate) return reports;
    return reports.filter(r => r.period_start.startsWith(filterDate));
  }, [reports, filterDate]);

  if (!animalId) return null;

  return (
    <div className="plot-panel" style={{ marginTop: 16 }}>
      <div className="plot-header">
        <div>
          <div className="plot-title">Reportes de Bienestar</div>
          <div className="plot-subtitle">
            {filterDate 
              ? `Viendo reporte del ${new Date(filterDate).toLocaleDateString('es-CL', { timeZone: 'UTC' })}`
              : "Historial completo"}
          </div>
        </div>
        
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {/* Button to clear filter and show everything */}
          {filterDate ? (
             <button 
               onClick={() => setFilterDate("")}
               className="link-btn"
               style={{ fontSize: 11, color: '#94a3b8' }}
             >
               Ver historial completo
             </button>
          ) : (
             <span style={{ fontSize: 11, color: '#64748b' }}>Mostrando todo</span>
          )}

          <input 
            type="date"
            value={filterDate}
            max={new Date().toLocaleDateString('en-CA')}
            onChange={(e) => setFilterDate(e.target.value)}
            style={{
              background: '#1e293b',
              border: '1px solid #334155',
              color: '#cbd5e1',
              padding: '4px 8px',
              borderRadius: '6px',
              fontSize: '11px',
              fontFamily: 'inherit',
              colorScheme: 'dark',
              cursor: 'pointer'
            }}
          />
        </div>
      </div>

      <div className="p-4">
        {loading && reports.length === 0 ? (
          <div className="plot-subtitle">Cargando historial...</div>
        ) : displayedReports.length === 0 ? (
          <div className="plot-subtitle" style={{ textAlign: 'center', padding: 20 }}>
            {filterDate 
              ? `No existe un reporte generado para el ${filterDate}.` 
              : "No hay reportes disponibles."}
          </div>
        ) : (
          <div style={{ maxHeight: 200, overflowY: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, color: '#cbd5e1' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #334155', color: '#94a3b8', textAlign: 'left' }}>
                  <th style={{ padding: 8 }}>Fecha</th>
                  <th style={{ padding: 8 }}>Estado</th>
                  <th style={{ padding: 8, textAlign: 'right' }}>Documento</th>
                </tr>
              </thead>
              <tbody>
                {displayedReports.map(r => (
                  <tr key={r.id} style={{ borderBottom: '1px solid #1e293b' }}>
                    <td style={{ padding: 8 }}>
                      {new Date(r.period_start).toLocaleDateString('es-CL', { timeZone: 'UTC' })}
                    </td>
                    <td style={{ padding: 8 }}>
                      {r.alerts_count > 0 ? (
                        <span style={{ color: '#ef4444', fontWeight: 'bold' }}>{r.alerts_count} Alertas</span>
                      ) : (
                        <span style={{ color: '#34d399' }}>Normal</span>
                      )}
                    </td>
                    <td style={{ padding: 8, textAlign: 'right' }}>
                      <button
                        onClick={() => downloadPDF(r.id)}
                        className="link-btn"
                        style={{ color: '#60a5fa', fontWeight: 500 }}
                      >
                        Descargar PDF
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

/* =================================
   App Principal
   ================================= */
export default function App() {
  const { user, logout } = useAuth();
  const animals = useAnimals();
  const [selectedId, setSelectedId] = useState(null);
  
  const selected = useMemo(
    () => animals.find((a) => a.animal_id === selectedId),
    [animals, selectedId]
  );
  
  useEffect(() => {
    if (!selectedId && animals[0]) setSelectedId(animals[0].animal_id);
  }, [animals, selectedId]);

  // Alertas
  const [alertScope, setAlertScope] = useState("selected");
  const toggleScope = useCallback(() => {
    setAlertScope((s) => (s === "selected" ? "all" : "selected"));
  }, []);

  const {
    notifications,
    setNotifications,
    reload: reloadAlerts,
  } = useAlerts(alertScope === "selected" ? selectedId : null);

  const unreadCount = notifications.filter((n) => n.unread).length;
  const [trayOpen, setTrayOpen] = useState(false);
  const bellRef = useRef(null);

  const markAllRead = useCallback(async () => {
      // 1. Get IDs of visible unread items
      const ids = notifications.filter((n) => n.unread).map((n) => String(n.id));
      if (!ids.length) return;

      // 2. Optimistic Update (Clear UI immediately)
      setNotifications((prev) => prev.map((n) => ({ ...n, unread: false })));

      try {
        // 3. Send to Backend
        const res = await postJSON("/api/alerts/ack/bulk", { ids });
        console.log("Backend Ack Result:", res); // Check browser console for this!
      } catch (err) {
        console.error("Ack failed", err);
        // Optional: Revert optimistic update here if needed
      } finally {
        // 4. Force Reload from Server to ensure sync
        await reloadAlerts();
      }
    }, [notifications, setNotifications, reloadAlerts]);

  async function ackAlert(id) {
    try {
      const sid = String(id);
      setNotifications((prev) =>
        prev.map((n) =>
          String(n.id) === sid ? { ...n, unread: false } : n
        )
      );
      await postJSON(`/api/alerts/ack/${sid}`);
      await reloadAlerts();
    } catch (e) {
      console.error(e);
    }
  }

  // Sidebar Key Nav
  const listRef = useRef(null);
  const handleKeyDown = useCallback((e) => {
      const idx = Math.max(0, animals.findIndex((i) => i.animal_id === selectedId));
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
      }
    }, [animals, selectedId]
  );
  const scrollItemIntoView = (index) => {
    const el = listRef.current?.querySelector(`[data-index="${index}"]`);
    el?.scrollIntoView({ block: "nearest" });
  };

  // --- DATOS DEL DASHBOARD ---

  // 1. KPI
  const currentBehavior = useCurrentBehavior(selectedId);
  const todayTimeline = useBehaviorTimeline(selectedId, todayISO);

  // 2. Gráfico % Día (Bars)
  const [chartOffset, setChartOffset] = useState(0);
  const maxOffset = 6;
  const totalOffsets = maxOffset + 1;
  useEffect(() => setChartOffset(0), [selectedId]);

  const dateISOdaysAgo = (n) => {
    const d = new Date();
    d.setDate(d.getDate() - n);
    return new Intl.DateTimeFormat("en-CA", { timeZone: tz }).format(d);
  };
  const chartDateISO = useMemo(() => dateISOdaysAgo(chartOffset), [chartOffset]);
  const dayDistribution = useBehaviorDayDistribution(selectedId, chartDateISO);
  
  const chartPercents = useMemo(() => {
    if (!dayDistribution?.behavior_percentages) return BEHAVIORS.map((b) => ({ behavior: b, pct: 0 }));
    const bp = dayDistribution.behavior_percentages;
    return BEHAVIORS.map((b) => ({ behavior: b, pct: bp[b] || 0 }));
  }, [dayDistribution]);

  const baselinePercents = useMemo(() => {
    const baseMap = selected?.baseline_behavior_pct || {};
    return BEHAVIORS.map((b) => ({ behavior: b, pct: baseMap[b] ?? 0 }));
  }, [selected]);

  // 3. Gráfico Historial (Lines)
  // FIX: Stabilize baselineRaw to prevent infinite fetches in useDeviationHistory
  const baselineRaw = useMemo(() => selected?.baseline_behavior_pct || {}, [selected]);
  const historyData = useDeviationHistory(selectedId, baselineRaw);
  
  // Estado para el selector del gráfico de historial
  const [historyBehavior, setHistoryBehavior] = useState("Stereotypy"); // Default to critical behavior
  // Reset behavior when animal changes? Maybe not necessary, but safe.
  useEffect(() => setHistoryBehavior("Stereotypy"), [selectedId]);


  // Helpers UI
  const chartDateLabel = useMemo(() => labelFromISO(chartDateISO), [chartDateISO]);
  const goOlderDay = () => setChartOffset((o) => (o + 1) % totalOffsets);
  const goNewerDay = () => setChartOffset((o) => (o - 1 + totalOffsets) % totalOffsets);


  console.log("Current API BASE:", import.meta.env.VITE_API_BASE_URL || "Fallback used");

  return (
    <div className="layout">
      <aside className="sidebar" role="listbox" tabIndex={0} onKeyDown={handleKeyDown} ref={listRef}>
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

      <main className="detail">
        <header className="detail-header">
          <h1 className="detail-title">{selected?.nombre || "—"}</h1>
          <p className="detail-subtitle">{selected?.especie || ""}</p>
          <div className="header-actions">
            {user && (
              <span className="plot-subtitle" title={user?.username}>
                {user?.full_name || user?.username}
              </span>
            )}
            <button className="icon-btn notif-bell" onClick={() => setTrayOpen((v) => !v)} ref={bellRef}>
              <BellIcon filled={unreadCount > 0} />
              {unreadCount > 0 && <span className="badge">{unreadCount}</span>}
            </button>
            <button className="icon-btn logout-btn" onClick={logout}>
              <LogoutIcon />
            </button>
          </div>
        </header>

        <NotificationTray
          open={trayOpen}
          onClose={() => setTrayOpen(false)}
          notifications={notifications}
          onMarkAllRead={markAllRead}
          anchorRef={bellRef}
          onAck={ackAlert}
          scope={alertScope}
          onToggleScope={toggleScope}
        />

        <section className="detail-body">
          <div className="detail-cards">
            <div className="card">
              <div className="card-label">ID del animal</div>
              <div className="card-value">{selected?.animal_id || "—"}</div>
            </div>
            <div className="card">
              <div className="card-label">Comportamiento actual</div>
              <div className="card-value">
                <BehaviorBadge
                  behavior={currentBehavior?.behavior}
                  confidence={currentBehavior?.confidence}
                />
              </div>
            </div>
            <div className="card">
              <div className="card-label">Actualizado</div>
              <div className="card-value">
                {currentBehavior?.ts ? new Date(currentBehavior.ts).toLocaleTimeString() : "—"}
              </div>
            </div>
          </div>

          {/* Cinta (Hoy) */}
          <div className="plot-panel" style={{ marginTop: 16 }}>
            <div className="plot-header">
              <div>
                <div className="plot-title">Comportamiento de hoy</div>
                <div className="plot-subtitle">Dominante por hora</div>
              </div>
            </div>
            <div className="p-4">
              <BehaviorRibbon timeline={todayTimeline} />
            </div>
          </div>


          {/* Bar Chart (Day Distribution) */}
          <div className="plot-panel" style={{ marginTop: 16 }}>
            <div className="plot-header">
              <div>
                <div className="plot-title">% del día (Vs Baseline)</div>
                <div className="plot-subtitle">{chartOffset === 0 ? "Hoy" : `Día: ${chartDateLabel}`}</div>
              </div>
              <div className="plot-switch">
                <button className="arrow-btn" onClick={goOlderDay}>
                  <svg viewBox="0 0 24 24" width="18" height="18">
                    <path d="M15 19l-7-7 7-7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
                <div className="plot-switch-label">{chartDateLabel}</div>
                <button className="arrow-btn" onClick={goNewerDay}>
                  <svg viewBox="0 0 24 24" width="18" height="18">
                    <path d="M9 5l7 7-7 7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
              </div>
            </div>
            <div className="p-4">
              {selectedId ? (
                <BehaviorPercentBarChart
                  data={chartPercents}
                  baseline={baselinePercents}
                />
              ) : (
                <div className="plot-subtitle">Selecciona un animal...</div>
              )}
            </div>
          </div>

          {/* Line Chart (History Deviation) */}
          <div className="plot-panel" style={{ marginTop: 16 }}>
            <div className="plot-header">
              <div>
                <div className="plot-title">Historial de Desviación</div>
                <div className="plot-subtitle">Variación respecto al baseline (7 días)</div>
              </div>
              
              {/* SELECTOR DE COMPORTAMIENTO PARA EL CHART */}
              <div className="plot-actions" style={{ display: 'flex', gap: 6, flexWrap: 'wrap', maxWidth: '50%' }}>
                {BEHAVIORS.map(b => {
                   const isActive = historyBehavior === b;
                   const baseColor = colorForBehavior(b);
                   return (
                     <button
                       key={b}
                       onClick={() => setHistoryBehavior(b)}
                       style={{
                         background: isActive ? baseColor : 'transparent',
                         color: isActive ? '#fff' : '#94a3b8',
                         border: `1px solid ${isActive ? baseColor : '#334155'}`,
                         padding: '2px 8px',
                         borderRadius: '12px',
                         fontSize: '10px',
                         cursor: 'pointer',
                         transition: 'all 0.2s'
                       }}
                     >
                       {b}
                     </button>
                   )
                })}
              </div>
            </div>

            <div className="p-4">
              {selectedId && historyData.length > 0 ? (
                <BehaviorHistoryChart 
                  data={historyData} 
                  selectedBehavior={historyBehavior}
                />
              ) : (
                <div className="plot-subtitle">
                  {selectedId ? "Cargando historial..." : "Selecciona un animal..."}
                </div>
              )}
            </div>
          </div>

          {/* Reports History Panel */}
          <ReportsPanel animalId={selectedId} />

        </section>
      </main>
    </div>
  );
}