import { useMemo, useState, useCallback, useEffect, useRef } from "react";
import "./styles.css";

/* =================================
   Data
   ================================= */
const ITEMS = [
  { id: "1", title: "Alpha", subtitle: "First item", description: "Alpha is the first item in the list. It demonstrates how details show up here." },
  { id: "2", title: "Bravo", subtitle: "Second item", description: "Bravo expands on Alpha with more details and a longer description text." },
  { id: "3", title: "Charlie", subtitle: "Third item", description: "Charlie is here to prove scrolling works. Add as many items as you like." },
  { id: "4", title: "Delta", subtitle: "Fourth item", description: "Delta explains how selection styles update in the sidebar." },
  { id: "5", title: "Echo", subtitle: "Fifth item", description: "Echo is another placeholder item with some sample content." },
  // add more to see the scrollbar
  ...Array.from({ length: 20 }, (_, i) => ({
    id: String(i + 6),
    title: `Item ${i + 6}`,
    subtitle: "Generated",
    description: `Dynamically generated item #${i + 6}.`
  }))
];

/* =================================
   Notifications (ADD-ON)
   ================================= */
const INITIAL_NOTIFICATIONS = [
  { id: "n1", title: "Build complete", body: "Your deployment finished successfully.", time: "2m", unread: true },
  { id: "n2", title: "Comment", body: "Sam mentioned you in Alpha.", time: "12m", unread: true },
  { id: "n3", title: "Reminder", body: "Standup in 15 minutes.", time: "30m", unread: false },
  { id: "n4", title: "System", body: "New version available.", time: "1h", unread: false }
];

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

