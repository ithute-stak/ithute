import type { Metadata } from "next";
import { BackgroundRefresh } from "@/components/background-refresh";
import { CommandPalette } from "@/components/command-palette";
import { FormEnhancer } from "@/components/form-enhancer";
import { HostingDocsRedirect } from "@/components/hosting-docs-redirect";
import { NavigationMemory } from "@/components/navigation-memory";
import { ToastProvider } from "@/components/toast-provider";
import "./globals.css";
import "./forms.css";
import "./platform-ux.css";
import "./control-polish.css";
import "./brand.css";

export const metadata: Metadata = {
  title: { default: "Ithute Digital Solutions · Applications, Email & DNS", template: "%s · Ithute Digital Solutions" },
  description: "Ithute Digital Solutions platform for managed applications, professional email, authoritative DNS and connected business systems.",
  applicationName: "Ithute Digital Solutions",
  keywords: ["Ithute Digital Solutions", "IDS", "application hosting", "website hosting", "DNS hosting", "mail hosting", "PowerDNS", "Ithute"],
  robots: { index: false, follow: false },
  icons: {
    icon: [{ url: "/brand/ids-mark.svg", type: "image/svg+xml" }],
    shortcut: "/brand/ids-mark.svg",
    apple: "/brand/ids-mark.svg",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <ToastProvider>
          <FormEnhancer />
          <HostingDocsRedirect />
          <NavigationMemory />
          <CommandPalette />
          <BackgroundRefresh />
          {children}
        </ToastProvider>
      </body>
    </html>
  );
}
