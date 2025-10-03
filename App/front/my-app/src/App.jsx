import { useMemo, useState, useCallback, useEffect, useRef } from "react";
import "./styles.css";

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

export default function App() {
  const [selectedId, setSelectedId] = useState(ITEMS[0].id);
  const selected = useMemo(() => ITEMS.find(i => i.id === selectedId), [selectedId]);

  // For keyboard navigation (Up/Down + Enter)
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

  // Keep focus on the list when the app loads (optional)
  useEffect(() => {
    listRef.current?.focus();
  }, []);

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
        </header>

        <section className="detail-body">
          <p>{selected?.description}</p>

          {/* Example: show some structured info about the selected item */}
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
        </section>
      </main>
    </div>
  );
}
