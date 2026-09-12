import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://ithute.co.ls"),
  title: {
    default: "Ithute · Digital infrastructure",
    template: "%s · Ithute",
  },
  description:
    "Ithute is a standalone digital infrastructure platform for secure identity, realtime communication, notifications and production operations.",
  applicationName: "Ithute",
  alternates: { canonical: "/" },
  robots: { index: true, follow: true },
  icons: {
    icon: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='16' fill='%230d2f2b'/%3E%3Ctext x='32' y='44' font-size='38' text-anchor='middle' fill='%23f4df85' font-family='Arial' font-weight='900'%3E!%3C/text%3E%3C/svg%3E",
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
