import type { Metadata } from "next";
import { cookies } from "next/headers";

import RealtimeAlerts from "@/components/realtime-alerts";
import "./globals.css";
import "./login.css";

export const metadata: Metadata = {
  title: "NBros",
  description: "NBros by Ithute Solutions",
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const store = await cookies();
  const signedIn = Boolean(store.get("nbros_access")?.value);

  return (
    <html lang="en">
      <body>
        {signedIn ? <RealtimeAlerts /> : null}
        {children}
      </body>
    </html>
  );
}
