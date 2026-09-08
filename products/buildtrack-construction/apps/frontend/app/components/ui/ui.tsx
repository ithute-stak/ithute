"use client";

import {
  ComponentPropsWithoutRef,
  ReactNode,
  createContext,
  useContext,
  useEffect,
  useId,
  useMemo,
  useState,
} from "react";

export function cn(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

type ButtonVariant = "default" | "secondary" | "outline" | "ghost" | "destructive";
type ButtonSize = "default" | "sm" | "lg" | "icon";

export function Button({
  className,
  variant = "default",
  size = "default",
  loading = false,
  children,
  disabled,
  ...props
}: ComponentPropsWithoutRef<"button"> & { variant?: ButtonVariant; size?: ButtonSize; loading?: boolean }) {
  return <button {...props} disabled={disabled || loading} aria-busy={loading || undefined} className={cn("bt-ui-button", `bt-ui-button-${variant}`, `bt-ui-button-${size}`, className)}>
    {loading && <span className="bt-ui-spinner" aria-hidden="true" />}{children}
  </button>;
}

export function Card({ className, children, ...props }: ComponentPropsWithoutRef<"section">) {
  return <section {...props} className={cn("bt-ui-card", className)}>{children}</section>;
}
export function CardHeader({ className, children, ...props }: ComponentPropsWithoutRef<"div">) {
  return <div {...props} className={cn("bt-ui-card-header", className)}>{children}</div>;
}
export function CardTitle({ className, children, ...props }: ComponentPropsWithoutRef<"h2">) {
  return <h2 {...props} className={cn("bt-ui-card-title", className)}>{children}</h2>;
}
export function CardDescription({ className, children, ...props }: ComponentPropsWithoutRef<"p">) {
  return <p {...props} className={cn("bt-ui-card-description", className)}>{children}</p>;
}
export function CardContent({ className, children, ...props }: ComponentPropsWithoutRef<"div">) {
  return <div {...props} className={cn("bt-ui-card-content", className)}>{children}</div>;
}
export function CardFooter({ className, children, ...props }: ComponentPropsWithoutRef<"div">) {
  return <div {...props} className={cn("bt-ui-card-footer", className)}>{children}</div>;
}

export function Badge({ className, tone = "neutral", children, ...props }: ComponentPropsWithoutRef<"span"> & { tone?: "neutral" | "success" | "warning" | "danger" | "info" }) {
  return <span {...props} className={cn("bt-ui-badge", `bt-ui-badge-${tone}`, className)}>{children}</span>;
}

export function Alert({ className, tone = "info", title, children, ...props }: ComponentPropsWithoutRef<"div"> & { tone?: "info" | "success" | "warning" | "danger"; title?: string }) {
  return <div {...props} role={tone === "danger" ? "alert" : "status"} className={cn("bt-ui-alert", `bt-ui-alert-${tone}`, className)}>
    <span className="bt-ui-alert-mark" aria-hidden="true">{tone === "success" ? "✓" : tone === "warning" ? "!" : tone === "danger" ? "×" : "i"}</span>
    <div>{title && <strong>{title}</strong>}{children && <div className="bt-ui-alert-copy">{children}</div>}</div>
  </div>;
}

export function Label({ className, children, ...props }: ComponentPropsWithoutRef<"label">) {
  return <label {...props} className={cn("bt-ui-label", className)}>{children}</label>;
}
export function Input({ className, ...props }: ComponentPropsWithoutRef<"input">) {
  return <input {...props} className={cn("bt-ui-input", className)} />;
}
export function Textarea({ className, ...props }: ComponentPropsWithoutRef<"textarea">) {
  return <textarea {...props} className={cn("bt-ui-textarea", className)} />;
}
export function Select({ className, children, ...props }: ComponentPropsWithoutRef<"select">) {
  return <select {...props} className={cn("bt-ui-select", className)}>{children}</select>;
}

export function FormField({
  label,
  description,
  error,
  required,
  className,
  children,
}: {
  label: string;
  description?: string;
  error?: string;
  required?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const id = useId();
  return <div className={cn("bt-ui-field", error && "has-error", className)}>
    <Label htmlFor={id}>{label}{required && <span aria-hidden="true"> *</span>}</Label>
    {typeof children === "object" && children && "type" in children
      ? <div className="bt-ui-field-control">{children}</div>
      : children}
    {description && !error && <p className="bt-ui-field-description">{description}</p>}
    {error && <p className="bt-ui-field-error" role="alert">{error}</p>}
  </div>;
}

function useEscape(open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [open, onClose]);
}

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  className,
  dismissible = true,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
  dismissible?: boolean;
}) {
  const titleId = useId();
  const descriptionId = useId();
  useEscape(open, () => { if (dismissible) onOpenChange(false); });
  if (!open) return null;
  return <div className="bt-ui-dialog-backdrop" role="presentation" onMouseDown={() => dismissible && onOpenChange(false)}>
    <section className={cn("bt-ui-dialog", className)} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={description ? descriptionId : undefined} onMouseDown={(event) => event.stopPropagation()}>
      <header className="bt-ui-dialog-header"><div><h2 id={titleId}>{title}</h2>{description && <p id={descriptionId}>{description}</p>}</div>{dismissible && <button className="bt-ui-dialog-close" type="button" onClick={() => onOpenChange(false)} aria-label="Close dialog">×</button>}</header>
      <div className="bt-ui-dialog-content">{children}</div>
      {footer && <footer className="bt-ui-dialog-footer">{footer}</footer>}
    </section>
  </div>;
}

