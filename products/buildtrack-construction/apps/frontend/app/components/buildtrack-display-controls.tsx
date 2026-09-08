"use client";

import { useEffect, useState } from "react";

type Density = "comfortable" | "compact";
type Preferences = {
  autoFit: boolean;
  uiScale: number;
  textScale: number;
  density: Density;
  lite: boolean;
  focus: boolean;
};

const PREFERENCES_KEY = "buildtrack.display-preferences";
const FULLSCREEN_KEY = "buildtrack.workspace-fullscreen";

function scaleForWidth(width: number) {
  if (width <= 1024) return 80;
  if (width <= 1280) return 85;
  if (width <= 1440) return 90;
  if (width <= 1600) return 95;
  return 100;
}

function defaults(): Preferences {
  return {
    autoFit: true,
    uiScale: 100,
    textScale: 100,
    density: "comfortable",
    lite: false,
    focus: true,
  };
}

function recommendedDefaults(): Preferences {
  return { ...defaults(), uiScale: scaleForWidth(window.innerWidth) };
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}

function normalise(value: unknown): Preferences {
  const initial = defaults();
  if (!value || typeof value !== "object") return initial;
  const saved = value as Partial<Preferences>;
  return {
    autoFit: saved.autoFit !== false,
    uiScale: clamp(Number(saved.uiScale) || initial.uiScale, 80, 125),
    textScale: clamp(Number(saved.textScale) || 100, 85, 130),
    density: saved.density === "compact" ? "compact" : "comfortable",
    lite: saved.lite === true,
    focus: saved.focus !== false,
  };
}

function apply(preferences: Preferences) {
  const root = document.documentElement;
  root.style.setProperty("--buildtrack-ui-scale", `${preferences.uiScale}%`);
  root.style.setProperty("--buildtrack-reading-scale", String(preferences.textScale / 100));
  root.dataset.buildtrackDensity = preferences.density;
  root.dataset.buildtrackLite = preferences.lite ? "true" : "false";
  root.dataset.buildtrackFocus = preferences.focus ? "true" : "false";
}

function describe(preferences: Preferences) {
  return `${preferences.autoFit ? "Auto fit" : "Manual"} · zoom ${preferences.uiScale}% · text ${preferences.textScale}%`;
}

