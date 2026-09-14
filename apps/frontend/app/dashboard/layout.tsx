import type { ReactNode } from "react";
import { ControlShell } from "../../components/control-shell";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <ControlShell
      title="Ithute Control Centre"
      subtitle="Manage your organisation, hosting, domains, email, billing, security and platform services."
    >
      {children}
    </ControlShell>
  );
}