export function AlertDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Continue",
  cancelLabel = "Cancel",
  destructive,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  onConfirm: () => void | Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  async function confirm() { setBusy(true); try { await onConfirm(); onOpenChange(false); } finally { setBusy(false); } }
  return <Dialog open={open} onOpenChange={onOpenChange} title={title} description={description} dismissible={!busy} footer={<><Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>{cancelLabel}</Button><Button variant={destructive ? "destructive" : "default"} loading={busy} onClick={() => void confirm()}>{confirmLabel}</Button></>}>
    <Alert tone={destructive ? "danger" : "warning"} title={destructive ? "This action is controlled" : "Please confirm"}>{description}</Alert>
  </Dialog>;
}

export function Popover({
  label,
  children,
  className,
}: {
  label: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  return <div className={cn("bt-ui-popover", className)}>
    <Button type="button" variant="outline" size="sm" aria-expanded={open} onClick={() => setOpen((visible) => !visible)}>{label}</Button>
    {open && <div className="bt-ui-popover-content" role="dialog">{children}</div>}
  </div>;
}

export function Tooltip({ content, children }: { content: string; children: ReactNode }) {
  return <span className="bt-ui-tooltip" data-tooltip={content} tabIndex={0}>{children}</span>;
}

export function Tabs({
  value,
  onValueChange,
  items,
}: {
  value: string;
  onValueChange: (value: string) => void;
  items: Array<{ value: string; label: string }>;
}) {
  return <div className="bt-ui-tabs" role="tablist">{items.map((item) => <button type="button" role="tab" aria-selected={value === item.value} className={value === item.value ? "is-active" : ""} key={item.value} onClick={() => onValueChange(item.value)}>{item.label}</button>)}</div>;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("bt-ui-skeleton", className)} aria-hidden="true" />;
}

export function Table({ className, children, ...props }: ComponentPropsWithoutRef<"table">) {
  return <div className="bt-ui-table-wrap"><table {...props} className={cn("bt-ui-table", className)}>{children}</table></div>;
}
export function TableHeader({ className, children, ...props }: ComponentPropsWithoutRef<"thead">) {
  return <thead {...props} className={cn("bt-ui-table-header", className)}>{children}</thead>;
}
export function TableBody({ className, children, ...props }: ComponentPropsWithoutRef<"tbody">) {
  return <tbody {...props} className={cn("bt-ui-table-body", className)}>{children}</tbody>;
}
export function TableRow({ className, children, ...props }: ComponentPropsWithoutRef<"tr">) {
  return <tr {...props} className={cn("bt-ui-table-row", className)}>{children}</tr>;
}
export function TableHead({ className, children, ...props }: ComponentPropsWithoutRef<"th">) {
  return <th {...props} className={cn("bt-ui-table-head", className)}>{children}</th>;
}
export function TableCell({ className, children, ...props }: ComponentPropsWithoutRef<"td">) {
  return <td {...props} className={cn("bt-ui-table-cell", className)}>{children}</td>;
}

