import Link from "next/link";
import { Activity, ArrowRight, Clock3, ExternalLink, ShieldCheck } from "lucide-react";

export type ControlCentreAudit = {
  id: string;
  action: string;
  resource_type?: string | null;
  created_at: string;
};

const connectedProducts = [
  { name: "LoanHub", category: "Financial services", href: "https://loanhub.co.ls" },
  { name: "Ithute Tutor", category: "Education & AI learning" },
  { name: "Ithute Pay", category: "Payments technology" },
  { name: "BuildTrack", category: "Construction & fleet operations" },
];

function formatAction(action: string) {
  return action.replace(/[._-]+/g, " ").replace(/\b\w/g, (value) => value.toUpperCase());
}

export function ControlCentreExtras({ audit, loading }: { audit: ControlCentreAudit[]; loading: boolean }) {
  return (
    <>
      <section className="grid gap-4 xl:grid-cols-[1.05fr_.95fr]">
        <article className="rounded-[24px] border border-[#e1e8e4] bg-white p-5 shadow-sm sm:p-6">
          <p className="text-[10px] font-black uppercase tracking-[.14em] text-[#718078]">IDS product access</p>
          <h2 className="mt-2 text-xl font-black tracking-[-.035em] text-[#20342a]">Standalone products remain independent.</h2>
          <p className="mt-2 max-w-2xl text-[11px] leading-5 text-[#718078]">Ithute provides the control and identity layer without moving LoanHub, Tutor, Pay or BuildTrack data into this platform. Product launch and SSO can be connected progressively without breaking repository or database boundaries.</p>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            {connectedProducts.map((product) => {
              const card = (
                <div className="rounded-2xl border border-[#e2e9e5] bg-[#fafcfa] p-4 transition hover:bg-white">
                  <div className="flex items-start justify-between gap-3">
                    <div><p className="text-sm font-black text-[#20342a]">{product.name}</p><p className="mt-1 text-[9px] font-bold uppercase tracking-[.09em] text-[#819087]">{product.category}</p></div>
                    {product.href ? <ExternalLink size={14} className="text-[#6f8279]" /> : <ShieldCheck size={14} className="text-[#6f8279]" />}
                  </div>
                  <div className="mt-4 inline-flex items-center gap-2 rounded-full border border-[#dfe7e3] bg-white px-2.5 py-1 text-[8px] font-black uppercase tracking-[.07em] text-[#5d756b]"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> Independent deployment</div>
                </div>
              );
              return product.href ? <a key={product.name} href={product.href} target="_blank" rel="noreferrer">{card}</a> : <div key={product.name}>{card}</div>;
            })}
          </div>
        </article>

        <article className="rounded-[24px] border border-[#e1e8e4] bg-white p-5 shadow-sm sm:p-6">
          <div className="flex items-center justify-between gap-4">
            <div><p className="text-[10px] font-black uppercase tracking-[.14em] text-[#718078]">Recent activity</p><h2 className="mt-2 text-xl font-black tracking-[-.035em] text-[#20342a]">Audit trail</h2></div>
            <Link href="/audit" className="text-[10px] font-black text-[#285b55]">View all</Link>
          </div>
          <div className="mt-5 space-y-2">
            {loading ? (
              <div className="rounded-2xl border border-dashed border-[#dfe7e3] p-5 text-center text-[10px] font-bold text-[#819087]">Loading activity...</div>
            ) : audit.length ? (
              audit.slice(0, 6).map((item) => (
                <div key={item.id} className="flex items-start gap-3 rounded-xl border border-[#e8edea] px-3 py-3">
                  <div className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[#edf4f1] text-[#285b55]"><Activity size={13} /></div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[10px] font-black text-[#314b40]">{formatAction(item.action)}</p>
                    <p className="mt-1 flex items-center gap-1.5 text-[8px] font-semibold text-[#8b9891]"><Clock3 size={10} /> {new Date(item.created_at).toLocaleString()}{item.resource_type ? <span>- {item.resource_type}</span> : null}</p>
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-2xl border border-dashed border-[#dfe7e3] p-5 text-center text-[10px] font-bold text-[#819087]">No recent activity is available for this context.</div>
            )}
          </div>
        </article>
      </section>

      <section className="rounded-[24px] border border-[#dfe6e2] bg-[#f8faf8] p-5 sm:p-6">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-[9px] font-black uppercase tracking-[.14em] text-[#718078]">About Ithute Digital Solutions</p>
            <p className="mt-2 text-sm font-black text-[#20342a]">Meet Koetlisi Theko, founder and software engineer.</p>
            <p className="mt-1 text-[10px] leading-5 text-[#718078]">View the founder profile, engineering portfolio and downloadable CV.</p>
          </div>
          <Link href="/founder" className="inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border border-[#cfdcd5] bg-white px-4 text-[11px] font-black text-[#285b55] shadow-sm">Founder profile <ArrowRight size={13} /></Link>
        </div>
      </section>
    </>
  );
}
