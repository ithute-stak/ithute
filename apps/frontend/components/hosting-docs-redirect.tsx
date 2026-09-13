"use client";

import { useEffect } from "react";

export function HostingDocsRedirect() {
  useEffect(() => {
    if (window.location.pathname === "/docs" && window.location.hash === "#hosting") {
      window.location.replace("/hosting-docs");
    }
  }, []);
  return null;
}