export function Separator({ className, ...props }: ComponentPropsWithoutRef<"hr">) {
  return <hr {...props} className={cn("bt-ui-separator", className)} />;
}

export function Switch({ checked, onCheckedChange, disabled, label }: { checked: boolean; onCheckedChange: (checked: boolean) => void; disabled?: boolean; label?: string }) {
  return <button type="button" className="bt-ui-switch" role="switch" aria-checked={checked} aria-label={label} disabled={disabled} onClick={() => onCheckedChange(!checked)}><span className={checked ? "is-on" : ""} /></button>;
}

export function FormDialog({
  title,
  description,
  triggerLabel,
  children,
  open: controlledOpen,
  onOpenChange,
}: {
  title: string;
  description?: string;
  triggerLabel?: string;
  children: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false);
  const open = controlledOpen ?? uncontrolledOpen;
  const setOpen = onOpenChange ?? setUncontrolledOpen;
  return <><Button className="bt-page-action" type="button" onClick={() => setOpen(true)}>{triggerLabel ?? `Add ${title}`}</Button><Dialog open={open} onOpenChange={setOpen} title={title} description={description}>{children}</Dialog></>;
}

type ToastTone = "success" | "info" | "warning" | "danger";
type ConfirmOptions = { title: string; description: string; confirmLabel?: string; cancelLabel?: string; destructive?: boolean };
type PromptOptions = { title: string; description?: string; label: string; defaultValue?: string; placeholder?: string; multiline?: boolean; required?: boolean; confirmLabel?: string };
type Toast = { id: number; message: string; tone: ToastTone };
type Interaction = ({ kind: "confirm"; options: ConfirmOptions; resolve: (value: boolean) => void } | { kind: "prompt"; options: PromptOptions; value: string; resolve: (value: string | null) => void });

type UiContextValue = {
  notify: (message: string, tone?: ToastTone) => void;
  confirm: (options: ConfirmOptions) => Promise<boolean>;
  promptText: (options: PromptOptions) => Promise<string | null>;
};

const UiContext = createContext<UiContextValue | null>(null);

type ManagedForm = { trigger: HTMLButtonElement; overlay: HTMLDivElement; dispose: () => void };
type FilterControl = { index: number; label: string; kind: "select" | "text" | "date" | "number"; control?: HTMLInputElement | HTMLSelectElement; from?: HTMLInputElement; to?: HTMLInputElement };
type EnhancedTable = { table: HTMLTableElement; toolbar: HTMLDivElement; pager: HTMLDivElement; search: HTMLInputElement; pageSize: HTMLSelectElement; summary: HTMLOutputElement; previous: HTMLButtonElement; next: HTMLButtonElement; filters: FilterControl[]; page: number; rows: HTMLTableRowElement[]; apply: () => void; dispose: () => void };

function normaliseText(value: string) {
  return value.replace(/\s+/g, " ").trim().toLocaleLowerCase();
}

function readableText(value: string) {
  return value.replace(/\s+/g, " ").trim();
}

function fieldValue(row: HTMLTableRowElement, index: number) {
  return readableText(row.cells.item(index)?.textContent ?? "");
}

function formTitle(form: HTMLFormElement) {
  const supplied = form.dataset.dialogTitle;
  const submit = form.querySelector<HTMLButtonElement | HTMLInputElement>('button[type="submit"], button:not([type]), input[type="submit"]');
  const heading = form.closest("section")?.querySelector("h2, h3, h4")?.textContent;
  return readableText(supplied ?? submit?.value ?? submit?.textContent ?? heading ?? "Manage record");
}

