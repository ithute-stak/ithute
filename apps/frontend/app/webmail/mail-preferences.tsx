"use client";

import { Check, LayoutPanelLeft, Monitor, Moon, RotateCcw, Settings2, Sun, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

export type MailTheme = "system" | "light" | "dark" | "ithute";
export type MailDensity = "comfortable" | "compact";
export type ReadingPane = "right" | "bottom" | "none";

export type MailPreferences = {
  theme: MailTheme;
  density: MailDensity;
  readingPane: ReadingPane;
  showPreview: boolean;
  openLinksNewTab: boolean;
  composeFullscreen: boolean;
  fontScale: "small" | "normal" | "large";
};

export const defaultMailPreferences: MailPreferences = {
  theme: "light",
  density: "comfortable",
  readingPane: "right",
  showPreview: true,
  openLinksNewTab: true,
  composeFullscreen: false,
  fontScale: "normal",
};

const STORAGE_KEY = "ithute-imail-preferences-v3";
const LEGACY_STORAGE_KEY = "ithute-imail-preferences-v2";

function normalizeStoredPreferences(stored: Partial<MailPreferences>, legacy = false): MailPreferences {
  const theme = legacy && stored.theme === "ithute" ? "light" : stored.theme;
  return {
    ...defaultMailPreferences,
    ...stored,
    theme: theme && ["system", "light", "dark", "ithute"].includes(theme) ? theme : defaultMailPreferences.theme,
  } as MailPreferences;
}

export function useMailPreferences() {
  const [preferences, setPreferencesState] = useState<MailPreferences>(defaultMailPreferences);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const current = window.localStorage.getItem(STORAGE_KEY);
      if (current) {
        setPreferencesState(normalizeStoredPreferences(JSON.parse(current) as Partial<MailPreferences>));
      } else {
        const legacy = window.localStorage.getItem(LEGACY_STORAGE_KEY);
        if (legacy) {
          const migrated = normalizeStoredPreferences(JSON.parse(legacy) as Partial<MailPreferences>, true);
          setPreferencesState(migrated);
          window.localStorage.setItem(STORAGE_KEY, JSON.stringify(migrated));
        }
      }
    } catch {
      // Local preferences are optional; fall back to the universal light defaults.
    } finally {
      setReady(true);
    }
  }, []);

  const setPreferences = useCallback((value: MailPreferences | ((current: MailPreferences) => MailPreferences)) => {
    setPreferencesState((current) => {
      const next = typeof value === "function" ? value(current) : value;
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        // The browser may block local storage; the current session still updates.
      }
      return next;
    });
  }, []);

  const resetPreferences = useCallback(() => {
    setPreferences(defaultMailPreferences);
  }, [setPreferences]);

  return { preferences, setPreferences, resetPreferences, ready };
}

export function resolvedTheme(theme: MailTheme) {
  if (theme !== "system") return theme;
  if (typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches) return "dark";
  return "light";
}

type SettingsPanelProps = {
  open: boolean;
  onClose: () => void;
  preferences: MailPreferences;
  setPreferences: (value: MailPreferences | ((current: MailPreferences) => MailPreferences)) => void;
  onReset: () => void;
  displayName?: string;
  signatureHtml?: string;
  onDisplayNameChange?: (value: string) => void;
  onSignatureChange?: (value: string) => void;
  onSaveAccount?: () => void | Promise<void>;
  savingAccount?: boolean;
};

function OptionButton({ active, title, subtitle, onClick, icon }: { active: boolean; title: string; subtitle?: string; onClick: () => void; icon?: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`imail-settings-option flex min-h-12 w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition ${active ? "border-[#0b57d0] bg-[#eaf1fb] text-[#174ea6] shadow-sm dark:border-blue-400 dark:bg-blue-400/10 dark:text-blue-100" : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50 dark:border-white/10 dark:bg-white/[.035] dark:text-slate-200 dark:hover:bg-white/[.06]"}`}
    >
      {icon ? <span className="imail-settings-option-icon grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-300">{icon}</span> : null}
      <span className="min-w-0 flex-1">
        <span className="imail-settings-option-title block text-sm font-bold">{title}</span>
        {subtitle ? <span className="imail-settings-option-subtitle mt-0.5 block text-[11px] font-medium text-slate-500 dark:text-slate-400">{subtitle}</span> : null}
      </span>
      {active ? <Check size={17} className="imail-settings-check shrink-0 text-[#0b57d0] dark:text-blue-300" /> : null}
    </button>
  );
}

