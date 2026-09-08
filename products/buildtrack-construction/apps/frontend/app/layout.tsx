import type { Metadata } from "next";
import { cookies } from "next/headers";
import { BrandNormalizer } from "./components/brand-normalizer";
import { BuildTrackDisplayControls } from "./components/buildtrack-display-controls";
import { BuildTrackNavigation } from "./components/buildtrack-navigation";
import { GlobalSystemSearch } from "./components/global-system-search";
import { BuildTrackUiProvider } from "./components/ui";
import { RealtimeProvider } from "./components/realtime-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "Nthane Brothers Construction Management System",
  description: "Integrated construction operations platform for Nthane Brothers, developed by Ithute Solution.",
  applicationName: "Nthane Brothers Construction Management System",
  authors: [{ name: "Ithute Solution" }],
  creator: "Ithute Solution",
};

const displayBootstrap = `(() => {
  try {
    const key = "buildtrack.display-preferences";
    const fullscreenKey = "buildtrack.workspace-fullscreen";
    const auto = () => window.innerWidth <= 1024 ? 80 : window.innerWidth <= 1280 ? 85 : window.innerWidth <= 1440 ? 90 : window.innerWidth <= 1600 ? 95 : 100;
    const raw = window.localStorage.getItem(key);
    const saved = raw ? JSON.parse(raw) : {};
    const uiScale = saved.autoFit === false ? Math.max(80, Math.min(125, Number(saved.uiScale) || auto())) : auto();
    const textScale = Math.max(85, Math.min(130, Number(saved.textScale) || 100));
    const root = document.documentElement;
    root.style.setProperty("--buildtrack-ui-scale", uiScale + "%");
    root.style.setProperty("--buildtrack-reading-scale", String(textScale / 100));
    root.dataset.buildtrackDensity = saved.density === "compact" ? "compact" : "comfortable";
    root.dataset.buildtrackLite = saved.lite === true ? "true" : "false";
    root.dataset.buildtrackFocus = window.localStorage.getItem(fullscreenKey) === "false" || saved.focus === false ? "false" : "true";
  } catch {}
})();`;

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const session = (await cookies()).get("buildtrack_session")?.value;
  const content = session ? <RealtimeProvider><BuildTrackUiProvider><div className="bt-dashboard"><BuildTrackNavigation /><div className="bt-content">{children}</div></div><BuildTrackDisplayControls /><GlobalSystemSearch /></BuildTrackUiProvider></RealtimeProvider> : children;
  return (
    <html lang="en" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: displayBootstrap }} /></head>
      <body><BrandNormalizer>{content}</BrandNormalizer></body>
    </html>
  );
}