function BuildTrackOperationalEnhancements() {
  useEffect(() => {
    const forms = new Map<HTMLFormElement, ManagedForm>();
    const tables = new Map<HTMLTableElement, EnhancedTable>();
    let frame = 0;

    const closeOpenForm = () => {
      const active = Array.from(forms.entries()).reverse().find(([form]) => form.classList.contains("is-open"));
      if (!active) return;
      const [, managed] = active;
      managed.overlay.click();
    };

    const enhanceForm = (form: HTMLFormElement) => {
      const existing = forms.get(form);
      if (existing) {
        if (!existing.trigger.isConnected) form.parentElement?.insertBefore(existing.trigger, form);
        if (!existing.overlay.isConnected) document.body.append(existing.overlay);
        form.classList.add("bt-managed-form");
        form.dataset.btFormEnhanced = "true";
        return;
      }
      // Forms remain in their normal page layout unless the author deliberately
      // requests a dialog.  Dialogs are for short, focused workflows—not a
      // global replacement for every business screen.
      if (form.id === "bt-ui-prompt-form" || form.closest("table") || form.dataset.btDialog !== "true") return;
      const title = formTitle(form);
      const trigger = document.createElement("button");
      trigger.type = "button";
      trigger.className = "bt-form-dialog-trigger";
      trigger.textContent = `+ ${title}`;
      trigger.setAttribute("aria-haspopup", "dialog");
      const overlay = document.createElement("div");
      overlay.className = "bt-form-dialog-overlay";
      overlay.hidden = true;
      overlay.setAttribute("aria-hidden", "true");
      document.body.append(overlay);

      form.classList.add("bt-managed-form");
      form.dataset.btFormEnhanced = "true";
      form.dataset.btFormTitle = title;
      form.setAttribute("role", "dialog");
      form.setAttribute("aria-modal", "true");
      form.setAttribute("aria-label", title);
      form.parentElement?.insertBefore(trigger, form);

      const open = () => {
        form.classList.add("is-open");
        overlay.hidden = false;
        overlay.setAttribute("aria-hidden", "false");
        document.body.classList.add("bt-form-dialog-open");
        window.setTimeout(() => form.querySelector<HTMLElement>('input:not([type="hidden"]):not([disabled]), select:not([disabled]), textarea:not([disabled])')?.focus(), 0);
      };
      const close = () => {
        form.classList.remove("is-open");
        overlay.hidden = true;
        overlay.setAttribute("aria-hidden", "true");
        if (!Array.from(forms.keys()).some((candidate) => candidate.classList.contains("is-open"))) document.body.classList.remove("bt-form-dialog-open");
        trigger.focus();
      };
      const submit = () => window.setTimeout(close, 0);
      trigger.addEventListener("click", open);
      overlay.addEventListener("click", close);
      form.addEventListener("submit", submit);
      forms.set(form, {
        trigger,
        overlay,
        dispose: () => {
          trigger.removeEventListener("click", open);
          overlay.removeEventListener("click", close);
          form.removeEventListener("submit", submit);
          trigger.remove();
          overlay.remove();
          form.classList.remove("bt-managed-form", "is-open");
          delete form.dataset.btFormEnhanced;
          delete form.dataset.btFormTitle;
          form.removeAttribute("role");
          form.removeAttribute("aria-modal");
          form.removeAttribute("aria-label");
        },
      });
    };

    const tableRows = (table: HTMLTableElement) => Array.from(table.tBodies).flatMap((body) => Array.from(body.rows));

    const enhanceTable = (table: HTMLTableElement) => {
      const existing = tables.get(table);
      if (existing) {
        if (!existing.toolbar.isConnected || !existing.pager.isConnected) {
          existing.dispose();
          tables.delete(table);
        } else {
          existing.apply();
          return;
        }
      }
      if (table.dataset.btTableSkip === "true" || !table.tHead || table.closest(".bt-ui-dialog")) return;
      const headerCells = Array.from(table.tHead.querySelectorAll("th"));
      if (!headerCells.length) return;

      const tableWrap = table.parentElement;
      const wrapped = Boolean(tableWrap?.className.toString().toLowerCase().includes("table"));
      const host = wrapped ? tableWrap?.parentElement : tableWrap;
      if (!host || !tableWrap) return;

      const toolbar = document.createElement("div");
      toolbar.className = "bt-data-toolbar";
      const controls = document.createElement("div");
      controls.className = "bt-data-toolbar-main";
      const search = document.createElement("input");
      search.type = "search";
      search.className = "bt-data-search";
      search.placeholder = "Search all table fields…";
      search.setAttribute("aria-label", "Search table");
      controls.append(search);
      const filterDetails = document.createElement("details");
      filterDetails.className = "bt-data-filter-details";
      const filterSummary = document.createElement("summary");
      filterSummary.textContent = "Filters";
      filterDetails.append(filterSummary);
      const filterGrid = document.createElement("div");
      filterGrid.className = "bt-data-filter-grid";
      filterDetails.append(filterGrid);
      controls.append(filterDetails);
      const clear = document.createElement("button");
      clear.type = "button";
      clear.className = "bt-data-clear";
      clear.textContent = "Reset";
      controls.append(clear);
      toolbar.append(controls);

      const pager = document.createElement("div");
      pager.className = "bt-data-pager";
      const summary = document.createElement("output");
      summary.className = "bt-data-summary";
      summary.setAttribute("aria-live", "polite");
      const sizeLabel = document.createElement("label");
      sizeLabel.textContent = "Rows";
      const pageSize = document.createElement("select");
      pageSize.className = "bt-data-page-size";
      pageSize.setAttribute("aria-label", "Rows per page");
      [15, 30, 50, 100].forEach((size) => {
        const option = document.createElement("option");
        option.value = String(size);
        option.textContent = String(size);
        pageSize.append(option);
      });
      sizeLabel.append(pageSize);
      const previous = document.createElement("button");
      previous.type = "button";
      previous.className = "bt-data-page-button";
      previous.textContent = "Previous";
      const next = document.createElement("button");
      next.type = "button";
      next.className = "bt-data-page-button";
      next.textContent = "Next";
      pager.append(summary, sizeLabel, previous, next);

      const rows = tableRows(table);
      const filters: FilterControl[] = [];
      headerCells.forEach((header, index) => {
        const label = readableText(header.textContent ?? `Column ${index + 1}`);
        if (!label || /^(action|actions)$/i.test(label)) return;
        const values = Array.from(new Set(rows.map((row) => fieldValue(row, index)).filter(Boolean))).sort((a, b) => a.localeCompare(b));
        const filter = document.createElement("label");
        filter.className = "bt-data-filter";
        const caption = document.createElement("span");
        caption.textContent = label;
        filter.append(caption);
        const dateLike = /date|time|due|expiry|issued|start|finish|period/i.test(label);
        const numberLike = /amount|cost|price|quantity|total|budget|meter|litres|hours|rating|step|value|margin|percent|%/i.test(label);
        if (dateLike) {
          const range = document.createElement("div");
          range.className = "bt-data-range";
          const from = document.createElement("input");
          from.type = "date";
          from.setAttribute("aria-label", `${label} from`);
          const to = document.createElement("input");
          to.type = "date";
          to.setAttribute("aria-label", `${label} to`);
          range.append(from, to);
          filter.append(range);
          filters.push({ index, label, kind: "date", from, to });
        } else if (numberLike) {
          const range = document.createElement("div");
          range.className = "bt-data-range";
          const from = document.createElement("input");
          from.type = "number";
          from.step = "any";
          from.placeholder = "Min";
          from.setAttribute("aria-label", `${label} minimum`);
          const to = document.createElement("input");
          to.type = "number";
          to.step = "any";
          to.placeholder = "Max";
          to.setAttribute("aria-label", `${label} maximum`);
          range.append(from, to);
          filter.append(range);
          filters.push({ index, label, kind: "number", from, to });
        } else if (values.length && values.length <= 80) {
          const control = document.createElement("select");
          control.setAttribute("aria-label", `Filter ${label}`);
          const any = document.createElement("option");
          any.value = "";
          any.textContent = `All ${label}`;
          control.append(any);
          values.forEach((value) => {
            const option = document.createElement("option");
            option.value = normaliseText(value);
            option.textContent = value;
            control.append(option);
          });
          filter.append(control);
          filters.push({ index, label, kind: "select", control });
        } else {
          const control = document.createElement("input");
          control.type = "search";
          control.placeholder = `Filter ${label}`;
          control.setAttribute("aria-label", `Filter ${label}`);
          filter.append(control);
          filters.push({ index, label, kind: "text", control });
        }
        filterGrid.append(filter);
      });

      let state: EnhancedTable;
      const apply = () => {
        state.rows = tableRows(table);
        const searchValue = normaliseText(search.value);
        const matching = state.rows.filter((row) => {
          const allText = normaliseText(row.textContent ?? "");
          if (searchValue && !allText.includes(searchValue)) return false;
          return filters.every((filter) => {
            const value = fieldValue(row, filter.index);
            const normalised = normaliseText(value);
            if (filter.kind === "select") return !filter.control?.value || normalised === filter.control.value;
            if (filter.kind === "text") return !filter.control?.value || normalised.includes(normaliseText(filter.control.value));
            if (filter.kind === "date") {
              const date = value.slice(0, 10);
              return (!filter.from?.value || date >= filter.from.value) && (!filter.to?.value || date <= filter.to.value);
            }
            const number = Number(value.replace(/[^0-9.-]/g, ""));
            return (!filter.from?.value || number >= Number(filter.from.value)) && (!filter.to?.value || number <= Number(filter.to.value));
          });
        });
        const size = Number(pageSize.value) || 15;
        const totalPages = Math.max(1, Math.ceil(matching.length / size));
        state.page = Math.min(Math.max(1, state.page), totalPages);
        const first = (state.page - 1) * size;
        const last = first + size;
        state.rows.forEach((row) => { row.hidden = !matching.includes(row) || matching.indexOf(row) < first || matching.indexOf(row) >= last; });
        summary.value = matching.length ? `Showing ${first + 1}–${Math.min(last, matching.length)} of ${matching.length} matching records` : "No matching records";
        previous.disabled = state.page <= 1;
        next.disabled = state.page >= totalPages;
        previous.setAttribute("aria-label", `Previous page, page ${state.page - 1}`);
        next.setAttribute("aria-label", `Next page, page ${state.page + 1}`);
      };
      const reset = () => {
        search.value = "";
        filters.forEach((filter) => { if (filter.control) filter.control.value = ""; if (filter.from) filter.from.value = ""; if (filter.to) filter.to.value = ""; });
        state.page = 1;
        apply();
      };
      const onFilter = () => { state.page = 1; apply(); };
      search.addEventListener("input", onFilter);
      filters.forEach((filter) => [filter.control, filter.from, filter.to].filter(Boolean).forEach((control) => control?.addEventListener("input", onFilter)));
      filters.forEach((filter) => filter.control?.addEventListener("change", onFilter));
      pageSize.addEventListener("change", onFilter);
      clear.addEventListener("click", reset);
      previous.addEventListener("click", () => { state.page -= 1; apply(); });
      next.addEventListener("click", () => { state.page += 1; apply(); });

      host.insertBefore(toolbar, wrapped ? tableWrap : table);
      host.insertBefore(pager, wrapped ? tableWrap.nextSibling : table.nextSibling);
      table.dataset.btTableEnhanced = "true";
      state = {
        table, toolbar, pager, search, pageSize, summary, previous, next, filters, page: 1, rows, apply,
        dispose: () => {
          toolbar.remove();
          pager.remove();
          state.rows.forEach((row) => { row.hidden = false; });
          delete table.dataset.btTableEnhanced;
        },
      };
      tables.set(table, state);
      apply();
    };

    const scan = () => {
      const root = document.querySelector<HTMLElement>(".bt-content");
      if (!root) return;
      forms.forEach((managed, form) => { if (!form.isConnected) { managed.dispose(); forms.delete(form); } });
      tables.forEach((enhanced, table) => { if (!table.isConnected) { enhanced.dispose(); tables.delete(table); } });
      root.querySelectorAll<HTMLFormElement>("form").forEach(enhanceForm);
      root.querySelectorAll<HTMLTableElement>("table").forEach(enhanceTable);
    };
    const schedule = () => { window.cancelAnimationFrame(frame); frame = window.requestAnimationFrame(scan); };
    const observer = new MutationObserver(schedule);
    const keydown = (event: KeyboardEvent) => { if (event.key === "Escape") closeOpenForm(); };
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener("keydown", keydown);
    scan();
    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
      document.removeEventListener("keydown", keydown);
      forms.forEach((managed) => managed.dispose());
      tables.forEach((enhanced) => enhanced.dispose());
    };
  }, []);
  return null;
}

