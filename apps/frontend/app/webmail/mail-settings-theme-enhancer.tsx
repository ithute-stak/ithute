"use client";

import { Check, Leaf, Monitor, Moon, Sun } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { type MailTheme, useMailPreferences } from "./mail-preferences";

const options: Array<{ value: MailTheme; title: string; subtitle: string; icon: React.ReactNode }> = [
  { value: "light", title: "Universal Gmail", subtitle: "Default · familiar light workspace", icon: <Sun size={17} /> },
  { value: "ithute", title: "Ithute Green", subtitle: "Brand-forward Ithute workspace", icon: <Leaf size={17} /> },
  { value: "dark", title: "Dark", subtitle: "Comfortable low-light workspace", icon: <Moon size={17} /> },
  { value: "system", title: "System", subtitle: "Follow this device only when selected", icon: <Monitor size={17} /> },
];

export function MailSettingsThemeEnhancer() {
  const pathname = usePathname();
  const { preferences, setPreferences, ready } = useMailPreferences();
  const [host, setHost] = useState<HTMLElement | null>(null);

  useEffect(() => {
    if (pathname !== "/webmail/settings") {
      setHost(null);
      return;
    }

    let cancelled = false;
    let attempts = 0;
    const attach = () => {
      if (cancelled) return;
      const section = document.getElementById("appearance");
      if (!section) {
        attempts += 1;
        if (attempts < 40) window.setTimeout(attach, 50);
        return;
      }

      let node = section.querySelector<HTMLElement>("[data-imail-theme-enhancer]");
      if (!node) {
        node = document.createElement("div");
        node.dataset.imailThemeEnhancer = "true";
        node.className = "imail-internal-theme-settings";
        const densityGrid = section.children.item(1);
        if (densityGrid) section.insertBefore(node, densityGrid);
        else section.appendChild(node);
      }
      setHost(node);
    };

    attach();
    return () => {
      cancelled = true;
      setHost(null);
    };
  }, [pathname]);

  if (!ready || !host) return null;

  return createPortal(
    <div className="imail-internal-theme-content">
      <div className="imail-internal-theme-heading">
        <div>
          <p className="imail-internal-theme-title">Mailbox theme</p>
          <p className="imail-internal-theme-copy">Universal Gmail is the default for hosted and external iMail. Your explicit choice is remembered on this device.</p>
        </div>
        <span className="imail-internal-theme-default">Universal default</span>
      </div>
      <div className="imail-internal-theme-grid">
        {options.map((option) => {
          const active = preferences.theme === option.value;
          return (
            <button
              key={option.value}
              type="button"
              data-active={active ? "true" : "false"}
              onClick={() => setPreferences((current) => ({ ...current, theme: option.value }))}
              className="imail-internal-theme-option"
            >
              <span className="imail-internal-theme-icon">{option.icon}</span>
              <span className="imail-internal-theme-text">
                <strong>{option.title}</strong>
                <small>{option.subtitle}</small>
              </span>
              {active ? <Check size={17} className="imail-internal-theme-check" /> : null}
            </button>
          );
        })}
      </div>
    </div>,
    host,
  );
}
