import { Construction, type LucideIcon } from "lucide-react";
import { ControlShell } from "@/components/control-shell";

export function FutureModule({ title, subtitle, phase, icon: Icon = Construction }: { title: string; subtitle: string; phase: string; icon?: LucideIcon }) {
  return (
    <ControlShell title={title} subtitle={subtitle}>
      <section className="rounded-2xl border border-[#e1e7e3] bg-white p-6 shadow-sm">
        <div className="grid h-12 w-12 place-items-center rounded-xl bg-[#edf4f1] text-[#123a38]"><Icon size={21} /></div>
        <p className="mt-5 text-[10px] font-black uppercase tracking-[.14em] text-[#718078]">Planned module · {phase}</p>
        <h1 className="mt-2 text-2xl font-black tracking-tight text-[#21342a]">{title}</h1>
        <p className="mt-2 max-w-2xl text-[12px] leading-5 text-[#718078]">{subtitle}</p>
        <div className="mt-5 rounded-xl border border-[#e6e9e7] bg-[#f8faf8] px-4 py-3 text-[11px] font-semibold text-[#5d6b63]">This navigation destination is intentionally reserved so the control-plane architecture remains stable as later infrastructure phases are implemented. No simulated infrastructure actions are exposed.</div>
      </section>
    </ControlShell>
  );
}
