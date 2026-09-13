"use client";

import { FormEvent, useState } from "react";
import { Building2, Loader2, Plus, X } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Tenant = {
  id: string;
  name: string;
  slug: string;
  status: string;
};

async function api(path: string, init?: RequestInit) {
  const options: RequestInit = {
    credentials: "include",
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  };
  let response = await fetch(`${API}${path}`, options);
  if (response.status === 401) {
    const refreshed = await fetch(`${API}/auth/refresh`, { method: "POST", credentials: "include" });
    if (refreshed.ok) response = await fetch(`${API}${path}`, options);
  }
  return response;
}

async function detail(response: Response, fallback: string) {
  const body = await response.json().catch(() => ({}));
  return String(body.detail || fallback);
}

function slugify(value: string) {
  const normalized = value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80)
    .replace(/-+$/g, "");
  if (normalized.length >= 3) return normalized;
  return normalized ? `${normalized}-org` : "";
}

export function CreateOrganizationDialog({ isPlatformOwner }: { isPlatformOwner: boolean }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (!isPlatformOwner) return null;

  function reset() {
    setOpen(false);
    setName("");
    setSlug("");
    setSlugTouched(false);
    setError("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;

    const cleanName = name.trim();
    const cleanSlug = slugify(slug || cleanName);
    if (cleanName.length < 2) {
      setError("Organization name must contain at least 2 characters.");
      return;
    }
    if (!/^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$/.test(cleanSlug)) {
      setError("Use a slug with 3-80 lowercase letters, numbers or hyphens, without a leading or trailing hyphen.");
      return;
    }

    setBusy(true);
    setError("");
    try {
      const response = await api("/tenants", {
        method: "POST",
        body: JSON.stringify({ name: cleanName, slug: cleanSlug }),
      });
      if (!response.ok) throw new Error(await detail(response, "Unable to create organization"));
      const created: Tenant = await response.json();
      window.localStorage.setItem("mailbox_dns_tenant", created.id);
      window.location.reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to create organization");
      setBusy(false);
    }
  }

  return (
    <>
      <button type="button" className="btn-secondary" onClick={() => setOpen(true)}>
        <Building2 size={14} />
        New organization
      </button>

      {open ? (
        <div
          className="fixed inset-0 z-[80] grid place-items-center bg-black/45 p-4"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !busy) reset();
          }}
        >
          <form
            onSubmit={submit}
            className="form-modal w-full max-w-lg rounded-2xl bg-white p-5 shadow-2xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-organization-title"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="mb-3 grid h-10 w-10 place-items-center rounded-xl bg-[#eef4f1] text-[#123a38]">
                  <Building2 size={18} />
                </div>
                <p id="create-organization-title" className="text-lg font-black text-[#21342a]">Create organization</p>
                <p className="mt-1 text-[11px] leading-5 text-[#718078]">
                  Create a new customer/company context, select it automatically, then add its domains under that organization.
                </p>
              </div>
              <button type="button" className="icon-button" onClick={reset} disabled={busy} aria-label="Close create organization form">
                <X size={16} />
              </button>
            </div>

            {error ? <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-[11px] font-semibold text-red-700">{error}</div> : null}

            <div className="mt-5 grid gap-4">
              <label className="form-field">
                <span className="form-label"><span>Organization name</span><span className="form-required">Required</span></span>
                <input
                  className="input"
                  value={name}
                  onChange={(event) => {
                    const next = event.target.value;
                    setName(next);
                    if (!slugTouched) setSlug(slugify(next));
                  }}
                  placeholder="Lelefa Debt Collectors"
                  autoComplete="organization"
                  required
                  autoFocus
                />
              </label>

              <label className="form-field">
                <span className="form-label"><span>Organization slug</span><span className="form-required">Required</span></span>
                <input
                  className="input font-mono"
                  value={slug}
                  onChange={(event) => {
                    setSlugTouched(true);
                    setSlug(event.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""));
                  }}
                  placeholder="lelefa-debt-collectors"
                  autoCapitalize="none"
                  spellCheck={false}
                  required
                />
                <span className="form-helper">Used internally in URLs and identifiers. You can accept the generated value.</span>
              </label>
            </div>

            <div className="form-actions">
              <button type="button" className="btn-secondary" onClick={reset} disabled={busy}>Cancel</button>
              <button type="submit" className="btn-primary" disabled={busy || !name.trim() || !slug.trim()}>
                {busy ? <><Loader2 size={14} className="animate-spin" />Creating…</> : <><Plus size={14} />Create organization</>}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </>
  );
}
