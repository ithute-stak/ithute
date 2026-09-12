"use client";

import { Bell, CheckCheck, RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ControlShell } from "@/components/control-shell";
import { EmptyState, LoadingPanel, PageHeader, StatusBadge } from "@/components/ui-kit";
import { useToast } from "@/components/toast-provider";
import { apiJson, apiMutation, invalidateApiCache } from "@/lib/platform-api";

type Membership = { tenant_id: string; tenant_name: string };
type Me = { email?: string };
type Item = {
  id: string;
  category: string;
  severity: string;
  title: string;
  message: string;
  action_url?: string | null;
  read_at?: string | null;
  created_at: string;
};
type NotificationResponse = { items?: Item[] };

export default function NotificationsPage() {
  const router = useRouter();
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [tenantName, setTenantName] = useState("");
  const [rows, setRows] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (force = false) => {
    setLoading(true);
    try {
      const me = await apiJson<Me>("/auth/me", { ttlMs: 30_000, force });
      setEmail(me.email || "");

      const memberships = await apiJson<Membership[]>("/me/memberships", { ttlMs: 30_000, force });
      const saved = window.localStorage.getItem("mailbox_dns_tenant");
      const membership = memberships.find((item) => item.tenant_id === saved) || memberships[0];
      if (!membership) {
        setRows([]);
        return;
      }

      setTenantId(membership.tenant_id);
      setTenantName(membership.tenant_name);
      window.localStorage.setItem("mailbox_dns_tenant", membership.tenant_id);
      const path = `/tenants/${membership.tenant_id}/notifications`;
      const data = await apiJson<NotificationResponse>(path, { ttlMs: 10_000, force });
      setRows(data.items || []);
      window.dispatchEvent(new CustomEvent("ithute:notifications-updated", { detail: { unread: (data.items || []).filter((item) => !item.read_at).length } }));
    } catch (error) {
      const status = (error as { status?: number }).status;
      if (status === 401) {
        router.replace("/login");
        return;
      }
      toast.error(error instanceof Error ? error.message : "Unable to load notifications", "Notifications unavailable");
    } finally {
      setLoading(false);
    }
  }, [router, toast]);

  useEffect(() => {
    void load();
    const onUpdated = () => void load(true);
    window.addEventListener("ithute:notifications-updated", onUpdated);
    return () => window.removeEventListener("ithute:notifications-updated", onUpdated);
  }, [load]);

  async function read(id: string) {
    if (!tenantId) return;
    try {
      await apiMutation(`/tenants/${tenantId}/notifications/${id}/read`, { method: "POST" }, [`/tenants/${tenantId}/notifications`]);
      setRows((current) => current.map((item) => item.id === id ? { ...item, read_at: new Date().toISOString() } : item));
      toast.success("Notification marked as read");
      window.dispatchEvent(new CustomEvent("ithute:notifications-updated", { detail: { unread: Math.max(rows.filter((item) => !item.read_at).length - 1, 0) } }));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to update notification");
    }
  }

  async function readAll() {
    if (!tenantId) return;
    try {
      await apiMutation(`/tenants/${tenantId}/notifications/read-all`, { method: "POST" }, [`/tenants/${tenantId}/notifications`]);
      const now = new Date().toISOString();
      setRows((current) => current.map((item) => ({ ...item, read_at: item.read_at || now })));
      invalidateApiCache(`/tenants/${tenantId}/notifications`);
      toast.success("All notifications marked as read");
      window.dispatchEvent(new CustomEvent("ithute:notifications-updated", { detail: { unread: 0 } }));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to update notifications");
    }
  }

  return (
    <ControlShell title="Notifications" subtitle={tenantName || "Account and infrastructure alerts"} userEmail={email}>
      <div className="space-y-4">
        <PageHeader eyebrow="Attention centre" title="Notifications" description="Billing, onboarding, security, support and infrastructure notices for the selected organization." actions={<button className="btn-secondary" onClick={() => void load(true)}><RefreshCw size={14}/>Refresh</button>}/>
        <div><button className="btn-secondary" onClick={() => void readAll()} disabled={!rows.some((item) => !item.read_at)}><CheckCheck size={14}/>Mark all read</button></div>
        {loading ? <LoadingPanel label="Loading notifications"/> : rows.length ? (
          <section className="grid gap-3">
            {rows.map((notification) => (
              <article key={notification.id} className={`surface-card p-4 ${!notification.read_at ? "border-l-4 border-l-[#d8c56a]" : ""}`}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-black">{notification.title}</p>
                      <StatusBadge state={notification.severity === "error" ? "bad" : notification.severity === "warning" ? "warn" : notification.severity === "success" ? "good" : "neutral"}>{notification.category}</StatusBadge>
                    </div>
                    <p className="mt-2 text-xs leading-5 text-[#617168]">{notification.message}</p>
                    <p className="mt-2 text-[9px] text-[#8a9890]">{new Date(notification.created_at).toLocaleString()}</p>
                  </div>
                  {!notification.read_at ? <button className="btn-secondary shrink-0" onClick={() => void read(notification.id)}>Read</button> : null}
                </div>
                {notification.action_url ? <button onClick={() => router.push(notification.action_url!)} className="mt-3 text-xs font-black text-[#285b55]">Open related page →</button> : null}
              </article>
            ))}
          </section>
        ) : <EmptyState icon={<Bell size={20}/>} title="No notifications" description="New billing, security and operational notices will appear here."/>}
      </div>
    </ControlShell>
  );
}
