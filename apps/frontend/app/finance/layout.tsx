import Link from "next/link";

export default function FinanceLayout({ children }: { children: React.ReactNode }) {
  return (
    <div>
      <div className="sticky top-0 z-30 border-b bg-white/95 px-4 py-2 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] flex-wrap gap-2 text-xs font-black">
          <Link className="rounded-xl border px-3 py-2 hover:bg-[#eef6f2]" href="/finance">Invoices & automation</Link>
          <Link className="rounded-xl border px-3 py-2 hover:bg-[#eef6f2]" href="/finance/documents">Quotations & pro-formas</Link>
          <Link className="rounded-xl border px-3 py-2 hover:bg-[#eef6f2]" href="/finance/clients">Clients</Link>
          <Link className="rounded-xl border px-3 py-2 hover:bg-[#eef6f2]" href="/finance/collections">Collections & payments</Link>
          <Link className="rounded-xl border px-3 py-2 hover:bg-[#eef6f2]" href="/finance/reports">Reports & statements</Link>
        </div>
      </div>
      {children}
    </div>
  );
}
