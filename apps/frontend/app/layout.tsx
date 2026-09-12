import type { Metadata } from "next";
import { BackgroundRefresh } from "@/components/background-refresh";
import { CommandPalette } from "@/components/command-palette";
import { FormEnhancer } from "@/components/form-enhancer";
import { NavigationMemory } from "@/components/navigation-memory";
import { ToastProvider } from "@/components/toast-provider";
import "./globals.css";
import "./forms.css";
import "./platform-ux.css";
import "./control-polish.css";

export const metadata: Metadata = {
  title: { default: "Mailbox DNS · Lelefa Infrastructure", template: "%s · Mailbox DNS" },
  description: "Multi-tenant mail and authoritative DNS infrastructure control plane.",
  applicationName: "Mailbox DNS",
  keywords: ["DNS hosting", "mail hosting", "PowerDNS", "infrastructure control plane"],
  robots: { index: false, follow: false },
  icons: {
    icon: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%23123a38'/%3E%3Ctext x='32' y='41' font-size='25' text-anchor='middle' fill='%23d8c56a' font-family='Arial' font-weight='700'%3EMD%3C/text%3E%3C/svg%3E",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <ToastProvider>
          <FormEnhancer />
          <NavigationMemory />
          <CommandPalette />
          <BackgroundRefresh />
          {children}
        </ToastProvider>
      </body>
    </html>
  );
}