export function BuildTrackUiProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [interaction, setInteraction] = useState<Interaction | null>(null);

  const value = useMemo<UiContextValue>(() => ({
    notify(message, tone = "success") {
      const id = Date.now() + Math.round(Math.random() * 1000);
      setToasts((current) => [...current, { id, message, tone }].slice(-4));
      window.setTimeout(() => setToasts((current) => current.filter((toast) => toast.id !== id)), 4200);
    },
    confirm(options) {
      return new Promise<boolean>((resolve) => setInteraction({ kind: "confirm", options, resolve }));
    },
    promptText(options) {
      return new Promise<string | null>((resolve) => setInteraction({ kind: "prompt", options, value: options.defaultValue ?? "", resolve }));
    },
  }), []);

  function resolve(value: boolean | string | null) {
    if (!interaction) return;
    if (interaction.kind === "confirm") interaction.resolve(Boolean(value));
    else interaction.resolve(typeof value === "string" ? value : null);
    setInteraction(null);
  }

  return <UiContext.Provider value={value}>
    {children}
    <BuildTrackOperationalEnhancements />
    <div className="bt-ui-toast-viewport" aria-live="polite">{toasts.map((toast) => <Alert key={toast.id} tone={toast.tone}>{toast.message}</Alert>)}</div>
    {interaction?.kind === "confirm" && <Dialog open onOpenChange={() => resolve(false)} title={interaction.options.title} description={interaction.options.description} dismissible footer={<><Button variant="outline" onClick={() => resolve(false)}>{interaction.options.cancelLabel ?? "Cancel"}</Button><Button variant={interaction.options.destructive ? "destructive" : "default"} onClick={() => resolve(true)}>{interaction.options.confirmLabel ?? "Continue"}</Button></>}>
      <Alert tone={interaction.options.destructive ? "danger" : "warning"}>{interaction.options.description}</Alert>
    </Dialog>}
    {interaction?.kind === "prompt" && <Dialog open onOpenChange={() => resolve(null)} title={interaction.options.title} description={interaction.options.description} footer={<><Button variant="outline" onClick={() => resolve(null)}>Cancel</Button><Button form="bt-ui-prompt-form" type="submit">{interaction.options.confirmLabel ?? "Save"}</Button></>}>
      <form id="bt-ui-prompt-form" className="bt-ui-prompt-form" onSubmit={(event) => { event.preventDefault(); if (interaction.options.required && !interaction.value.trim()) return; resolve(interaction.value.trim()); }}>
        <FormField label={interaction.options.label} required={interaction.options.required}>
          {interaction.options.multiline
            ? <Textarea autoFocus rows={5} value={interaction.value} placeholder={interaction.options.placeholder} onChange={(event) => setInteraction({ ...interaction, value: event.target.value })} />
            : <Input autoFocus value={interaction.value} placeholder={interaction.options.placeholder} onChange={(event) => setInteraction({ ...interaction, value: event.target.value })} />}
        </FormField>
      </form>
    </Dialog>}
  </UiContext.Provider>;
}

export function useBuildTrackUi() {
  const value = useContext(UiContext);
  if (!value) throw new Error("useBuildTrackUi must be used inside BuildTrackUiProvider.");
  return value;
}
