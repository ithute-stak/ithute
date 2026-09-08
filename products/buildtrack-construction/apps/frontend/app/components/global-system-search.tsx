"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { MANUAL_ENTRIES, SYSTEM_FORMS } from "../lib/system-manual";
import styles from "./global-system-search.module.css";

type Mode = "routes" | "forms";

function searchable(value: unknown) {
  return String(value ?? "").toLowerCase();
}

function isTypingTarget(target: EventTarget | null) {
  const el = target as HTMLElement | null;
  if (!el) return false;
  return el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable;
}

export function GlobalSystemSearch() {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<Mode>("routes");
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState("All modules");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const lastShift = useRef(0);
  const formChordArmed = useRef(false);

  const routes = useMemo(() => [
    { route: "/index", title: "System Manual", group: "Overview", summary: "Open the complete user manual, task finder, role guide and system information.", find: ["documentation", "manual", "help", "how to use the system"] },
    ...MANUAL_ENTRIES.filter((entry) => !entry.public && !entry.dynamicRoute),
  ], []);
  const groups = useMemo(() => ["All modules", ...Array.from(new Set(SYSTEM_FORMS.map((item) => item.module)))], []);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (mode === "routes") {
      return routes.filter((entry) => {
        const haystack = [entry.title, entry.route, entry.group, entry.summary, ...entry.find].map(searchable).join(" ");
        return !q || haystack.includes(q);
      }).slice(0, 18).map((entry) => ({
        key: `route:${entry.route}`,
        title: entry.title,
        description: entry.summary,
        route: entry.route,
        badge: entry.group,
      }));
    }
    return SYSTEM_FORMS.filter((item) => {
      const inModule = group === "All modules" || item.module === group;
      const haystack = [item.label, item.purpose, item.module, item.group, item.route].map(searchable).join(" ");
      return inModule && (!q || haystack.includes(q));
    }).slice(0, 24).map((item) => ({
      key: `form:${item.route}:${item.label}`,
      title: item.label,
      description: `${item.module} — ${item.purpose}`,
      route: item.route,
      badge: item.module,
    }));
  }, [group, mode, query, routes]);

  function show(nextMode: Mode) {
    setMode(nextMode);
    setQuery("");
    setGroup("All modules");
    setActive(0);
    setOpen(true);
  }

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && open) {
        event.preventDefault();
        setOpen(false);
        return;
      }

      const modifier = event.key === "Control" || event.key === "Shift" || event.key === "Meta";
      if ((event.ctrlKey || event.metaKey) && event.shiftKey && modifier && !event.repeat) {
        formChordArmed.current = true;
      } else if (formChordArmed.current && !modifier) {
        // Do not steal browser/app shortcuts such as Ctrl+Shift+I or Ctrl+Shift+T.
        formChordArmed.current = false;
      }

      if (event.key === "Shift" && !event.repeat && !event.ctrlKey && !event.metaKey && !event.altKey && !isTypingTarget(event.target)) {
        const now = Date.now();
        if (now - lastShift.current <= 450) {
          event.preventDefault();
          lastShift.current = 0;
          show("routes");
        } else {
          lastShift.current = now;
        }
      }
    };

    const onKeyUp = (event: KeyboardEvent) => {
      if (formChordArmed.current && (event.key === "Control" || event.key === "Shift" || event.key === "Meta")) {
        event.preventDefault();
        formChordArmed.current = false;
        show("forms");
      }
    };

    const onDoubleClick = (event: MouseEvent) => {
      if (event.shiftKey && !isTypingTarget(event.target)) {
        event.preventDefault();
        show("routes");
      }
    };

    const routeEvent = () => show("routes");
    const formEvent = () => show("forms");
    window.addEventListener("keydown", onKeyDown, true);
    window.addEventListener("keyup", onKeyUp, true);
    window.addEventListener("dblclick", onDoubleClick, true);
    window.addEventListener("nth:open-route-search", routeEvent);
    window.addEventListener("nth:open-form-search", formEvent);
    return () => {
      window.removeEventListener("keydown", onKeyDown, true);
      window.removeEventListener("keyup", onKeyUp, true);
      window.removeEventListener("dblclick", onDoubleClick, true);
      window.removeEventListener("nth:open-route-search", routeEvent);
      window.removeEventListener("nth:open-form-search", formEvent);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const id = window.setTimeout(() => inputRef.current?.focus(), 20);
    return () => window.clearTimeout(id);
  }, [open, mode]);

  useEffect(() => setActive(0), [query, group, mode]);

  function go(route: string) {
    setOpen(false);
    window.location.assign(route);
  }

  if (!open) return null;

  return <div className={styles.backdrop} role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) setOpen(false); }}>
    <section className={styles.panel} role="dialog" aria-modal="true" aria-label={mode === "routes" ? "Global route search" : "Global form search"}>
      <header className={styles.head}>
        <div className={styles.headTop}>
          <div>
            <div className={styles.eyebrow}>Nthane Brothers · Global finder</div>
            <h2 className={styles.title}>{mode === "routes" ? "Go to any system screen" : "Find any operational form"}</h2>
            <p className={styles.subtitle}>{mode === "routes" ? "Search by screen, task or business term." : "Search by action, then optionally narrow the list to a module."}</p>
          </div>
          <button className={styles.close} onClick={() => setOpen(false)} aria-label="Close global search">×</button>
        </div>
      </header>
      <div className={styles.searchRow}>
        <input ref={inputRef} className={styles.search} value={query} onChange={(event) => setQuery(event.target.value)} placeholder={mode === "routes" ? "Try: fuel, payroll, project risks, supplier, tender..." : "Try: purchase order, daily report, employee, contract notice..."}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") { event.preventDefault(); setActive((value) => Math.min(results.length - 1, value + 1)); }
            if (event.key === "ArrowUp") { event.preventDefault(); setActive((value) => Math.max(0, value - 1)); }
            if (event.key === "Enter" && results[active]) { event.preventDefault(); go(results[active].route); }
          }} />
        {mode === "forms" ? <select className={styles.select} value={group} onChange={(event) => setGroup(event.target.value)} aria-label="Filter forms by module">
          {groups.map((value) => <option key={value}>{value}</option>)}
        </select> : <button className={styles.select} onClick={() => show("forms")}>Search forms instead</button>}
      </div>
      <div className={styles.results}>
        {results.length ? results.map((result, index) => <button key={result.key} className={`${styles.item} ${active === index ? styles.active : ""}`} onMouseEnter={() => setActive(index)} onClick={() => go(result.route)}>
          <span className={styles.code}>{mode === "routes" ? "GO" : "FORM"}</span>
          <span className={styles.copy}><strong>{result.title}</strong><span>{result.description}</span></span>
          <span className={styles.route}>{result.route}</span>
        </button>) : <div className={styles.empty}>No matching {mode === "routes" ? "screen" : "form"}. Try a broader business term.</div>}
      </div>
      <footer className={styles.foot}>
        <span><span className={styles.kbd}>↑ ↓</span> select</span><span><span className={styles.kbd}>Enter</span> open</span><span><span className={styles.kbd}>Esc</span> close</span><span>Double-tap <span className={styles.kbd}>Shift</span> for routes</span><span><span className={styles.kbd}>Ctrl</span> + <span className={styles.kbd}>Shift</span> for forms</span>
      </footer>
    </section>
  </div>;
}
