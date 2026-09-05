"use client";

import { AlertTriangle, CheckCircle2, ChevronRight, CircleAlert, Info, LoaderCircle, X } from "lucide-react";
import Link from "next/link";
import {
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
  useEffect,
} from "react";

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) {
  return <section className="surface-card page-header-premium relative overflow-hidden p-4 sm:p-5"><div className="pointer-events-none absolute -right-14 -top-16 h-40 w-40 rounded-full border-[24px] border-[#285b55]/[.035]"/><div className="pointer-events-none absolute right-20 top-0 h-20 w-20 rounded-full bg-[#d8c56a]/[.07] blur-2xl"/><div className="relative flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between"><div>{eyebrow ? <p className="eyebrow-label">{eyebrow}</p> : null}<h1 className="mt-2 text-2xl font-black tracking-tight text-[var(--admin-ink)] sm:text-[28px]">{title}</h1>{description ? <p className="mt-1.5 max-w-3xl text-[12px] leading-5 text-[var(--admin-muted)]">{description}</p> : null}</div>{actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}</div></section>;
}

export function StatusBadge({ state, children }: { state: "good" | "warn" | "bad" | "neutral"; children: ReactNode }) {
  return <span className={`status-pill status-${state}`}>{children}</span>;
}

export function Skeleton({ className = "h-4 w-full" }: { className?: string }) { return <div className={`skeleton ${className}`} aria-hidden="true" />; }

export function SkeletonRows({ rows = 5 }: { rows?: number }) {
  return <div className="divide-y divide-[var(--admin-line)]">{Array.from({ length: rows }).map((_, index) => <div key={index} className="flex items-center gap-3 p-3.5"><Skeleton className="h-8 w-8 rounded-lg"/><div className="min-w-0 flex-1 space-y-2"><Skeleton className="h-2.5 w-1/3"/><Skeleton className="h-2 w-1/2"/></div><Skeleton className="h-7 w-20 rounded-full"/></div>)}</div>;
}

export function EmptyState({ title, description, action, icon }: { title: string; description: string; action?: ReactNode; icon?: ReactNode }) {
  return <div className="grid min-h-48 place-items-center rounded-2xl border border-dashed border-[var(--admin-line)] bg-[var(--admin-soft)] p-6 text-center"><div>{icon ? <div className="mx-auto mb-3 grid h-11 w-11 place-items-center rounded-xl bg-white text-[var(--admin-pine)] shadow-sm">{icon}</div> : null}<p className="text-sm font-black text-[var(--admin-ink)]">{title}</p><p className="mx-auto mt-1 max-w-lg text-[11px] leading-5 text-[var(--admin-muted)]">{description}</p>{action ? <div className="mt-4 flex justify-center">{action}</div> : null}</div></div>;
}

export function Breadcrumbs({ items }: { items: { label: string; href?: string }[] }) {
  return <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-1 text-[10px] font-bold text-[var(--admin-muted)]">{items.map((item, index) => <span key={`${item.label}-${index}`} className="flex items-center gap-1">{index ? <ChevronRight size={11}/> : null}{item.href ? <Link className="hover:text-[var(--admin-pine)] hover:underline" href={item.href}>{item.label}</Link> : <span className="text-[var(--admin-ink)]">{item.label}</span>}</span>)}</nav>;
}

export function Toast({ tone = "info", message, onClose }: { tone?: "success" | "warning" | "error" | "info"; message: string; onClose?: () => void }) {
  const Icon = tone === "success" ? CheckCircle2 : tone === "warning" ? AlertTriangle : tone === "error" ? CircleAlert : Info;
  useEffect(() => { if (!onClose) return; const id = window.setTimeout(onClose, 4500); return () => window.clearTimeout(id); }, [message, onClose]);
  return <div className={`toast toast-${tone}`} role="status"><Icon size={16}/><span className="flex-1">{message}</span>{onClose ? <button aria-label="Dismiss notification" onClick={onClose}><X size={14}/></button> : null}</div>;
}

export function Button({ tone = "primary", busy = false, children, className = "", disabled, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: "primary" | "secondary" | "danger"; busy?: boolean }) {
  const base = tone === "primary" ? "btn-primary" : tone === "danger" ? "btn-danger" : "btn-secondary";
  return <button {...props} disabled={disabled || busy} aria-busy={busy || undefined} className={`${base} ${className}`}>{busy ? <LoaderCircle size={14} className="animate-spin"/> : null}{children}</button>;
}

