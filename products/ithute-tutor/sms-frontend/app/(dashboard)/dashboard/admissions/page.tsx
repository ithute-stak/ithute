"use client"

import * as React from "react"
import { CheckCircle2, Clock3, Loader2, UserPlus, XCircle } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { createAdmissionApplication, decideAdmissionApplication, getAdmissionApplications, type AdmissionApplication, type AdmissionStatus } from "@/api/admissions"
import { useSchoolWorkspace } from "@/provider/school_workspace_provider"

const MANAGER_ROLES = ["school_admin", "principal", "vice_principal", "registrar", "admissions_officer"]

export default function AdmissionsPage() {
  const { workspace } = useSchoolWorkspace()
  const canManage = Boolean(workspace?.is_platform_admin) || MANAGER_ROLES.includes(workspace?.role ?? "")
  const [applications, setApplications] = React.useState<AdmissionApplication[]>([])
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [form, setForm] = React.useState({ applicant_first_name: "", applicant_last_name: "", date_of_birth: "", guardian_name: "", guardian_email: "", guardian_phone: "", notes: "" })

  const refresh = React.useCallback(async () => {
    if (!canManage) { setLoading(false); return }
    setLoading(true); setError(null)
    try { setApplications(await getAdmissionApplications()) }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to load applications") }
    finally { setLoading(false) }
  }, [canManage])

  React.useEffect(() => { void refresh() }, [workspace?.school.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setSaving(true); setError(null)
    try {
      await createAdmissionApplication({ ...form, date_of_birth: form.date_of_birth || null })
      setForm({ applicant_first_name: "", applicant_last_name: "", date_of_birth: "", guardian_name: "", guardian_email: "", guardian_phone: "", notes: "" })
      await refresh()
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to create application") }
    finally { setSaving(false) }
  }

  const decide = async (id: string, status: Exclude<AdmissionStatus, "draft" | "submitted">) => {
    setSaving(true); setError(null)
    try { await decideAdmissionApplication(id, status); await refresh() }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to update application") }
    finally { setSaving(false) }
  }

  if (loading) return <div className="flex min-h-[55vh] items-center justify-center gap-3 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" />Loading admissions…</div>

  return <div className="space-y-6">
    <div className="rounded-2xl border bg-card p-6"><div className="flex items-center gap-2 text-sm font-medium text-muted-foreground"><UserPlus className="h-4 w-4" />Applicant pipeline</div><h1 className="mt-2 text-3xl font-bold tracking-tight">Admissions</h1><p className="mt-2 max-w-3xl text-sm text-muted-foreground">Applications are separate from the professional transfer workflow. Review applicants here; use Admissions & Transfers when an already-enrolled learner moves between schools.</p></div>
    {error && <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</div>}
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
      <Card><CardHeader><CardTitle>Application register</CardTitle><CardDescription>{applications.length} application{applications.length === 1 ? "" : "s"} in this school workspace.</CardDescription></CardHeader><CardContent className="space-y-3">{applications.length === 0 ? <div className="py-8 text-center text-sm text-muted-foreground">No applications yet.</div> : applications.map((item) => <div key={item.id} className="rounded-xl border p-4"><div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between"><div><div className="font-semibold">{item.applicant_first_name} {item.applicant_last_name}</div><div className="mt-1 text-xs text-muted-foreground">Guardian: {item.guardian_name} · {item.guardian_phone || item.guardian_email || "No contact supplied"}</div><div className="mt-2 inline-flex rounded-full border px-2 py-1 text-xs font-medium">{item.status.replaceAll("_", " ")}</div></div>{canManage && <div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" disabled={saving} onClick={() => void decide(item.id, "under_review")}><Clock3 className="mr-1 h-3.5 w-3.5" />Review</Button><Button size="sm" disabled={saving} onClick={() => void decide(item.id, "accepted")}><CheckCircle2 className="mr-1 h-3.5 w-3.5" />Accept</Button><Button size="sm" variant="destructive" disabled={saving} onClick={() => void decide(item.id, "rejected")}><XCircle className="mr-1 h-3.5 w-3.5" />Reject</Button></div>}</div></div>)}</CardContent></Card>
      <Card><CardHeader><CardTitle>New application</CardTitle><CardDescription>Capture an application received online, by email or at the school office.</CardDescription></CardHeader><CardContent><form className="space-y-4" onSubmit={submit}><div className="grid grid-cols-2 gap-3"><div className="grid gap-1.5"><Label>First name</Label><Input value={form.applicant_first_name} onChange={(e) => setForm((v) => ({ ...v, applicant_first_name: e.target.value }))} required /></div><div className="grid gap-1.5"><Label>Last name</Label><Input value={form.applicant_last_name} onChange={(e) => setForm((v) => ({ ...v, applicant_last_name: e.target.value }))} required /></div></div><div className="grid gap-1.5"><Label>Date of birth</Label><Input type="date" value={form.date_of_birth} onChange={(e) => setForm((v) => ({ ...v, date_of_birth: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Guardian</Label><Input value={form.guardian_name} onChange={(e) => setForm((v) => ({ ...v, guardian_name: e.target.value }))} required /></div><div className="grid grid-cols-2 gap-3"><div className="grid gap-1.5"><Label>Phone</Label><Input value={form.guardian_phone} onChange={(e) => setForm((v) => ({ ...v, guardian_phone: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Email</Label><Input type="email" value={form.guardian_email} onChange={(e) => setForm((v) => ({ ...v, guardian_email: e.target.value }))} /></div></div><div className="grid gap-1.5"><Label>Notes</Label><Input value={form.notes} onChange={(e) => setForm((v) => ({ ...v, notes: e.target.value }))} /></div><Button className="w-full" type="submit" disabled={saving}>Save application</Button></form></CardContent></Card>
    </div>
  </div>
}