export function MailSettingsPanel({
  open,
  onClose,
  preferences,
  setPreferences,
  onReset,
  displayName = "",
  signatureHtml = "",
  onDisplayNameChange,
  onSignatureChange,
  onSaveAccount,
  savingAccount = false,
}: SettingsPanelProps) {
  if (!open) return null;

  const update = <K extends keyof MailPreferences>(key: K, value: MailPreferences[K]) => {
    setPreferences((current) => ({ ...current, [key]: value }));
  };

  return (
    <div className="imail-settings-overlay fixed inset-0 z-[110] flex justify-end bg-slate-950/20 backdrop-blur-[2px]" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}>
      <aside className="imail-settings-drawer h-full w-full max-w-[430px] overflow-y-auto border-l border-slate-200 bg-[#f8fafd] shadow-[-22px_0_70px_rgba(15,23,42,.16)] dark:border-white/10 dark:bg-[#101817]">
        <div className="imail-settings-header sticky top-0 z-10 flex h-16 items-center gap-3 border-b border-slate-200 bg-white/95 px-5 backdrop-blur dark:border-white/10 dark:bg-[#101817]/95">
          <span className="imail-settings-header-icon grid h-9 w-9 place-items-center rounded-xl bg-[#eaf1fb] text-[#0b57d0] dark:bg-white/10 dark:text-blue-300"><Settings2 size={18} /></span>
          <div className="min-w-0 flex-1"><p className="text-sm font-black text-slate-900 dark:text-white">iMail settings</p><p className="imail-settings-header-subtitle text-[11px] font-medium text-slate-500 dark:text-slate-400">Personalize your mailbox workspace</p></div>
          <button type="button" onClick={onClose} className="imail-settings-close grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" aria-label="Close settings"><X size={18} /></button>
        </div>

        <div className="imail-settings-body space-y-7 p-5">
          <section className="imail-settings-section">
            <h2 className="imail-settings-section-title text-xs font-black uppercase tracking-[.15em] text-slate-500 dark:text-slate-400">Appearance</h2>
            <div className="imail-settings-grid imail-settings-grid-appearance mt-3 grid grid-cols-2 gap-2">
              <OptionButton active={preferences.theme === "light"} title="Universal" subtitle="Clean, familiar light workspace" onClick={() => update("theme", "light")} icon={<Sun size={16} />} />
              <OptionButton active={preferences.theme === "ithute"} title="Ithute Green" subtitle="Brand-forward workspace" onClick={() => update("theme", "ithute")} icon={<span className="text-xs font-black text-emerald-800">!T</span>} />
              <OptionButton active={preferences.theme === "dark"} title="Dark" subtitle="Low-light mode" onClick={() => update("theme", "dark")} icon={<Moon size={16} />} />
              <OptionButton active={preferences.theme === "system"} title="System" subtitle="Follow device" onClick={() => update("theme", "system")} icon={<Monitor size={16} />} />
            </div>
          </section>

          <section className="imail-settings-section">
            <h2 className="imail-settings-section-title text-xs font-black uppercase tracking-[.15em] text-slate-500 dark:text-slate-400">Reading layout</h2>
            <div className="imail-settings-grid imail-settings-grid-reading mt-3 space-y-2">
              <OptionButton active={preferences.readingPane === "right"} title="Reading pane on right" subtitle="Inbox and message stay visible together" onClick={() => update("readingPane", "right")} icon={<LayoutPanelLeft size={16} />} />
              <OptionButton active={preferences.readingPane === "bottom"} title="Reading pane below" subtitle="Wide message list above the reader" onClick={() => update("readingPane", "bottom")} icon={<LayoutPanelLeft size={16} className="rotate-90" />} />
              <OptionButton active={preferences.readingPane === "none"} title="Open messages full width" subtitle="Classic single-page reading" onClick={() => update("readingPane", "none")} icon={<Monitor size={16} />} />
            </div>
          </section>

          <section className="imail-settings-section">
            <h2 className="imail-settings-section-title text-xs font-black uppercase tracking-[.15em] text-slate-500 dark:text-slate-400">Inbox density</h2>
            <div className="imail-settings-grid imail-settings-grid-density mt-3 grid grid-cols-2 gap-2">
              <OptionButton active={preferences.density === "comfortable"} title="Comfortable" subtitle="Roomier rows" onClick={() => update("density", "comfortable")} />
              <OptionButton active={preferences.density === "compact"} title="Compact" subtitle="More mail on screen" onClick={() => update("density", "compact")} />
            </div>
            <label className="imail-settings-toggle mt-3 flex items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white px-3.5 py-3 dark:border-white/10 dark:bg-white/[.035]">
              <span className="min-w-0"><span className="block text-sm font-bold text-slate-800 dark:text-slate-100">Message previews</span><span className="imail-settings-toggle-subtitle block text-[11px] text-slate-500 dark:text-slate-400">Show a short body snippet in the inbox</span></span>
              <input type="checkbox" checked={preferences.showPreview} onChange={(event) => update("showPreview", event.target.checked)} className="h-4 w-4 shrink-0 accent-[#0b57d0]" />
            </label>
            <label className="imail-settings-toggle mt-2 flex items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white px-3.5 py-3 dark:border-white/10 dark:bg-white/[.035]">
              <span className="min-w-0"><span className="block text-sm font-bold text-slate-800 dark:text-slate-100">Compose full screen by default</span><span className="imail-settings-toggle-subtitle block text-[11px] text-slate-500 dark:text-slate-400">Best for longer documents and proposals</span></span>
              <input type="checkbox" checked={preferences.composeFullscreen} onChange={(event) => update("composeFullscreen", event.target.checked)} className="h-4 w-4 shrink-0 accent-[#0b57d0]" />
            </label>
          </section>

          <section className="imail-settings-section">
            <h2 className="imail-settings-section-title text-xs font-black uppercase tracking-[.15em] text-slate-500 dark:text-slate-400">Reading</h2>
            <div className="imail-settings-grid imail-settings-grid-font mt-3 grid grid-cols-3 gap-2">
              {(["small", "normal", "large"] as const).map((size) => <OptionButton key={size} active={preferences.fontScale === size} title={size[0].toUpperCase() + size.slice(1)} onClick={() => update("fontScale", size)} />)}
            </div>
            <label className="imail-settings-toggle mt-3 flex items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white px-3.5 py-3 dark:border-white/10 dark:bg-white/[.035]">
              <span className="min-w-0"><span className="block text-sm font-bold text-slate-800 dark:text-slate-100">Open links in a new tab</span><span className="imail-settings-toggle-subtitle block text-[11px] text-slate-500 dark:text-slate-400">Keeps iMail open while browsing a link</span></span>
              <input type="checkbox" checked={preferences.openLinksNewTab} onChange={(event) => update("openLinksNewTab", event.target.checked)} className="h-4 w-4 shrink-0 accent-[#0b57d0]" />
            </label>
          </section>

          {(onDisplayNameChange || onSignatureChange) ? (
            <section className="imail-settings-section">
              <h2 className="imail-settings-section-title text-xs font-black uppercase tracking-[.15em] text-slate-500 dark:text-slate-400">Account identity</h2>
              <div className="imail-settings-account mt-3 space-y-3 rounded-2xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-white/[.035]">
                {onDisplayNameChange ? <label className="block"><span className="text-xs font-bold text-slate-600 dark:text-slate-300">Display name</span><input value={displayName} onChange={(event) => onDisplayNameChange(event.target.value)} className="mt-1.5 h-11 w-full rounded-xl border border-slate-200 bg-transparent px-3 text-sm outline-none focus:border-[#0b57d0] focus:ring-4 focus:ring-blue-500/10 dark:border-white/10" placeholder="Name shown to recipients" /></label> : null}
                {onSignatureChange ? <label className="block"><span className="text-xs font-bold text-slate-600 dark:text-slate-300">Signature</span><textarea value={signatureHtml} onChange={(event) => onSignatureChange(event.target.value)} rows={5} className="imail-settings-signature mt-1.5 w-full resize-y rounded-xl border border-slate-200 bg-transparent px-3 py-2.5 text-sm outline-none focus:border-[#0b57d0] focus:ring-4 focus:ring-blue-500/10 dark:border-white/10" placeholder="Your name, title, phone or closing message" /><span className="imail-settings-account-help mt-1 block text-[10px] text-slate-500">Plain text or simple HTML is supported by your account signature.</span></label> : null}
                {onSaveAccount ? <button type="button" disabled={savingAccount} onClick={() => void onSaveAccount()} className="h-10 w-full rounded-full bg-[#0b57d0] text-xs font-black text-white transition hover:bg-[#0842a0] disabled:opacity-60">{savingAccount ? "Saving…" : "Save account settings"}</button> : null}
              </div>
            </section>
          ) : null}

          <button type="button" onClick={onReset} className="imail-settings-reset flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs font-bold text-slate-600 hover:bg-slate-50 dark:border-white/10 dark:bg-white/[.035] dark:text-slate-300 dark:hover:bg-white/[.06]"><RotateCcw size={15} /> Reset layout preferences</button>
        </div>
      </aside>
    </div>
  );
}