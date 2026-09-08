import type { Metadata } from "next";
import { cookies } from "next/headers";
import { ManualClient } from "./manual-client";

export const metadata: Metadata = {
  title: "User Manual & System Documentation | Nthane Brothers",
  description: "Complete online user manual for the Nthane Brothers Construction Management System, developed by Ithute Solution.",
};

export default async function ManualIndexPage() {
  const authenticated = Boolean((await cookies()).get("buildtrack_session")?.value);
  return <ManualClient authenticated={authenticated} />;
}