export function BuildTrackDisplayControls() {
  const [preferences, setPreferences] = useState<Preferences>(() => defaults());
  const [open, setOpen] = useState(false);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(PREFERENCES_KEY);
      const loaded = stored ? normalise(JSON.parse(stored)) : recommendedDefaults();
      const saved = loaded.autoFit ? { ...loaded, uiScale: scaleForWidth(window.innerWidth) } : loaded;
      const focusStored = window.localStorage.getItem(FULLSCREEN_KEY);
      const resolved = focusStored === null ? saved : { ...saved, focus: focusStored !== "false" };
      setPreferences(resolved);
      apply(resolved);
    } catch {
      apply(recommendedDefaults());
    }
  }, []);

  useEffect(() => {
    if (!preferences.autoFit) return;
    const updateForViewport = () => {
      setPreferences((current) => {
        const next = { ...current, uiScale: scaleForWidth(window.innerWidth) };
        apply(next);
        return next;
      });
    };
    window.addEventListener("resize", updateForViewport);
    return () => window.removeEventListener("resize", updateForViewport);
  }, [preferences.autoFit]);

  function update(change: Partial<Preferences>) {
    setPreferences((current) => {
      const next = normalise({ ...current, ...change });
      apply(next);
      try {
        window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify(next));
        window.localStorage.setItem(FULLSCREEN_KEY, String(next.focus));
      } catch {
        // The display still works if the browser blocks local persistence.
      }
      return next;
    });
  }

  function adjustScale(amount: number) {
    update({ autoFit: false, uiScale: clamp(preferences.uiScale + amount, 80, 125) });
  }

  function adjustText(amount: number) {
    update({ textScale: clamp(preferences.textScale + amount, 85, 130) });
  }

  function restoreAutomaticFit() {
    update({ autoFit: true, uiScale: scaleForWidth(window.innerWidth) });
  }

  function reset() {
    const next = recommendedDefaults();
    try {
      window.localStorage.removeItem(PREFERENCES_KEY);
      window.localStorage.setItem(FULLSCREEN_KEY, String(next.focus));
    } catch {
      // The default is still applied during this session.
    }
    update(next);
  }

  return (
    <div className="bt-display-dock">
      <div className="bt-display-actions">
        <button className="bt-display-focus" type="button" aria-pressed={preferences.focus} onClick={() => update({ focus: !preferences.focus })} title={preferences.focus ? "Show navigation" : "Focus this workspace"}>
          {preferences.focus ? "Show navigation" : "Focus workspace"}
        </button>
        <button className="bt-display-trigger" type="button" aria-expanded={open} aria-controls="buildtrack-display-panel" onClick={() => setOpen((visible) => !visible)}>
          Display
        </button>
      </div>
      {open && <section className="bt-display-panel" id="buildtrack-display-panel" aria-label="Display and accessibility controls">
        <div className="bt-display-heading"><div><strong>Display controls</strong><span>Saved on this device</span></div><button type="button" className="bt-display-close" onClick={() => setOpen(false)} aria-label="Close display controls">×</button></div>
        <p className="bt-display-summary" aria-live="polite">{describe(preferences)}</p>

        <div className="bt-display-row">
          <div><strong>Workspace zoom</strong><span>Fits all controls and layouts</span></div>
          <div className="bt-stepper"><button type="button" onClick={() => adjustScale(-5)} disabled={preferences.uiScale <= 80} aria-label="Zoom out">−</button><output aria-label="Workspace zoom">{preferences.uiScale}%</output><button type="button" onClick={() => adjustScale(5)} disabled={preferences.uiScale >= 125} aria-label="Zoom in">+</button></div>
        </div>
        <div className="bt-display-presets" aria-label="Workspace zoom presets">
          <button type="button" className={preferences.autoFit ? "is-active" : ""} onClick={restoreAutomaticFit}>Auto fit</button>
          <button type="button" className={!preferences.autoFit && preferences.uiScale === 85 ? "is-active" : ""} onClick={() => update({ autoFit: false, uiScale: 85 })}>Compact</button>
          <button type="button" className={!preferences.autoFit && preferences.uiScale === 100 ? "is-active" : ""} onClick={() => update({ autoFit: false, uiScale: 100 })}>Standard</button>
          <button type="button" className={!preferences.autoFit && preferences.uiScale === 115 ? "is-active" : ""} onClick={() => update({ autoFit: false, uiScale: 115 })}>Presentation</button>
        </div>

        <div className="bt-display-row">
          <div><strong>Reading size</strong><span>Enlarges content without changing the navigation</span></div>
          <div className="bt-stepper"><button type="button" onClick={() => adjustText(-5)} disabled={preferences.textScale <= 85} aria-label="Decrease text size">A−</button><output aria-label="Reading size">{preferences.textScale}%</output><button type="button" onClick={() => adjustText(5)} disabled={preferences.textScale >= 130} aria-label="Increase text size">A+</button></div>
        </div>

        <div className="bt-display-switches">
          <button type="button" aria-pressed={preferences.density === "compact"} onClick={() => update({ density: preferences.density === "comfortable" ? "compact" : "comfortable" })}><span><strong>Compact spacing</strong><small>Fit more controlled records on screen</small></span><b>{preferences.density === "compact" ? "On" : "Off"}</b></button>
          <button type="button" aria-pressed={preferences.lite} onClick={() => update({ lite: !preferences.lite })}><span><strong>Low-resource mode</strong><small>Reduces motion, blur and visual effects</small></span><b>{preferences.lite ? "On" : "Off"}</b></button>
        </div>

        <button className="bt-display-reset" type="button" onClick={reset}>Restore recommended display</button>
      </section>}
    </div>
  );
}