export function IconButton({ label, children, className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return <button {...props} aria-label={label} title={props.title || label} className={`icon-button ${className}`}>{children}</button>;
}

export function Panel({ children, className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={`surface-card ithute-panel ${className}`}>{children}</div>;
}

export function Field({ label, helper, error, children }: { label: string; helper?: string; error?: string; children: ReactNode }) {
  return <label className="block"><span className="label">{label}</span>{children}{error ? <span className="mt-1 block text-[10px] font-semibold text-[var(--admin-danger)]">{error}</span> : helper ? <span className="helper block">{helper}</span> : null}</label>;
}

export function TextInput({ className = "", ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`input ${className}`} />;
}

export function SelectInput({ className = "", children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`input ${className}`}>{children}</select>;
}

export function TextArea({ className = "", ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={`input min-h-28 resize-y ${className}`} />;
}

export function InlineAlert({ tone = "info", title, children }: { tone?: "success" | "warning" | "error" | "info"; title?: string; children: ReactNode }) {
  const Icon = tone === "success" ? CheckCircle2 : tone === "warning" ? AlertTriangle : tone === "error" ? CircleAlert : Info;
  const colors = tone === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-900" : tone === "warning" ? "border-amber-200 bg-amber-50 text-amber-950" : tone === "error" ? "border-red-200 bg-red-50 text-red-900" : "border-sky-200 bg-sky-50 text-sky-950";
  return <div className={`flex items-start gap-3 rounded-xl border p-3 ${colors}`} role={tone === "error" ? "alert" : "status"}><Icon size={16} className="mt-0.5 shrink-0"/><div className="min-w-0">{title ? <p className="text-[11px] font-black">{title}</p> : null}<div className={`${title ? "mt-0.5" : ""} text-[10px] leading-5`}>{children}</div></div></div>;
}

export function ConfirmDialog({ open, title, description, confirmLabel = "Confirm", dangerous = false, requireText, value, onValueChange, onCancel, onConfirm }: { open: boolean; title: string; description: string; confirmLabel?: string; dangerous?: boolean; requireText?: string; value?: string; onValueChange?: (value: string) => void; onCancel: () => void; onConfirm: () => void }) {
  if (!open) return null;
  const blocked = Boolean(requireText && value !== requireText);
  return <div className="fixed inset-0 z-[80] grid place-items-center bg-black/45 p-4" role="dialog" aria-modal="true"><div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-2xl"><div className="flex items-start justify-between gap-4"><div><p className="text-lg font-black text-[var(--admin-ink)]">{title}</p><p className="mt-2 text-[12px] leading-5 text-[var(--admin-muted)]">{description}</p></div><IconButton onClick={onCancel} label="Close"><X size={15}/></IconButton></div>{requireText ? <div className="mt-4"><label className="label">Type <strong>{requireText}</strong> to confirm</label><input className="input" value={value || ""} onChange={(e) => onValueChange?.(e.target.value)} autoFocus /></div> : null}<div className="mt-5 flex justify-end gap-2"><Button tone="secondary" onClick={onCancel}>Cancel</Button><Button disabled={blocked} onClick={onConfirm} tone={dangerous ? "danger" : "primary"}>{confirmLabel}</Button></div></div></div>;
}

export function LoadingPanel({ label = "Loading" }: { label?: string }) { return <div className="flex min-h-36 items-center justify-center gap-2 text-[12px] font-semibold text-[var(--admin-muted)]"><LoaderCircle size={16} className="animate-spin"/>{label}</div>; }

export function MetricCard({ label, value, detail, status = "neutral" }: { label: string; value: ReactNode; detail?: string; status?: "good" | "warn" | "bad" | "neutral" }) {
  return <div className="surface-card metric-card-premium p-4"><div className="flex items-center justify-between gap-3"><p className="text-[10px] font-black uppercase tracking-[.1em] text-[var(--admin-muted)]">{label}</p><span className={`metric-dot metric-${status}`} /></div><div className="mt-3 text-2xl font-black tracking-tight text-[var(--admin-ink)]">{value}</div>{detail ? <p className="mt-1 text-[10px] leading-4 text-[var(--admin-muted)]">{detail}</p> : null}</div>;
}
