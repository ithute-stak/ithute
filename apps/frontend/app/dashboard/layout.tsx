import type { ReactNode } from "react";
import { ControlShell } from "../../components/control-shell";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <ControlShell
      title="Command centre"
      subtitle="Monitor domains, DNS, mail infrastructure and platform operations."
    >
      {children}
    </ControlShell>
  );
}
