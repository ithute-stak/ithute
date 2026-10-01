"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ControlShell } from "../../components/control-shell";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type ApplicationState = {
  application?: {
    status?: "pending" | "approved" | "rejected";
  } | null;
};

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    void fetch(`${API}/me/customer-application`, {
      credentials: "include",
      cache: "no-store",
    })
      .then(async (response) => {
        if (response.status === 401) {
          router.replace("/login");
          return;
        }
        if (!response.ok) {
          if (!cancelled) setReady(true);
          return;
        }

        const body = (await response.json().catch(() => ({}))) as ApplicationState;
        const status = body.application?.status;
        if (status === "pending" || status === "rejected") {
          router.replace("/application-status");
          return;
        }
        if (!cancelled) setReady(true);
      })
      .catch(() => {
        // Application-state lookup must never lock established customers out of
        // the dashboard if the optional status probe is temporarily unavailable.
        if (!cancelled) setReady(true);
      });

    return () => {
      cancelled = true;
    };
  }, [router]);

  if (!ready) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#f4f7f5] px-6 text-[#20342a]">
        <div className="text-center">
          <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-[#cbd8d2] border-t-[#123a38]" />
          <p className="mt-4 text-xs font-black uppercase tracking-[.12em] text-[#667a71]">Preparing your Ithute workspace</p>
        </div>
      </main>
    );
  }

  return (
    <ControlShell
      title="Ithute Control Centre"
      subtitle="Manage your organisation, hosting, domains, email, billing, security and platform services."
    >
      {children}
    </ControlShell>
  );
}
