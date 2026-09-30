"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

type FinanceAccess = {
  email: string;
  allowed: boolean;
  role: string | null;
  isPlatformOwner: boolean;
  loading: boolean;
};

async function api(path: string) {
  return fetch(`${API}${path}`, { credentials: "include" });
}

export function useFinanceAccess(): FinanceAccess {
  const [state, setState] = useState<FinanceAccess>({
    email: "",
    allowed: false,
    role: null,
    isPlatformOwner: false,
    loading: true,
  });

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const me = await api("/auth/me");
        if (!me.ok) throw new Error("Authentication required");
        const user = await me.json();
        const access = await api("/finance/completion/access");
        const body = access.ok ? await access.json() : { allowed: false, role: null, is_platform_owner: false };
        if (!cancelled) {
          setState({
            email: user.email || "",
            allowed: Boolean(body.allowed),
            role: body.role || null,
            isPlatformOwner: Boolean(body.is_platform_owner),
            loading: false,
          });
        }
      } catch {
        if (!cancelled) setState((current) => ({ ...current, loading: false }));
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return state;
}

export function financeRoleRank(role: string | null): number {
  if (role === "owner") return 5;
  return ({ viewer: 1, clerk: 2, approver: 3, admin: 4 } as Record<string, number>)[role || ""] || 0;
}