function NotificationTray({ open, onClose, notifications, onMarkAllRead, anchorRef }) {
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
    <div ref={trayRef} className="notif-tray" role="dialog" aria-label="Notifications">
      <div className="notif-header">
        <span>Notifications</span>
        <button className="link-btn" onClick={onMarkAllRead}>Mark all read</button>
      </div>
      <div className="notif-list" role="list">
        {notifications.length === 0 ? (
          <div className="notif-empty">You're all caught up 🎉</div>
        ) : notifications.map(n => (
          <div key={n.id} className={`notif-item ${n.unread ? "unread" : ""}`} role="listitem" tabIndex={0}>
            <div className="notif-title">{n.title}</div>
            <div className="notif-body">{n.body}</div>
            <div className="notif-meta">{n.time} ago</div>
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
   Tiny plotting utilities (no deps)
   ================================= */
const useSeededData = (seed, n = 24) => {
  // deterministic series per item id
  return useMemo(() => {
    let x = Number(seed);
    if (!Number.isFinite(x)) {
      x = String(seed).split("").reduce((a, c) => a + c.charCodeAt(0), 0);
    }
    const arr = [];
    for (let i = 0; i < n; i++) {
      x = (1103515245 * x + 12345) % 2 ** 31;
      const val = 40 + (x % 60); // 40..99
      arr.push({ x: i, y: val });
    }
    return arr;
  }, [seed, n]);
};

function LineChart({ data, width = 520, height = 160, padding = 18 }) {
  const xmin = 0, xmax = data.length - 1;
  const ymin = Math.min(...data.map(d => d.y));
  const ymax = Math.max(...data.map(d => d.y));
  const sx = (x) => padding + (x - xmin) * (width - 2 * padding) / (xmax - xmin || 1);
  const sy = (y) => height - padding - (y - ymin) * (height - 2 * padding) / (ymax - ymin || 1);
  const d = data.map((p, i) => `${i === 0 ? "M" : "L"} ${sx(p.x)},${sy(p.y)}`).join(" ");
  return (
    <svg className="plot" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Line chart">
      <rect x="0" y="0" width={width} height={height} className="plot-bg" />
      <path d={d} className="plot-line" fill="none" />
      <g className="plot-axes">
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} />
        <line x1={padding} y1={padding} x2={padding} y2={height - padding} />
      </g>
    </svg>
  );
}

function BarChart({ data, width = 520, height = 160, padding = 18 }) {
  const ymin = 0;
  const ymax = Math.max(...data.map(d => d.y));
  const bw = (width - 2 * padding) / data.length;
  const sy = (y) => height - padding - (y - ymin) * (height - 2 * padding) / (ymax - ymin || 1);
  return (
    <svg className="plot" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Bar chart">
      <rect x="0" y="0" width={width} height={height} className="plot-bg" />
      {data.map((d, i) => {
        const x = padding + i * bw + 1;
        const y = sy(d.y);
        const h = height - padding - y;
        return <rect key={i} x={x} y={y} width={Math.max(1, bw - 2)} height={h} className="plot-bars" />;
      })}
      <g className="plot-axes">
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} />
        <line x1={padding} y1={padding} x2={padding} y2={height - padding} />
      </g>
    </svg>
  );
}

function ScatterChart({ data, width = 520, height = 160, padding = 18 }) {
  const xmin = 0, xmax = data.length - 1;
  const ymin = Math.min(...data.map(d => d.y));
  const ymax = Math.max(...data.map(d => d.y));
  const sx = (x) => padding + (x - xmin) * (width - 2 * padding) / (xmax - xmin || 1);
  const sy = (y) => height - padding - (y - ymin) * (height - 2 * padding) / (ymax - ymin || 1);
  return (
    <svg className="plot" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Scatter chart">
      <rect x="0" y="0" width={width} height={height} className="plot-bg" />
      {data.map((p, i) => (
        <circle key={i} cx={sx(p.x)} cy={sy(p.y)} r="2.5" className="plot-dots" />
      ))}
      <g className="plot-axes">
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} />
        <line x1={padding} y1={padding} x2={padding} y2={height - padding} />
      </g>
    </svg>
  );
}

const PLOT_LABEL = { line: "Line", bar: "Bar", scatter: "Scatter" };

/* =================================
   Plot panel with switcher
   ================================= */
function PlotPanel({ selectedId, title, plotType, onPrev, onNext, index, total }) {
  const data = useSeededData(selectedId);

  // Keyboard support for switching
  const containerRef = useRef(null);
  const onKeyDown = (e) => {
    if (e.key === "ArrowLeft") { e.preventDefault(); onPrev(); }
    if (e.key === "ArrowRight") { e.preventDefault(); onNext(); }
  };

  return (
    <div className="plot-panel" tabIndex={0} onKeyDown={onKeyDown} ref={containerRef}>
      <div className="plot-header">
        <div>
          <div className="plot-title">Visualization</div>
          <div className="plot-subtitle">Auto-selected for “{title}”</div>
        </div>

        <div className="plot-switch">
          <button
            className="arrow-btn"
            aria-label="Previous chart"
            title="Previous (←)"
            onClick={onPrev}
          >
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path d="M15 19l-7-7 7-7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
          <div className="plot-switch-label">
            {PLOT_LABEL[plotType]} · {index + 1}/{total}
          </div>
          <button
            className="arrow-btn"
            aria-label="Next chart"
            title="Next (→)"
            onClick={onNext}
          >
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path d="M9 5l7 7-7 7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        </div>
      </div>

      {plotType === "line" && <LineChart data={data} />}
      {plotType === "bar" && <BarChart data={data} />}
      {plotType === "scatter" && <ScatterChart data={data} />}

      <div className="plot-footer">
        <div className="plot-stat">
          <div className="label">Min</div>
          <div className="value">{Math.min(...data.map(d => d.y))}</div>
        </div>
        <div className="plot-stat">
          <div className="label">Max</div>
          <div className="value">{Math.max(...data.map(d => d.y))}</div>
        </div>
        <div className="plot-stat">
          <div className="label">Last</div>
          <div className="value">{data[data.length - 1].y}</div>
        </div>
      </div>
    </div>
  );
}

/* =================================
   App
   ================================= */
export default function App() {
  const [selectedId, setSelectedId] = useState(ITEMS[0].id);
  const selected = useMemo(() => ITEMS.find(i => i.id === selectedId), [selectedId]);

  // Notifications state
  const [notifications, setNotifications] = useState(INITIAL_NOTIFICATIONS);
  const unreadCount = notifications.filter(n => n.unread).length;
  const [trayOpen, setTrayOpen] = useState(false);
  const bellRef = useRef(null);
  const toggleTray = () => setTrayOpen(v => !v);
  const closeTray = () => setTrayOpen(false);
  const markAllRead = () => setNotifications(prev => prev.map(n => ({ ...n, unread: false })));

  // Keyboard navigation for sidebar
  const listRef = useRef(null);
  const handleKeyDown = useCallback((e) => {
    const currentIndex = ITEMS.findIndex(i => i.id === selectedId);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      const next = Math.min(currentIndex + 1, ITEMS.length - 1);
      setSelectedId(ITEMS[next].id);
      scrollItemIntoView(next);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const prev = Math.max(currentIndex - 1, 0);
      setSelectedId(ITEMS[prev].id);
      scrollItemIntoView(prev);
    } else if (e.key === "Home") {
      e.preventDefault();
      setSelectedId(ITEMS[0].id);
      scrollItemIntoView(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setSelectedId(ITEMS[ITEMS.length - 1].id);
      scrollItemIntoView(ITEMS.length - 1);
    }
  }, [selectedId]);

  const scrollItemIntoView = (index) => {
    const el = listRef.current?.querySelector(`[data-index="${index}"]`);
    el?.scrollIntoView({ block: "nearest" });
  };

  useEffect(() => {
    listRef.current?.focus();
  }, []);

  // Plot carousel state (resets when selection changes)
  const getPlotSequence = (id) => {
    // Customize per item if you want:
    // return id === "1" ? ["line", "bar"] : ["line", "bar", "scatter"];
    return ["line", "bar", "scatter"];
  };
  const plotSequence = getPlotSequence(selectedId);
  const [plotIndex, setPlotIndex] = useState(0);
  useEffect(() => { setPlotIndex(0); }, [selectedId]); // reset on item change
  const nextPlot = useCallback(() => setPlotIndex(i => (i + 1) % plotSequence.length), [plotSequence.length]);
  const prevPlot = useCallback(() => setPlotIndex(i => (i - 1 + plotSequence.length) % plotSequence.length), [plotSequence.length]);
  const plotType = plotSequence[plotIndex];

  return (
    <div className="layout">
      {/* Sidebar */}
      <aside
        className="sidebar"
        role="listbox"
        aria-label="Items"
        aria-activedescendant={`item-${selectedId}`}
        tabIndex={0}
        onKeyDown={handleKeyDown}
        ref={listRef}
      >
        {ITEMS.map((item, idx) => {
          const isSelected = item.id === selectedId;
          return (
            <button
              key={item.id}
              id={`item-${item.id}`}
              data-index={idx}
              role="option"
              aria-selected={isSelected}
              className={`row ${isSelected ? "selected" : ""}`}
              onClick={() => setSelectedId(item.id)}
            >
              <div className="row-title">{item.title}</div>
              <div className="row-subtitle">{item.subtitle}</div>
            </button>
          );
        })}
      </aside>

      {/* Details panel */}
      <main className="detail">
        <header className="detail-header">
          <h1 className="detail-title">{selected?.title}</h1>
          <p className="detail-subtitle">{selected?.subtitle}</p>

          {/* Notifications button (added) */}
          <button
            className="icon-btn notif-bell"
            aria-label={`Open notifications${unreadCount ? `, ${unreadCount} unread` : ""}`}
            aria-haspopup="dialog"
            aria-expanded={trayOpen}
            onClick={toggleTray}
            ref={bellRef}
          >
            <BellIcon filled={unreadCount > 0} />
            {unreadCount > 0 && <span className="badge" aria-hidden="true">{unreadCount}</span>}
          </button>
        </header>

        {/* Popover tray (added) */}
        <NotificationTray
          open={trayOpen}
          onClose={closeTray}
          notifications={notifications}
          onMarkAllRead={markAllRead}
          anchorRef={bellRef}
        />

        <section className="detail-body">
          <p>{selected?.description}</p>

          {/* Example: structured info about the selected item */}
          <div className="detail-cards">
            <div className="card">
              <div className="card-label">ID</div>
              <div className="card-value">{selected?.id}</div>
            </div>
            <div className="card">
              <div className="card-label">Status</div>
              <div className="card-value">Active</div>
            </div>
            <div className="card">
              <div className="card-label">Owner</div>
              <div className="card-value">Team A</div>
            </div>
          </div>

          {/* Plot + switcher */}
          <PlotPanel
            selectedId={selected?.id ?? "0"}
            title={selected?.title ?? ""}
            plotType={plotType}
            onPrev={prevPlot}
            onNext={nextPlot}
            index={plotIndex}
            total={plotSequence.length}
          />
        </section>
      </main>
    </div>
  );
}
