"use client";

import { AlertTriangle, CheckCircle2, CircleAlert, Info, X } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

export type ToastTone = "success" | "warning" | "error" | "info";
export type ToastInput = {
  title?: string;
  message: string;
  tone?: ToastTone;
  duration?: number;
  action?: { label: string; onClick: () => void };
};

type ToastItem = ToastInput & { id: number; tone: ToastTone };
type ToastContextValue = {
  notify: (input: ToastInput | string) => number;
  success: (message: string, title?: string) => number;
  warning: (message: string, title?: string) => number;
  error: (message: string, title?: string) => number;
  info: (message: string, title?: string) => number;
  dismiss: (id: number) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

const toneClasses: Record<ToastTone, string> = {
  success: "border-emerald-200 bg-white text-emerald-900",
  warning: "border-amber-200 bg-white text-amber-950",
  error: "border-red-200 bg-white text-red-900",
  info: "border-sky-200 bg-white text-slate-900",
};

function ToneIcon({ tone }: { tone: ToastTone }) {
  if (tone === "success") return <CheckCircle2 size={18} className="text-emerald-600" />;
  if (tone === "warning") return <AlertTriangle size={18} className="text-amber-600" />;
  if (tone === "error") return <CircleAlert size={18} className="text-red-600" />;
  return <Info size={18} className="text-sky-600" />;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const sequence = useRef(0);

  const dismiss = useCallback((id: number) => {
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  const notify = useCallback(
    (input: ToastInput | string) => {
      sequence.current += 1;
      const id = sequence.current;
      const normalized: ToastInput = typeof input === "string" ? { message: input } : input;
      const item: ToastItem = { ...normalized, id, tone: normalized.tone || "info" };
      setItems((current) => [...current.slice(-3), item]);
      const duration = normalized.duration ?? (item.tone === "error" ? 7000 : 4500);
      if (duration > 0) window.setTimeout(() => dismiss(id), duration);
      return id;
    },
    [dismiss],
  );

  const value = useMemo<ToastContextValue>(
    () => ({
      notify,
      dismiss,
      success: (message, title) => notify({ message, title, tone: "success" }),
      warning: (message, title) => notify({ message, title, tone: "warning" }),
      error: (message, title) => notify({ message, title, tone: "error" }),
      info: (message, title) => notify({ message, title, tone: "info" }),
    }),
    [dismiss, notify],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[120] flex w-[min(420px,calc(100vw-2rem))] flex-col gap-2" aria-live="polite" aria-atomic="false">
        {items.map((item) => (
          <div
            key={item.id}
            role={item.tone === "error" ? "alert" : "status"}
            className={`pointer-events-auto animate-[ithuteToastIn_.18s_ease-out] rounded-2xl border p-3.5 shadow-[0_18px_50px_rgba(20,40,30,.16)] ${toneClasses[item.tone]}`}
          >
            <div className="flex items-start gap-3">
              <div className="mt-0.5 shrink-0"><ToneIcon tone={item.tone} /></div>
              <div className="min-w-0 flex-1">
                {item.title ? <p className="text-[12px] font-black">{item.title}</p> : null}
                <p className={`${item.title ? "mt-0.5" : ""} text-[11px] leading-5 text-slate-600`}>{item.message}</p>
                {item.action ? (
                  <button
                    type="button"
                    onClick={() => { item.action?.onClick(); dismiss(item.id); }}
                    className="mt-2 rounded-lg px-2 py-1 text-[10px] font-black text-[var(--admin-pine)] hover:bg-[var(--admin-soft)]"
                  >
                    {item.action.label}
                  </button>
                ) : null}
              </div>
              <button type="button" onClick={() => dismiss(item.id)} className="grid h-7 w-7 shrink-0 place-items-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="Dismiss notification">
                <X size={14} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const value = useContext(ToastContext);
  if (!value) throw new Error("useToast must be used inside ToastProvider");
  return value;
}
