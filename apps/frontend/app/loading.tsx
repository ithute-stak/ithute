export default function Loading() {
  return (
    <div className="min-h-screen bg-[var(--admin-paper)] p-3 sm:p-4 lg:p-5" aria-label="Loading !thute">
      <div className="mx-auto w-full max-w-[1510px] animate-[ithuteFadeIn_.16s_ease-out]">
        <div className="mb-4 flex items-center gap-3 rounded-2xl border border-[var(--admin-line)] bg-white p-4 shadow-sm">
          <div className="skeleton h-10 w-10 rounded-xl" />
          <div className="min-w-0 flex-1 space-y-2">
            <div className="skeleton h-3 w-36" />
            <div className="skeleton h-2.5 w-56 max-w-full" />
          </div>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className="surface-card p-4">
              <div className="skeleton h-2.5 w-24" />
              <div className="mt-4 skeleton h-7 w-20" />
              <div className="mt-3 skeleton h-2.5 w-2/3" />
            </div>
          ))}
        </div>
        <div className="mt-3 surface-card overflow-hidden">
          <div className="border-b border-[var(--admin-line)] p-4"><div className="skeleton h-3 w-40" /></div>
          <div className="divide-y divide-[var(--admin-line)]">
            {Array.from({ length: 7 }).map((_, index) => (
              <div key={index} className="flex items-center gap-4 p-4">
                <div className="skeleton h-8 w-8 rounded-lg" />
                <div className="min-w-0 flex-1 space-y-2">
                  <div className="skeleton h-2.5 w-1/3" />
                  <div className="skeleton h-2 w-1/2" />
                </div>
                <div className="skeleton h-7 w-20 rounded-full" />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
